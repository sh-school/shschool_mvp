"""لوحةُ المعلّم: كلُّ بلاطةٍ وعدّادٍ يظهر بقدرةٍ لا باسم الدور (W-20261010-043، D-335م وD-171م).

الحكمُ لكلّ بلاطة: تظهر لمن تملك قدرةَ الشاشة التي تفتحها (حارسُ العرض نفسُه)، فلا يرى
المتخصّصُ ولا المساعدُ زرّاً يردّه بـ403. والعدّاداتُ تعدّ ما تفتحه نقرتُها لمن يملك قدرتها.
"""

import pytest

from core.capabilities import has_capability
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

TEACHER_LIKE_ROLES = [
    "teacher",
    "coordinator",
    "ese_teacher",
    "e_projects_coordinator",
    "specialist",
    "teacher_assistant",
    "ese_assistant",
]

# وصفُ البلاطة (فريدٌ في اللوحة لا في القائمة الجانبيّة) ← قدرةُ الشاشة التي تفتحها.
TILE_CAPABILITY = {
    "مراجعةٌ واعتماد": ("swap.approve", "coordinator"),
    "تعيين البدلاء": ("operations.reports", "coordinator"),
    "حصصُ اليوم وتسجيلُ حضور الطلبة": ("schedule.day", None),
    "حصصي هذا الأسبوع": ("schedule.weekly", None),
    "جداولُ كلّ المعلّمين": ("schedule.browse", None),
    "تسجيلُ مخالفةٍ لطالب": ("behavior.record", None),
    "إدخال الدرجات": ("assessments.view_results", None),
    "تبديلُ حصّةٍ مع زميل": ("swap.request", "teacher"),
}

# عدّادات المنسّق ← قدرتها.
KPI_CAPABILITY = {
    "تبديلاتٌ تنتظر اعتمادك": "swap.approve",
    "تعويضاتٌ معلّقة": "compensatory.approve",
    "معلّمون غائبون اليوم": "operations.reports",
}


@pytest.fixture(autouse=True)
def real_schedule(monkeypatch):
    """الجدولُ الفعليّ لا المؤقّت: المؤقّتُ يخفي حصصي والتبديلَ كلَّهما بحكمٍ آخر (D-227م)."""
    from operations.services import provisional_session

    monkeypatch.setattr(provisional_session, "enabled", lambda school=None: False)


def _dash(client_as, school, role_name):
    """يرسم قالبَ اللوحة مباشرةً بسياق الدور: المتخصّصُ لا يبلغ `/dashboard/` أصلاً (لا قدرةَ dashboard.open)
    لكنّ القالبَ مشتركٌ ويجب ألّا يعرض له ما لا يفتحه."""
    from django.template.loader import render_to_string
    from django.test import RequestFactory
    from django.utils import timezone

    from core.dashboard_presentation import present
    from core.dashboard_selectors import get_teacher_ctx

    user = UserFactory(full_name="مستخدمُ اختبار")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    today = timezone.localdate()
    ctx = {"today": today, "school": school, **get_teacher_ctx(user, school, today, role_name)}
    ctx.update(present(ctx))
    request = RequestFactory().get("/dashboard/")
    request.user = user
    request.school = school
    return user, render_to_string("dashboard/roles/teacher.html", ctx, request=request)


@pytest.mark.parametrize("role_name", TEACHER_LIKE_ROLES)
def test_every_tile_shows_exactly_to_whoever_holds_its_capability(client_as, school, role_name):
    user, body = _dash(client_as, school, role_name)
    is_coordinator_view = role_name == "coordinator"

    for desc, (cap, only_view) in TILE_CAPABILITY.items():
        # بلاطتا الاعتماد والغياب في عرض المنسّق وحدَه، وطلبُ التبديل في عرض غيره.
        if only_view == "coordinator" and not is_coordinator_view:
            assert desc not in body
        elif only_view == "teacher" and is_coordinator_view:
            assert desc not in body
        else:
            assert (desc in body) is has_capability(user, cap), (role_name, desc, cap)


def test_a_specialist_sees_no_action_tile_it_cannot_open(client_as, school):
    """المتخصّصُ لا يملك قدرةَ تبديلٍ ولا تقييمٍ ولا سلوكٍ ولا رصد: لا بلاطةَ في إجراءاته."""
    _, body = _dash(client_as, school, "specialist")

    for desc in TILE_CAPABILITY:
        assert desc not in body
    assert "تبديلاتٌ تنتظر ردّك" not in body


def test_the_specialist_pending_swap_counter_is_zero_even_with_a_pending_request(
    school, build_swap_for
):
    """عدّادُ «تنتظر ردّك» بقدرة swap.respond: من لا يملكها لا يُعدّ له ما لا يفتحه."""
    from core.dashboard_selectors import get_teacher_ctx

    user, today = build_swap_for("specialist")

    assert get_teacher_ctx(user, school, today, "specialist")["my_pending_swaps"] == 0


def test_the_teacher_pending_swap_counter_still_counts(school, build_swap_for):
    from core.dashboard_selectors import get_teacher_ctx

    user, today = build_swap_for("teacher")

    assert get_teacher_ctx(user, school, today, "teacher")["my_pending_swaps"] == 1


def test_the_coordinator_sees_all_three_counters(client_as, school):
    user, body = _dash(client_as, school, "coordinator")

    for label, cap in KPI_CAPABILITY.items():
        assert has_capability(user, cap)
        assert label in body


@pytest.mark.parametrize("role_name", [r for r in TEACHER_LIKE_ROLES if r != "coordinator"])
def test_no_non_coordinator_role_sees_a_coordinator_counter(client_as, school, role_name):
    _, body = _dash(client_as, school, role_name)

    for label in KPI_CAPABILITY:
        assert label not in body


def test_the_general_schedule_link_follows_the_browse_capability(client_as, school):
    """«الجدول العامّ» بقدرة schedule.browse لا بعضويّة مجموعة أدوار في الشيفرة."""
    coordinator, coordinator_body = _dash(client_as, school, "coordinator")
    teacher, teacher_body = _dash(client_as, school, "teacher")

    assert has_capability(coordinator, "schedule.browse")
    assert "جداولُ كلّ المعلّمين" in coordinator_body
    assert not has_capability(teacher, "schedule.browse")
    assert "جداولُ كلّ المعلّمين" not in teacher_body


@pytest.fixture
def build_swap_for(school):
    """طلبُ تبديلٍ ينتظر ردَّ المستخدم (الطرف ب) في حالة pending_b."""
    import datetime as dt

    from core.academic_calendar import academic_year_for_school
    from operations.models import ScheduleSlot, TeacherSwap
    from tests.conftest import ClassGroupFactory

    sunday = dt.date(2026, 9, 20)

    def _slot(teacher, group, period):
        return ScheduleSlot.objects.create(
            school=school,
            teacher=teacher,
            class_group=group,
            day_of_week=0,
            period_number=period,
            start_time=dt.time(6 + period, 0),
            end_time=dt.time(6 + period, 45),
            academic_year=academic_year_for_school(school),
        )

    def _build(role_name):
        user = UserFactory(full_name="مستخدمُ اختبار")
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
        other = UserFactory(full_name="المعلّمُ أ")
        group = ClassGroupFactory(school=school)
        TeacherSwap.objects.create(
            school=school,
            teacher_a=other,
            teacher_b=user,
            slot_a=_slot(other, group, 1),
            slot_b=_slot(user, group, 2),
            swap_date_a=sunday,
            swap_date_b=sunday,
            status="pending_b",
        )
        return user, sunday

    return _build
