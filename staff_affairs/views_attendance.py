"""شاشاتُ حضور الموظّفين (1.1) والأذونات القصيرة (1.3) — للكادر وحدَه.

العرضُ يقرأ الطلبَ ويستدعي الخدمة ويرسم؛ القواعدُ والاستعلاماتُ كلُّها في
``staff_affairs/attendance.py``، والتدقيقُ يُكتب هناك مع كلّ كتابة.
"""

from __future__ import annotations

from datetime import date
from typing import cast
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core.audit_export import log_export
from core.capabilities import capability_required
from core.export_utils import excel_to_response
from core.middleware import SchoolRequest
from core.models.school import School
from core.models.user import CustomUser

from .attendance import PermitService, PolicyError, StaffAttendanceService
from .forms import AttendanceMarkForm, PermitRequestForm, PermitReviewForm
from .models import PERMIT_TYPES


def _school(request: HttpRequest) -> School:
    """مدرسةُ الطلب — والحارسُ فوق كلّ عرضٍ هنا لا يُدخل من لا مدرسةَ له."""
    school = cast(SchoolRequest, request).school
    if school is None:
        raise Http404("لا مدرسةَ لهذا الحساب")
    return school


def _user(request: HttpRequest) -> CustomUser:
    return cast(CustomUser, request.user)


def _day(raw: str | None) -> date:
    """اليومُ من الطلب — واليومُ الحاضرُ لما غاب أو فسد أو جاوز اليوم."""
    today = timezone.localdate()
    parsed = parse_date(raw or "") if raw else None
    return parsed if parsed and parsed <= today else today


def _month(raw: str | None) -> tuple[int, int]:
    """«YYYY-MM» من حقل الشهر — والشهرُ الحاضرُ لما فسد."""
    try:
        year, month = (int(part) for part in (raw or "").split("-"))
        date(year, month, 1)
    except ValueError:
        today = timezone.localdate()
        return today.year, today.month
    return year, month


@login_required
@capability_required("staff_affairs.attendance_record")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def attendance_board(request: HttpRequest) -> HttpResponse:
    """رصدُ اليوم: الكادرُ كلُّه، وحالةُ كلٍّ بنقرة."""
    day = _day(request.GET.get("date"))
    board = StaffAttendanceService.daily_board(_school(request), day)
    return render(
        request,
        "staff_affairs/attendance_board.html",
        {"day": day, "today": timezone.localdate(), **board},
    )


@login_required
@capability_required("staff_affairs.attendance_record")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@require_POST
def attendance_mark(request: HttpRequest) -> HttpResponse:
    """نقرةُ الرصد (HTMX) — تُعيد سطرَ الموظّف نفسَه، وخطأُ السياسة فيه باسم البند."""
    form = AttendanceMarkForm(request.POST)
    if not form.is_valid():
        raise Http404("رصدٌ ناقص")
    data = form.cleaned_data
    try:
        row = StaffAttendanceService.board_row(_school(request), data["staff_id"], data["date"])
    except ObjectDoesNotExist as exc:  # موظّفٌ من غير هذه المدرسة لا يُكشف وجودُه
        raise Http404("ليس من كادر هذه المدرسة") from exc
    error = ""
    try:
        row["record"] = StaffAttendanceService.mark(
            school=_school(request),
            staff=row["staff"],
            day=data["date"],
            status=data["status"],
            check_in=data["check_in"],
            actor=_user(request),
            request=request,
        )
    except PolicyError as exc:
        error = str(exc)
    return render(
        request,
        "staff_affairs/partials/attendance_row.html",
        {**row, "day": data["date"], "error": error},
    )


@login_required
@capability_required("staff_affairs.attendance_report")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def attendance_report(request: HttpRequest) -> HttpResponse:
    """تقريرُ الشهر: جدولٌ لكلّ موظّف، وتنزيلُه Excel بالرقم الوظيفيّ."""
    year, month = _month(request.GET.get("month"))
    report = StaffAttendanceService.monthly_report(_school(request), year, month)
    return render(
        request,
        "staff_affairs/attendance_report.html",
        {"month_value": f"{year:04d}-{month:02d}", **report},
    )


@login_required
@capability_required("staff_affairs.attendance_report")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def attendance_report_xlsx(request: HttpRequest) -> HttpResponse:
    """Excel التقرير — الرقم الشخصيّ: مستور (لا يُكتب أصلاً؛ الرقمُ الوظيفيّ وحدَه)."""
    year, month = _month(request.GET.get("month"))
    report = StaffAttendanceService.monthly_report(_school(request), year, month)
    workbook = StaffAttendanceService.monthly_workbook(report)
    log_export(
        request,
        "staff_affairs.attendance_month_xlsx",
        rows=len(report["rows"]),
        object_repr=f"حضور الموظفين {year:04d}-{month:02d}",
    )
    return cast(
        HttpResponse, excel_to_response(workbook, f"حضور_الموظفين_{year:04d}_{month:02d}.xlsx")
    )


@login_required
@capability_required("staff_affairs.own_permits")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def my_permits(request: HttpRequest) -> HttpResponse:
    """طلبُ الموظّف إذناً لنفسه (نموذج 02)، وطلباتُه ورصيدُ شهره."""
    form = PermitRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            PermitService.submit(
                school=_school(request),
                staff=_user(request),
                permit_type=data["permit_type"],
                day=data["date"],
                start_time=data["start_time"],
                end_time=data["end_time"],
                reason=data["reason"],
                request=request,
            )
        except PolicyError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "قُدِّم الطلب — ولا يُحتسب إلّا بعد اعتماده (البند 4.1).")
            return redirect("staff_affairs:my_permits")
    return render(
        request,
        "staff_affairs/my_permits.html",
        {
            "form": form,
            "permit_types": PERMIT_TYPES,
            "balance": PermitService.balance(
                _school(request), _user(request), timezone.localdate()
            ),
            "permits": PermitService.own_permits(_school(request), _user(request)),
        },
    )


@login_required
@capability_required("staff_affairs.permits_review")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def permit_queue(request: HttpRequest) -> HttpResponse:
    """الطلباتُ التي تنتظر مرحلةَ دور المستخدم في نموذج 02."""
    return render(
        request,
        "staff_affairs/permit_queue.html",
        {"permits": PermitService.awaiting(_school(request), _user(request))},
    )


@login_required
@capability_required("staff_affairs.permits_review")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@require_POST
def permit_review(request: HttpRequest, pk: UUID) -> HttpResponse:
    """مرحلةُ طلبٍ واحد — والخدمةُ تفحص أنّها مرحلةُ دور المستخدم."""
    form = PermitReviewForm(request.POST)
    if not form.is_valid():
        raise Http404("قرارٌ ناقص")
    try:
        permit = PermitService.pending_one(_school(request), pk)
    except ObjectDoesNotExist as exc:
        raise Http404("لا طلبَ بهذا المعرّف") from exc
    try:
        PermitService.act(
            permit,
            actor=_user(request),
            approve=form.cleaned_data["decision"] == "approve",
            reason=form.cleaned_data["rejection_reason"],
            request=request,
        )
    except PolicyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, f"سُجّل: {permit.get_stage_display()} — {permit.get_status_display()}."
        )
    return redirect("staff_affairs:permit_queue")
