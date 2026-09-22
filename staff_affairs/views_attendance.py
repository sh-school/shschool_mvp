"""شاشاتُ حضور الموظّفين (1.1) والأذونات القصيرة (1.3) — للكادر وحدَه.

العرضُ يقرأ الطلبَ ويستدعي الخدمة ويرسم؛ القواعدُ والاستعلاماتُ كلُّها في
``staff_affairs/attendance/`` (حزمة)، والتدقيقُ يُكتب هناك مع كلّ كتابة.
"""

from __future__ import annotations

from datetime import date
from typing import Any, cast
from uuid import UUID

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ObjectDoesNotExist, PermissionDenied
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

from .attendance import (
    AssignmentService,
    ExceptionService,
    PermitService,
    PolicyError,
    StaffAttendanceService,
    can_submit_permits,
)
from .forms import (
    AssignmentForm,
    AttendanceMarkForm,
    ExceptionDecisionForm,
    ExceptionRequestForm,
    PermitRequestForm,
    PermitReviewForm,
)
from .models import (
    ABSENCE_TYPES,
    EXCEPTION_EVIDENCE_ROLES,
    EXCEPTION_TYPES,
    PERMIT_TYPES,
    StaffAttendance,
)


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


def _row_values(record: StaffAttendance | None, can_excuse: bool) -> dict[str, str]:
    """ما يُعرض في حقول سطر الرصد من السجلّ المحفوظ.

    ونصُّ العذر المقبول لجهة قبوله وحدَها (م-7): قد يحمل بيانةً صحّيّة (PDPPL م.16)،
    فلا يصل قالبَ من يرصد الوقت أصلاً.
    """
    if record is None:
        return dict.fromkeys(("check_in", "check_out", "absence_type", "accepted_excuse"), "")
    return {
        "check_in": f"{record.check_in:%H:%M}" if record.check_in else "",
        "check_out": f"{record.check_out:%H:%M}" if record.check_out else "",
        "absence_type": record.absence_type,
        "accepted_excuse": record.accepted_excuse if can_excuse else "",
    }


def _posted_values(post: Any, can_excuse: bool) -> dict[str, str]:
    """ما كتبه المستخدمُ في السطر كما أُرسل — يعود مع رسالة الرفض فلا يُكتب ثانية."""
    values = {
        key: str(post.get(key, ""))[:300]
        for key in ("check_in", "check_out", "absence_type", "accepted_excuse")
    }
    if not can_excuse:
        values["accepted_excuse"] = ""
    return values


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
    """رصدُ اليوم: الكادرُ كلُّه، وحالةُ كلٍّ بنقرة.

    ونائبُ الشؤون الإدارية يصل إليها دائماً، ولا يرى الكادرَ ولا يرصد إلّا حين ينوب عن
    المدير (م-24) — وإلّا فرسالةٌ تقول متى تُفتح له.
    """
    day = _day(request.GET.get("date"))
    can_record = StaffAttendanceService.can_open_board(_school(request), _user(request))
    can_excuse = StaffAttendanceService.can_decide_excuse(_school(request), _user(request))
    board: dict[str, Any] = {"rows": [], "counts": {}}
    if can_record:
        board = StaffAttendanceService.daily_board(_school(request), day, viewer=_user(request))
        for row in board["rows"]:
            row["values"] = _row_values(row["record"], can_excuse)
    return render(
        request,
        "staff_affairs/attendance_board.html",
        {
            "day": day,
            "today": timezone.localdate(),
            "absence_types": ABSENCE_TYPES,
            "can_record": can_record,
            "can_excuse": can_excuse,
            **board,
        },
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
    if not StaffAttendanceService.can_record_for(_school(request), _user(request), row["staff"]):
        raise PermissionDenied(
            "الرصدُ للسكرتارية والمدير ومن كُلّف بأعبائه، وللمسؤول المباشر لمن تحته"
        )
    error = ""
    try:
        row["record"] = StaffAttendanceService.mark(
            school=_school(request),
            staff=row["staff"],
            day=data["date"],
            status=data["status"],
            check_in=data["check_in"],
            check_out=data["check_out"],
            absence_type=data["absence_type"],
            # الحقلُ لا يُعرض إلّا لجهة القبول؛ وغيابُه «لم يُمسّ العذر» لا «رُفع» (م-7).
            accepted_excuse=(
                data["accepted_excuse"] if "accepted_excuse" in request.POST else None
            ),
            actor=_user(request),
            request=request,
        )
    except PolicyError as exc:
        error = str(exc)
    can_excuse = StaffAttendanceService.can_decide_excuse(_school(request), _user(request))
    values = (
        _posted_values(request.POST, can_excuse)
        if error
        else _row_values(row["record"], can_excuse)
    )
    return render(
        request,
        "staff_affairs/partials/attendance_row.html",
        {
            **row,
            "values": values,
            "day": data["date"],
            "error": error,
            "absence_types": ABSENCE_TYPES,
            "can_excuse": can_excuse,
        },
    )


@login_required
@capability_required("staff_affairs.attendance_report")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def attendance_report(request: HttpRequest) -> HttpResponse:
    """تقريرُ الشهر: جدولٌ لكلّ موظّفٍ في نطاق القارئ، وتنزيلُه Excel بالرقم الوظيفيّ."""
    year, month = _month(request.GET.get("month"))
    report = StaffAttendanceService.monthly_report(
        _school(request), year, month, viewer=_user(request)
    )
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
    report = StaffAttendanceService.monthly_report(
        _school(request), year, month, viewer=_user(request)
    )
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


def _submit_exception(request: HttpRequest, form: ExceptionRequestForm) -> bool:
    """يقدّم استثناءَ نموذج 03 من نموذجٍ صحيح؛ ويُعيد نجاحَه، وإلّا يعلّق سببَ الرفض بالنموذج."""
    data = form.cleaned_data
    try:
        ExceptionService.submit(
            school=_school(request),
            staff=_user(request),
            exception_type=data["exception_type"],
            start_date=data["start_date"],
            end_date=data["end_date"],
            boundary=data["boundary_time"],
            content=data["content"],
            evidence=data["evidence"],
            evidence_file=data["evidence_file"],
            request=request,
        )
    except PolicyError as exc:
        form.add_error(None, str(exc))
        return False
    messages.success(request, "قُدِّم طلبُ الاستثناء إلى مدير المدرسة (نموذج 03).")
    return True


def _submit_permit(request: HttpRequest, form: PermitRequestForm) -> bool:
    """يقدّم إذنَ نموذج 02 من نموذجٍ صحيح؛ ويُعيد نجاحَه، وإلّا يعلّق سببَ الرفض بالنموذج."""
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
        return False
    messages.success(request, "قُدِّم الطلب — ولا يُحتسب إلّا بعد اعتماده (البند 4.1).")
    return True


@login_required
@capability_required("staff_affairs.own_permits")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def my_permits(request: HttpRequest) -> HttpResponse:
    """طلبُ الموظّف إذناً لنفسه (نموذج 02) أو استثناءً من المدير (نموذج 03)، وطلباتُه ورصيدُه."""
    is_exception = request.POST.get("form") == "exception"
    form = PermitRequestForm(
        request.POST if request.method == "POST" and not is_exception else None
    )
    exception_form = ExceptionRequestForm(
        request.POST if is_exception else None, request.FILES if is_exception else None
    )
    can_submit = can_submit_permits(_user(request))
    can_request_exception = can_submit and not AssignmentService.is_principal(
        _school(request), _user(request)
    )
    if is_exception and can_request_exception and exception_form.is_valid():
        if _submit_exception(request, exception_form):
            return redirect("staff_affairs:my_permits")
    elif request.method == "POST" and not is_exception and can_submit and form.is_valid():
        if _submit_permit(request, form):
            return redirect("staff_affairs:my_permits")
    return render(
        request,
        "staff_affairs/my_permits.html",
        {
            "form": form,
            "exception_form": exception_form,
            "can_submit": can_submit,
            "can_request_exception": can_request_exception,
            "permit_types": PERMIT_TYPES,
            "exception_types": EXCEPTION_TYPES,
            "exceptions": ExceptionService.own(_school(request), _user(request)),
            # ``own_permits`` يكنس ما انتهى وقتُه (م-18ب) قبل أن يُحسب الرصيد، ويعلّم ما
            # يُلغى من المعتمد قبل بدء نافذته (م-20).
            "permits": PermitService.own_permits(_school(request), _user(request)),
            "balance": PermitService.balance(
                _school(request), _user(request), timezone.localdate()
            ),
        },
    )


@login_required
@capability_required("staff_affairs.own_permits")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@require_POST
def permit_cancel(request: HttpRequest, pk: UUID) -> HttpResponse:
    """إلغاءُ صاحب الطلب طلبَه المعلَّق أو إذنَه المعتمدَ قبل نافذته (م-20) — والخدمةُ تفحص."""
    try:
        permit = PermitService.pending_one(_school(request), pk)
    except ObjectDoesNotExist as exc:
        raise Http404("لا طلبَ بهذا المعرّف") from exc
    try:
        PermitService.cancel(permit, actor=_user(request), request=request)
    except PolicyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "أُلغي الطلب — وأُفرج عن يومه ودقائقه (م-20).")
    return redirect("staff_affairs:my_permits")


@login_required
@capability_required("staff_affairs.permits_review")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def permit_queue(request: HttpRequest) -> HttpResponse:
    """الطلباتُ التي تنتظر مرحلةَ المستخدم في نموذج 02، واستثناءاتُ نموذج 03 للمدير وإنابتُه."""
    school, user = _school(request), _user(request)
    return render(
        request,
        "staff_affairs/permit_queue.html",
        {
            "permits": PermitService.awaiting(school, user),
            "exceptions": ExceptionService.awaiting(school, user),
            "is_principal": AssignmentService.is_principal(school, user),
            # من لا يفتح المرفقَ بوّابةُ الملفّات لا يُعرض له رابطٌ يردّه (عدمُ الاتّساق كان هنا).
            "can_view_evidence": _user(request).get_role() in EXCEPTION_EVIDENCE_ROLES,
        },
    )


@login_required
@capability_required("staff_affairs.permits_review")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@require_POST
def exception_review(request: HttpRequest, pk: UUID) -> HttpResponse:
    """«استخدام مدير المدرسة» في نموذج 03 — والخدمةُ تفحص أنّه المدير أو من ينوب عنه (م-30)."""
    form = ExceptionDecisionForm(request.POST)
    if not form.is_valid():
        raise Http404("قرارٌ ناقص")
    try:
        exception = ExceptionService.pending_one(_school(request), pk)
    except ObjectDoesNotExist as exc:
        raise Http404("لا طلبَ بهذا المعرّف") from exc
    try:
        ExceptionService.decide(
            exception,
            actor=_user(request),
            approve=form.cleaned_data["decision"] == "approve",
            feedback=form.cleaned_data["feedback"],
            request=request,
        )
    except PolicyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"سُجّل: {exception.get_status_display()} (نموذج 03).")
    return redirect("staff_affairs:permit_queue")


@login_required
@capability_required("staff_affairs.assignments")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def staff_assignments(request: HttpRequest) -> HttpResponse:
    """التكليفات: قرارُ المدير ونائبَيه بندبِ موظّفٍ لأعباء وظيفتهم (م-43) — وسجلُّها."""
    school, user = _school(request), _user(request)
    form = AssignmentForm(request.POST if request.method == "POST" else None)
    if request.method == "POST" and form.is_valid():
        data = form.cleaned_data
        assignee = (
            AssignmentService.candidates(school, user, data["start_date"])
            .filter(pk=data["assignee"])
            .first()
        )
        try:
            if assignee is None:
                raise PolicyError("ليس ممّن يجوز لك تكليفُهم بحسب قرار المدرسة.")
            AssignmentService.assign(
                school=school,
                assigner=user,
                assignee=assignee,
                start=data["start_date"],
                end=data["end_date"],
                reason=data["reason"],
                reference=data["reference"],
                request=request,
            )
        except PolicyError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, "سُجّل التكليفُ — ويعمل المكلَّفُ بأعباء الوظيفة في المدّة.")
            return redirect("staff_affairs:assignments")
    return render(
        request,
        "staff_affairs/assignments.html",
        {
            "form": form,
            "acting_role": AssignmentService.acting_role_of(user),
            "candidates": AssignmentService.candidates(school, user),
            "today": timezone.localdate(),
            **AssignmentService.screen(school),
        },
    )


@login_required
@capability_required("staff_affairs.assignments")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
@require_POST
def staff_assignment_revoke(request: HttpRequest, pk: UUID) -> HttpResponse:
    """رفعُ تكليف — لمن كلّف به أو للمدير، والخدمةُ تفحص."""
    school = _school(request)
    assignment = AssignmentService.one(school, pk)
    try:
        AssignmentService.revoke(assignment, actor=_user(request), request=request)
    except PolicyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "رُفع التكليفُ — ويبقى في السجلّ.")
    return redirect("staff_affairs:assignments")


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
            written_approval=form.cleaned_data["written_approval"],
            request=request,
        )
    except PolicyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(
            request, f"سُجّل: {permit.get_stage_display()} — {permit.get_status_display()}."
        )
    return redirect("staff_affairs:permit_queue")
