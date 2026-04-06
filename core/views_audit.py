# ══════════════════════════════════════════════════════════════════════
# core/views_audit.py
# PermissionAuditLog — صفحة سجل تغييرات الصلاحيات للمدير
# ══════════════════════════════════════════════════════════════════════

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models.permission_audit import PermissionAuditLog
from .permissions import role_required


@login_required
@role_required("principal", "vice_admin", "vice_academic")
def permission_audit_log(request):
    """
    عرض سجل كامل لتغييرات الصلاحيات والأدوار في المدرسة.
    متاح للمدير ونائبيه (الإداري والأكاديمي) فقط.
    يدعم التصفية بـ: نوع الإجراء، نطاق التاريخ، البحث بالاسم.
    """
    school = request.user.get_school()

    # ── بناء الـ queryset الأساسي ──────────────────────────────────
    logs = PermissionAuditLog.objects.filter(school=school).select_related("actor", "target")

    # ── فلتر نوع الإجراء ──────────────────────────────────────────
    action = request.GET.get("action", "").strip()
    if action:
        logs = logs.filter(action=action)

    # ── فلتر نطاق التاريخ ─────────────────────────────────────────
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    if date_from:
        logs = logs.filter(created_at__date__gte=date_from)
    if date_to:
        logs = logs.filter(created_at__date__lte=date_to)

    # ── فلتر البحث بالاسم (المنفّذ أو المستهدف) ───────────────────
    search = request.GET.get("q", "").strip()
    if search:
        logs = logs.filter(actor__full_name__icontains=search) | PermissionAuditLog.objects.filter(
            school=school,
            target__full_name__icontains=search,
        ).select_related("actor", "target")
        # إعادة تطبيق الفلاتر الأخرى على نتائج البحث
        if action:
            logs = logs.filter(action=action)
        if date_from:
            logs = logs.filter(created_at__date__gte=date_from)
        if date_to:
            logs = logs.filter(created_at__date__lte=date_to)

    logs = logs.order_by("-created_at")[:200]

    ctx = {
        "logs": logs,
        "actions": PermissionAuditLog.ACTIONS,
        "selected_action": action,
        "date_from": date_from,
        "date_to": date_to,
        "search": search,
        "total_count": logs.count() if hasattr(logs, "count") else len(logs),
    }

    # ── HTMX partial response ──────────────────────────────────────
    if request.htmx:
        return render(request, "core/partials/audit_log_table.html", ctx)

    return render(request, "core/permission_audit_log.html", ctx)
