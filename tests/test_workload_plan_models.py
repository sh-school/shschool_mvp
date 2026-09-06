"""[WORKLOAD] خطّةُ النصاب — تُكتب الاختباراتُ قبل الـmigration.

وثلاثةُ أشياءَ كشفتها الشاشةُ على الـ73 معلّماً هي التي فرضت هذا التصميم:
ستّةَ عشرَ معلّماً يعملون في مرحلتين، وثلاثةَ عشرَ يدرّسون أكثرَ من مادّة،
وخمسةٌ لهم حصصٌ في شعبةٍ منقسمة. فلا يكفي رقمٌ واحدٌ جامدٌ للنصاب.

والثوابتُ التي تحرسها هذه الاختبارات:

    TeachingTarget = RequiredWeeklyPeriods − ApprovedReductionPeriods
    ∑ AssignedInstructionalPeriods = TeachingTarget      (بعد الاعتماد فقط)
    InstructionalPeriods ≠ OccupiedSlots
    ObservedScheduledWorkload ≠ ApprovedWorkload

والأخيرُ أهمُّها: خطّةٌ تُملأ من الجدول تحوّل التاريخَ إلى سياسةٍ لم يقرّرها
أحد. والفرقُ بين المرصود والمعتمد ليس خطأً بذاته — هو `discrepancy` يحتاج
تفسيراً، وقد يكون تفسيرُه تكليفاً إداريّاً لا يعرفه الجدول.
"""

import pytest
from django.core.exceptions import ValidationError

from academic_management.models import (
    APPROVED,
    DRAFT,
    LOCKED,
    REVIEWED,
    ApprovedPlanImmutableError,
    TeacherWorkloadAllocation,
    TeacherWorkloadPlan,
)

pytestmark = pytest.mark.django_db


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-T")


@pytest.fixture
def teacher(db):
    from core.models import CustomUser

    return CustomUser.objects.create(national_id="20000000001", full_name="أحمد")


@pytest.fixture
def approver(db):
    from core.models import CustomUser

    return CustomUser.objects.create(national_id="20000000002", full_name="النائب الأكاديميّ")


@pytest.fixture
def subject(db, school):
    from operations.models import Subject

    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


def plan(school, teacher, *, required=18, reduction=0, version=1, status=DRAFT, **kw):
    return TeacherWorkloadPlan.objects.create(
        school=school,
        teacher=teacher,
        academic_year="2026-2027",
        plan_version=version,
        required_weekly_periods=required,
        reduction_periods=reduction,
        status=status,
        **kw,
    )


# ── الثابتُ الأوّل: الهدفُ التدريسيُّ مشتقٌّ لا مخزَّن ─────────────────


def test_the_teaching_target_is_derived_and_cannot_drift(school, teacher):
    """`teaching_target` خاصّيّةٌ محسوبة لا حقلٌ يُكتب.

    ولو خُزِّن لأمكن أن يقول الحقلُ ستّةَ عشرَ والطرحُ يقول أربعةَ عشر، فيصير
    في القاعدة مصدران لحقيقةٍ واحدة — وهو بعينه الخللُ الذي صحّحناه في
    `weekly_periods`.
    """
    row = plan(school, teacher, required=18, reduction=2)

    assert row.teaching_target == 16
    assert not hasattr(TeacherWorkloadPlan, "teaching_target_field")
    assert "teaching_target" not in {f.name for f in TeacherWorkloadPlan._meta.get_fields()}


def test_a_teacher_with_no_reduction_teaches_the_full_required_load(school, teacher):
    assert plan(school, teacher, required=18, reduction=0).teaching_target == 18


def test_a_reduction_larger_than_the_required_load_is_refused(school, teacher):
    row = TeacherWorkloadPlan(
        school=school,
        teacher=teacher,
        academic_year="2026-2027",
        plan_version=1,
        required_weekly_periods=12,
        reduction_periods=14,
    )

    with pytest.raises(ValidationError):
        row.full_clean()


def test_a_reduction_must_carry_its_reason(school, teacher):
    """«تخفيضُ منسّقِ مادّة» قرارٌ إداريّ — ورقمٌ بلا سببٍ لا يُراجَع."""
    row = TeacherWorkloadPlan(
        school=school,
        teacher=teacher,
        academic_year="2026-2027",
        plan_version=1,
        required_weekly_periods=18,
        reduction_periods=4,
        reduction_reason="",
    )

    with pytest.raises(ValidationError):
        row.full_clean()


# ── الحالاتُ الثمانُ التي كشفتها الشاشة ──────────────────────────────


def test_a_single_level_single_subject_teacher_needs_no_breakdown(school, teacher):
    """الأغلبيّة: التفصيلُ حسب المرحلة اختياريٌّ ولا يُفرض."""
    row = plan(school, teacher, required=18)

    assert row.allocations.count() == 0
    assert row.allocations_balanced, "خطّةٌ بلا تفصيلٍ متوازنةٌ بحكم التعريف"
    row.full_clean()


def test_a_teacher_across_two_levels_may_split_the_target_by_level(school, teacher):
    """ستّةَ عشرَ معلّماً يعملون في المرحلتين — ولا يُحشر ذلك في رقمٍ واحد."""
    row = plan(school, teacher, required=18, reduction=2, reduction_reason="منسّق مادّة")
    TeacherWorkloadAllocation.objects.create(
        workload_plan=row, level_type="prep", target_periods=10
    )
    TeacherWorkloadAllocation.objects.create(workload_plan=row, level_type="sec", target_periods=6)

    assert row.teaching_target == 16
    assert sum(a.target_periods for a in row.allocations.all()) == 16
    assert row.allocations_balanced


def test_the_reduction_lives_only_on_the_plan_head_never_on_a_level(school, teacher):
    """رقمُ تخفيضٍ واحدٌ في النظام — وإلّا لم نعرف أيُّهما الحقيقة.

    فلو حمل التوزيعُ تخفيضاً خاصّاً بالمرحلة لأمكن أن يقول الرأسُ «حصّتان»
    ويقول مجموعُ المراحل «ثلاث»، ولا حَكَمَ بينهما. والتخفيضُ قرارٌ إداريٌّ
    له سببٌ ومصدر، فمقامُه رأسُ الخطّة وحدَه.
    """
    names = {f.name for f in TeacherWorkloadAllocation._meta.get_fields()}
    assert "reduction_periods" not in names
    assert "reduction_periods" in {f.name for f in TeacherWorkloadPlan._meta.get_fields()}


def test_a_breakdown_that_overshoots_the_target_is_refused_on_the_spot(school, teacher):
    """التجاوزُ خطأٌ حين يُكتب، لا حين يُعتمد — والنقصُ يُنتظر تمامُه."""
    row = plan(school, teacher, required=18, reduction=2, reduction_reason="منسّق مادّة")
    TeacherWorkloadAllocation.objects.create(
        workload_plan=row, level_type="prep", target_periods=10
    )

    partial = TeacherWorkloadAllocation(workload_plan=row, level_type="sec", target_periods=4)
    partial.full_clean()  # ناقصٌ بعدُ — ولا يُرفض

    overshoot = TeacherWorkloadAllocation(workload_plan=row, level_type="sec", target_periods=7)
    with pytest.raises(ValidationError):
        overshoot.full_clean()


def test_a_breakdown_that_does_not_add_up_to_the_target_is_refused(school, teacher):
    row = plan(school, teacher, required=18, reduction=2, reduction_reason="منسّق مادّة")
    TeacherWorkloadAllocation.objects.create(
        workload_plan=row, level_type="prep", target_periods=10
    )
    TeacherWorkloadAllocation.objects.create(workload_plan=row, level_type="sec", target_periods=4)

    assert not row.allocations_balanced
    with pytest.raises(ValidationError):
        row.validate_allocations()


def test_one_allocation_per_level_at_most(school, teacher):
    from django.db import IntegrityError

    row = plan(school, teacher)
    TeacherWorkloadAllocation.objects.create(workload_plan=row, level_type="prep", target_periods=9)

    with pytest.raises(IntegrityError):
        TeacherWorkloadAllocation.objects.create(
            workload_plan=row, level_type="prep", target_periods=9
        )


def test_the_target_is_measured_in_instructional_periods_not_occupied_slots(school, teacher):
    """خانةٌ واحدةٌ تحمل مجموعتين في مادّتين — وكلُّ معلّمٍ فيها يعمل حصّةً.

    وما صحّحناه من 849 إلى 870 أثبت أنّ الوحدة هي الحصّة الفعليّة. والخانةُ
    الزمنيّةُ وعاءُ جدولةٍ لا وحدةَ نصاب.
    """
    from operations.schedule_profile import Lesson
    from operations.workload_profile import observed_workload

    lessons = [
        Lesson(
            teacher_id="t1",
            teacher_name="أحمد",
            class_id="11/1",
            class_name="11/1",
            class_label="11/1",
            subject_id="s1",
            subject_name="حاسب",
            subject_code="CS",
            day=0,
            period=3,
        ),
        Lesson(
            teacher_id="t2",
            teacher_name="خالد",
            class_id="11/1",
            class_name="11/1",
            class_label="11/1",
            subject_id="s2",
            subject_name="أعمال",
            subject_code="BUS",
            day=0,
            period=3,
        ),
    ]

    rows = observed_workload(lessons)

    assert rows["t1"].observed_weekly == 1, "حصّةٌ كاملةٌ رغم مشاركة الخانة"
    assert rows["t1"].split_periods == 1, "والانقسامُ يُوصف ولا يُنقِص النصاب"
    assert rows["t1"].observed_weekly == rows["t2"].observed_weekly


# ── دورةُ الخطّة: لا تعديلَ صامتٍ بعد الاعتماد ──────────────────────


def test_the_status_moves_only_forward_through_the_declared_cycle(school, teacher):
    row = plan(school, teacher)

    for nxt in (REVIEWED, APPROVED):
        row.status = nxt
        row.save()
    assert row.status == APPROVED


def test_an_approved_plan_cannot_be_edited_in_place(school, teacher, approver):
    """أيُّ تغييرٍ بعد الاعتماد يولّد نسخةً جديدة — ولا يُكتب فوق القديمة."""
    row = plan(school, teacher, required=18, status=DRAFT)
    row.status = APPROVED
    row.approved_by = approver
    row.save()

    row.required_weekly_periods = 16
    with pytest.raises(ApprovedPlanImmutableError):
        row.save()

    row.refresh_from_db()
    assert row.required_weekly_periods == 18, "النسخةُ المعتمدةُ سليمةٌ كما اعتُمدت"


def test_a_locked_plan_is_immutable_too(school, teacher):
    row = plan(school, teacher, status=APPROVED)
    row.status = LOCKED
    row.save()

    row.reduction_periods = 3
    with pytest.raises(ApprovedPlanImmutableError):
        row.save()


def test_a_new_version_carries_the_change_and_leaves_the_old_one_standing(school, teacher):
    first = plan(school, teacher, required=18, version=1, status=APPROVED)
    second = plan(school, teacher, required=16, version=2, status=DRAFT)

    first.refresh_from_db()
    assert first.required_weekly_periods == 18
    assert second.plan_version == 2
    assert TeacherWorkloadPlan.objects.filter(teacher=teacher).count() == 2


def test_two_plans_cannot_share_a_version_for_one_teacher_and_year(school, teacher):
    from django.db import IntegrityError

    plan(school, teacher, version=1)

    with pytest.raises(IntegrityError):
        plan(school, teacher, version=1)


def test_the_current_plan_is_the_highest_approved_version(school, teacher):
    plan(school, teacher, required=18, version=1, status=APPROVED)
    plan(school, teacher, required=16, version=2, status=APPROVED)
    plan(school, teacher, required=14, version=3, status=DRAFT)

    current = TeacherWorkloadPlan.current_for(school, teacher, "2026-2027")

    assert current.plan_version == 2, "المسوّدةُ لا تصير سياسةً لأنّها الأحدث"
    assert current.required_weekly_periods == 16


def test_a_teacher_without_any_approved_plan_has_none(school, teacher):
    plan(school, teacher, version=1, status=DRAFT)

    assert TeacherWorkloadPlan.current_for(school, teacher, "2026-2027") is None


# ── المؤهّلات ───────────────────────────────────────────────────────


def test_nothing_creates_a_plan_from_the_observed_schedule(school, teacher):
    """لا دالّةَ تحوّل المرصودَ إلى معتمَد. والاقتراحُ فعلُ إنسانٍ لا نظام.

    HistoricalAssignment → Proposal        (وليس → Truth)
    """
    from academic_management import models as models_module

    forbidden = [
        name
        for name in dir(models_module)
        if name.startswith(("import_", "seed_", "sync_", "adopt_", "derive_"))
    ]

    assert not forbidden, f"دوالُّ نسخٍ آليٍّ محتملة: {forbidden}"
    assert not TeacherWorkloadPlan.objects.filter(teacher=teacher).exists()


def test_the_discrepancy_is_reported_and_not_called_an_error(school, teacher):
    """المرصود 18 والمعتمد 16 فرقٌ يحتاج تفسيراً — لا حكماً بالخطأ."""
    row = plan(school, teacher, required=18, reduction=2, reduction_reason="منسّق مادّة")

    gap = row.discrepancy(observed=18)

    assert gap["observed"] == 18
    assert gap["approved"] == 16
    assert gap["delta"] == 2
    assert gap["is_error"] is False
    assert "تفسير" in gap["note"]
