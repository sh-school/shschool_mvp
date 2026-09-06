"""[WORKLOAD] شاشاتُ الخطّة: القراءةُ في مسار، والأوامرُ في مسارات.

وأهمُّ ما تحرسه هذه الاختبارات ليس أنّ الأزرار تعمل، بل أنّ الـviews **لا
تعرف** منطقَ الانتقالات: زرُّ الاعتماد لا يكتب `plan.status = APPROVED`، ولو
كتبها لمرّت رحلةُ النجاح ولمرّت معها خطّةٌ ساقطةُ البوّابة. فرحلةُ الفشل هنا
هي الدليلُ على أنّ الشاشةَ تستدعي الخدمةَ ولا تُقلّدها.

    رحلةٌ ناجحة:  مسودّةٌ ← نصابٌ ← تخفيضٌ ← توزيعٌ ← مؤهّلٌ ← رفعٌ ← مراجعةٌ ← اعتماد
    رحلةٌ فاشلة:  البوّابةُ تمرّ، ثمّ يتغيّر الإسنادُ، ثمّ يُرفض الاعتماد
"""

import pytest
from django.urls import reverse

from academic_management import workload_workflow as flow
from academic_management.models import (
    APPROVED,
    DRAFT,
    FROM_MANUAL,
    REVIEWED,
    SUBMITTED,
    TeacherWorkloadPlan,
)
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


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
def target_teacher(school):
    return actor(school, "teacher", "المعلّم صاحب الخطّة")


@pytest.fixture
def subject(school):
    from operations.models import Subject

    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


def assign(school, teacher, subject, *, periods, grade="G7", level="prep"):
    """إسنادُ مادّةٍ لشعبة — الواقعُ الذي تُقاس الخطّةُ عليه."""
    from operations.models import SubjectClassAssignment

    group = ClassGroupFactory(school=school, grade=grade, level_type=level, academic_year=YEAR)
    return SubjectClassAssignment.objects.create(
        school=school,
        academic_year=YEAR,
        teacher=teacher,
        class_group=group,
        subject=subject,
        weekly_periods=periods,
        is_active=True,
    )


def a_draft(school, teacher, by, **kw):
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
    return flow.open_draft(school, teacher, YEAR, by=by, **fields)


# ══════════════════════════════════════════════════════════════════════
#  الفصلُ بين القراءة والأمر
# ══════════════════════════════════════════════════════════════════════


def test_the_observatory_stays_read_only(client_as, coordinator):
    """`/workload/` مرصدٌ — ولا يقبل أمراً."""
    response = client_as(coordinator).post(reverse("academic_management:workload"))

    assert (
        response.status_code in (403, 405) or response.status_code == 200
    ), "المرصدُ لا يُنشئ شيئاً بالـPOST"
    assert TeacherWorkloadPlan.objects.count() == 0


def test_a_command_refuses_get(client_as, coordinator, target_teacher):
    url = reverse("academic_management:open_draft", args=[target_teacher.pk])

    assert client_as(coordinator).get(url).status_code == 405


def test_a_missing_capability_is_403(client_as, teacher_user, coordinator, target_teacher, school):
    plan = a_draft(school, target_teacher, coordinator)
    url = reverse("academic_management:edit_head", args=[plan.pk])

    response = client_as(teacher_user).post(url, {"required_weekly_periods": 20})

    assert response.status_code == 403


def test_a_plan_from_another_school_is_404_not_403(client_as, coordinator, school):
    """`403` تُخبر السائلَ أنّها موجودة — وهذا وحدَه تسريب."""
    other = SchoolFactory(code="OTHER")
    stranger = actor(other, "teacher", "معلّمٌ في مدرسةٍ أخرى")
    outsider_admin = actor(other, "coordinator", "منسّقٌ هناك")
    foreign = a_draft(other, stranger, outsider_admin)

    response = client_as(coordinator).get(
        reverse("academic_management:plan_editor", args=[foreign.pk])
    )

    assert response.status_code == 404


def test_an_illegal_transition_is_a_message_not_a_500(
    client_as, head, coordinator, school, target_teacher
):
    plan = a_draft(school, target_teacher, coordinator)

    response = client_as(head).post(
        reverse("academic_management:approve_plan", args=[plan.pk]), follow=True
    )

    assert response.status_code == 200
    assert "لا انتقالَ" in response.content.decode()
    plan.refresh_from_db()
    assert plan.status == DRAFT


def test_a_stale_write_is_refused_not_merged(client_as, coordinator, school, target_teacher):
    """آخرُ من يضغط «حفظ» ليس أحقَّ بالحقيقة من زميلٍ سبقه."""
    plan = a_draft(school, target_teacher, coordinator)
    seen = plan.updated_at.isoformat()

    plan.required_weekly_periods = 20
    plan.save()

    response = client_as(coordinator).post(
        reverse("academic_management:edit_head", args=[plan.pk]),
        {
            "seen_at": seen,
            "required_weekly_periods": 24,
            "required_source_kind": FROM_MANUAL,
            "required_source_reference": "تعميم 7 / 2026",
            "required_policy_key": "",
        },
    )

    assert response.status_code == 409
    plan.refresh_from_db()
    assert plan.required_weekly_periods == 20, "لم يُطمَس ما كتبه غيرُه"


def test_the_assignment_cannot_be_edited_from_the_plan_editor(
    client_as, coordinator, school, target_teacher, subject
):
    """معالجةُ فرقِ الإسناد عمليّةٌ مستقلّة — ولا مدخلَ لها من هنا."""
    from operations.models import SubjectClassAssignment

    plan = a_draft(school, target_teacher, coordinator)
    assign(school, target_teacher, subject, periods=14)

    body = (
        client_as(coordinator)
        .get(reverse("academic_management:plan_editor", args=[plan.pk]))
        .content.decode()
    )

    assert "14 / 16" in body, "الإسنادُ معروضٌ"
    assert 'name="weekly_periods"' not in body, "ولا حقلَ يُحرّر الإسناد"
    assert "يُعالَج فرقُ الإسناد من شاشة إسناد الموادّ" in body, "ويُقال أين يُعالَج"
    assert SubjectClassAssignment.objects.count() == 1


# ══════════════════════════════════════════════════════════════════════
#  البوّابة بنداً بنداً
# ══════════════════════════════════════════════════════════════════════


def test_the_gate_reports_item_by_item_not_one_verdict(
    client_as, coordinator, school, target_teacher, subject
):
    plan = a_draft(school, target_teacher, coordinator)
    assign(school, target_teacher, subject, periods=14)

    body = (
        client_as(coordinator)
        .get(reverse("academic_management:validate_plan", args=[plan.pk]))
        .content.decode()
    )

    assert "كلُّ رقمٍ يعرف من أين جاء" in body
    assert "المُسنَدُ فعلاً يساوي الهدفَ التدريسيّ" in body
    assert "14 مقابل 16" in body, "الرقمُ الذي يدلّ على الطريق، لا «غير صالحة»"


# ══════════════════════════════════════════════════════════════════════
#  منظورُ المراجع
# ══════════════════════════════════════════════════════════════════════


def test_the_reviewer_sees_the_previous_version_beside_the_proposed_one(
    client_as, coordinator, deputy, head, school, target_teacher, subject
):
    assign(school, target_teacher, subject, periods=16)
    first = a_draft(school, target_teacher, coordinator)
    flow.submit_for_review(first, by=coordinator)
    flow.record_review(first, by=deputy)
    flow.approve(first, by=head)

    second = flow.new_version_from(first, by=coordinator)
    second.reduction_periods = 4
    second.save()

    body = (
        client_as(deputy)
        .get(reverse("academic_management:plan_review", args=[second.pk]))
        .content.decode()
    )

    assert "v1 معتمدة" in body and "v2 مقترحة" in body
    assert "الهدف التدريسيّ" in body
    assert "16" in body and "12" in body, "الهدفُ قبلَ التخفيض وبعدَه معروضان"


# ══════════════════════════════════════════════════════════════════════
#  الرحلةُ الكاملة — من مسودّةٍ إلى اعتماد
# ══════════════════════════════════════════════════════════════════════


def test_a_whole_journey_from_draft_to_approved(
    client_as, coordinator, deputy, head, school, target_teacher, subject
):
    """رحلةٌ واحدةٌ حقيقيّةٌ عبر الشاشات — لا استدعاءٌ مباشرٌ للخدمة."""
    assign(school, target_teacher, subject, periods=10, grade="G7", level="prep")
    assign(school, target_teacher, subject, periods=6, grade="G10", level="sec")

    drafter = client_as(coordinator)

    # ١. فتحُ المسودّة
    drafter.post(
        reverse("academic_management:open_draft", args=[target_teacher.pk]), {"year": YEAR}
    )
    plan = TeacherWorkloadPlan.objects.get(teacher=target_teacher, academic_year=YEAR)
    assert plan.status == DRAFT and plan.plan_version == 1

    # ٢. النصابُ ومنبعُه
    drafter.post(
        reverse("academic_management:edit_head", args=[plan.pk]),
        {
            "seen_at": plan.updated_at.isoformat(),
            "required_weekly_periods": 18,
            "required_source_kind": FROM_MANUAL,
            "required_source_reference": "تعميم 7 / 2026",
            "required_policy_key": "",
        },
    )
    plan.refresh_from_db()
    assert plan.required_weekly_periods == 18

    # ٣. التخفيضُ ومنبعُه
    drafter.post(
        reverse("academic_management:edit_reduction", args=[plan.pk]),
        {
            "seen_at": plan.updated_at.isoformat(),
            "reduction_periods": 2,
            "reduction_reason": "منسّق مادّة",
            "reduction_source": "school",
            "reduction_source_reference": "محضر 12",
        },
    )
    plan.refresh_from_db()
    assert plan.teaching_target == 16, "الهدفُ محسوبٌ لا مكتوب"

    # ٤. التوزيعُ حسب المرحلة
    for level, periods in (("prep", 10), ("sec", 6)):
        drafter.post(
            reverse("academic_management:add_allocation", args=[plan.pk]),
            {"level_type": level, "target_periods": periods, "notes": ""},
        )
    assert sum(a.target_periods for a in plan.allocations.all()) == 16

    # ٥. البوّابةُ قبل الرفع
    assert flow.blocking(flow.validate(plan)) == []

    # ٦. الرفعُ ثمّ المراجعةُ ثمّ الاعتماد — كلٌّ من صاحبه
    drafter.post(reverse("academic_management:submit_plan", args=[plan.pk]))
    plan.refresh_from_db()
    assert plan.status == SUBMITTED and plan.submitted_by == coordinator

    client_as(deputy).post(
        reverse("academic_management:review_plan", args=[plan.pk]), {"comment": "مطابقٌ للتعميم"}
    )
    plan.refresh_from_db()
    assert plan.status == REVIEWED and plan.reviewed_by == deputy

    client_as(head).post(reverse("academic_management:approve_plan", args=[plan.pk]))
    plan.refresh_from_db()

    assert plan.status == APPROVED and plan.approved_by == head
    assert plan.self_approval_override is False
    assert plan.validated_assignment_count == 2
    assert plan.validated_assignment_periods == 16
    assert plan.validation_fingerprint, "بصمةُ ما فُحص محفوظةٌ لحظةَ التوقيع"
    assert flow.has_diverged(plan) is False


# ══════════════════════════════════════════════════════════════════════
#  الرحلةُ الفاشلة — تغيّر الإسنادُ بين التحقّق والاعتماد
# ══════════════════════════════════════════════════════════════════════


def test_an_assignment_changed_after_validate_blocks_the_approval(
    client_as, coordinator, deputy, head, school, target_teacher, subject
):
    """البوّابةُ تُعاد عند التوقيع — ولو كانت قد مرّت قبل دقيقة.

    ولو كان الـview يكتب `status = APPROVED` بيده لمرّت هذه الخطّةُ ساقطةَ
    البوّابة. فهذا الاختبارُ هو الدليلُ على أنّ الشاشةَ تستدعي الخدمةَ ولا
    تُقلّدها.
    """
    from operations.models import SubjectClassAssignment

    row = assign(school, target_teacher, subject, periods=16)
    plan = a_draft(school, target_teacher, coordinator)

    # التحقّقُ يمرّ الآن — والشاشةُ تقول ذلك
    body = (
        client_as(coordinator)
        .get(reverse("academic_management:validate_plan", args=[plan.pk]))
        .content.decode()
    )
    assert "16 مقابل 16" in body

    client_as(coordinator).post(reverse("academic_management:submit_plan", args=[plan.pk]))
    client_as(deputy).post(reverse("academic_management:review_plan", args=[plan.pk]))

    # ثمّ يتغيّر الواقعُ من تحت الخطّة
    SubjectClassAssignment.objects.filter(pk=row.pk).update(weekly_periods=14)

    response = client_as(head).post(
        reverse("academic_management:approve_plan", args=[plan.pk]), follow=True
    )

    plan.refresh_from_db()
    assert plan.status == REVIEWED, "لم تُعتمد — والبوّابةُ أُعيدت"
    assert plan.approved_at is None and not plan.validation_fingerprint
    assert "المُسنَدُ فعلاً يساوي الهدفَ التدريسيّ" in response.content.decode()


def test_a_divergence_after_approval_is_named_a_divergence_not_an_error(
    client_as, coordinator, deputy, head, school, target_teacher, subject
):
    """خطّةٌ صحّت ثمّ تباعد عنها الواقعُ ليست خطّةً وُلدت خاطئة."""
    from operations.models import SubjectClassAssignment

    row = assign(school, target_teacher, subject, periods=16)
    plan = a_draft(school, target_teacher, coordinator)
    flow.submit_for_review(plan, by=coordinator)
    flow.record_review(plan, by=deputy)
    flow.approve(plan, by=head)

    SubjectClassAssignment.objects.filter(pk=row.pk).update(weekly_periods=14)

    assert flow.has_diverged(plan) is True

    body = (
        client_as(head)
        .get(
            reverse("academic_management:teacher_workload", args=[target_teacher.pk])
            + f"?year={YEAR}"
        )
        .content.decode()
    )

    assert "تباعد الإسنادُ بعد الاعتماد" in body
    assert "ما فُحص عند الاعتماد" in body and "16" in body, "وما فُحص وقتَها معروضٌ كما كان"
