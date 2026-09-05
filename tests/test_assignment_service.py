"""[ASSIGNMENT] خدمةُ الإسناد — المسارُ الوحيدُ الذي تُكتب منه الحقيقة.

الثوابتُ التي تحرسها هذه الاختبارات:

    Screen → check() → apply()          ولا كتابةَ من خارجها
    BLOCK ≠ WARN ≠ INFO                 وثلاثتُها ليست حكماً واحداً
    TotalLoad = TeachingLoad + PreparationLoad
    PreparerTeachesTheCourse            مانعٌ لا تحذير

وأخطرُ ما يُحرَس أنّ **غيابَ الخطّة لا يمنع الكتابة**: مدرسةٌ نُشر لها الكود
قبل أن تُبذر خطّتُها كانت ستُمنع من كلّ إسنادٍ حتى يُشغَّل أمرُ البذر — بوّابةٌ
تحرس ما لا وجودَ له.
"""

import pytest
from django.core.exceptions import ValidationError

from academic_management import assignment_service as svc
from academic_management import load as loads
from academic_management.models import (
    APPROVED,
    FROM_MANUAL,
    FROM_MINISTRY_GUIDE,
    CoursePreparation,
    CurriculumPlan,
    TeacherWorkloadPlan,
    WorkloadGovernance,
)

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
GUIDE = "دليل الخطط الدراسية 2025-2026 ص14"


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-A")


@pytest.fixture
def subjects(db, school):
    from operations.models import Subject

    return {
        code: Subject.objects.create(school=school, name_ar=name, code=code)
        for code, name in (("MAT", "الرياضيات"), ("SCI", "العلوم"), ("ART", "الفنون البصرية"))
    }


def a_teacher(school, name="المعلّم", role_name="teacher"):
    from tests.conftest import MembershipFactory, RoleFactory, UserFactory

    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def teacher(db, school):
    return a_teacher(school, "معلّم الرياضيات")


@pytest.fixture
def actor(db, school):
    return a_teacher(school, "النائب الأكاديميّ", role_name="vice_academic")


@pytest.fixture
def seventh(db, school):
    from core.models import ClassGroup

    return ClassGroup.objects.create(
        school=school, grade="G7", section="1", level_type="prep", academic_year=YEAR
    )


def plan_row(school, subject, *, grade="G7", track="", periods=5, group=""):
    return CurriculumPlan.objects.create(
        school=school,
        academic_year=YEAR,
        grade=grade,
        track=track,
        subject=subject,
        weekly_periods=periods,
        source_kind=FROM_MINISTRY_GUIDE,
        source_reference=GUIDE,
        elective_group=group,
    )


def apply(school, class_group, subject, teacher, by, *, periods=5, **kw):
    return svc.apply_assignment(
        school=school,
        academic_year=YEAR,
        class_group=class_group,
        subject=subject,
        teacher=teacher,
        weekly_periods=periods,
        by=by,
        **kw,
    )


def codes(findings, level=None):
    return {f.code for f in findings if level is None or f.level == level}


# ══════════════════════════════════════════════════════════════════════
#  المسارُ الواحد
# ══════════════════════════════════════════════════════════════════════


def test_a_clean_assignment_is_written_with_its_author(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)

    row, findings = apply(school, seventh, subjects["MAT"], teacher, actor)

    assert row.pk and row.weekly_periods == 5
    assert row.created_by == actor and row.updated_by == actor
    assert not svc.blocking(findings)


def test_the_write_is_recorded_with_what_changed(school, subjects, seventh, teacher, actor):
    from core.models import AuditLog

    plan_row(school, subjects["MAT"], periods=5)
    apply(school, seventh, subjects["MAT"], teacher, actor)
    other = a_teacher(school, "معلّمٌ آخر")
    apply(school, seventh, subjects["MAT"], other, actor)

    # المفتاحُ UUID فترتيبُه عشوائيّ — والزمنُ هو ما يُرتَّب به.
    entry = (
        AuditLog.objects.filter(model_name="SubjectClassAssignment", action="update")
        .order_by("-timestamp")
        .first()
    )
    assert entry.changes["before"]["teacher"] == str(teacher.id)
    assert entry.changes["after"]["teacher"] == str(other.id)


# ══════════════════════════════════════════════════════════════════════
#  الخطّةُ مرجعُ الحصص
# ══════════════════════════════════════════════════════════════════════


def test_a_subject_outside_the_plan_is_blocked(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)

    with pytest.raises(svc.AssignmentError) as err:
        apply(school, seventh, subjects["ART"], teacher, actor, periods=2)
    assert svc.NOT_IN_PLAN in codes(err.value.findings, svc.BLOCK)


def test_periods_that_differ_from_the_plan_need_a_reason(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)

    with pytest.raises(svc.AssignmentError) as err:
        apply(school, seventh, subjects["MAT"], teacher, actor, periods=3)
    assert svc.PERIODS_MISMATCH_NO_REASON in codes(err.value.findings, svc.BLOCK)


def test_a_documented_override_is_saved_as_a_warning(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)

    row, findings = apply(
        school,
        seventh,
        subjects["MAT"],
        teacher,
        actor,
        periods=3,
        override_reason="شعبةٌ مدمجةٌ بقرار الإدارة",
    )
    assert row.weekly_periods == 3
    assert row.periods_override_reason == "شعبةٌ مدمجةٌ بقرار الإدارة"
    assert svc.PERIODS_MISMATCH in codes(findings, svc.WARN)


def test_without_a_seeded_plan_nothing_is_blocked(school, subjects, seventh, teacher, actor):
    """مدرسةٌ لم تُبذر خطّتُها بعد — تُكتب إسناداتُها ولا تُمنع بمرجعٍ غائب."""
    row, findings = apply(school, seventh, subjects["MAT"], teacher, actor, periods=5)

    assert row.pk
    assert not svc.blocking(findings)
    assert svc.NOT_IN_PLAN in codes(findings, svc.INFO)


def test_a_section_with_its_own_timetable_refuses_assignment(school, subjects, teacher, actor):
    from core.models import ClassGroup

    ese = ClassGroup.objects.create(
        school=school,
        grade="G8",
        section="ESE",
        level_type="prep",
        academic_year=YEAR,
        has_own_timetable=True,
    )
    with pytest.raises(svc.AssignmentError) as err:
        apply(school, ese, subjects["MAT"], teacher, actor)
    assert svc.OWN_TIMETABLE in codes(err.value.findings, svc.BLOCK)


def test_a_teacher_from_another_school_is_refused(school, subjects, seventh, actor):
    from core.models import School

    other_school = School.objects.create(name="مدرسة أخرى", code="OTH-A")
    stranger = a_teacher(other_school, "غريب")
    plan_row(school, subjects["MAT"], periods=5)

    with pytest.raises(svc.AssignmentError) as err:
        apply(school, seventh, subjects["MAT"], stranger, actor)
    assert svc.TEACHER_OUTSIDE_SCHOOL in codes(err.value.findings, svc.BLOCK)


# ══════════════════════════════════════════════════════════════════════
#  الحملُ والهدف
# ══════════════════════════════════════════════════════════════════════


def approve_plan(school, teacher, actor, *, required=6, reduction=0):
    plan = TeacherWorkloadPlan.objects.create(
        school=school,
        teacher=teacher,
        academic_year=YEAR,
        plan_version=1,
        required_weekly_periods=required,
        reduction_periods=reduction,
        required_source_kind=FROM_MANUAL,
        required_source_reference="محضر 1",
        status=APPROVED,
        created_by=actor,
    )
    return plan


def test_going_over_an_approved_target_warns_but_saves(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)
    approve_plan(school, teacher, actor, required=4)

    row, findings = apply(school, seventh, subjects["MAT"], teacher, actor, periods=5)

    assert row.pk, "التجاوزُ يُوصف ولا يمنع — قد يكون تكليفاً إداريّاً"
    assert svc.OVER_TARGET in codes(findings, svc.WARN)


def test_a_school_may_raise_a_warning_into_a_block(school, subjects, seventh, teacher, actor):
    """الصرامةُ تهيئةٌ للمدرسة لا شرطٌ محفورٌ في الكود."""
    plan_row(school, subjects["MAT"], periods=5)
    approve_plan(school, teacher, actor, required=4)
    WorkloadGovernance.objects.create(school=school, strict_codes=[svc.OVER_TARGET])

    with pytest.raises(svc.AssignmentError) as err:
        apply(school, seventh, subjects["MAT"], teacher, actor, periods=5)
    assert svc.OVER_TARGET in codes(err.value.findings, svc.BLOCK)


def test_editing_a_row_does_not_count_its_own_load_twice(school, subjects, seventh, teacher, actor):
    """تعديلُ إسنادٍ قائمٍ من 5 إلى 5 لا يُظهر المعلّمَ على عشر."""
    plan_row(school, subjects["MAT"], periods=5)
    approve_plan(school, teacher, actor, required=5)
    apply(school, seventh, subjects["MAT"], teacher, actor, periods=5)

    _row, findings = apply(school, seventh, subjects["MAT"], teacher, actor, periods=5)
    assert svc.OVER_TARGET not in codes(findings, svc.WARN)


def test_a_full_day_exemption_shrinks_the_available_capacity(
    school, subjects, seventh, teacher, actor
):
    from operations.models import TeacherExemption

    plan_row(school, subjects["MAT"], periods=34)
    for day in range(4):
        TeacherExemption.objects.create(
            school=school,
            teacher=teacher,
            academic_year=YEAR,
            exemption_type="full_day",
            day_of_week=day,
            reason="دورةٌ خارج المدرسة",
        )
    _row, findings = apply(school, seventh, subjects["MAT"], teacher, actor, periods=34)
    assert svc.OVER_CAPACITY in codes(findings, svc.WARN)


def test_a_coordinator_below_the_ministry_minimum_is_flagged(school, subjects, seventh, actor):
    coordinator = a_teacher(school, "منسّق الرياضيات", role_name="coordinator")
    plan_row(school, subjects["MAT"], periods=2)

    _row, findings = apply(school, seventh, subjects["MAT"], coordinator, actor, periods=2)
    assert svc.COORDINATOR_BELOW_MIN in codes(findings, svc.WARN)


# ══════════════════════════════════════════════════════════════════════
#  التزامنُ والحذف
# ══════════════════════════════════════════════════════════════════════


def test_a_stale_write_is_refused_not_merged(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)
    row, _ = apply(school, seventh, subjects["MAT"], teacher, actor)
    seen = row.updated_at.isoformat()

    other = a_teacher(school, "زميل")
    apply(school, seventh, subjects["MAT"], other, actor)

    with pytest.raises(svc.StaleWriteError):
        apply(school, seventh, subjects["MAT"], teacher, actor, expected_updated_at=seen)


def test_a_deletion_carries_who_and_why(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)
    row, _ = apply(school, seventh, subjects["MAT"], teacher, actor)

    svc.remove_assignment(assignment=row, by=actor, reason="نُقل المعلّم")
    row.refresh_from_db()

    assert row.is_active is False
    assert row.deleted_by == actor
    assert row.deletion_reason == "نُقل المعلّم"


def test_a_deletion_without_a_reason_is_refused(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)
    row, _ = apply(school, seventh, subjects["MAT"], teacher, actor)

    with pytest.raises(ValidationError):
        svc.remove_assignment(assignment=row, by=actor, reason="   ")


# ══════════════════════════════════════════════════════════════════════
#  إسنادُ التحضير
# ══════════════════════════════════════════════════════════════════════


def prepare(school, subject, teacher, by, *, grade="G7", track=""):
    return svc.apply_preparation(
        school=school,
        academic_year=YEAR,
        grade=grade,
        track=track,
        subject=subject,
        teacher=teacher,
        by=by,
    )


def test_the_preparer_must_teach_the_course(school, subjects, seventh, teacher, actor):
    """قرارُ الإدارة: المحضِّرُ من مدرّسي المقرّر حصراً — مانعٌ لا تحذير."""
    plan_row(school, subjects["MAT"], periods=5)

    with pytest.raises(svc.AssignmentError) as err:
        prepare(school, subjects["MAT"], teacher, actor)
    assert svc.PREPARER_DOES_NOT_TEACH in codes(err.value.findings, svc.BLOCK)


def test_a_teacher_of_the_course_may_prepare_it(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)
    apply(school, seventh, subjects["MAT"], teacher, actor)

    row, findings = prepare(school, subjects["MAT"], teacher, actor)
    assert row.pk and row.teacher == teacher
    assert not svc.blocking(findings)


def test_one_preparer_per_course(school, subjects, seventh, teacher, actor):
    from core.models import ClassGroup

    second = ClassGroup.objects.create(
        school=school, grade="G7", section="2", level_type="prep", academic_year=YEAR
    )
    other = a_teacher(school, "زميل الرياضيات")
    plan_row(school, subjects["MAT"], periods=5)
    apply(school, seventh, subjects["MAT"], teacher, actor)
    apply(school, second, subjects["MAT"], other, actor)
    prepare(school, subjects["MAT"], teacher, actor)

    with pytest.raises(svc.AssignmentError) as err:
        prepare(school, subjects["MAT"], other, actor)
    assert svc.COURSE_ALREADY_PREPARED in codes(err.value.findings, svc.BLOCK)


def test_losing_the_last_teaching_row_drops_the_preparation(
    school, subjects, seventh, teacher, actor
):
    """سقط شرطُ التدريس فسقطت المسؤوليّةُ معه — لا تبقى معلّقةً بلا سند."""
    plan_row(school, subjects["MAT"], periods=5)
    row, _ = apply(school, seventh, subjects["MAT"], teacher, actor)
    prepare(school, subjects["MAT"], teacher, actor)

    svc.remove_assignment(assignment=row, by=actor, reason="نُقل المعلّم")

    assert not CoursePreparation.objects.live(school, year=YEAR).filter(teacher=teacher).exists()


def test_reassigning_the_row_drops_the_previous_preparer(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)
    apply(school, seventh, subjects["MAT"], teacher, actor)
    prepare(school, subjects["MAT"], teacher, actor)

    other = a_teacher(school, "المعلّم البديل")
    apply(school, seventh, subjects["MAT"], other, actor)

    assert not CoursePreparation.objects.live(school, year=YEAR).filter(teacher=teacher).exists()


# ══════════════════════════════════════════════════════════════════════
#  صيغةُ الحمل
# ══════════════════════════════════════════════════════════════════════


def test_preparation_costs_two_periods_per_course(school, subjects, seventh, teacher, actor):
    """قرارُ الإدارة: حصّتان لكلّ مقرّرٍ يحضّره — فمقرّران أربع."""
    from core.models import ClassGroup

    eighth = ClassGroup.objects.create(
        school=school, grade="G8", section="1", level_type="prep", academic_year=YEAR
    )
    plan_row(school, subjects["MAT"], grade="G7", periods=5)
    plan_row(school, subjects["MAT"], grade="G8", periods=5)
    apply(school, seventh, subjects["MAT"], teacher, actor)
    apply(school, eighth, subjects["MAT"], teacher, actor)
    prepare(school, subjects["MAT"], teacher, actor, grade="G7")
    prepare(school, subjects["MAT"], teacher, actor, grade="G8")

    load = loads.load_for(school, YEAR, teacher.id)
    assert load.teaching == 10
    assert load.prepared_courses == 2
    assert load.preparation == 4
    assert load.total == 14


def test_the_weight_is_a_school_setting_not_a_constant(school, subjects, seventh, teacher, actor):
    WorkloadGovernance.objects.create(school=school, preparation_weight=3)
    plan_row(school, subjects["MAT"], periods=5)
    apply(school, seventh, subjects["MAT"], teacher, actor)
    prepare(school, subjects["MAT"], teacher, actor)

    assert loads.load_for(school, YEAR, teacher.id).preparation == 3


def test_the_label_reads_as_the_screen_shows_it(school, subjects, seventh, teacher, actor):
    plan_row(school, subjects["MAT"], periods=5)
    approve_plan(school, teacher, actor, required=7)
    apply(school, seventh, subjects["MAT"], teacher, actor)
    prepare(school, subjects["MAT"], teacher, actor)

    assert (
        loads.load_for(school, YEAR, teacher.id).label() == "5 تدريس + 2 تحضير (مقرّرٌ واحد) = 7 من 7"
    )


def test_a_teacher_without_any_target_is_not_compared(school, subjects, seventh, teacher, actor):
    """لا خطّةَ ولا نصابَ مرجعيّ — فلا مقارنة، ولا يُخترع رقم."""
    plan_row(school, subjects["MAT"], periods=5)
    apply(school, seventh, subjects["MAT"], teacher, actor)

    load = loads.load_for(school, YEAR, teacher.id)
    assert load.target is None and load.delta is None
    assert load.label() == "5 تدريس"


def test_the_reference_load_stands_in_when_no_plan_is_approved(
    school, subjects, seventh, teacher, actor
):
    WorkloadGovernance.objects.create(school=school, reference_load=16)
    plan_row(school, subjects["MAT"], periods=5)
    apply(school, seventh, subjects["MAT"], teacher, actor)

    load = loads.load_for(school, YEAR, teacher.id)
    assert load.target == 16
    assert load.target_source == loads.FROM_REFERENCE
