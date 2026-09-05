"""التوليدُ المعتمَد لا يُحذف — وما يُحذف يأخذ حصصَه الميّتةَ معه.

حذفُ توليدٍ معتمَد من لوحة الإدارة كان يمرّ بلا اعتراض، وحقلُ `generation` على
الحصّة `SET_NULL`: فيفقد الجدولُ الحيّ نسبَه إلى توليده، ويصير — إن أُطفئ
يوماً — ركاماً في عين `prune_schedule_slots`. وقع هذا فعلاً في 2026-09-05.
"""

from datetime import time

import pytest
from django.db.models import ProtectedError

from operations.models import ScheduleGeneration, ScheduleSlot, Subject


@pytest.fixture
def subject_ar(db, school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


def _gen(school, year, status):
    return ScheduleGeneration.objects.create(school=school, academic_year=year, status=status)


def _slot(school, class_group, teacher, subject, gen, *, year, period, active):
    return ScheduleSlot.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher,
        subject=subject,
        generation=gen,
        day_of_week=0,
        period_number=period,
        start_time=time(7, 30),
        end_time=time(8, 15),
        academic_year=year,
        is_active=active,
    )


class TestApprovedIsProtected:
    def test_deleting_an_approved_generation_is_refused_and_slots_keep_their_link(
        self, school, class_group, teacher_user, subject_ar, seeded_calendar
    ):
        gen = _gen(school, seeded_calendar, "approved")
        slot = _slot(
            school,
            class_group,
            teacher_user,
            subject_ar,
            gen,
            year=seeded_calendar,
            period=1,
            active=True,
        )

        with pytest.raises(ProtectedError):
            gen.delete()

        slot.refresh_from_db()
        assert slot.generation_id == gen.id, "النسبُ باقٍ — لا SET_NULL"
        assert ScheduleGeneration.objects.filter(pk=gen.pk).exists()

    def test_an_approved_generation_without_slots_is_still_protected(self, school, seeded_calendar):
        """الحمايةُ بالحالة لا بالحصص — المعتمَدُ القديمُ حصصُه بلا مرجعٍ أصلاً."""
        gen = _gen(school, seeded_calendar, "approved")
        with pytest.raises(ProtectedError):
            gen.delete()

    def test_any_generation_with_a_live_slot_is_protected(
        self, school, class_group, teacher_user, subject_ar, seeded_calendar
    ):
        """حالةٌ شاذّة — مسودّةٌ لها حصّةٌ حيّة — تُحمى أيضاً: الحيُّ لا يُيتَّم."""
        gen = _gen(school, seeded_calendar, "draft")
        _slot(
            school,
            class_group,
            teacher_user,
            subject_ar,
            gen,
            year=seeded_calendar,
            period=1,
            active=True,
        )
        with pytest.raises(ProtectedError):
            gen.delete()


class TestDeadGenerationsGoWithTheirSlots:
    def test_deleting_a_draft_removes_its_inactive_slots(
        self, school, class_group, teacher_user, subject_ar, seeded_calendar
    ):
        gen = _gen(school, seeded_calendar, "draft")
        _slot(
            school,
            class_group,
            teacher_user,
            subject_ar,
            gen,
            year=seeded_calendar,
            period=1,
            active=False,
        )
        _slot(
            school,
            class_group,
            teacher_user,
            subject_ar,
            gen,
            year=seeded_calendar,
            period=2,
            active=False,
        )

        gen.delete()

        assert ScheduleSlot.objects.count() == 0, "لا يتامى — كانت تبقى بلا مرجعٍ فتتراكم"

    def test_bulk_delete_refuses_the_whole_batch_if_one_is_protected(
        self, school, class_group, teacher_user, subject_ar, seeded_calendar
    ):
        approved = _gen(school, seeded_calendar, "approved")
        draft = _gen(school, seeded_calendar, "draft")
        _slot(
            school,
            class_group,
            teacher_user,
            subject_ar,
            draft,
            year=seeded_calendar,
            period=1,
            active=False,
        )

        with pytest.raises(ProtectedError):
            ScheduleGeneration.objects.filter(school=school).delete()

        assert ScheduleGeneration.objects.count() == 2, "كلٌّ أو لا شيء"
        assert ScheduleSlot.objects.count() == 1
        assert approved.is_protected and not draft.is_protected

    def test_bulk_delete_of_dead_generations_takes_their_slots(
        self, school, class_group, teacher_user, subject_ar, seeded_calendar
    ):
        archived = _gen(school, seeded_calendar, "archived")
        failed = _gen(school, seeded_calendar, "failed")
        _slot(
            school,
            class_group,
            teacher_user,
            subject_ar,
            archived,
            year=seeded_calendar,
            period=1,
            active=False,
        )

        ScheduleGeneration.objects.filter(pk__in=[archived.pk, failed.pk]).delete()

        assert ScheduleGeneration.objects.count() == 0
        assert ScheduleSlot.objects.count() == 0


class TestAdminSurface:
    def test_admin_hides_delete_for_protected_and_keeps_it_for_drafts(
        self, school, seeded_calendar, rf, principal_user
    ):
        from django.contrib.admin.sites import AdminSite

        from operations.admin import ScheduleGenerationAdmin

        principal_user.is_superuser = True
        principal_user.is_staff = True
        principal_user.save()
        request = rf.get("/admin/")
        request.user = principal_user
        model_admin = ScheduleGenerationAdmin(ScheduleGeneration, AdminSite())

        assert (
            model_admin.has_delete_permission(request, _gen(school, seeded_calendar, "approved"))
            is False
        )
        assert (
            model_admin.has_delete_permission(request, _gen(school, seeded_calendar, "draft"))
            is True
        )
