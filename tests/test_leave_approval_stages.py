"""مراحلُ اعتماد الإجازة (W-20261001-009) — نموذج 01 في ``07_forms_catalog.md``.

التسلسلُ: المسؤول المباشر والنائب المسؤول ← السكرتارية (تُثبت الرصيد) ← مدير المدرسة
(«الاعتماد النهائي؛ الطلب لا يُعتبر معتمداً إلا بتوقيعه»). ولائحة الموارد البشرية م76:
«يقدم طلباً بذلك إلى رئيسه المباشر». والمكلَّفُ بأعباء المدير تعريفُه افتراضٌ معلَن
(تكليفٌ صريحٌ قائم) يراجعه المالكُ عند المعاينة. أشخاصٌ اصطناعيّون بلا رقمٍ شخصيّ.
"""

import datetime as dt

import pytest
from django.utils import timezone

from core.models.access import Membership
from staff_affairs.leave_flow import LeaveFlowError, act, eligible_actors
from staff_affairs.models import LeaveBalance
from staff_affairs.services import LeaveService
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

SUN = dt.date(2026, 10, 4)
_N = {"n": 0}


def _person(school, role):
    _N["n"] += 1
    user = UserFactory(
        full_name=f"موظف اصطناعي {_N['n']}", employee_number=f"T-{900 + _N['n']:04d}"
    )
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


def _actor(school, role):
    member = (
        Membership.objects.filter(school=school, role__name=role, is_active=True)
        .select_related("user")
        .first()
    )
    return member.user if member else _person(school, role)


@pytest.fixture
def school():
    return SchoolFactory()


@pytest.fixture
def leave(school):
    """إجازةُ معلّمٍ (مسؤولُه المباشر نائبُ الشؤون الأكاديمية) وطاقمُ المراحل كاملٌ في المدرسة."""
    for role in ("principal", "vice_admin", "vice_academic", "secretary"):
        _actor(school, role)
    teacher = _person(school, "teacher")
    return LeaveService.create_leave_request(
        school=school,
        staff=teacher,
        leave_type="emergency",
        start_date=SUN,
        end_date=SUN,
        days_count=1,
        reason="ظرف عائلي",
    )


def _advance_to_principal(leave, school):
    act(leave, actor=_actor(school, "vice_academic"), approve=True)
    act(leave, actor=_actor(school, "secretary"), approve=True)
    leave.refresh_from_db()
    assert leave.stage == "principal"


def test_form01_a_new_request_starts_at_the_line_manager_box(leave):
    """نموذج 01: أوّلُ المربّعات المسؤولُ المباشر والنائب؛ ودورُه لقطةٌ يومَ التقديم (م76 لائحة)."""
    assert leave.stage == "supervisor"
    assert leave.deputy_role == "vice_academic"


def test_form01_deputy_recommends_but_cannot_approve_finally(leave, school):
    """نموذج 01: النائبُ يوصي فقط — موافقتُه تنقل الطلبَ إلى السكرتارية ولا تُعتمد."""
    act(leave, actor=_actor(school, "vice_academic"), approve=True)
    leave.refresh_from_db()
    assert (leave.status, leave.stage) == ("pending", "secretary")
    assert not LeaveBalance.objects.filter(staff=leave.staff).exists()


def test_form01_deputy_cannot_act_in_the_principals_box(leave, school):
    """نموذج 01: «لا يُعتبر معتمداً إلا بتوقيع المدير» — النائبُ يُردّ في مربّع المدير."""
    _advance_to_principal(leave, school)
    with pytest.raises(LeaveFlowError):
        act(leave, actor=_actor(school, "vice_academic"), approve=True)
    with pytest.raises(LeaveFlowError):
        act(leave, actor=_actor(school, "vice_admin"), approve=True)
    leave.refresh_from_db()
    assert leave.status == "pending"


def test_form01_principal_final_approval_moves_status_and_deducts_balance(leave, school):
    """نموذج 01: المديرُ يعتمد فتصير «معتمدة» ويُخصم الرصيد (م65: عارضة)."""
    _advance_to_principal(leave, school)
    principal = _actor(school, "principal")
    act(leave, actor=principal, approve=True)
    leave.refresh_from_db()
    assert (leave.status, leave.stage, leave.reviewed_by) == ("approved", "closed", principal)
    assert LeaveBalance.objects.get(staff=leave.staff, leave_type="emergency").used_days == 1
    assert leave.decided_on_behalf is False


def test_form01_secretary_records_the_balance_snapshot_and_cannot_reject(leave, school):
    """نموذج 01: السكرتاريةُ «تُثبت الرصيد» لقطةً ولا تقرّر (م65: 10 أيام ← المتبقّي 10)."""
    act(leave, actor=_actor(school, "vice_academic"), approve=True)
    secretary = _actor(school, "secretary")
    with pytest.raises(LeaveFlowError):
        act(leave, actor=secretary, approve=False)
    act(leave, actor=secretary, approve=True)
    leave.refresh_from_db()
    assert leave.recorded_balance_days == 10
    assert leave.secretary_by == secretary
    assert leave.secretary_at is not None


def test_form01_acting_principal_by_assignment_may_finalize_and_is_marked(leave, school):
    """نموذج 01: «المكلّف بأعباء المدير» (تكليفٌ صريحٌ قائم) كالمدير — ويُوسم القرارُ بالإنابة."""
    from staff_affairs.attendance import AssignmentService

    acting = _person(school, "vice_academic")
    today = timezone.localdate()
    AssignmentService.assign(
        school=school,
        assigner=_actor(school, "principal"),
        assignee=acting,
        start=today,
        end=today,
        reason="غيابُ المدير في مهمّة",
    )
    _advance_to_principal(leave, school)
    assert acting in eligible_actors(leave)
    act(leave, actor=acting, approve=True)
    leave.refresh_from_db()
    assert leave.status == "approved"
    assert leave.decided_on_behalf is True


def test_form01_principal_rejection_requires_a_reason(leave, school):
    """نموذج 01: «سبب الرفض» إلزاميٌّ في مربّع المدير."""
    _advance_to_principal(leave, school)
    principal = _actor(school, "principal")
    with pytest.raises(LeaveFlowError):
        act(leave, actor=principal, approve=False)
    act(leave, actor=principal, approve=False, reason="ضغطُ الحصص")
    leave.refresh_from_db()
    assert (leave.status, leave.rejected_stage) == ("rejected", "principal")
    assert not LeaveBalance.objects.filter(staff=leave.staff).exists()


def test_form01_line_manager_disapproval_closes_the_request(leave, school):
    """نموذج 01: «غير موافق» من المسؤول تُنهي الطلبَ مرفوضاً ولا تبلغ المدير."""
    act(leave, actor=_actor(school, "vice_academic"), approve=False)
    leave.refresh_from_db()
    assert (leave.status, leave.stage, leave.rejected_stage) == ("rejected", "closed", "supervisor")


def test_form01_nobody_acts_on_their_own_request(school):
    """البند 4.1 بالقياس: لا يعمل أحدٌ في طلبه هو — نائبٌ يطلب إجازةً لا يوقّع عنها."""
    for role in ("principal", "vice_admin", "secretary"):
        _actor(school, role)
    deputy = _actor(school, "vice_academic")
    own = LeaveService.create_leave_request(
        school=school,
        staff=deputy,
        leave_type="emergency",
        start_date=SUN,
        end_date=SUN,
        days_count=1,
        reason="ظرف",
    )
    assert own.deputy_role == "principal"  # مسؤولُ النائب المديرُ (LINE_MANAGER)
    assert own.stage == "secretary"  # خطوةُ المسؤول مدمجةٌ في مربّع المدير
    with pytest.raises(LeaveFlowError):
        act(own, actor=deputy, approve=True)


def test_form01_stage_order_cannot_be_skipped(leave, school):
    """نموذج 01: لا يوقّع المديرُ قبل السكرتارية — مرحلةُ الطلب لا مرحلةُ المستخدم."""
    with pytest.raises(LeaveFlowError):
        act(leave, actor=_actor(school, "principal"), approve=True)
    leave.refresh_from_db()
    assert leave.stage == "supervisor"


def test_m65_final_approval_over_the_cap_is_refused_and_stays_pending(school):
    """م65 مع المراحل: تجاوزُ العشرة يُرفض عند الاعتماد النهائيّ والطلبُ يبقى معلّقاً."""
    for role in ("principal", "vice_admin", "vice_academic", "secretary"):
        _actor(school, role)
    teacher = _person(school, "teacher")
    over = LeaveService.create_leave_request(
        school=school,
        staff=teacher,
        leave_type="emergency",
        start_date=SUN,
        end_date=SUN,
        days_count=11,
        reason="ظرف",
    )
    _advance_to_principal(over, school)
    with pytest.raises(LeaveFlowError, match="م65"):
        act(over, actor=_actor(school, "principal"), approve=True)
    over.refresh_from_db()
    assert (over.status, over.stage) == ("pending", "principal")
