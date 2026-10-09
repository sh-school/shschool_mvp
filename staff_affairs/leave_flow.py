"""staff_affairs/leave_flow.py — مراحلُ اعتماد الإجازة على نسق ``PermitService`` (نموذج 01).

التسلسلُ من ``07_forms_catalog.md`` (نموذج 01): المسؤول المباشر والنائب المسؤول (بتوقيعٍ واحد
كما في نموذج 02) ← السكرتارية (تُثبت الرصيد ولا تقرّر) ← مدير المدرسة: «الاعتماد النهائي؛
الطلب لا يُعتبر معتمداً إلا بتوقيعه». فالنائبُ يوصي ولا يبلغ الاعتمادَ النهائيّ.

والمكلَّفُ بأعباء المدير **افتراضٌ معلَن**: من كلّفه المديرُ بقرارٍ صريحٍ قائمٍ (``StaffAssignment``،
م-43 من النظام الوظيفيّ) أو — عند شغور المنصب — نائبُ الشؤون الإدارية؛ وهو التعريفُ نفسُه الذي
تعتمده الأذوناتُ (``PermitService._principal_side``). يراجعه المالكُ عند معاينة 8500.

الأرصدةُ والسقوفُ تبقى في ``LeaveService.review_leave`` (007)، وهي الخطوةُ الأخيرة من هنا.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from core.models.audit import AuditLog
from core.models.user import CustomUser

from .models import LeaveBalance, LeaveRequest


class LeaveFlowError(ValueError):
    """مخالفةٌ لتسلسل الاعتماد — ورسالتُها تسمّي المرحلة."""


def initial_stage(staff: CustomUser) -> tuple[str, str]:
    """(دورُ النائب المسؤول، المرحلةُ الأولى) — من مسؤولُه المديرُ تُدمج خطوتُه في مربّع المدير."""
    from .attendance.context import PRINCIPAL, _role_of
    from .attendance.permits import deputy_role_for

    deputy_role = deputy_role_for(_role_of(staff))
    return deputy_role, ("secretary" if deputy_role in ("", PRINCIPAL) else "supervisor")


def _eligible(leave: LeaveRequest, day: Any) -> tuple[set[Any], str]:
    """(من يعمل في مرحلة الطلب الآن، الدورُ الذي تُنسب إليه المرحلة)."""
    from .attendance.context import PRINCIPAL, PRINCIPAL_DELEGATE
    from .attendance.permits import PermitService

    applicant = leave.staff_id
    side = PermitService._principal_side(day, applicant)
    if leave.stage == "supervisor":
        role = leave.deputy_role
        deputies = PermitService._available(day, role, applicant) if role else set()
        return (deputies or side), (role or PRINCIPAL)
    if leave.stage == "secretary":
        secretaries = PermitService._available(day, "secretary", applicant)
        if secretaries:
            return secretaries, "secretary"
        if not leave.deputy_role:
            # إجازةُ المدير نفسِه: لا يُثبت رصيدَه بيده.
            return day.holders(PRINCIPAL_DELEGATE) - day.absent() - {applicant}, "secretary"
        return side, "secretary"
    if leave.stage == "principal":
        if not leave.deputy_role:
            # إجازةُ المدير نفسِه: اعتمادُ رئيسه من خارج المدرسة غيرُ مُنمذَج؛ فيعمل نائبُه الإداريّ.
            return day.holders(PRINCIPAL_DELEGATE) - day.absent() - {applicant}, PRINCIPAL
        return side, PRINCIPAL
    return set(), ""


def _stage_day(school: Any) -> Any:
    from .attendance import _now
    from .attendance.context import _StageDay

    return _StageDay(school, _now())


def eligible_actors(leave: LeaveRequest) -> list[CustomUser]:
    """من يعمل في مرحلة الطلب الآن — أشخاصاً."""
    if leave.status != "pending":
        return []
    ids, _role = _eligible(leave, _stage_day(leave.school))
    return list(CustomUser.objects.filter(pk__in=ids).order_by("full_name"))


def remaining_before(leave: LeaveRequest) -> int | None:
    """المتبقّي من سقف النوع قبل هذا الطلب — ``None`` لنوعٍ لا سقفَ له."""
    from .services import LeaveService

    balance = LeaveBalance.objects.filter(
        school=leave.school,
        staff=leave.staff,
        academic_year=leave.academic_year,
        leave_type=leave.leave_type,
    ).first()
    from .leave_rules import default_total_days

    probe = balance or LeaveBalance(
        total_days=default_total_days(leave.leave_type, LeaveService.DEFAULT_ANNUAL_DAYS),
        used_days=0,
    )
    limit = LeaveService.limit_for(leave.leave_type, probe)
    return None if limit is None else max(0, limit - probe.used_days)


def _audit(actor: CustomUser, leave: LeaveRequest, changes: dict[str, Any], request: Any) -> None:
    """أثرٌ في سجلّ التدقيق بلا اسمٍ ولا رقمٍ شخصيّ."""
    AuditLog.log(  # type: ignore[no-untyped-call]
        user=actor,
        action="update",
        model_name="other",
        object_id=leave.pk,
        object_repr=f"LeaveRequest {leave.start_date:%Y-%m-%d}",
        changes=changes,
        school=leave.school,
        request=request,
    )


@transaction.atomic
def act(
    leave: LeaveRequest,
    *,
    actor: CustomUser,
    approve: bool,
    reason: str = "",
    request: HttpRequest | None = None,
) -> LeaveRequest:
    """مربّعٌ واحدٌ من نموذج 01 — تحت قفل صفّ الطلب فلا تتسابق مرحلتان.

    * المسؤول والنائب: يوافق فيمرّ إلى السكرتارية، أو لا يوافق فيُنهي الطلبَ مرفوضاً.
    * السكرتارية: تُثبت لقطةَ الرصيد ولا تقرّر (لا ترفض).
    * المدير أو المكلَّف بأعبائه: الاعتمادُ النهائيّ أو الرفضُ بسببٍ إلزاميّ — وبه وحدَه يُخصم الرصيد.
    """
    from .services import LeaveService

    locked = LeaveRequest.objects.select_for_update().get(pk=leave.pk)
    leave.status, leave.stage = locked.status, locked.stage
    if leave.status != "pending":
        raise LeaveFlowError(f"الطلبُ «{leave.get_status_display()}» — لا يُراجَع ثانيةً.")
    if actor.pk == leave.staff_id:
        raise LeaveFlowError("لا يعمل أحدٌ في طلبه هو.")
    day = _stage_day(leave.school)
    eligible, stage_role = _eligible(leave, day)
    if actor.pk not in eligible:
        raise LeaveFlowError(f"الطلبُ بانتظار «{leave.get_stage_display()}» لا دورك.")
    now = timezone.now()
    stage = leave.stage
    on_behalf = stage == "principal" and day.assignment_basis(actor) != {}

    if stage == "secretary":
        if not approve:
            raise LeaveFlowError(
                "السكرتاريةُ تُثبت الرصيدَ ولا تقرّر في الطلب (نموذج 01) — والرفضُ في مربّع المدير."
            )
        leave.secretary_by, leave.secretary_at = actor, now
        leave.recorded_balance_days = remaining_before(leave)
        leave.stage = "principal"
        leave.updated_by = actor
        leave.save(
            update_fields=[
                "secretary_by",
                "secretary_at",
                "recorded_balance_days",
                "stage",
                "updated_by",
                "updated_at",
            ]
        )
        _audit(actor, leave, {"stage": stage, "status": "pending"}, request)
        return leave

    if not approve:
        if stage == "principal" and not reason.strip():
            raise LeaveFlowError("سببُ الرفض مطلوبٌ في مربّع المدير (نموذج 01).")
        if stage == "supervisor":
            leave.supervisor_by, leave.supervisor_at = actor, now
        else:
            _sign_supervisor_if_merged(leave, actor, now)
        leave.decided_on_behalf = on_behalf
        LeaveService.review_leave(leave, "rejected", actor, reason.strip()[:500])
        leave.save(
            update_fields=["supervisor_by", "supervisor_at", "decided_on_behalf", "updated_at"]
        )
        _audit(
            actor, leave, {"stage": stage, "status": "rejected", "on_behalf": on_behalf}, request
        )
        return leave

    if stage == "supervisor":
        leave.supervisor_by, leave.supervisor_at = actor, now
        leave.stage = "secretary"
        leave.updated_by = actor
        leave.save(
            update_fields=["supervisor_by", "supervisor_at", "stage", "updated_by", "updated_at"]
        )
        _audit(actor, leave, {"stage": stage, "status": "pending"}, request)
        return leave

    # principal — الاعتمادُ النهائيّ: السقوفُ والرصيدُ في review_leave (007) وتُرفض بخطأٍ صريح.
    _sign_supervisor_if_merged(leave, actor, now)
    leave.decided_on_behalf = on_behalf
    try:
        LeaveService.review_leave(leave, "approved", actor)
    except ValueError as exc:
        raise LeaveFlowError(str(exc)) from exc
    leave.save(update_fields=["supervisor_by", "supervisor_at", "decided_on_behalf", "updated_at"])
    _audit(actor, leave, {"stage": stage, "status": "approved", "on_behalf": on_behalf}, request)
    return leave


def _sign_supervisor_if_merged(leave: LeaveRequest, actor: CustomUser, now: Any) -> None:
    """من مسؤولُه المديرُ: توقيعُ المدير يملأ مربّعَ المسؤول كذلك — الخطوةُ مدمجة."""
    if not leave.deputy_role or leave.deputy_role == "principal":
        leave.supervisor_by, leave.supervisor_at = actor, now
