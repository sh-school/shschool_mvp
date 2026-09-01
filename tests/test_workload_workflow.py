"""[WORKLOAD] دورةُ الخطّة: مسودّةٌ ← تحقّقٌ ← مراجعةٌ ← اعتماد.

    Approval ≠ save(status="APPROVED")

وهذه الاختباراتُ تحرس ثلاثةَ أشياءَ لا يحرسها الـschema وحدَه:

    ١. القدرةُ لا المسمّى — من يعتمد يُعرَف بقدرةٍ تُهيّئها المدرسة، إذ لا
       نملك نصّاً وزاريّاً منشوراً يُسنِد الاعتمادَ إلى وظيفةٍ بعينها.
    ٢. `reviewed_by != approved_by` افتراضاً — وإلّا فُقدت المراجعةُ المستقلّة
       عمليّاً، والجمعُ إن لزم فتجاوزٌ مسجَّلٌ لا سلوكٌ صامت.
    ٣. كلُّ حقيقةٍ إداريّةٍ مؤثّرةٍ لها منبعُها هي — فالنصابُ قد يأتي من تعميمٍ
       والتخفيضُ من قرارِ مديرٍ والتخصّصُ من ملفِّ موظّف.
"""

from datetime import date

import pytest
from django.core.exceptions import PermissionDenied, ValidationError

from academic_management import workload_workflow as flow
from academic_management.models import (
    APPROVED,
    DRAFT,
    FROM_MANUAL,
    FROM_PREVIOUS_PLAN,
    LOCKED,
    QUALIFIED,
    REVIEWED,
    SUBMITTED,
    TeacherSubjectQualification,
    TeacherWorkloadPlan,
    WorkloadGovernance,
)
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


# ── تجهيز ────────────────────────────────────────────────────────────


def actor(school, role_name, name):
    role = RoleFactory(school=school, name=role_name)
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


@pytest.fixture
def coordinator(school):
    return actor(school, "coordinator", "منسّق الرياضيات")


@pytest.fixture
def deputy(school):
    return actor(school, "vice_academic", "النائب الأكاديميّ")


@pytest.fixture
def head(school):
    return actor(school, "principal", "مدير المدرسة")


@pytest.fixture
def subject(school):
    from operations.models import Subject

    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


@pytest.fixture
def target_teacher(school):
    return actor(school, "teacher", "المعلّم صاحب الخطّة")


def draft(school, teacher, by, **kw):
    fields = {
        "required_weekly_periods": 18,
        "required_source_kind": FROM_MANUAL,
        "required_source_reference": "تعميم 7 / 2026",
        "reduction_periods": 2,
        "reduction_reason": "منسّق مادّة",
        "reduction_source": "school",
        "reduction_source_reference": "محضر 12",
    }
    fields.update(kw)
    return flow.open_draft(school, teacher, "2026-2027", by=by, **fields)


# ── القدرةُ لا المسمّى الوظيفيّ ──────────────────────────────────────


def test_the_capability_is_configured_by_the_school_not_hard_coded(school, coordinator):
    """لا نصَّ وزاريّاً منشوراً يقول إنّ الاعتمادَ لوظيفةٍ بعينها — فلا نحفره."""
    assert flow.capability_roles(school, flow.APPROVE) == {"principal"}

    WorkloadGovernance.objects.create(school=school, approve_roles=["vice_academic"])

    assert flow.capability_roles(school, flow.APPROVE) == {"vice_academic"}, (
        "المدرسةُ تربط القدرةَ بدورها — والافتراضُ افتراضٌ لا قاعدةٌ محفورة"
    )


def test_an_empty_configuration_means_the_default_not_nobody(school):
    """فراغُ القائمة «خُذ الافتراض»، لا «لا أحدَ يملك القدرة»."""
    WorkloadGovernance.objects.create(school=school)

    assert flow.capability_roles(school, flow.REVIEW) == {"vice_academic", "principal"}


def test_a_teacher_cannot_open_a_draft(school, teacher_user, target_teacher):
    with pytest.raises(PermissionDenied):
        draft(school, target_teacher, teacher_user)


# ── الدورةُ لا تُقفز فوق مراحلها ────────────────────────────────────


def test_the_cycle_records_who_did_what_and_when(school, coordinator, deputy, target_teacher):
    """«قيد المراجعة» و«روجعت» حالتان — ولكلِّ فعلٍ فاعلٌ ووقت."""
    plan = draft(school, target_teacher, coordinator)
    assert plan.status == DRAFT and plan.plan_version == 1

    flow.submit_for_review(plan, by=coordinator)
    assert (plan.status, plan.submitted_by) == (SUBMITTED, coordinator)
    assert plan.submitted_at is not None

    flow.record_review(plan, by=deputy, comment="مطابقٌ للتعميم")
    assert (plan.status, plan.reviewed_by) == (REVIEWED, deputy)
    assert plan.reviewed_at is not None and plan.review_comment == "مطابقٌ للتعميم"


def test_a_draft_cannot_leap_straight_to_approved(school, coordinator, head, target_teacher):
    plan = draft(school, target_teacher, coordinator)

    with pytest.raises(flow.WorkflowError):
        flow.approve(plan, by=head)


def test_a_reviewer_may_send_it_back_to_the_drafter(school, coordinator, deputy, target_teacher):
    plan = draft(school, target_teacher, coordinator)
    flow.submit_for_review(plan, by=coordinator)

    flow.return_to_draft(plan, by=deputy, comment="مرجعُ التخفيض ناقص")

    assert plan.status == DRAFT and plan.review_comment == "مرجعُ التخفيض ناقص"


# ── الفصلُ بين المراجع والمعتمِد ─────────────────────────────────────


def _ready_for_approval(school, teacher, coordinator, deputy):
    """خطّةٌ بلغت المراجعةَ وكلُّ بنود البوّابة مثبتةٌ فيها.

    لا إسنادَ لهذا المعلّم، فالمُسنَدُ صفر — ولذلك يكون الهدفُ التدريسيُّ صفراً
    أيضاً: نصابٌ كامل مُخفَّضٌ كلُّه (حالةُ المتفرّغ إداريّاً).
    """
    plan = draft(
        school,
        teacher,
        coordinator,
        required_weekly_periods=4,
        reduction_periods=4,
        reduction_reason="تفرّغٌ إداريّ",
    )
    flow.submit_for_review(plan, by=coordinator)
    flow.record_review(plan, by=deputy, comment="")
    return plan


def test_the_reviewer_does_not_approve_what_they_reviewed(
    school, coordinator, deputy, target_teacher
):
    """`reviewed_by == approved_by` يُلغي المراجعةَ المستقلّةَ عمليّاً."""
    WorkloadGovernance.objects.create(school=school, approve_roles=["vice_academic"])
    plan = _ready_for_approval(school, target_teacher, coordinator, deputy)

    with pytest.raises(PermissionDenied):
        flow.approve(plan, by=deputy)

    plan.refresh_from_db()
    assert plan.status == REVIEWED, "لم تُعتمد — والحالةُ لم تتغيّر"


def test_a_separate_approver_signs_it(school, coordinator, deputy, head, target_teacher):
    plan = _ready_for_approval(school, target_teacher, coordinator, deputy)

    flow.approve(plan, by=head)

    assert (plan.status, plan.approved_by) == (APPROVED, head)
    assert plan.approved_at is not None
    assert plan.self_approval_override is False


def test_self_approval_is_possible_only_by_explicit_configuration_and_is_recorded(
    school, coordinator, deputy, target_teacher
):
    """المدرسةُ الصغيرةُ قد تحتاج الجمعَ — فيكون تجاوزاً مسجّلاً لا صمتاً."""
    from core.models import AuditLog

    WorkloadGovernance.objects.create(
        school=school, approve_roles=["vice_academic"], allow_self_approval=True
    )
    plan = _ready_for_approval(school, target_teacher, coordinator, deputy)

    flow.approve(plan, by=deputy)

    assert plan.status == APPROVED and plan.self_approval_override is True
    logged = AuditLog.objects.filter(object_id=str(plan.pk))
    assert any(
        (row.changes or {}).get("event") == "workload_self_approval_override" for row in logged
    ), "التجاوزُ يُكتب في سجلّ التدقيق — وإلّا فقد معناه"


# ── البوّابة: لا اعتمادَ ببندٍ ساقط ─────────────────────────────────


def test_a_number_without_a_source_blocks_approval(
    school, coordinator, deputy, head, target_teacher
):
    """«ثمانيةَ عشرَ لأنّ الجميعَ يعرف» ليست معرفةً يقبلها النظام."""
    plan = draft(
        school,
        target_teacher,
        coordinator,
        required_weekly_periods=0,
        required_source_reference="مرجعٌ مؤقّت",
        reduction_periods=0,
        reduction_reason="",
        reduction_source="",
        reduction_source_reference="",
    )
    TeacherWorkloadPlan.objects.filter(pk=plan.pk).update(required_source_reference="")
    plan.refresh_from_db()

    flow.submit_for_review(plan, by=coordinator)
    flow.record_review(plan, by=deputy)

    with pytest.raises(ValidationError):
        flow.approve(plan, by=head)


def test_each_fact_carries_its_own_provenance(school, coordinator, target_teacher):
    """ثلاثةُ مصادرَ مختلفةٍ لثلاث حقائق — لا حقلٌ واحدٌ يجمعها."""
    plan = draft(school, target_teacher, coordinator)

    assert plan.provenance_gaps() == []

    plan.reduction_source_reference = ""
    gaps = plan.provenance_gaps()
    assert gaps and "التخفيض" in gaps[0], "نقصُ مرجعِ التخفيض لا يُخفيه وجودُ مرجعِ النصاب"


def test_a_qualification_without_a_reference_blocks_approval(
    school, coordinator, deputy, head, target_teacher, subject
):
    plan = _ready_for_approval(school, target_teacher, coordinator, deputy)
    TeacherSubjectQualification.objects.create(
        school=school,
        teacher=target_teacher,
        subject=subject,
        qualification_status=QUALIFIED,
        source="school",
        source_reference="",
        valid_from=date(2026, 9, 1),
    )

    with pytest.raises(ValidationError):
        flow.approve(plan, by=head)


def test_the_gate_reruns_at_approval_not_only_at_validate(
    school, coordinator, deputy, head, target_teacher
):
    """بين زرّ التحقّق والاعتماد قد يتغيّر الإسنادُ تحت الخطّة."""
    plan = _ready_for_approval(school, target_teacher, coordinator, deputy)
    assert flow.blocking(flow.validate(plan)) == []

    TeacherWorkloadPlan.objects.filter(pk=plan.pk).update(reduction_periods=3)
    plan.refresh_from_db()

    with pytest.raises(ValidationError):
        flow.approve(plan, by=head)


# ── التعديلُ بعد الاعتماد ───────────────────────────────────────────


def test_editing_an_approved_plan_means_a_new_version(
    school, coordinator, deputy, head, target_teacher
):
    plan = _ready_for_approval(school, target_teacher, coordinator, deputy)
    flow.approve(plan, by=head)

    nxt = flow.new_version_from(plan, by=coordinator)

    assert (nxt.plan_version, nxt.status) == (2, DRAFT)
    assert nxt.required_source_kind == FROM_PREVIOUS_PLAN
    assert nxt.required_source_plan_id == plan.pk, "النسخُ يُذكر صريحاً لا ضمناً"

    plan.refresh_from_db()
    assert plan.status == APPROVED, "القديمةُ تبقى قائمةً كما اعتُمدت"


def test_a_draft_has_no_new_version_to_derive(school, coordinator, target_teacher):
    plan = draft(school, target_teacher, coordinator)

    with pytest.raises(flow.WorkflowError):
        flow.new_version_from(plan, by=coordinator)


def test_locking_is_the_last_move(school, coordinator, deputy, head, target_teacher):
    plan = _ready_for_approval(school, target_teacher, coordinator, deputy)
    flow.approve(plan, by=head)

    flow.lock(plan, by=head)
    assert plan.status == LOCKED

    with pytest.raises(flow.WorkflowError):
        flow.lock(plan, by=head)
