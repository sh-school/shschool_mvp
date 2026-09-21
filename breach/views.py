"""
breach/views.py — SchoolOS v5
إدارة خرق البيانات (PDPPL م.11 + NCSA 72h)
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.capabilities import capability_required
from core.models import AuditLog, BreachReport

from .forms import BreachEditForm, BreachReportForm
from .services import (
    InvalidTransitionError,
    register_breach,
    transition,
    update_breach,
)

_STATUS = dict(BreachReport.STATUS)


@login_required
@capability_required("breach.manage")
def dashboard(request):
    from django.db.models import Count, Q

    school = request.user.get_school()
    reports = BreachReport.objects.filter(school=school).order_by("-discovered_at")
    open_states = ["discovered", "assessing"]
    stats = reports.aggregate(
        active=Count("id", filter=Q(status__in=open_states)),
        notified=Count("id", filter=Q(status="notified")),
        resolved=Count("id", filter=Q(status="resolved")),
        # نفسُ شرط `BreachReport.is_overdue` في قاعدة البيانات: لا حلقةَ في Python.
        overdue=Count(
            "id",
            filter=Q(ncsa_deadline__lt=timezone.now()) & Q(status__in=open_states),
        ),
    )
    return render(
        request,
        "breach/dashboard.html",
        {
            "reports": reports,
            "stats": stats,
            # اللونُ يحمل التنبيه: مهلةٌ فائتةٌ حمراء، وخرقٌ نشطٌ كهرمانيّ، وصفرُهما أخضر.
            "overdue_tone": "red" if stats["overdue"] else "green",
            "active_tone": "amber" if stats["active"] else "green",
        },
    )


@login_required
@capability_required("breach.manage")
def create(request):
    school = request.user.get_school()

    if request.method == "POST":
        form = BreachReportForm(request.POST, school=school)
        if form.is_valid():
            breach = register_breach(form=form, user=request.user, school=school, request=request)
            return redirect("breach:detail", pk=breach.pk)
    else:
        form = BreachReportForm(
            school=school,
            initial={
                "discovered_at": timezone.localtime().strftime("%Y-%m-%dT%H:%M"),
                "affected_count": 0,
            },
        )
    return render(request, "breach/form.html", {"form": form})


def _history(breach):
    """سجلُّ ما جرى على الخرق من AuditLog: من فعل ماذا ومتى (الأحدثُ أوّلاً)."""
    rows = (
        AuditLog.objects.filter(object_id=str(breach.pk), model_name="other")
        .select_related("user")
        .order_by("-timestamp")[:15]
    )
    out = []
    for row in rows:
        changes = row.changes or {}
        if row.action == "create":
            what = "سُجّل الخرق"
        elif "to" in changes:
            what = (
                f"الحالة: {_STATUS.get(changes['from'], '—')} ← {_STATUS.get(changes['to'], '—')}"
            )
            if changes.get("closed_without_ncsa_notice"):
                what += " (بلا إشعار NCSA)"
        else:
            what = "تعديل بيانات الخرق"
        who = getattr(row.user, "full_name", "") or "—"
        out.append({"what": what, "who": who, "at": row.timestamp})
    return out


@login_required
@capability_required("breach.manage")
def edit(request, pk):
    school = request.user.get_school()
    breach = get_object_or_404(BreachReport, pk=pk, school=school)
    if breach.status == "resolved":
        messages.error(request, "لا يُعدَّل خرقٌ مُغلق.")
        return redirect("breach:detail", pk=pk)

    if request.method == "POST":
        form = BreachEditForm(request.POST, instance=breach, school=school)
        if form.is_valid():
            try:
                update_breach(breach, form, user=request.user, request=request)
            except InvalidTransitionError as exc:
                messages.error(request, str(exc))
            else:
                messages.success(request, "حُفظ التعديل.")
            return redirect("breach:detail", pk=pk)
    else:
        form = BreachEditForm(instance=breach, school=school)
    return render(request, "breach/form.html", {"form": form, "breach": breach, "is_edit": True})


@login_required
@capability_required("breach.manage")
def detail(request, pk):
    breach = get_object_or_404(BreachReport, pk=pk, school=request.user.get_school())
    hours = breach.hours_remaining
    return render(
        request,
        "breach/detail.html",
        {
            "breach": breach,
            "history": _history(breach),
            # اللونُ يحمل التنبيه كما في اللوحة: 12 ساعةً فأقلّ كهرمانيّ.
            "remaining_tone": "amber" if hours is not None and hours <= 12 else "green",
            "severity_tone": {"critical": "red", "high": "red", "medium": "amber"}.get(
                breach.severity, "green"
            ),
            "status_tone": {"discovered": "red", "assessing": "amber", "notified": "green"}.get(
                breach.status, "teal"
            ),
            # الساعاتُ تُقتطع فيظهر «0» قبل الفوات بدقائق — يُقال ذلك صراحةً.
            "remaining_sub": "أقلّ من ساعة" if hours == 0 else "حتى موعد إشعار NCSA",
            "overdue_sub": (
                f"كان الموعد {timezone.localtime(breach.ncsa_deadline):%d/%m %H:%M}"
                if breach.is_overdue
                else ""
            ),
        },
    )


@login_required
@capability_required("breach.manage")
def update_status(request, pk):
    if request.method != "POST":
        return redirect("breach:detail", pk=pk)

    breach = get_object_or_404(BreachReport, pk=pk, school=request.user.get_school())
    try:
        transition(breach, request.POST.get("status", ""), user=request.user, request=request)
    except InvalidTransitionError as exc:
        messages.error(request, str(exc))

    return redirect("breach:detail", pk=pk)


@login_required
@capability_required("breach.manage")
def breach_pdf(request, pk):
    breach = get_object_or_404(BreachReport, pk=pk, school=request.user.get_school())
    from django.template.loader import render_to_string

    from core.audit_export import log_export
    from core.pdf_utils import render_pdf

    log_export(
        request,
        "breach.report_pdf",
        rows=1,
        object_id=breach.pk,
        object_repr=f"تقرير خرق — {breach.title}",
    )
    html = render_to_string(
        "breach/pdf_report.html",
        {
            "breach": breach,
            "generated_at": timezone.now(),
            "generated_by": request.user,
        },
    )
    return render_pdf(html, f"breach_{breach.pk}.pdf")
