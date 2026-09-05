"""حصصُ الجدول والعامُ الدراسيّ — قاعدةٌ واحدةٌ محروسةٌ في ثلاثة مواضع.

القاعدة: **لا حصّةَ نشطةٌ خارجَ العام الجاري.**

وسببها واقعة: بقيت مئتان وخمسون حصّةً من 2025-2026 نشطةً بعد دخول 2026-2027،
وتسعةٌ من معلّميها العشرة يدرّسون في العام الجديد. فكان المعلّم المتفرّغ
يُرى مشغولاً في اقتراح البدلاء، وشُعبةُ عامٍ مضى تدخل نطاقَ طلاب المنسّق.

وهذا الملفّ يحرس الأمرين معاً: أنّ القراءةَ تُقيَّد بالعام حتّى لو اتّسخت
القاعدة، وأنّ الحارسَ يُنظّف القاعدة من نفسه.
"""

from datetime import date, time

import pytest

from operations.models import ScheduleSlot, Subject
from operations.services import ScheduleService, SubstituteService


@pytest.fixture
def subject_ar(db, school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


def _slot(school, class_group, teacher, subject, *, year, day=0, period=1, active=True):
    return ScheduleSlot.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher,
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=time(7, 30),
        end_time=time(8, 15),
        academic_year=year,
        is_active=active,
    )


@pytest.fixture
def current_year(db, school):
    from core.academic_calendar import academic_year_for_school

    return academic_year_for_school(school)


@pytest.fixture
def past_year(current_year):
    """عامٌ مضى — مشتقٌّ من الجاري كي لا يتقادم الاختبار بمرور السنين."""
    start = int(str(current_year).split("-")[0])
    return f"{start - 1}-{start}"


class TestLiveQuerySet:
    def test_live_excludes_past_years(
        self, school, class_group, teacher_user, subject_ar, current_year, past_year
    ):
        now = _slot(school, class_group, teacher_user, subject_ar, year=current_year)
        _slot(school, class_group, teacher_user, subject_ar, year=past_year, day=1)

        live = list(ScheduleSlot.objects.live(school))
        assert live == [now]

    def test_live_excludes_inactive_drafts(
        self, school, class_group, teacher_user, subject_ar, current_year
    ):
        """مسودّةُ توليدٍ لم تُعتمد مطفأةٌ بحكم التصميم — فلا تُرى في الحيّ."""
        _slot(school, class_group, teacher_user, subject_ar, year=current_year, active=False)
        assert ScheduleSlot.objects.live(school).count() == 0

    def test_past_years_is_the_complement(
        self, school, class_group, teacher_user, subject_ar, current_year, past_year
    ):
        _slot(school, class_group, teacher_user, subject_ar, year=current_year)
        old = _slot(school, class_group, teacher_user, subject_ar, year=past_year, day=1)

        assert list(ScheduleSlot.objects.past_years(school)) == [old]


class TestYearGuard:
    def test_retire_turns_off_past_years_only(
        self, school, class_group, teacher_user, subject_ar, current_year, past_year
    ):
        now = _slot(school, class_group, teacher_user, subject_ar, year=current_year)
        old = _slot(school, class_group, teacher_user, subject_ar, year=past_year, day=1)

        assert ScheduleService.retire_past_year_slots(school) == 1

        now.refresh_from_db()
        old.refresh_from_db()
        assert now.is_active is True
        assert old.is_active is False

    def test_retire_is_idempotent(
        self, school, class_group, teacher_user, subject_ar, current_year, past_year
    ):
        _slot(school, class_group, teacher_user, subject_ar, year=past_year)

        assert ScheduleService.retire_past_year_slots(school) == 1
        assert ScheduleService.retire_past_year_slots(school) == 0

    def test_retire_never_deletes(
        self, school, class_group, teacher_user, subject_ar, past_year
    ):
        """الإطفاءُ لا حذف — الحذفُ قرارُ `prune_schedule_slots` بيد إنسان."""
        _slot(school, class_group, teacher_user, subject_ar, year=past_year)
        ScheduleService.retire_past_year_slots(school)

        assert ScheduleSlot.objects.count() == 1


class TestPastYearDoesNotLeak:
    def test_teacher_busy_in_past_year_is_still_available_as_substitute(
        self, school, class_group, teacher_user, subject_ar, current_year, past_year
    ):
        """الواقعةُ التي كشفت العطب: معلّمٌ حصّتُه في جدولٍ مضى كان يُعدّ مشغولاً."""
        _slot(
            school,
            class_group,
            teacher_user,
            subject_ar,
            year=past_year,
            day=0,
            period=3,
        )

        available = SubstituteService.get_available_teachers(
            school, date.today(), day_of_week=0, period_number=3
        )

        assert teacher_user in list(available)

    def test_department_scope_ignores_past_year_classes(
        self, db, school, class_group, teacher_user, subject_ar, past_year
    ):
        from core.models import Department, Membership

        dept = Department.objects.create(school=school, name="الرياضيات")
        Membership.objects.filter(user=teacher_user, school=school).update(department_obj=dept)

        _slot(school, class_group, teacher_user, subject_ar, year=past_year)

        assert dept.get_student_ids() == set()
