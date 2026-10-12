"""الإنابةُ بالتكليف تحمل قدراتِ الوظيفة المُنَابة مدّتَها وحدَها (W-20261001-021).

المصدر: م-43 من النظام الوظيفيّ لموظفي المدارس (قرار مجلس الوزراء 32/2019): «يجوز لمدير
المدرسة ندب الموظف للقيام مؤقتاً بأعباء وظيفة أخرى داخل المدرسة … لمدة لا تجاوز عام
أكاديمي»؛ وقراراتُ المالك المباشرة في 2026-10-04: النائبان يكلّفان من تحتهما أيّاً كان دورُه،
والمنسّقُ أحدَ معلّمي قسمه، والمنقولُ كلُّ قدرات الوظيفة المُنَابة عدا إدارة المستخدمين
وإدارة النظام.

والأشخاصُ اصطناعيّون: لا رقمَ شخصيّاً، والرقمُ الوظيفيُّ «T-000n».
"""

from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from django.http import HttpResponse
from django.test import RequestFactory

import staff_affairs.attendance as attendance_module
from core.capabilities import (
    Capability,
    acting_capabilities,
    acting_transferable,
    capability,
    capability_required,
    has_capability,
)
from core.models import PermissionAuditLog
from core.models.access import Membership
from core.models.department import Department
from core.models.user import CustomUser
from core.permissions import SYSTEM_ADMIN, USER_MANAGE, get_accessible_modules
from staff_affairs.attendance import AssignmentService, PolicyError
from staff_affairs.models import StaffAssignment
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

NOW = datetime(2026, 2, 15, 12, 0)
TODAY = NOW.date()
#: قدرةٌ للمدير وحدَه (ومطوّر المنصّة): اعتمادُ خطط الأنصبة — ممّا يعطّله غيابُ المدير.
PRINCIPAL_ONLY = "workload.approve"
CLOCK = {"now": NOW}


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    from django.utils import timezone

    CLOCK["now"] = NOW
    monkeypatch.setattr(
        attendance_module,
        "_now",
        lambda: timezone.localtime(timezone.make_aware(CLOCK["now"])),
        raising=False,
    )


def _on(day: date) -> None:
    CLOCK["now"] = datetime.combine(day, NOW.time())


def _staff(school, n, role="teacher", department=None):
    user = UserFactory(full_name=f"موظف اصطناعي {n}", employee_number=f"T-{n:04d}")
    MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name=role),
        department_obj=department,
    )
    return user


def _fresh(user):
    """كائنُ مستخدمٍ جديد — كطلبٍ جديد: لا تحمل ذاكرتُه المؤقّتةُ شيئاً من قبل."""
    return CustomUser.objects.get(pk=user.pk)


def _assign(school, assigner, assignee, start=TODAY, end=TODAY, reason="غيابُ صاحب الوظيفة"):
    return AssignmentService.assign(
        school=school, assigner=assigner, assignee=assignee, start=start, end=end, reason=reason
    )


@pytest.fixture
def vice_admin(school):
    return _staff(school, 902, "vice_admin")


@pytest.fixture
def vice_academic(school):
    return _staff(school, 903, "vice_academic")


# ── المدير يكلّف النائبَ فيحمل قدراتِه مدّةَ التكليف وحدَها ─────────────────────────────────


@pytest.mark.parametrize("deputy_role", ["vice_admin", "vice_academic"])
def test_a_deputy_tasked_by_the_principal_holds_his_capabilities_only_inside_the_period(
    school, principal_user, deputy_role
):
    deputy = _staff(school, 905, deputy_role)
    start, end = TODAY + timedelta(days=1), TODAY + timedelta(days=3)
    assert not has_capability(_fresh(deputy), PRINCIPAL_ONLY)
    row = _assign(school, principal_user, deputy, start=start, end=end)
    assert row.acting_role == "principal"

    _on(TODAY)  # قبل البدء
    assert not has_capability(_fresh(deputy), PRINCIPAL_ONLY)
    for day in (start, start + timedelta(days=1), end):  # داخل المدّة بحدّيها
        _on(day)
        assert has_capability(_fresh(deputy), PRINCIPAL_ONLY), day
    _on(end + timedelta(days=1))  # بعد end_date تسقط فوراً بلا تدخّل
    assert not has_capability(_fresh(deputy), PRINCIPAL_ONLY)


def test_revoking_drops_the_capabilities_at_once(school, principal_user, vice_admin):
    row = _assign(school, principal_user, vice_admin)
    assert has_capability(_fresh(vice_admin), PRINCIPAL_ONLY)
    AssignmentService.revoke(row, actor=principal_user)
    assert not has_capability(_fresh(vice_admin), PRINCIPAL_ONLY)


def test_the_assignee_is_still_not_the_principal(school, principal_user, vice_admin):
    """الحاملُ يحمل القدرةَ لا الدورَ: دورُه الحاكمُ كما هو، فلا يصير مفتاحُ «المدير» له."""
    _assign(school, principal_user, vice_admin)
    deputy = _fresh(vice_admin)
    assert has_capability(deputy, PRINCIPAL_ONLY)
    assert deputy.get_role() == "vice_admin"
    assert not AssignmentService.is_principal(school, deputy)


def test_without_an_assignment_the_other_roles_gain_nothing(school, principal_user, vice_admin):
    other = _staff(school, 906, "teacher")
    _assign(school, principal_user, vice_admin)
    assert not has_capability(_fresh(other), PRINCIPAL_ONLY)


def test_a_capability_of_the_acting_role_is_not_an_explicit_grant(
    school, principal_user, vice_admin
):
    """`Capability.granted` منحٌ صريحٌ باسم الشخص يقرؤه `is_operator` بحرفه — لا يتلوّث بالتكليف."""
    _assign(school, principal_user, vice_admin)
    deputy = _fresh(vice_admin)
    for key in ("wings.school_wide", PRINCIPAL_ONLY):
        assert not capability(key).granted(deputy)


# ── ما لا يُنَاب ──────────────────────────────────────────────────────────────────────────


def test_user_management_and_system_administration_are_never_transferred(
    school, principal_user, vice_admin
):
    """USER_MANAGE وSYSTEM_ADMIN: قدرةٌ أعضاؤها هؤلاء وحدَهم لا تنتقل، ولا تظهر وحدةُ المستخدمين."""
    for roles in (USER_MANAGE, SYSTEM_ADMIN):
        cap = Capability("x.never", "قدرةٌ افتراضيّة", frozenset(roles))
        assert not acting_transferable(cap)
    assert acting_transferable(
        capability(PRINCIPAL_ONLY)
    )  # مجموعةُ المدير مع المطوّر ليست USER_MANAGE وحدَها
    assert PRINCIPAL_ONLY in acting_capabilities()

    _assign(school, principal_user, vice_admin)
    deputy = _fresh(vice_admin)
    assert "users" in get_accessible_modules(principal_user)
    assert "users" not in get_accessible_modules(deputy)


def test_the_schedule_generation_stays_with_the_platform_developer(
    school, principal_user, vice_admin, settings
):
    """حصرُ توليد الجدول واعتماده بمطوّر المنصّة (W-20261010-034) أقوى من الإنابة."""
    settings.SCHEDULE_DEVELOPER_ONLY = True
    _assign(school, principal_user, vice_admin)
    deputy = _fresh(vice_admin)
    for key in ("schedule.admin", "schedule.operator", "schedule.approve"):
        assert not has_capability(deputy, key)


# ── الحارسُ يقرأ التكليفَ كما تقرؤه has_capability ────────────────────────────────────────


def _guarded():
    @capability_required(PRINCIPAL_ONLY)
    def view(request):
        return HttpResponse("ok")

    return view


def _call(view, user):
    request = RequestFactory().get("/x/")
    request.user = user
    return view(request)


def test_the_screen_guard_admits_the_assignee_for_the_period_only(
    school, principal_user, vice_admin
):
    view = _guarded()
    assert _call(view, _fresh(vice_admin)).status_code == 403
    row = _assign(school, principal_user, vice_admin)
    assert _call(view, _fresh(vice_admin)).status_code == 200
    AssignmentService.revoke(row, actor=principal_user)
    assert _call(view, _fresh(vice_admin)).status_code == 403
    assert view._required_roles == tuple(capability(PRINCIPAL_ONLY).expanded_roles)


def test_the_navigation_grant_follows_the_assignment(school, principal_user, vice_admin):
    view = _guarded()
    assert view._grant is not None
    assert not view._grant(_fresh(vice_admin))
    _assign(school, principal_user, vice_admin)
    assert view._grant(_fresh(vice_admin))


# ── المنسّق يكلّف معلّماً من قسمه فقط ───────────────────────────────────────────────────────


@pytest.fixture
def departments(school):
    math = Department.objects.create(school=school, name="الرياضيات", code="math")
    science = Department.objects.create(school=school, name="العلوم", code="sci")
    return math, science


def test_a_coordinator_tasks_a_teacher_of_his_department_and_refuses_another(school, departments):
    math, science = departments
    coordinator = _staff(school, 910, "coordinator", department=math)
    math_teacher = _staff(school, 911, "teacher", department=math)
    science_teacher = _staff(school, 912, "teacher", department=science)

    row = _assign(school, coordinator, math_teacher, reason="خروجٌ لموعد رسميّ")
    assert (row.assignee, row.acting_role) == (math_teacher, "coordinator")
    with pytest.raises(PolicyError, match="معلّمي قسمه"):
        _assign(school, coordinator, science_teacher)
    candidates = set(AssignmentService.candidates(school, coordinator).values_list("pk", flat=True))
    assert candidates == {math_teacher.pk}

    assert has_capability(_fresh(math_teacher), "swap.approve")
    assert not has_capability(_fresh(science_teacher), "swap.approve")


def test_a_coordinator_sees_only_his_own_assignments_on_the_screen(school, departments):
    math, _ = departments
    coordinator = _staff(school, 910, "coordinator", department=math)
    other = _staff(school, 913, "coordinator", department=math)
    first, second = _staff(school, 911, "teacher", department=math), _staff(school, 914, "teacher")
    Membership.objects.filter(user=second).update(department_obj=math)
    _assign(school, coordinator, first)
    _assign(school, other, second)
    mine = AssignmentService.screen(school, coordinator)["current"]
    assert [row.assignee for row in mine] == [first]
    assert len(AssignmentService.screen(school)["current"]) == 2


@pytest.mark.parametrize("role", ["teacher", "secretary"])
def test_only_the_named_roles_task(school, role):
    someone = _staff(school, 920, role)
    other = _staff(school, 921, "teacher")
    with pytest.raises(PolicyError, match="لمدير المدرسة"):
        _assign(school, someone, other)


def test_each_deputy_tasks_everyone_under_him_whatever_the_role(school, vice_admin, vice_academic):
    teacher = _staff(school, 930, "teacher")
    librarian = _staff(school, 931, "librarian")
    supervisor = _staff(school, 932, "admin_supervisor")
    assert _assign(school, vice_academic, teacher).acting_role == "vice_academic"
    assert _assign(school, vice_academic, librarian).acting_role == "vice_academic"
    assert _assign(school, vice_admin, supervisor).acting_role == "vice_admin"
    with pytest.raises(PolicyError, match="تحت مسؤوليته"):
        _assign(school, vice_academic, supervisor)  # مسؤولُه المباشرُ النائبُ الإداريّ
    with pytest.raises(PolicyError, match="تحت مسؤوليته"):
        _assign(school, vice_admin, teacher)


# ── الحدودُ: 365 يوماً ومتداخل ورجعيّ ───────────────────────────────────────────────────────


def test_an_assignment_beyond_365_days_overlapping_or_retroactive_is_refused(
    school, principal_user, vice_admin
):
    with pytest.raises(PolicyError, match="رجعيّ"):
        _assign(school, principal_user, vice_admin, start=TODAY - timedelta(days=1))
    with pytest.raises(PolicyError, match="عاماً"):
        _assign(school, principal_user, vice_admin, end=TODAY + timedelta(days=365))
    ok = _assign(school, principal_user, vice_admin, end=TODAY + timedelta(days=364))
    assert (ok.end_date - ok.start_date).days + 1 == 365

    with pytest.raises(PolicyError, match="يتداخل"):
        _assign(
            school,
            principal_user,
            vice_admin,
            start=TODAY + timedelta(days=10),
            end=TODAY + timedelta(days=20),
        )
    assert StaffAssignment.objects.filter(assignee=vice_admin).count() == 1


def test_repeating_the_same_decision_makes_neither_a_second_row_nor_a_second_trail(
    school, principal_user, vice_admin
):
    first = _assign(school, principal_user, vice_admin)
    again = _assign(school, principal_user, vice_admin)
    assert again.pk == first.pk
    assert PermissionAuditLog.objects.filter(action="acting_assigned").count() == 1


def test_a_revoked_period_can_be_tasked_again(school, principal_user, vice_admin):
    row = _assign(school, principal_user, vice_admin)
    AssignmentService.revoke(row, actor=principal_user)
    assert _assign(school, principal_user, vice_admin).pk != row.pk


def test_the_reason_is_mandatory(school, principal_user, vice_admin):
    with pytest.raises(PolicyError, match="سببُ"):
        _assign(school, principal_user, vice_admin, reason="  ")


# ── التدقيق ────────────────────────────────────────────────────────────────────────────────


def test_assigning_and_revoking_are_each_written_to_the_permission_audit_log(
    school, principal_user, vice_admin
):
    end = TODAY + timedelta(days=2)
    row = _assign(school, principal_user, vice_admin, end=end, reason="مهمّةٌ خارج المدرسة")
    AssignmentService.revoke(row, actor=principal_user)

    trail = list(PermissionAuditLog.objects.order_by("created_at"))
    assert [t.action for t in trail] == ["acting_assigned", "acting_revoked"]
    assigned, revoked = trail
    assert (assigned.actor, assigned.target, assigned.school) == (
        principal_user,
        vice_admin,
        school,
    )
    assert assigned.details == {
        "assignment": str(row.pk),
        "acting_role": "principal",
        "start": f"{TODAY:%Y-%m-%d}",
        "end": f"{end:%Y-%m-%d}",
        "reason_given": True,
    }
    assert (revoked.actor, revoked.target) == (principal_user, vice_admin)
    assert "مهمّةٌ" not in str(assigned.details)  # نصُّ السبب يبقى في سجلّ التكليف لا في السجلّ الثابت


def test_the_coordinator_decision_is_audited_too(school, departments):
    math, _ = departments
    coordinator = _staff(school, 910, "coordinator", department=math)
    teacher = _staff(school, 911, "teacher", department=math)
    row = _assign(school, coordinator, teacher)
    AssignmentService.revoke(row, actor=coordinator)
    assert list(
        PermissionAuditLog.objects.order_by("created_at").values_list("action", flat=True)
    ) == [
        "acting_assigned",
        "acting_revoked",
    ]


def test_only_the_assigner_or_the_principal_revokes(
    school, principal_user, vice_admin, vice_academic
):
    teacher = _staff(school, 930, "teacher")
    row = _assign(school, vice_academic, teacher)
    with pytest.raises(PolicyError, match="يرفع"):
        AssignmentService.revoke(row, actor=vice_admin)
    AssignmentService.revoke(row, actor=principal_user)
    row.refresh_from_db()
    assert row.revoked_by == principal_user
