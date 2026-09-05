"""الجدولُ وإسناداتُه والعامُ الدراسيّ — قاعدةٌ واحدةٌ محروسةٌ في ثلاثة مواضع.

القاعدة: **لا سجلَّ نشطٌ خارجَ العام الجاري** — لا حصّةً ولا إسنادَ مادّة.

وسببها واقعة: بقيت مئتان وخمسون حصّةً من 2025-2026 نشطةً بعد دخول 2026-2027،
وتسعةٌ من معلّميها العشرة يدرّسون في العام الجديد. فكان المعلّم المتفرّغ
يُرى مشغولاً في اقتراح البدلاء، وشُعبةُ عامٍ مضى تدخل نطاقَ طلاب المنسّق.

وهذا الملفّ يحرس الأمرين معاً: أنّ القراءةَ تُقيَّد بالعام حتّى لو اتّسخت
القاعدة، وأنّ الحارسَ يُنظّف القاعدة من نفسه.
"""

from datetime import date, time

import pytest

from operations.models import ScheduleSlot, Subject, SubjectClassAssignment
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

    def test_retire_never_deletes(self, school, class_group, teacher_user, subject_ar, past_year):
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


def _assignment(school, class_group, teacher, subject, *, year, active=True):
    return SubjectClassAssignment.objects.create(
        school=school,
        class_group=class_group,
        subject=subject,
        teacher=teacher,
        weekly_periods=4,
        academic_year=year,
        is_active=active,
    )


class TestAssignmentYearScope:
    """الإسنادُ أصلُ الجدول — والقيدُ عليه أوجبُ منه على الحصّة."""

    def test_live_excludes_past_year_assignments(
        self, school, class_group, teacher_user, subject_ar, current_year, past_year
    ):
        now = _assignment(school, class_group, teacher_user, subject_ar, year=current_year)
        other = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
        _assignment(school, class_group, teacher_user, other, year=past_year)

        assert list(SubjectClassAssignment.objects.live(school)) == [now]

    def test_guard_retires_assignments_too(
        self, school, class_group, teacher_user, subject_ar, current_year, past_year
    ):
        now = _assignment(school, class_group, teacher_user, subject_ar, year=current_year)
        other = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
        old = _assignment(school, class_group, teacher_user, other, year=past_year)
        _slot(school, class_group, teacher_user, subject_ar, year=past_year, day=1)

        retired = ScheduleService.retire_past_year_records(school)

        assert retired == {"assignments": 1, "slots": 1}
        now.refresh_from_db()
        old.refresh_from_db()
        assert now.is_active is True
        assert old.is_active is False

    def test_guard_is_idempotent_across_both_models(
        self, school, class_group, teacher_user, subject_ar, past_year
    ):
        _assignment(school, class_group, teacher_user, subject_ar, year=past_year)
        _slot(school, class_group, teacher_user, subject_ar, year=past_year)

        assert ScheduleService.retire_past_year_records(school) == {
            "assignments": 1,
            "slots": 1,
        }
        assert ScheduleService.retire_past_year_records(school) == {
            "assignments": 0,
            "slots": 0,
        }

    def test_past_year_subject_does_not_bias_substitute_ranking(
        self, db, school, class_group, teacher_user, subject_ar, past_year
    ):
        """ترجيحُ «صاحبِ المادّة» لا يُبنى على إسنادِ عامٍ مضى.

        معلّمان متاحان: الأوّلُ درّس المادّة في عامٍ مضى، والثاني لم يدرّسها
        قطّ. فبلا قيد العام يتقدّم الأوّلُ بحجّةٍ منقضية.
        """
        from tests.conftest import MembershipFactory, RoleFactory, UserFactory

        role = RoleFactory(school=school, name="teacher")
        other = UserFactory(full_name="أ. آخر")
        MembershipFactory(user=other, school=school, role=role)

        _assignment(school, class_group, teacher_user, subject_ar, year=past_year)

        ranked = list(
            SubstituteService.get_available_teachers(
                school,
                date.today(),
                day_of_week=0,
                period_number=2,
                subject_id=subject_ar.id,
            )
        )

        assert {teacher_user, other} <= set(ranked)
        # لا ترجيحَ لأحدهما — كلاهما «ليس صاحبَ المادّة» هذا العام، فالترتيبُ بالاسم.
        assert ranked == sorted(ranked, key=lambda u: u.full_name)
