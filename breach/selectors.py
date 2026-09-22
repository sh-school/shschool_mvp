"""breach/selectors.py — قراءاتُ وحدة خرق البيانات.

القراءةُ هنا والكتابةُ في `services.py`، وتبقى العروضُ رقيقةً (سقّاطةُ الطبقات `tests/test_layering.py`).
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import AuditLog, BreachReport

_STATUS = dict(BreachReport.STATUS)
OPEN_STATES = ["discovered", "assessing"]


def school_reports(school):
    """تقاريرُ المدرسة، الأحدثُ اكتشافاً أوّلاً."""
    return BreachReport.objects.filter(school=school).order_by("-discovered_at")


def dashboard_stats(reports) -> dict:
    """أرقامُ اللوحة في استعلامٍ واحد — و«تجاوز المهلة» بشرط `BreachReport.is_overdue` نفسِه في القاعدة."""
    return reports.aggregate(
        active=Count("id", filter=Q(status__in=OPEN_STATES)),
        notified=Count("id", filter=Q(status="notified")),
        resolved=Count("id", filter=Q(status="resolved")),
        overdue=Count(
            "id",
            filter=Q(ncsa_deadline__lt=timezone.now()) & Q(status__in=OPEN_STATES),
        ),
    )


def breach_for_school(pk, school) -> BreachReport:
    """خرقٌ بمعرّفه في مدرسة الطلب — أو 404 (لا يُعرض خرقُ مدرسةٍ أخرى)."""
    return get_object_or_404(BreachReport, pk=pk, school=school)


def history_for(breach: BreachReport, limit: int = 15) -> list[dict]:
    """سجلُّ ما جرى على الخرق من `AuditLog`: من فعل ماذا ومتى (الأحدثُ أوّلاً)."""
    rows = (
        AuditLog.objects.filter(object_id=str(breach.pk), model_name="other")
        .select_related("user")
        .order_by("-timestamp")[:limit]
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
