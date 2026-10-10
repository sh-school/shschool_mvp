"""قياساتُ صحّة الخارطة — قراءةٌ فقط، بلا هجرةٍ ولا كتابة (W-20261009-026، الموجة 1 من تجويد /roadmap/).

أربعةُ أمورٍ كانت خافيةً عن عين المالك والمايسترو، تُحسب هنا من جداول الخارطة نفسِها ولا تُخزَّن:

- **عمرُ القرار المفتوح**: أيّامٌ منذ ظهر القرارُ في الخارطة (`created_at`)؛ يُلوَّن بعد `DECISION_STALE_DAYS`.
  القرارُ لا يحمل تاريخَ «طُرح» مستقلّاً، فالعمرُ هنا عمرُه في الخارطة لا عمرُ السؤال عند صاحبه.
- **مغلقٌ بلا مرجع**: بندٌ حالتُه «مُغلَق» وليس في `pr` رقمُ طلب ولا في `note` ما يدلّ على دليلٍ (رقمُ طلب `#N`، قرارٌ `D-…`،
  بطاقةٌ `W-…`، مؤشّرٌ `…K1`) — القاعدةُ «لا يُغلَق بندٌ إلّا بدليل». و`ref` **ليس** دليلاً: هو مصدرُ البند في الخطّة لا إغلاقُه.
  وبنودُ الأرشيف (`src=DONE`) أُغلقت قبل القاعدة، فتُعدّ على حدةٍ ولا تدخل القائمة الحمراء.
- **بطاقاتُ الدفتر** (routed بلا حامل وأعمارُها وانحرافُ الدفتر عن الخارطة): الدفترُ خارج المنصّة (`delivery_manager_work`) ولا يبلغ
  الإنتاج، فلا تقرؤه الصفحة بل **لقطةً** تُوضع في وثيقة الخارطة (`RoadmapMeta.data["ledger"]`) من `roadmap_drift --json`
  (`ledger_health.py`). ولا لقطةَ = «غير مقيس» لا صفراً.
- **معاني الأرقام والشارات** (`GLOSSARY`): مصدرٌ واحد تقرؤه الصفحةُ تلميحاً على كلّ رقمٍ وشارة وجدولاً في «القواعد والتعريفات».
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from django.utils import timezone

from roadmap.models import DecisionStatus, ItemStatus, RoadmapDecision, RoadmapItem

#: قرارٌ مفتوحٌ مضى على ظهوره في الخارطة هذا العددُ من الأيّام فأكثر يُلوَّن (قرارُ المالك 10-09).
DECISION_STALE_DAYS = 7
#: لقطةُ الدفتر الأقدمُ من هذا تُوسَم «قياسٌ قديم» ولا تُعرض كأنّها حيّة.
SNAPSHOT_STALE_DAYS = 3
ARCHIVE_SRC = "DONE"

#: دليلُ إغلاقٍ في الملاحظة: طلبٌ #N أو قرارٌ D-… أو بطاقةٌ W-… أو مؤشّرٌ UK1/MK3/…
_EVIDENCE = re.compile(r"#\d{2,6}\b|D-\d+|W-\d{8}-\d+|\b[A-Z]{1,3}K\d+\b")

#: المفتاحُ ← (الاسم، المعنى). كلُّ `tip('…')` في static/js/roadmap.js يجب أن يكون هنا (يحرسه tests/test_roadmap_health.py).
GLOSSARY: dict[str, tuple[str, str]] = {
    "items": ("بنودٌ في الخارطة", "عددُ كلّ البنود بحالاتها كلِّها، المؤجَّلةُ منها والمُغلَقة."),
    "done": (
        "مُغلَق",
        "بنودٌ حالتُها «مُغلَق» من كلّ البنود (المؤجَّلةُ تُحسب في المقام)؛ النسبةُ تحتها من الإجمالي لا من غير المؤجَّل.",
    ),
    "doing": ("قيد التنفيذ", "بنودٌ حالتُها «قيد التنفيذ» الآن."),
    "overdue": (
        "متأخّر عن موعده",
        "بنودٌ ليست مُغلَقةً ولا مؤجَّلةً وتاريخُ نهايتها قبل اليوم. بند بلا تاريخ نهاية لا يُعدّ متأخّراً.",
    ),
    "blocked": ("محجوب", "بنودٌ حالتُها «محجوب»: تنتظر شيئاً خارجها لا يُنجزه صاحبُها."),
    "owner": (
        "ينتظر المالك",
        "بنودٌ علامةُ بوّابتها «المالك» وليست مُغلَقة: لا تتقدّم إلّا بقراره أو إذنه.",
    ),
    "progress": (
        "% تقدّم",
        "تقدّمُ كلّ البنود مرجَّحاً بجهد كلٍّ منها بالأيّام؛ المُغلَق = 100% والمؤجَّلُ لا وزنَ له.",
    ),
    "decisions_open": (
        "قراراتٌ مفتوحة",
        "قراراتٌ لم تُحسم. اللونُ يظهر بعد 7 أيّامٍ من ظهور القرار في الخارطة (لا من طرحه عند صاحبه؛ الحقلُ غيرُ محفوظ).",
    ),
    "decision_age": (
        "عمر القرار",
        "أيّامٌ مضت منذ ظهر القرارُ المفتوح في الخارطة. أصفر: 7 أيّام فأكثر.",
    ),
    "closed_no_ref": (
        "مُغلَق بلا مرجع",
        "بنودٌ مُغلَقة ليس في «طلب الدمج» رقمٌ ولا في ملاحظتها دليلٌ (طلب #N، قرار D-، بطاقة W-، مؤشّر). "
        "بنودُ الأرشيف مستثناة. انقر لتفتح القائمة.",
    ),
    "routed_unheld": (
        "بطاقاتٌ موجَّهةٌ بلا حامل",
        "بطاقاتُ الدفتر بحالة routed وليس لها جلسةٌ حاملة: لا يعرف أحدٌ أنّها عليه. "
        "الدفترُ خارج المنصّة فالرقمُ من لقطةٍ تاريخُها في التلميح؛ «غير مقيس» = لا لقطة.",
    ),
    "ledger_drift": (
        "انحرافُ الدفتر عن الخارطة",
        "طلباتٌ مدموجة تذكرها بطاقاتُ الدفتر ولا يذكرها بندٌ، مع بنودٍ تذكر بطاقةً لا يعرفها الدفتر. "
        "من اللقطة نفسِها؛ التقريرُ الكامل: python manage.py roadmap_drift.",
    ),
    "lane": ("المسار", "نسبةُ التقدّم المرجَّحُ لبنود المسار، وتحتها المُغلَقُ منها من كلّ بنوده."),
    "phase": (
        "المرحلة",
        "بنودُ المرحلة = ما يقع تاريخُ نهايته بين بدايتها ونهايتها، وبجانبه تقدّمُها المرجَّح.",
    ),
    "soon_late": ("متأخّر", "تاريخُ نهاية البند قبل اليوم وهو ليس مُغلَقاً."),
    "soon_date": ("الموعد", "تاريخُ نهاية البند (شهر-يوم) وهو يقع خلال 14 يوماً."),
    "st_todo": ("لم يبدأ", "لم يبدأ العملُ على البند."),
    "st_doing": ("قيد التنفيذ", "العملُ جارٍ؛ الرقمُ بجانبه نسبةُ تقدّمه."),
    "st_done": ("مُغلَق", "أُنجز البند. لا يُغلَق بندٌ إلّا بدليل: رقمُ طلب دمجٍ أو مؤشّرٌ تحرّك."),
    "st_blocked": ("محجوب", "ينتظر شيئاً خارجه."),
    "st_deferred": ("مؤجّل", "أُجّل بقرار؛ خارج النسبة وخارج «متأخّر»."),
    "kpi_unmeasured": ("لم يُقَس", "لا قيمةَ حاليّةً للمؤشّر؛ سببُ الغياب في تلميح مصدره."),
    "kpi_notarget": ("بلا هدف", "للمؤشّر قيمةٌ حاليّة ولا هدفَ يُقارَن به."),
    "kpi_reached": ("بلغ الهدف", "القيمةُ الحاليّةُ بلغت الهدف بحسب اتّجاه المؤشّر."),
    "kpi_onway": (
        "في الطريق",
        "تحرّك المؤشّرُ عن أساسه ولم يبلغ هدفه؛ الشريطُ نسبةُ ما قُطع من الأساس إلى الهدف.",
    ),
    "kpi_base": ("عند الأساس", "القيمةُ الحاليّةُ لم تتحرّك عن خطّ الأساس."),
    "dc_open": ("مفتوح", "القرارُ لم يُحسم بعدُ."),
    "dc_decided": ("محسوم", "حُسم القرار وسُجّل تاريخُه."),
    "dc_deferred": ("مؤجَّل", "أُجّل حسمُ القرار."),
    "risk_prob": ("احتمال", "احتمالُ وقوع الخطر كما قدّره صاحبُه."),
    "risk_impact": ("أثر", "أثرُ الخطر إن وقع كما قدّره صاحبُه."),
}


def has_closing_evidence(item: RoadmapItem) -> bool:
    """في `pr` رقمٌ، أو في `note` رقمُ طلبٍ/قرارٌ/بطاقةٌ/مؤشّر."""
    return bool(item.pr.strip()) or bool(_EVIDENCE.search(item.note or ""))


def closed_without_reference(items: Iterable[RoadmapItem]) -> tuple[list[RoadmapItem], int]:
    """(بنودٌ مُغلَقة بلا دليل خارج الأرشيف، عددُ ما في الأرشيف منها)."""
    red: list[RoadmapItem] = []
    archived = 0
    for item in items:
        if item.status != ItemStatus.DONE or has_closing_evidence(item):
            continue
        if item.src == ARCHIVE_SRC:
            archived += 1
        else:
            red.append(item)
    return red, archived


def open_decision_ages(decisions: Iterable[RoadmapDecision], today: date) -> dict[str, int]:
    """رمزُ كلّ قرارٍ مفتوح ← أيّامُه في الخارطة (لا سالب)."""
    return {
        d.code: max(0, (today - timezone.localtime(d.created_at).date()).days)
        for d in decisions
        if d.status == DecisionStatus.OPEN
    }


def ledger_snapshot(meta: Mapping[str, Any], today: date) -> dict[str, Any] | None:
    """لقطةُ الدفتر من وثيقة الخارطة، أو `None` (غير مقيس) إن غابت أو فسد شكلُها؛ و`stale` إن قدمت.

    الشكلُ المقبول يُنتجه `ledger_health.ledger_summary`؛ أيُّ حقلٍ غيرِ عددٍ صحيحٍ يُسقط اللقطةَ كلَّها فلا يُعرض نصفُ رقم.
    """
    raw = meta.get("ledger")
    if not isinstance(raw, Mapping):
        return None
    numbers = ("routed", "routedNoHolder", "routedOldestDays", "total")
    if not all(isinstance(raw.get(k), int) and not isinstance(raw.get(k), bool) for k in numbers):
        return None
    as_of = raw.get("asOf")
    try:
        age = (today - date.fromisoformat(str(as_of))).days
    except ValueError:
        return None
    by_state = raw.get("byState")
    drift = raw.get("drift")
    return {
        **{k: raw[k] for k in numbers},
        "asOf": str(as_of),
        "ageDays": max(0, age),
        "stale": age > SNAPSHOT_STALE_DAYS,
        "byState": dict(by_state) if isinstance(by_state, Mapping) else {},
        "drift": dict(drift) if isinstance(drift, Mapping) else None,
    }


def page_health(
    items: list[RoadmapItem],
    decisions: list[RoadmapDecision],
    meta: Mapping[str, Any],
    today: date,
) -> dict[str, Any]:
    """كلُّ ما تحتاجه الواجهةُ مما لا يُشتقّ من الصفوف في المتصفّح."""
    red, archived = closed_without_reference(items)
    return {
        "staleDays": DECISION_STALE_DAYS,
        "decisionAges": open_decision_ages(decisions, today),
        "closedNoRef": [o.code for o in red],
        "closedNoRefArchived": archived,
        "ledger": ledger_snapshot(meta, today),
    }


def glossary_payload() -> dict[str, dict[str, str]]:
    return {key: {"name": name, "meaning": meaning} for key, (name, meaning) in GLOSSARY.items()}
