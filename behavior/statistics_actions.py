"""توزيعاتُ إحصاء السلوك: التجميعُ في سطور، وتوزيعُ الإجراءات المتّخذة (W-20261107-017)."""

from __future__ import annotations

from typing import Any

from django.db.models import Count, QuerySet

from behavior.models import BehaviorInfraction

NO_ACTION_LABEL = "لم يُتخذ إجراء"


def tally(counter: dict[Any, int], labels: dict[Any, str], fallback: str) -> list[dict[str, Any]]:
    """سطورُ توزيعٍ مرتّبةٌ بالأكثر؛ ومن لا اسمَ له (مفتاحُه غائبٌ من `labels`) يُجمع في سطرٍ مستقلّ آخرَ القائمة."""
    rows: dict[str, int] = {}
    for key, count in counter.items():
        label = labels.get(key, fallback)
        rows[label] = rows.get(label, 0) + count
    ordered = sorted(rows.items(), key=lambda item: (item[0] == fallback, -item[1], item[0]))
    return [{"label": label, "count": count} for label, count in ordered if count]


def action_distributions(period_qs: QuerySet) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """(توزيعُ النوع التأديبيّ، توزيعُ الخطوة التصاعديّة) — لا نصُّ `action_taken` المشفّر.

    فارغُ النوع وخطوةُ 0 سطرُ «لم يُتخذ إجراء» المستقلّ فيبقى مجموعُ كلّ توزيعٍ يساوي إجماليَّ المدّة.
    """
    types = {k: v for k, v in BehaviorInfraction.DISCIPLINARY_ACTION_CHOICES if k}
    steps = {k: v for k, v in BehaviorInfraction.ESCALATION_STEP_CHOICES if k}
    by_type = {
        r["disciplinary_action_type"]: r["n"]
        for r in period_qs.values("disciplinary_action_type").annotate(n=Count("id"))
    }
    by_step = {
        r["escalation_step"]: r["n"]
        for r in period_qs.values("escalation_step").annotate(n=Count("id"))
    }
    return tally(by_type, types, NO_ACTION_LABEL), tally(by_step, steps, NO_ACTION_LABEL)
