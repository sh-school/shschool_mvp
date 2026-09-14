"""شاشاتُ حضور الموظّفين (1.1) والأذونات القصيرة (1.3) — للكادر وحدَه.

العرضُ يقرأ الطلبَ ويستدعي الخدمة ويرسم؛ القواعدُ والاستعلاماتُ كلُّها في
``staff_affairs/attendance.py``، والتدقيقُ يُكتب هناك مع كلّ كتابة.
"""

from __future__ import annotations

from datetime import date

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils import timezone
from django.utils.dateparse import parse_date
from django.views.decorators.http import require_POST

from core.audit_export import log_export
from core.capabilities import capability_required
from core.export_utils import excel_to_response

from .attendance import PermitService, PolicyError, StaffAttendanceService
from .forms import AttendanceMarkForm, PermitRequestForm, PermitReviewForm
from .models import PERMIT_TYPES


def _day(raw) -> date:
    """اليومُ من الطلب — واليومُ الحاضرُ لما غاب أو فسد أو جاوز اليوم."""
    today = timezone.localdate()
    parsed = parse_date(raw or "") if raw else None
    return parsed if parsed and parsed <= today else today


def _month(raw) -> tuple[int, int]:
    """«YYYY-MM» من حقل الشهر — والشهرُ الحاضرُ لما فسد."""
    try:
        year, month = (int(part) for part in (raw or "").split("-"))
        date(year, month, 1)
    except ValueError:
        today = timezone.localdate()
        return today.year, today.month
    return year, month


@login_required
@capability_required("staff_affairs.manage")
def attendance_board(request):
    """رصدُ اليوم: الكادرُ كلُّه، وحالةُ كلٍّ بنقرة."""
    day = _day(request.GET.get("date"))
    board = StaffAttendanceService.daily_board(request.school, day)
    return render(
        request,
        "staff_affairs/attendance_board.html",
        {"day": day, "today": timezone.localdate(), **board},
    )


@login_required
@capability_required("staff_affairs.manage")
@require_POST
def attendance_mark(request):
    """نقرةُ الرصد (HTMX) — تُعيد سطرَ الموظّف نفسَه، وخطأُ السياسة فيه باسم البند."""
    form = AttendanceMarkForm(request.POST)
    if not form.is_valid():
        raise Http404("رصدٌ ناقص")
    data = form.cleaned_data
    try:
        row = StaffAttendanceService.board_row(request.school, data["staff_id"], data["date"])
    except ObjectDoesNotExist as exc:  # موظّفٌ من غير هذه المدرسة لا يُكشف وجودُه
        raise Http404("ليس من كادر هذه المدرسة") from exc
    error = ""
    try:
        row["record"] = StaffAttendanceService.mark(
            school=request.school,
            staff=row["staff"],
            day=data["date"],
            status=data["status"],
            check_in=data["check_in"],
            actor=request.user,
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
@capability_required("staff_affairs.manage")
def attendance_report(request):
    """تقريرُ الشهر: جدولٌ لكلّ موظّف، وتنزيلُه Excel بالرقم الوظيفيّ."""
    year, month = _month(request.GET.get("month"))
    report = StaffAttendanceService.monthly_report(request.school, year, month)
    return render(
        request,
        "staff_affairs/attendance_report.html",
        {"month_value": f"{year:04d}-{month:02d}", **report},
    )


@login_required
@capability_required("staff_affairs.manage")
def attendance_report_xlsx(request):
    """Excel التقرير — الرقم الشخصيّ: مستور (لا يُكتب أصلاً؛ الرقمُ الوظيفيّ وحدَه)."""
    year, month = _month(request.GET.get("month"))
    report = StaffAttendanceService.monthly_report(request.school, year, month)
    workbook = StaffAttendanceService.monthly_workbook(report)
    log_export(
        request,
        "staff_affairs.attendance_month_xlsx",
        rows=len(report["rows"]),
        object_repr=f"حضور الموظفين {year:04d}-{month:02d}",
    )
    return excel_to_response(workbook, f"حضور_الموظفين_{year:04d}_{month:02d}.xlsx")


@login_required
@capability_required("staff_affairs.own_permits")
def my_permits(request):
    """طلبُ الموظّف إذناً لنفسه (نموذج 02)، وطلباتُه ورصيدُ شهره."""
    form = PermitRequestForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        try:
            PermitService.submit(
                school=request.school,
                staff=request.user,
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
            "balance": PermitService.balance(request.school, request.user, timezone.localdate()),
            "permits": PermitService.own_permits(request.school, request.user),
        },
    )


@login_required
@capability_required("staff_affairs.manage")
def permit_queue(request):
    """الطلباتُ المعلّقة للاعتماد أو الرفض."""
    return render(
        request,
        "staff_affairs/permit_queue.html",
        {"permits": PermitService.pending(request.school)},
    )


@login_required
@capability_required("staff_affairs.manage")
@require_POST
def permit_review(request, pk):
    """قرارُ طلبٍ واحد — والسياسةُ تُفحص ثانيةً عند الاعتماد."""
    form = PermitReviewForm(request.POST)
    if not form.is_valid():
        raise Http404("قرارٌ ناقص")
    try:
        permit = PermitService.pending_one(request.school, pk)
    except ObjectDoesNotExist as exc:
        raise Http404("لا طلبَ بهذا المعرّف") from exc
    try:
        PermitService.review(
            permit,
            reviewer=request.user,
            approve=form.cleaned_data["decision"] == "approve",
            reason=form.cleaned_data["rejection_reason"],
            request=request,
        )
    except PolicyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"الطلب: {permit.get_status_display()}.")
    return redirect("staff_affairs:permit_queue")
