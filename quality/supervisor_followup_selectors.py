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

# قراءةٌ من طبقة القراءة: يستدعيها العرضُ من هنا لا من ملفّها.
from .supervisor_followup_evidence import indicator_evidence as indicator_evidence
from .supervisor_followup_indicators import DEFAULT_CODE, FORMS, FollowUpForm
from .supervisor_followup_models import (
    FINAL_STATUSES,
    SupervisorFollowUp,
    SupervisorFollowUpRecommendation,
)


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


def get_form(code: str) -> FollowUpForm:
    """تعريفُ الاستمارة برقمها (الفارغُ نموذج 19)؛ ورقمٌ مجهولٌ 404."""
    found = FORMS.get(code or DEFAULT_CODE)
    if found is None:
        raise Http404
    return found


def supervisors(school: School, code: str = DEFAULT_CODE) -> QuerySet[CustomUser]:
    """موظّفو دور الاستمارة وحدَه بعضويةٍ فعّالة."""
    return (
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__is_active=True,
            memberships__role__name=get_form(code).role,
        )
        .distinct()
        .order_by("full_name")
    )


def get_supervisor(school: School, raw_id: str, code: str = DEFAULT_CODE) -> CustomUser:
    try:
        key = uuid.UUID(raw_id)
    except ValueError:
        raise Http404 from None
    found = supervisors(school, code).filter(pk=key).first()
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
    """المديرُ والنائبُ الإداريّ يقرآن الكلّ؛ والمشرفُ غيرَ مسودّاتِه؛ ومعرّفٌ غيرُ موجودٍ 404."""
    try:
        found = get_follow_up(school, pk)
    except (ValueError, ValidationError):
        raise Http404 from None
    if not has_capability(user, "quality.supervisor_followup") and (
        found.supervisor_id != user.pk or found.status not in FINAL_STATUSES
    ):
        raise PermissionDenied
    return found


def print_context(school: School, followup: SupervisorFollowUp) -> dict[str, Any]:
    """سياقُ الورقة المطبوعة لاستمارة المتابعة."""
    context = detail_context(school, followup)
    scores = context.pop("scores")
    context.update(
        school=school,
        followup=followup,
        form=followup.form,
        year=academic_year_for_school(school, followup.follow_date),
        rows=[(n, text, scores.get(n)) for n, text in followup.form.indicators],
        signatures=signature_stamps(followup),
    )
    return context


def signature_stamps(followup: SupervisorFollowUp) -> dict[str, dict[str, str] | None]:
    """خانتا التوقيع: الاسمُ وحدَه (D-221م) — المتابِعُ بعد الإرسال، والمشرفُ بعد إقراره."""
    sent = followup.status in ("sent", "acknowledged")
    return {
        "follower": {"name": followup.follower.full_name} if sent else None,
        "supervisor": {"name": followup.supervisor.full_name} if followup.is_locked else None,
    }


def open_draft(
    school: School, supervisor: CustomUser, code: str = DEFAULT_CODE
) -> SupervisorFollowUp | None:
    rows = follow_ups(school).filter(supervisor=supervisor, status="draft", form_code=code)
    return rows.first()


def previous_saved(
    school: School,
    supervisor: CustomUser,
    on: dt.date,
    current: SupervisorFollowUp | None = None,
    code: str = DEFAULT_CODE,
) -> SupervisorFollowUp | None:
    """آخرُ متابعةٍ محفوظةٍ للموظّف من الاستمارة نفسِها قبل هذه (في اليوم نفسِه تُحسم بوقت الإنشاء)."""
    before = Q(follow_date__lt=on)
    if current is not None and current.created_at:
        before |= Q(follow_date=on, created_at__lt=current.created_at)
    else:
        before |= Q(follow_date=on)
    if current is not None:
        code = current.form_code
    rows = follow_ups(school).filter(
        before, supervisor=supervisor, status__in=FINAL_STATUSES, form_code=code
    )
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


def list_context(school: School, *, own: CustomUser | None, code: str = "") -> dict[str, Any]:
    """قائمةُ المدير لاستمارةٍ واحدة: كلُّ موظّفٍ وآخرُ متابعةٍ له ثمّ متابعاتُها؛ وللموظّف (`own`) محفوظاتُه وحدَها."""
    rows = follow_ups(school).order_by("-follow_date", "-created_at")
    if own is not None:
        mine = list(rows.filter(supervisor=own, status__in=FINAL_STATUSES))
        # عنوانُ القائمة من استمارة أحدث متابعاته، وإلا فمن دوره.
        if mine:
            form = mine[0].form
        else:
            role = str(own.get_role())
            form = next((f for f in FORMS.values() if f.role == role), FORMS[DEFAULT_CODE])
        return {"can_manage": False, "form": form, "history": mine}
    form = get_form(code)
    history = list(rows.filter(form_code=form.code))
    latest: dict[Any, SupervisorFollowUp] = {}
    for item in history:
        latest.setdefault(item.supervisor_id, item)
    staff = supervisors(school, form.code)
    return {
        "can_manage": True,
        "form": form,
        "forms": list(FORMS.values()),
        "history": history,
        "supervisor_rows": [(user, latest.get(user.pk)) for user in staff],
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
            and (reviewer.status in FINAL_STATUSES or reviewer.pk == followup.pk)
        )
        reviews.append((item, item.status if visible else "pending", item.note if visible else ""))
    return {
        "reviews": reviews,
        "scores": {s.indicator_no: s for s in followup.scores.all()},
        "recommendations": list(followup.recommendations.filter(is_deleted=False)),
    }
