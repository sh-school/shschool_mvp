"""قراءةُ الخارطة — لا كتابةَ هنا ولا تحقّق."""

from __future__ import annotations

from django.db.models import QuerySet

from roadmap.models import (
    RoadmapChecklistItem,
    RoadmapDecision,
    RoadmapItem,
    RoadmapKpi,
    RoadmapMeta,
    RoadmapRisk,
)


def items() -> QuerySet[RoadmapItem]:
    return RoadmapItem.objects.all()


def kpis() -> QuerySet[RoadmapKpi]:
    return RoadmapKpi.objects.all()


def decisions() -> QuerySet[RoadmapDecision]:
    return RoadmapDecision.objects.all()


def risks() -> QuerySet[RoadmapRisk]:
    return RoadmapRisk.objects.all()


def checklist() -> QuerySet[RoadmapChecklistItem]:
    return RoadmapChecklistItem.objects.all()


def meta_data() -> dict[str, object]:
    """محتوى الوثيقة المفردة، أو قاموسٌ فارغٌ قبل أوّل استيراد."""
    doc = RoadmapMeta.objects.filter(key=RoadmapMeta.KEY).first()
    return dict(doc.data) if doc else {}


def next_new_item_code() -> str:
    """`N-001`، `N-002`… للبنود المضافة من الواجهة — التالي بعد أكبر رقمٍ مستعمَل."""
    used = RoadmapItem.objects.filter(code__regex=r"^N-[0-9]+$").values_list("code", flat=True)
    return f"N-{max((int(c[2:]) for c in used), default=0) + 1:03d}"


def next_item_sort_order() -> int:
    top = RoadmapItem.objects.order_by("-sort_order").values_list("sort_order", flat=True).first()
    return (top or 0) + 1


def item_by_code(code: str) -> RoadmapItem | None:
    return RoadmapItem.objects.filter(code=code).first()


def decision_by_code(code: str) -> RoadmapDecision | None:
    return RoadmapDecision.objects.filter(code=code).first()


def checklist_by_code(code: str) -> RoadmapChecklistItem | None:
    return RoadmapChecklistItem.objects.filter(code=code).first()
