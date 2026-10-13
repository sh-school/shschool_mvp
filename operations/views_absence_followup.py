"""شاشةُ «متابعة الغياب» — جدولان رسميّان: التواصلُ مع الأولياء، والإجراءاتُ الإداريّة (W-20261013-011).

تحلّ محلَّ «غياب اليوم» على المسار القديم `/teacher/reports/daily/` (فلا ينكسر رابطٌ محفوظ)، ومصدرُ
غائبي اليوم هو `daily_absence.daily_report` نفسُه. والسجلّان مضافان فقط (`services/absence_followup.py`).

- **النطاق:** مشرفُ الجناح لجناحه بـ`student_scope_for` — وطالبٌ من خارجه في أيّ نموذج = 404؛ وغيرُه على المدرسة.
  النائبُ الأكاديميّ ومنسّقُ القسم يرون ولا يسجّلون (القدراتُ في `core/capabilities.py`).
- **رقمُ وليّ الأمر** يظهر لمن بلغ الشاشة (قرارُ المالك D-431م) **بلا اسمِ وليٍّ ولا أمّ** في أيّ مخرج،
  وعرضُه سطرُ تدقيقٍ بعدده لا برقمه. **تغذيةُ الأهل** (نصٌّ مشفَّر) لحاملي قدرتها وحدَهم، وفتحُها سطرُ تدقيقٍ
  بعددها بلا نصّ.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format
from django.views.decorators.http import require_POST

from core.audit_export import log_export
from core.capabilities import capability_required, has_capability
from core.export_utils import generate_export_filename, get_export_context
from core.models import AuditLog
from core.pdf_utils import render_pdf
from operations.models import AbsenceActionLog, AbsenceContactLog
from operations.services import ScheduleService
from operations.services import absence_followup as service
from wings.scope import student_scope_for

#: ما يحمله الطلبُ من قدراتٍ — يُحسب مرّةً ويُمرَّر للقالب.
_FLAGS = {
    "can_record": "operations.absence_followup_record",
    "can_feedback": "operations.absence_followup_feedback",
    "can_print": "operations.absence_followup_print",
}


def _day(raw: str | None) -> dt.date:
    try:
        return dt.date.fromisoformat(raw or "")
    except ValueError:
        return timezone.localdate()


def _flags(user: Any) -> dict[str, bool]:
    return {name: has_capability(user, key) for name, key in _FLAGS.items()}


def _rows(request: HttpRequest, day: dt.date) -> tuple[list[dict], Any, bool]:
    """صفوفُ الخدمة + تقريرُ اليوم للعدّادات؛ ونصُّ التغذية يُحجب في الخدمة عمّن لا قدرةَ له."""
    from core.permissions import get_department_teacher_ids
    from operations.daily_absence import daily_report as build_report

    school = request.user.get_school()
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
    school = user.get_school()  # type: ignore[union-attr]
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
            object_repr="تغذيةُ الأهل الراجعة — متابعة الغياب",
            changes={"feedback_opened": opened, "role": role},
            school=school,
            request=request,
        )


@login_required
@capability_required("operations.absence_followup_view")
def absence_followup(request: HttpRequest) -> HttpResponse:
    """متابعةُ غياب اليوم — جدولا التواصل والإجراء، لأيّ تاريخ."""
    school = request.user.get_school()
    day = _day(request.GET.get("date"))
    flags = _flags(request.user)
    rows, report, wing_bound = _rows(request, day)
    _audit_reads(request, rows)
    subtitle = f"{school.name} · {date_format(day, 'l d/m/Y')}"
    if wing_bound:
        subtitle = f"{subtitle} · طلبةُ جناحك"
    return render(
        request,
        "operations/absence_followup/index.html",
        {
            "rows": rows,
            "day": day,
            "subtitle": subtitle,
            "absent_students": len(rows),
            "ministry_count": report.ministry_absent_count,
            "contacted": sum(1 for r in rows if r["contact"]),
            "actioned": sum(1 for r in rows if r["action"]),
            "outcomes": AbsenceContactLog.OUTCOMES,
            "statuses": AbsenceActionLog.STATUSES,
            **flags,
        },
    )


def _day_of(request: HttpRequest) -> dt.date:
    return _day(request.POST.get("date"))


def _back(day: dt.date) -> HttpResponse:
    return redirect(f"{reverse('daily_report')}?date={day:%Y-%m-%d}")


@login_required
@require_POST
@capability_required("operations.absence_followup_record")
def contact_save(request: HttpRequest) -> HttpResponse:
    """يسجّل اتّصالاً بوليّ الأمر (أو يصحّحه بسجلٍّ جديد) — والقدرات والنطاق في الخدمة."""
    day = _day_of(request)
    feedback = request.POST.get("feedback", "")
    try:
        if request.POST.get("supersedes"):
            fields: dict[str, Any] = {"outcome": request.POST.get("outcome", "")}
            if feedback:
                fields["feedback"] = feedback
            service.correct_contact(request.user, request.POST["supersedes"], **fields)
        else:
            service.record_contact(
                request.user,
                request.POST.get("student"),
                day,
                request.POST.get("outcome", ""),
                feedback,
            )
        messages.success(request, "سُجِّل الاتّصال.")
    except service.FollowupError as exc:
        messages.error(request, str(exc))
    return _back(day)


@login_required
@require_POST
@capability_required("operations.absence_followup_record")
def action_save(request: HttpRequest) -> HttpResponse:
    """يسجّل إجراءً إداريّاً (أو يصحّحه بسجلٍّ جديد) — واستلامُ الإجازة المرضيّة حالةٌ منه."""
    day = _day_of(request)
    try:
        if request.POST.get("supersedes"):
            service.correct_action(
                request.user,
                request.POST["supersedes"],
                status=request.POST.get("status", ""),
                action_kind=request.POST.get("action_type", ""),
                note=request.POST.get("note", ""),
            )
        else:
            service.record_action(
                request.user,
                request.POST.get("student"),
                day,
                request.POST.get("action_type", ""),
                request.POST.get("status", ""),
                request.POST.get("note", ""),
            )
        messages.success(request, "سُجِّل الإجراء.")
    except service.FollowupError as exc:
        messages.error(request, str(exc))
    return _back(day)


@login_required
@capability_required("operations.absence_followup_print")
def followup_print(request: HttpRequest) -> HttpResponse:
    """كشفُ المتابعة للطباعة — معاينةٌ في المتصفّح، و`?format=pdf` تنزيلاً (Tajawal مضمَّن)."""
    from wings.register import footer_lines

    school = request.user.get_school()
    day = _day(request.GET.get("date"))
    flags = _flags(request.user)
    rows, _report, wing_bound = _rows(request, day)
    _audit_reads(request, rows)
    title = f"متابعة الغياب — {date_format(day, 'd/m/Y')}"
    ctx = get_export_context(request, title)
    ctx.update(
        school=school,
        footer=footer_lines(school),
        rows=rows,
        day=day,
        wing_bound=wing_bound,
        orient="landscape",
        outcomes=dict(AbsenceContactLog.OUTCOMES),
        statuses=dict(AbsenceActionLog.STATUSES),
        can_feedback=flags["can_feedback"],
    )
    if request.GET.get("format") == "pdf":
        log_export(request, "operations.absence_followup_pdf", object_repr=title)
        html = render_to_string("operations/absence_followup_print.html", ctx, request=request)
        filename = generate_export_filename("operations", "absence-followup", "pdf")
        return render_pdf(html, filename, as_attachment=True)
    ctx["for_screen"] = True
    return render(request, "operations/absence_followup_print.html", ctx)
