"""لوحةُ «الخارطةُ وقراراتُك» — ملخّصٌ من جداول الخارطة بلا تكرارها (التفاصيلُ في `/roadmap/`).

قراءةُ القرص = نسبةُ البنود المُغلَقة من غير المؤجَّلة. الأحمرُ لا يقع هنا (الخارطةُ خطّةٌ لا نظامٌ حيّ):
بندٌ محجوبٌ أو قرارٌ مفتوحٌ = «انتبه» يدلّك على ما ينتظر قرارَك.
"""

from __future__ import annotations

from django.db.models import Count

from command_center import contract
from command_center.collectors.publish import publish
from roadmap.models import DecisionStatus, ItemStatus, RoadmapDecision, RoadmapItem

PANEL = "roadmap"


def collect() -> None:
    counts = dict(RoadmapItem.objects.values_list("status").annotate(n=Count("pk")))
    total = sum(counts.values())
    deferred = counts.get(ItemStatus.DEFERRED, 0)
    done = counts.get(ItemStatus.DONE, 0)
    blocked = counts.get(ItemStatus.BLOCKED, 0)
    doing = counts.get(ItemStatus.DOING, 0)
    live = total - deferred
    open_decisions = RoadmapDecision.objects.filter(status=DecisionStatus.OPEN).count()
    if not total:
        status, headline, gauge = contract.WARN, "لا بنودَ في الخارطة", None
    else:
        status = contract.WARN if blocked or open_decisions else contract.OK
        headline = f"{done} من {live} بنداً مُغلَق"
        gauge = 100 * done / live if live else 0
    publish(
        PANEL,
        status=status,
        headline=headline,
        gauge=gauge,
        metrics=(
            ("قيد التنفيذ", doing),
            ("محجوب", blocked),
            ("قراراتٌ بانتظارك", open_decisions),
            ("مؤجَّل", deferred),
        ),
    )
