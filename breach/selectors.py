"""breach/selectors.py — قراءاتُ وحدة خرق البيانات.

القراءةُ هنا والكتابةُ في `services.py`، وتبقى العروضُ رقيقةً (سقّاطةُ الطبقات `tests/test_layering.py`).
"""

from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import AuditLog, BreachReport

_STATUS = dict(BreachReport.STATUS)
_INDIVIDUALS = dict(BreachReport.INDIVIDUALS_STATUS)
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
        # أفرادٌ واجبٌ إخطارُهم ولم يُخطَروا، ومنها ما فات موعدُه — بشرط `BreachReport.individuals_overdue` نفسِه.
        individuals_pending=Count("id", filter=Q(individuals_status="required")),
        individuals_overdue=Count(
            "id",
            filter=Q(individuals_status="required", individuals_deadline__lt=timezone.now()),
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
        elif "individuals_status" in changes:
            what = f"إخطار الأفراد: {_INDIVIDUALS.get(changes['individuals_status'], '—')}"
            if changes.get("notified_after_deadline"):
                what += " (بعد الموعد)"
        elif "to" in changes:
            what = (
                f"الحالة: {_STATUS.get(changes['from'], '—')} ← {_STATUS.get(changes['to'], '—')}"
            )
            if changes.get("closed_without_ncsa_notice"):
                what += " (بلا إشعار NCSA)"
            if changes.get("ncsa_notice_stage") == "initial":
                what += " (إشعار مبدئي)"
        elif "ncsa_notice_stage" in changes:
            what = "استُكمل إشعار NCSA" + (
                " (بعد الموعد المعلَن)" if changes.get("completed_after_due") else ""
            )
        else:
            what = "تعديل بيانات الخرق"
        who = getattr(row.user, "full_name", "") or "—"
        out.append({"what": what, "who": who, "at": row.timestamp})
    return out
