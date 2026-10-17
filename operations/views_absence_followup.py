"""شاشةُ «متابعة الغياب» — جدولان رسميّان: التواصلُ مع الأولياء، والإجراءاتُ الإداريّة (W-20261013-011).

تحلّ محلَّ «غياب اليوم» على المسار القديم `/teacher/reports/daily/` (فلا ينكسر رابطٌ محفوظ)، ومصدرُ
غائبي اليوم هو `daily_absence.daily_report` نفسُه. والسجلّان مضافان فقط (`services/absence_followup.py`).

- **النطاق:** مشرفُ الجناح لجناحه بـ`student_scope_for` — وطالبٌ من خارجه في أيّ نموذج = 404؛ وغيرُه على المدرسة.
  النائبُ الأكاديميّ ومنسّقُ القسم يرون ولا يسجّلون (القدراتُ في `core/capabilities.py`).
- **رقمُ وليّ الأمر** يظهر لمن بلغ الشاشة (قرارُ المالك D-431م) **بلا اسمِ وليٍّ ولا أمّ** في أيّ مخرج،
  وعرضُه سطرُ تدقيقٍ بعدده لا برقمه. **التغذية الراجعة من وليّ الأمر** (نصٌّ مشفَّر) لحاملي قدرتها وحدَهم، وفتحُها سطرُ تدقيقٍ
  بعددها بلا نصّ.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.clickjacking import xframe_options_sameorigin
from django.views.decorators.http import require_POST

from core.capabilities import capability_required, has_capability
from core.export_utils import generate_export_filename
from core.models import AuditLog
from operations.models import AbsenceActionLog, AbsenceContactLog
from operations.services import ScheduleService
from operations.services import absence_followup as service
from wings.scope import student_scope_for

#: ما يحمله الطلبُ من قدراتٍ — يُحسب مرّةً ويُمرَّر للقالب.
_FLAGS = {
    "can_record": "operations.absence_followup_record",
    "can_feedback": "operations.absence_followup_feedback",
    "can_print": "operations.absence_followup_print",
    "can_followup": "operations.absence_followup_followup",
}


_TITLES = {"contact": "التواصل مع أولياء الأمور", "actions": "متابعة إجراءات الغياب"}


def _day(raw: str | None) -> dt.date:
    try:
        return dt.date.fromisoformat(raw or "")
    except ValueError:
        return timezone.localdate()


def _statuses_for(can_followup: bool) -> list[tuple[str, str]]:
    """خياراتُ «حالة الإجراء» في نموذج التسجيل: كاملةٌ لحاملِ قدرة المتابعة، ولغيره إجراءٌ مُنفَّذٌ أو استلامُ إجازة.

    كاتبٌ بلا القدرة لا يرى عمودَ الحالة ولا يختارها؛ والفارغُ يُعدّ في الخدمة «تمّ» (إجراءٌ سُجِّل).
    """
    if can_followup:
        return list(AbsenceActionLog.STATUSES)
    return [("", "إجراءٌ مُنفَّذ"), ("sick_leave_received", "استلامُ إجازة مرضيّة")]


def _shown(params: Any, rows: list[dict]) -> list[dict]:
    """ما تعرضه الشاشةُ بتصفيتها وفرزها — تُطبَّق نفسُها على الكشف والورقة، فيطابق المطبوعُ المعروض."""
    return service.apply_view(
        rows,
        grade=params.get("grade", ""),
        wing=params.get("wing", ""),
        followup=params.get("followup", ""),
        sort=params.get("sort", ""),
    )


def _flags(user: Any) -> dict[str, bool]:
    return {name: has_capability(user, key) for name, key in _FLAGS.items()}


def _rows(request: HttpRequest, day: dt.date) -> tuple[list[dict], Any, bool]:
    """صفوفُ الخدمة + تقريرُ اليوم للعدّادات؛ ونصُّ التغذية يُحجب في الخدمة عمّن لا قدرةَ له."""
    from core.permissions import get_department_teacher_ids
    from operations.daily_absence import daily_report as build_report

    school = request.school
    ScheduleService.ensure_sessions_for_date(school, day)
    scope = student_scope_for(request)
    report = build_report(
        school,
        day,
        teacher_ids=(
            get_department_teacher_ids(request.user)
            if request.user.get_role() == "coordinator"  # type: ignore[union-attr]
            else None
        ),
        student_ids=scope.student_ids() if scope.is_wing_bound else None,
    )
    return service.followup_rows(request.user, day), report, scope.is_wing_bound


def _audit_reads(request: HttpRequest, rows: list[dict]) -> None:
    """أثرُ عرضِ أرقام الأولياء والتغذية الراجعة: العددُ والدورُ وحدَهما — لا رقمَ ولا اسمَ ولا نصّ."""
    user = request.user
    school = request.school
    role = user.get_role()  # type: ignore[union-attr]
    phones = sum(len(r["phones"]) for r in rows)
    if phones:
        AuditLog.log(
            user=user,
            action="view",
            model_name="ParentStudentLink",
            object_id=school.id,
            object_repr="أرقامُ أولياء الأمور — متابعة الغياب",
            changes={"phones": phones, "role": role},
            school=school,
            request=request,
        )
    opened = sum(1 for r in rows if r["feedback"])
    if opened:
        AuditLog.log(
            user=user,
            action="view",
            model_name="other",
            object_id=school.id,
            object_repr="التغذية الراجعة من وليّ الأمر — متابعة الغياب",
            changes={"feedback_opened": opened, "role": role},
            school=school,
            request=request,
        )


def _screen(request: HttpRequest, page: str) -> HttpResponse:
    """الصفحتان المستقلّتان تتقاسمان التصفيةَ والعدّاداتِ والنطاق، وتختلفان بالقالب وحده."""
    school = request.school
    day = _day(request.GET.get("date"))
    flags = _flags(request.user)
    all_rows, report, wing_bound = _rows(request, day)
    q = {k: request.GET.get(k, "") for k in ("grade", "wing", "followup", "sort")}
    rows = service.apply_view(all_rows, **q)
    _audit_reads(request, rows)
    subtitle = f"{school.name} · {date_format(day, 'l d/m/Y')}"
    if wing_bound:
        subtitle = f"{subtitle} · طلبةُ جناحك"
    grades = sorted(
        {(r["class_group"].grade, r["class_group"].get_grade_display()) for r in all_rows}
    )
    return render(
        request,
        f"operations/absence_followup/{page}.html",
        {
            "rows": rows,
            "day": day,
            "page": page,
            "screen_title": _TITLES[page],
            "screen_icon": "call_parent" if page == "contact" else "checklist",
            "subtitle": subtitle,
            "absent_students": len(rows),
            "ministry_count": report.ministry_absent_count,
            "contacted": sum(1 for r in rows if r["contact"]),
            "actioned": sum(1 for r in rows if r["action"]),
            "outcomes": AbsenceContactLog.OFFERED_OUTCOMES,
            "statuses": _statuses_for(flags["can_followup"]),
            "kinds": AbsenceActionLog.KINDS,
            "grades": grades,
            "wings": [] if wing_bound else service.wing_choices(school),
            "view_query": service.view_query(**q),
            "followups": service.FOLLOWUP_FILTERS,
            "sorts": service.SORTS,
            "f_sort": q["sort"] if q["sort"] in dict(service.SORTS) else "",
            "f_grade": q["grade"],
            "f_wing": q["wing"],
            "f_followup": q["followup"],
            "empty_title": (
                "لا غائبَ يطابق التصفية"
                if any(q[k] for k in ("grade", "wing", "followup"))
                else "لا غيابَ مرصوداً في هذا اليوم"
            ),
            **flags,
        },
    )


@login_required
@capability_required("operations.absence_followup_view")
def absence_followup(request: HttpRequest) -> HttpResponse:
    """صفحةُ «التواصل مع أولياء الأمور» — وهي المسارُ القديم `/reports/daily/` فلا ينكسر رابطٌ محفوظ."""
    return _screen(request, "contact")


@login_required
@capability_required("operations.absence_followup_view")
def absence_actions(request: HttpRequest) -> HttpResponse:
    """صفحةُ «متابعة إجراءات الغياب» المستقلّة."""
    return _screen(request, "actions")


def _day_of(request: HttpRequest) -> dt.date:
    return _day(request.POST.get("date"))


def _back(request: HttpRequest, day: dt.date) -> HttpResponse:
    """يعود إلى الشاشة بيومها وبالفلاتر التي كان عليها صاحبُ الطلب."""
    query = {"date": f"{day:%Y-%m-%d}"}
    for key in ("grade", "wing", "followup", "sort"):
        if request.POST.get(key):
            query[key] = request.POST[key]
    target = "absence_actions" if request.POST.get("page") == "actions" else "daily_report"
    return redirect(f"{reverse(target)}?{urlencode(query)}")


@login_required
@require_POST
@capability_required("operations.absence_followup_record")
def contact_save(request: HttpRequest) -> HttpResponse:
    """يسجّل اتّصالاً بوليّ الأمر (أو يصحّحه بسجلٍّ جديد) — والقدرات والنطاق في الخدمة."""
    day = _day_of(request)
    feedback = request.POST.get("feedback", "")
    try:
        if request.POST.get("corrects"):
            fields: dict[str, Any] = {"outcome": request.POST.get("outcome", "")}
            if "status" in request.POST:
                fields["status"] = request.POST["status"]
            if feedback:
                fields["feedback"] = feedback
            service.correct_contact(request.user, request.POST["corrects"], **fields)
        else:
            service.record_contact(
                request.user,
                request.POST.get("student"),
                day,
                request.POST.get("outcome", ""),
                feedback,
                request.POST.get("status", ""),
            )
        messages.success(request, "سُجِّل الاتّصال.")
    except service.FollowupError as exc:
        messages.error(request, str(exc))
    return _back(request, day)


@login_required
@require_POST
@capability_required("operations.absence_followup_record")
def action_save(request: HttpRequest) -> HttpResponse:
    """يسجّل إجراءً إداريّاً (أو يصحّحه بسجلٍّ جديد) — واستلامُ الإجازة المرضيّة حالةٌ منه."""
    day = _day_of(request)
    try:
        if request.POST.get("corrects"):
            service.correct_action(
                request.user,
                request.POST["corrects"],
                status=request.POST.get("status", ""),
                action_kind=request.POST.get("action_kind", ""),
                note=request.POST.get("note", ""),
            )
        else:
            service.record_action(
                request.user,
                request.POST.get("student"),
                day,
                request.POST.get("action_kind", ""),
                request.POST.get("status", ""),
                request.POST.get("note", ""),
            )
        messages.success(request, "سُجِّل الإجراء.")
    except service.FollowupError as exc:
        messages.error(request, str(exc))
    return _back(request, day)


@login_required
@capability_required("operations.absence_followup_print")
def followup_print(request: HttpRequest) -> HttpResponse:
    """صفحةُ المنصّة بإطار الكشف (المسارُ القديم `reports/daily/print/` باقٍ) — الفرضُ في الخادم لا في الواجهة."""
    from operations.absence_followup_print import followup_viewer_response

    return followup_viewer_response(request, _day(request.GET.get("date")))


# `X_FRAME_OPTIONS = "DENY"` عامٌّ على المشروع فيحجب عرضَ الملفّ داخل إطار صفحة المنصّة؛ والمصدرُ الموقعُ نفسُه فـ sameorigin يكفي.
@xframe_options_sameorigin
@login_required
@capability_required("operations.absence_followup_print")
def followup_pdf(request: HttpRequest) -> HttpResponse:
    """ملفُّ PDF للصفحة المطلوبة بالاتّجاه المطلوب — inline للإطار، و`download=1` تنزيلاً. التدقيقُ: العددُ لا الأسماء."""
    from core.audit_export import log_export
    from operations.absence_followup_print import build_followup_pdf, sheet_options

    result = build_followup_pdf(request.school, request.user, request.GET)
    page, orient = sheet_options(request.GET)
    log_export(
        request,
        f"operations.absence_followup_{page}_pdf",
        rows=result.rows,
        object_repr=f"{page}/{orient}",
    )
    response = HttpResponse(result.content, content_type=result.content_type)
    mode = "attachment" if request.GET.get("download") else "inline"
    response["Content-Disposition"] = f'{mode}; filename="{result.filename}"'
    return response


@login_required
@capability_required("operations.absence_followup_print")
def contact_sheet(request: HttpRequest) -> HttpResponse:
    """ورقةُ الاتّصال PDF (W-20261013-017) — القدرةُ والنطاقُ والتدقيقُ في الدالة نفسها فلا `log_export` معها."""
    from operations.absence_followup_print import render_contact_sheet

    day = _day(request.GET.get("date"))
    pdf = render_contact_sheet(request.user, day, request.GET)
    response = HttpResponse(pdf, content_type="application/pdf")
    filename = generate_export_filename("operations", "absence-contact-sheet", "pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
