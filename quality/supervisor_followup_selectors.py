"""قراءاتُ متابعة المشرف الإداريّ — كلُّها مقيَّدةٌ بالمدرسة."""

from __future__ import annotations

import datetime as dt
import uuid
from dataclasses import asdict, dataclass
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, QuerySet
from django.http import Http404

from core.academic_calendar import academic_year_for_school, academic_year_window
from core.capabilities import has_capability
from core.models import CustomUser, School
from staff_affairs.models import LeaveRequest, PermitRequest, StaffAttendance

from .supervisor_followup_indicators import INDICATORS
from .supervisor_followup_models import (
    SupervisorFollowUp,
    SupervisorFollowUpRecommendation,
)

SUPERVISOR_ROLE = "admin_supervisor"


@dataclass(frozen=True)
class AttendanceSummary:
    period_start: dt.date
    period_end: dt.date
    sick_days: int = 0
    casual_days: int = 0
    unpaid_days: int = 0
    permit_count: int = 0
    late_count: int = 0

    def as_fields(self) -> dict[str, Any]:
        return asdict(self)


def supervisors(school: School) -> QuerySet[CustomUser]:
    return (
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__is_active=True,
            memberships__role__name=SUPERVISOR_ROLE,
        )
        .distinct()
        .order_by("full_name")
    )


def get_supervisor(school: School, raw_id: str) -> CustomUser:
    try:
        key = uuid.UUID(raw_id)
    except ValueError:
        raise Http404 from None
    found = supervisors(school).filter(pk=key).first()
    if found is None:
        raise Http404
    return found


def follow_ups(school: School) -> QuerySet[SupervisorFollowUp]:
    return SupervisorFollowUp.objects.filter(school=school).select_related("supervisor", "follower")


def get_follow_up(school: School, pk: Any) -> SupervisorFollowUp:
    found = follow_ups(school).filter(pk=pk).first()
    if found is None:
        raise Http404
    return found


def readable_follow_up(school: School, user: CustomUser, pk: Any) -> SupervisorFollowUp:
    """المديرُ والنائبُ الإداريّ يقرآن الكلّ؛ والمشرفُ محفوظاتِه وحدَها؛ ومعرّفٌ غيرُ موجودٍ 404."""
    try:
        found = get_follow_up(school, pk)
    except (ValueError, ValidationError):
        raise Http404 from None
    if not has_capability(user, "quality.supervisor_followup") and (
        found.supervisor_id != user.pk or found.status != "saved"
    ):
        raise PermissionDenied
    return found


def print_context(school: School, followup: SupervisorFollowUp) -> dict[str, Any]:
    """سياقُ الورقة المطبوعة (نموذج 19)."""
    context = detail_context(school, followup)
    scores = context.pop("scores")
    context.update(
        school=school,
        followup=followup,
        year=academic_year_for_school(school, followup.follow_date),
        rows=[(n, text, scores.get(n)) for n, text in INDICATORS],
    )
    return context


def open_draft(school: School, supervisor: CustomUser) -> SupervisorFollowUp | None:
    return follow_ups(school).filter(supervisor=supervisor, status="draft").first()


def previous_saved(
    school: School,
    supervisor: CustomUser,
    on: dt.date,
    current: SupervisorFollowUp | None = None,
) -> SupervisorFollowUp | None:
    """آخرُ متابعةٍ محفوظةٍ للمشرف قبل هذه (في اليوم نفسِه تُحسم بوقت الإنشاء)."""
    before = Q(follow_date__lt=on)
    if current is not None and current.created_at:
        before |= Q(follow_date=on, created_at__lt=current.created_at)
    else:
        before |= Q(follow_date=on)
    rows = follow_ups(school).filter(before, supervisor=supervisor, status="saved")
    if current is not None:
        rows = rows.exclude(pk=current.pk)
    return rows.order_by("-follow_date", "-created_at").first()


def attendance_summary(
    school: School,
    supervisor: CustomUser,
    on: dt.date,
    previous: SupervisorFollowUp | None,
) -> AttendanceSummary:
    """الغيابُ والاستئذانُ والتأخّرُ من اليوم التالي للمتابعة السابقة (أو أوّلِ العام) إلى `on`.

    ثلاثةُ استعلاماتٍ ثابتة. أيامُ الإجازة: المتقاطعُ من أيامها مع الفترة، بحدّ `days_count`.
    """
    if previous is not None:
        start = previous.follow_date + dt.timedelta(days=1)
    else:
        window = academic_year_window(school, on)
        start = window[0] if window else on
    leaves: dict[str, int] = {"sick": 0, "emergency": 0, "unpaid": 0}
    for leave_type, first, last, days in LeaveRequest.objects.filter(
        school=school,
        staff=supervisor,
        status="approved",
        leave_type__in=list(leaves),
        start_date__lte=on,
        end_date__gte=start,
    ).values_list("leave_type", "start_date", "end_date", "days_count"):
        overlap = (min(last, on) - max(first, start)).days + 1
        leaves[leave_type] += max(0, min(days, overlap))
    permits = PermitRequest.objects.filter(
        school=school, staff=supervisor, status="approved", date__range=(start, on)
    ).count()
    lates = StaffAttendance.objects.filter(
        school=school, staff=supervisor, late_minutes__gt=0, date__range=(start, on)
    ).count()
    return AttendanceSummary(
        period_start=start,
        period_end=on,
        sick_days=leaves["sick"],
        casual_days=leaves["emergency"],
        unpaid_days=leaves["unpaid"],
        permit_count=permits,
        late_count=lates,
    )


def review_items(
    school: School,
    followup: SupervisorFollowUp | None,
    previous: SupervisorFollowUp | None,
) -> list[SupervisorFollowUpRecommendation]:
    """توصياتُ المتابعة المحفوظة السابقة، ومعها ما سبق أن تابعته هذه المتابعة."""
    wanted = Q()
    if previous is not None:
        wanted |= Q(followup=previous)
    if followup is not None:
        wanted |= Q(reviewed_in=followup)
    if not wanted:
        return []
    return list(
        SupervisorFollowUpRecommendation.objects.filter(wanted, school=school)
        .select_related("reviewed_in")
        .order_by("followup__follow_date", "order", "created_at")
    )


def list_context(school: School, *, own: CustomUser | None) -> dict[str, Any]:
    """قائمةُ المدير: كلُّ مشرفٍ وآخرُ متابعةٍ له ثمّ كلُّ المتابعات؛ وللمشرف (`own`) محفوظاتُه وحدَها."""
    rows = follow_ups(school).order_by("-follow_date", "-created_at")
    if own is not None:
        return {"can_manage": False, "history": list(rows.filter(supervisor=own, status="saved"))}
    history = list(rows)
    latest: dict[Any, SupervisorFollowUp] = {}
    for item in history:
        latest.setdefault(item.supervisor_id, item)
    return {
        "can_manage": True,
        "history": history,
        "supervisor_rows": [(user, latest.get(user.pk)) for user in supervisors(school)],
    }


def detail_context(school: School, followup: SupervisorFollowUp) -> dict[str, Any]:
    previous = previous_saved(school, followup.supervisor, followup.follow_date, followup)
    items = review_items(school, followup, previous)
    reviews = []
    for item in items:
        # حالةٌ كتبتها مسودةٌ لا تظهر قبل حفظها — إلّا داخل المسودة نفسِها.
        reviewer = item.reviewed_in
        visible = (
            reviewer is not None
            and not reviewer.is_deleted
            and (reviewer.status == "saved" or reviewer.pk == followup.pk)
        )
        reviews.append((item, item.status if visible else "pending", item.note if visible else ""))
    return {
        "reviews": reviews,
        "scores": {s.indicator_no: s for s in followup.scores.all()},
        "recommendations": list(followup.recommendations.filter(is_deleted=False)),
    }
