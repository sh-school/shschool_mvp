"""
breach/views.py — SchoolOS v5
إدارة خرق البيانات (PDPPL م.11 + NCSA 72h)
"""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from core.models import BreachReport


def _admin_only(user):
    return user.is_authenticated and (user.is_admin() or user.is_superuser)


NCSA_TEMPLATE = """إلى: المركز الوطني للأمن السيبراني (NCSA)
الموضوع: إشعار بخرق بيانات — PDPPL م.11

المؤسسة: مدرسة الشحانية الإعدادية الثانوية للبنين
التاريخ: {date}

1. طبيعة الخرق: {title}
2. وقت الاكتشاف: {discovered_at}
3. البيانات المتأثرة: {data_type}
4. عدد الأشخاص المتأثرين: {affected_count}
5. الإجراءات الفورية المتخذة: {immediate_action}
6. خطة الاحتواء: {containment}

نؤكد التزامنا بالإجراءات المنصوص عليها في قانون حماية البيانات الشخصية رقم 13/2016.
""".strip()


@login_required
def dashboard(request):
    if not _admin_only(request.user):
        return HttpResponseForbidden("للمدير فقط")
    school = request.user.get_school()
    reports = BreachReport.objects.filter(school=school).order_by("-discovered_at")
    stats = {
        "overdue": sum(1 for r in reports if r.is_overdue),
        "active": reports.filter(status__in=["discovered", "assessing"]).count(),
        "notified": reports.filter(status="notified").count(),
        "resolved": reports.filter(status="resolved").count(),
    }
    return render(request, "breach/dashboard.html", {"reports": reports, "stats": stats})


@login_required
def create(request):
    if not _admin_only(request.user):
        return HttpResponseForbidden("للمدير فقط")
    school = request.user.get_school()

    if request.method == "POST":
        from datetime import datetime

        discovered_str = request.POST.get("discovered_at", "")
        try:
            discovered_at = timezone.make_aware(datetime.strptime(discovered_str, "%Y-%m-%dT%H:%M"))
        except Exception:
            discovered_at = timezone.now()

        breach = BreachReport.objects.create(
            school=school,
            title=request.POST["title"],
            description=request.POST["description"],
            severity=request.POST.get("severity", "medium"),
            data_type_affected=request.POST.get("data_type_affected", "personal"),
            affected_count=request.POST.get("affected_count", 0),
            discovered_at=discovered_at,
            immediate_action=request.POST.get("immediate_action", ""),
            containment_action=request.POST.get("containment_action", ""),
            notification_text=request.POST.get("notification_text", ""),
            reported_by=request.user,
        )
        # AuditLog
        from core.models import AuditLog

        AuditLog.log(
            user=request.user,
            action="create",
            model_name="other",
            object_id=str(breach.pk),
            object_repr=f"BreachReport: {breach.title}",
            school=school,
            request=request,
        )
        return redirect("breach:detail", pk=breach.pk)

    now_str = timezone.now().strftime("%Y-%m-%dT%H:%M")
    return render(
        request,
        "breach/form.html",
        {
            "now": now_str,
            "ncsa_template": NCSA_TEMPLATE.format(
                date=timezone.now().date(),
                title="",
                discovered_at="",
                data_type="",
                affected_count="",
                immediate_action="",
                containment="",
            ),
        },
    )


@login_required
def detail(request, pk):
    if not _admin_only(request.user):
        return HttpResponseForbidden("للمدير فقط")
    breach = get_object_or_404(BreachReport, pk=pk, school=request.user.get_school())
    return render(request, "breach/detail.html", {"breach": breach})


@login_required
def update_status(request, pk):
    if not _admin_only(request.user):
        return HttpResponseForbidden("للمدير فقط")
    if request.method != "POST":
        return redirect("breach:detail", pk=pk)

    breach = get_object_or_404(BreachReport, pk=pk, school=request.user.get_school())
    new_status = request.POST.get("status")

    if new_status in dict(BreachReport.STATUS):
        breach.status = new_status
        if new_status == "notified":
            breach.ncsa_notified_at = timezone.now()
        if new_status == "resolved":
            breach.resolved_at = timezone.now()
        breach.save()

    return redirect("breach:detail", pk=pk)


@login_required
def breach_pdf(request, pk):
    breach = get_object_or_404(BreachReport, pk=pk, school=request.user.get_school())
    from django.template.loader import render_to_string

    from core.pdf_utils import render_pdf

    html = render_to_string(
        "breach/pdf_report.html",
        {
            "breach": breach,
            "generated_at": timezone.now(),
            "generated_by": request.user,
        },
    )
    return render_pdf(html, f"breach_{breach.pk}.pdf")
