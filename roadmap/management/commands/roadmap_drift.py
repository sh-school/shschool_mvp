"""حارسُ الانحراف بين دفتر العمل والخارطة — تقريرٌ فقط، لا كتابةَ في أيّ قاعدةٍ ولا ملف (W-20261009-026).

    python manage.py roadmap_drift [--ledger <events.jsonl>] [--limit 20] [--json]

المسارُ الافتراضيّ من متغيّر البيئة `LEDGER_PATH` (كأداة الدفتر). و`--json` يطبع **لقطةً** بالشكل الذي تقرؤه صفحةُ `/roadmap/`
من `RoadmapMeta.data["ledger"]` (`health.ledger_snapshot`) — يضعها في الوثيقة من يملك مزامنة الخارطة (0701) ضمن هجرتها؛ هذا
الأمرُ لا يضعها. يخرج دائماً بـ0 (تقريرٌ لا بوّابة)، وبـ1 إن تعذّرت القراءة.
"""

from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandError, CommandParser
from django.utils import timezone

from roadmap import ledger_health, selectors

LABELS = {
    "prsWithoutItem": "طلباتٌ مدموجةٌ تذكرها بطاقاتٌ ولا يذكرها أيُّ بند",
    "mergedWithoutPr": "بطاقاتٌ مدموجةٌ/منشورةٌ بلا رقمِ طلبٍ في ملاحظاتها (لا تُطابَق آليّاً)",
    "closedWithoutReference": "بنودٌ مُغلَقةٌ بلا دليل (بلا رقم طلب ولا قرارٍ ولا بطاقةٍ في ملاحظتها)",
    "itemsWithUnknownCard": "بنودٌ تذكر بطاقةً W-… لا يعرفها الدفتر",
}


def _line(key: str, row: Any) -> str:
    if key == "prsWithoutItem":
        return f"  #{row['pr']}  ← {row['card']}"
    if key == "itemsWithUnknownCard":
        return f"  {row['item']}  ← {row['card']}"
    return f"  {row}"


class Command(BaseCommand):
    help = "تقريرُ انحراف الدفتر عن الخارطة (قراءةٌ فقط) ولقطةُ الدفتر بـ--json"

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--ledger", help="مسارُ events.jsonl (الافتراضيّ: LEDGER_PATH)")
        parser.add_argument("--limit", type=int, default=20, help="أقصى ما يُعرض من كلّ صنف")
        parser.add_argument(
            "--json", dest="as_json", action="store_true", help="يطبع لقطةَ الدفتر JSON بدل التقرير"
        )

    def handle(
        self, *args: Any, ledger: str | None, limit: int, as_json: bool, **options: Any
    ) -> None:
        raw = ledger or os.environ.get("LEDGER_PATH")
        if not raw:
            raise CommandError("لم يُحدَّد الدفتر: مرّر --ledger <events.jsonl> أو اضبط LEDGER_PATH")
        path = Path(raw)
        if not path.is_file():
            raise CommandError(f"لا ملفَّ في {path}")
        try:
            cards = ledger_health.reduce_cards(ledger_health.read_events(path))
        except (OSError, ValueError) as exc:
            raise CommandError(f"تعذّرت قراءةُ الدفتر: {exc}") from exc
        today = timezone.localdate()
        report = ledger_health.drift_report(cards, list(selectors.items()))
        if as_json:
            self._snapshot(cards, report, today)
            return
        self._report(cards, report, today, limit)

    def _snapshot(self, cards: dict[str, Any], report: dict[str, Any], today: date) -> None:
        summary = ledger_health.ledger_summary(cards, today)
        summary["drift"] = ledger_health.drift_counts(report)
        self.stdout.write(_dumps({"ledger": summary}))

    def _report(
        self, cards: dict[str, Any], report: dict[str, Any], today: date, limit: int
    ) -> None:
        summary = ledger_health.ledger_summary(cards, today)
        self.stdout.write(
            f"الدفتر في {today}: {summary['total']} بطاقة؛ routed {summary['routed']} منها "
            f"{summary['routedNoHolder']} بلا حامل (أقدمها {summary['routedOldestDays']} يوماً)."
        )
        self.stdout.write("حدٌّ أدنى للانحراف: المطابقةُ بأرقام الطلبات في ملاحظات البطاقات.")
        for key, label in LABELS.items():
            rows = report[key]
            self.stdout.write(f"\n{label}: {len(rows)}")
            for row in rows[:limit]:
                self.stdout.write(_line(key, row))
            if len(rows) > limit:
                self.stdout.write(f"  … و{len(rows) - limit} أخرى (--limit)")


def _dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)
