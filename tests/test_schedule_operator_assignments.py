# ruff: noqa: F401  — الأجهزةُ المستورَدةُ من `test_assignment_screen` تُقرأ بأسمائها في وسائط الاختبارات
"""[CAPABILITY] مُشغِّل الجدول على شاشة الإسناد — يُدخل لكلّ الأقسام، ولا يوقفه وقفُ المنسّقين، ولا يراجع ولا يعتمد.

التذكرة SOS-20260924-1CFE، الجزء أ. يُختبَر على الشاشة الحقيقيّة (`/academic/assignments/`) بعميلٍ حقيقيّ، بأجهزة
`test_assignment_screen` نفسِها — فما يُثبَت هنا هو السلوكُ لا المصفوفةُ وحدَها (`test_capability_grants`).

    المنسّقُ              قسمُه وحدَه، ويوقفه الوقفُ                  (كما كان)
    المشغِّل (بمنحٍ فعّال)  كلُّ الأقسام، ولا يوقفه الوقف
    المشغِّل                لا يراجع خطّةً ولا يعتمدها، ولا يُعدّل ما رُفع للمراجعة، ولا يفتح مفتاحَ الوقف
    السحبُ                 يُعيده معلّماً عاديّاً فيُغلق عنه الباب
"""

import pytest

from academic_management import assignment_selectors as selectors
from academic_management.models import SUBMITTED, TeacherWorkloadPlan
from core import capability_grants as grants
from operations.models import SubjectClassAssignment
from tests.test_assignment_screen import (
    YEAR,
    a_user,
    add,
    coordinator,
    departments,
    is_paused,
    login,
    maths_teacher,
    move,
    page,
    plan_rows,
    principal,
    school,
    science_teacher,
    set_quota,
    seventh,
    subjects,
    toggle,
    vice,
)

pytestmark = pytest.mark.django_db

KEY = "schedule.operator"
REASON = "تكليفٌ بمسؤوليّة الجدول العامّ"


@pytest.fixture
def operator(db, school, principal):
    """معلّمٌ عاديٌّ (لا منسّقٌ ولا قسم) مفوَّضٌ باسمه مشغِّلاً للجدول."""
    user = a_user(school, "مشغّل الجدول", "teacher")
    grants.grant(user=user, capability=KEY, by=principal, reason=REASON)
    return type(user).objects.get(pk=user.pk)


def revoke(operator, by):
    grants.revoke(user=operator, capability=KEY, by=by, reason="انتهى التكليف")


# ── الدخول ──────────────────────────────────────────────────────────────────────


def test_a_teacher_with_the_grant_opens_the_screen_and_one_without_does_not(
    client, school, operator, maths_teacher
):
    login(client, maths_teacher, school)
    assert page(client).status_code == 403

    client.logout()
    login(client, operator, school)
    assert page(client).status_code == 200


def test_the_operator_s_flags_are_entry_only(school, operator):
    flags = selectors.caps(operator, school)

    assert flags["operator"] and flags["edit"]
    assert not flags["review"] and not flags["approve"] and not flags["toggle"]


def test_a_plain_teacher_has_no_operator_flag(school, maths_teacher):
    flags = selectors.caps(maths_teacher, school)

    assert not flags["operator"] and not flags["edit"]


# ── الإدخالُ لكلّ الأقسام ───────────────────────────────────────────────────────


def test_the_operator_enters_assignments_for_every_department(
    client,
    school,
    departments,
    operator,
    maths_teacher,
    science_teacher,
    seventh,
    subjects,
    plan_rows,
):
    login(client, operator, school)

    assert add(client, maths_teacher, seventh, subjects["MAT"]).status_code == 200
    assert add(client, science_teacher, seventh, subjects["SCI"]).status_code == 200

    assert SubjectClassAssignment.objects.filter(teacher=maths_teacher).count() == 1
    assert SubjectClassAssignment.objects.filter(teacher=science_teacher).count() == 1


def test_the_operator_opens_a_plan_by_setting_a_quota(
    client, school, departments, operator, maths_teacher, seventh, subjects, plan_rows
):
    login(client, operator, school)

    set_quota(client, maths_teacher, 5)

    assert TeacherWorkloadPlan.objects.get(teacher=maths_teacher).required_weekly_periods == 5


def test_a_coordinator_is_still_confined_to_their_department(
    client,
    school,
    departments,
    operator,
    coordinator,
    science_teacher,
    seventh,
    subjects,
    plan_rows,
):
    """المنحُ لغير المنسّق لا يوسّع المنسّقَ: يبقى قسمُه حدَّه."""
    login(client, coordinator, school)

    assert add(client, science_teacher, seventh, subjects["SCI"]).status_code == 403
    assert not SubjectClassAssignment.objects.exists()


# ── وقفُ المنسّقين ──────────────────────────────────────────────────────────────


def test_the_pause_stops_the_coordinator_but_not_the_operator(
    client,
    school,
    departments,
    operator,
    coordinator,
    vice,
    maths_teacher,
    seventh,
    subjects,
    plan_rows,
):
    login(client, vice, school)
    toggle(client, True)
    assert is_paused(school)

    login(client, coordinator, school)
    refused = add(client, maths_teacher, seventh, subjects["MAT"])
    assert "الإسنادُ موقوفٌ عن المنسّقين" in refused.content.decode()
    assert not SubjectClassAssignment.objects.exists()

    login(client, operator, school)
    assert add(client, maths_teacher, seventh, subjects["MAT"]).status_code == 200
    assert SubjectClassAssignment.objects.count() == 1


def test_the_operator_cannot_flip_the_pause_switch(client, school, operator):
    login(client, operator, school)

    assert toggle(client, True).status_code == 403
    assert not is_paused(school)
    assert "وقفُ الإسناد عن المنسّقين" not in page(client).content.decode()  # لا مفتاحَ عنده


# ── لا مراجعةَ ولا اعتماد ───────────────────────────────────────────────────────


def submitted_plan(client, school, coordinator, teacher, seventh, subjects):
    login(client, coordinator, school)
    set_quota(client, teacher, 5)
    add(client, teacher, seventh, subjects["MAT"])
    move(client, teacher, "submit")
    plan = TeacherWorkloadPlan.objects.get(teacher=teacher)
    assert plan.status == SUBMITTED
    return plan


def test_the_operator_cannot_review_return_or_approve_a_plan(
    client, school, departments, operator, coordinator, maths_teacher, seventh, subjects, plan_rows
):
    plan = submitted_plan(client, school, coordinator, maths_teacher, seventh, subjects)

    login(client, operator, school)
    for action in ("review", "return", "approve"):
        move(client, maths_teacher, action, comment="محاولةٌ من المشغِّل")
        plan.refresh_from_db()
        assert plan.status == SUBMITTED, action
        assert plan.reviewed_by is None and plan.approved_by is None


def test_the_operator_cannot_edit_what_was_submitted_for_review(
    client, school, departments, operator, coordinator, maths_teacher, seventh, subjects, plan_rows
):
    """المسودّةُ لكلّ مُدخِل، وما رُفع للمراجعة لا يُعدَّل من تحت المراجع إلّا بيد المراجع."""
    submitted_plan(client, school, coordinator, maths_teacher, seventh, subjects)
    before = SubjectClassAssignment.objects.count()

    login(client, operator, school)
    refused = add(client, maths_teacher, seventh, subjects["SCI"])

    assert "مرفوعةٌ للمراجعة" in refused.content.decode()
    assert SubjectClassAssignment.objects.count() == before


# ── السحب ───────────────────────────────────────────────────────────────────────


def test_revoking_closes_the_screen_again(
    client, school, departments, operator, principal, maths_teacher, seventh, subjects, plan_rows
):
    login(client, operator, school)
    assert add(client, maths_teacher, seventh, subjects["MAT"]).status_code == 200

    revoke(operator, principal)

    client.logout()
    login(client, type(operator).objects.get(pk=operator.pk), school)
    assert page(client).status_code == 403
    assert add(client, maths_teacher, seventh, subjects["SCI"]).status_code == 403
    assert SubjectClassAssignment.objects.count() == 1
