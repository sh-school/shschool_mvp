"""نسخُ الجدول المؤرشفة — جدولٌ واحدٌ فقط، الحيّ.

كلُّ اعتمادٍ يُؤرشف الجدولَ السابق كاملاً (870 صفّاً) ولا يحذفه، فبلغت النسخُ
على الإنتاج خمساً في يومٍ واحد: 4,350 صفّاً مطفأً مقابل 870 حيّة. وقرارُ
المدرسة (2026-09-05): لا يُبقى إلّا الحيّ.

وحدُّ الإبقاء إعدادٌ لا رقمٌ مدفون، والاعتمادُ والأمرُ يقرآنه من موضعٍ واحد
كي لا يحذف أحدُهما ما يحفظه الآخر.
"""

from datetime import time
from io import StringIO

import pytest
from django.core.management import call_command
from django.test import override_settings

from operations.models import ScheduleGeneration, ScheduleSlot, Subject
from operations.services import ScheduleService


@pytest.fixture
def subject_ar(db, school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


def _gen(school, year, status, *, minutes_ago=0):
    from django.utils import timezone

    gen = ScheduleGeneration.objects.create(school=school, academic_year=year, status=status)
    if minutes_ago:
        ScheduleGeneration.objects.filter(pk=gen.pk).update(
            generated_at=timezone.now() - timezone.timedelta(minutes=minutes_ago)
        )
        gen.refresh_from_db()
    return gen


def _slot(school, class_group, teacher, subject, gen, *, year, period=1, active=False):
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


# ══════════════════════ الافتراض: لا نسخةَ تبقى ══════════════════════


@pytest.mark.django_db
def test_by_default_no_archived_copy_is_kept(school, seeded_calendar):
    assert ScheduleService.retained_archived_ids(school, seeded_calendar) == []


@pytest.mark.django_db
def test_an_archived_generation_goes_with_its_dead_slots(
    school, class_group, teacher_user, subject_ar, seeded_calendar
):
    old = _gen(school, seeded_calendar, "archived")
    _slot(school, class_group, teacher_user, subject_ar, old, year=seeded_calendar)

    deleted = ScheduleService.retain_archived_generations(school, seeded_calendar)

    assert deleted == 1
    assert not ScheduleGeneration.objects.filter(pk=old.pk).exists()
    assert not ScheduleSlot.objects.filter(generation_id=old.pk).exists()


@pytest.mark.django_db
def test_the_approved_generation_and_the_drafts_survive(school, seeded_calendar):
    """المسودّةُ عملٌ جارٍ قد يُعتمد غداً، والمعتمَدُ هو الجدولُ نفسُه."""
    approved = _gen(school, seeded_calendar, "approved")
    draft = _gen(school, seeded_calendar, "draft")
    failed = _gen(school, seeded_calendar, "failed")

    ScheduleService.retain_archived_generations(school, seeded_calendar)

    for gen in (approved, draft, failed):
        assert ScheduleGeneration.objects.filter(pk=gen.pk).exists()


@pytest.mark.django_db
def test_an_archived_generation_holding_a_live_slot_is_never_touched(
    school, class_group, teacher_user, subject_ar, seeded_calendar
):
    """الحالةُ «مؤرشف» لا تكفي: حصّةٌ حيّةٌ تعني أنّ الجدولَ المعروضَ نسبُه إليه."""
    gen = _gen(school, seeded_calendar, "archived")
    _slot(school, class_group, teacher_user, subject_ar, gen, year=seeded_calendar, active=True)

    deleted = ScheduleService.retain_archived_generations(school, seeded_calendar)

    assert deleted == 0
    assert ScheduleGeneration.objects.filter(pk=gen.pk).exists()


# ══════════════════════ حدٌّ أكبر من صفر ══════════════════════════════


@pytest.mark.django_db
@override_settings(SCHEDULE_ARCHIVE_RETENTION=2)
def test_a_larger_limit_keeps_the_newest_copies(school, seeded_calendar):
    oldest = _gen(school, seeded_calendar, "archived", minutes_ago=30)
    middle = _gen(school, seeded_calendar, "archived", minutes_ago=20)
    newest = _gen(school, seeded_calendar, "archived", minutes_ago=10)

    deleted = ScheduleService.retain_archived_generations(school, seeded_calendar)

    assert deleted == 1
    assert not ScheduleGeneration.objects.filter(pk=oldest.pk).exists()
    assert ScheduleGeneration.objects.filter(pk__in=[middle.pk, newest.pk]).count() == 2


# ══════════════════════ الأمر: عرضٌ ثمّ حذف ═══════════════════════════


@pytest.mark.django_db
def test_the_command_shows_before_it_deletes(
    school, class_group, teacher_user, subject_ar, seeded_calendar
):
    gen = _gen(school, seeded_calendar, "archived")
    _slot(school, class_group, teacher_user, subject_ar, gen, year=seeded_calendar)
    out = StringIO()

    call_command("prune_schedule_archives", "--year", seeded_calendar, stdout=out)

    assert "عرضٌ فقط" in out.getvalue()
    assert ScheduleGeneration.objects.filter(pk=gen.pk).exists(), "العرضُ لا يحذف"


@pytest.mark.django_db
def test_the_command_deletes_with_apply(
    school, class_group, teacher_user, subject_ar, seeded_calendar
):
    gen = _gen(school, seeded_calendar, "archived")
    _slot(school, class_group, teacher_user, subject_ar, gen, year=seeded_calendar)
    out = StringIO()

    call_command("prune_schedule_archives", "--year", seeded_calendar, "--apply", stdout=out)

    assert not ScheduleGeneration.objects.filter(pk=gen.pk).exists()
    assert not ScheduleSlot.objects.filter(generation_id=gen.pk).exists()
