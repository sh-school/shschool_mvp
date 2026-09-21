"""استيرادُ لقطة الخارطة — `update_or_create` بالرمز، ذرّيّاً، فتكرارُه لا يُضاعف صفّاً.

يُتحقَّق من اللقطة كلِّها قبل أيّ كتابة (فلا يُكتب نصفُها)، ويُبلَّغ بعدد المُنشأ والمُحدَّث
لكلّ نوع، ويُكتب في سجلّ التدقيق **العددُ** لا المحتوى. والملفّاتُ ذاتُ الاسم
`*_services.py` طبقةُ كتابةٍ كـ`services.py` عند حارس الطبقات.

**ما عُدِّل من الواجهة لا يُمحى:** الصفحةُ نفسُها تأمر بإعادة الاستيراد بعد كلّ قياس، فلو كتب
الاستيرادُ فوق الملاحظات والحالةَ والتقدّمَ والتواريخَ وتأشيراتِ الفحص لضاع عملُ المطوّر في
كلّ مرّة. فالصفوفُ **الموجودةُ** لا تُمسّ حقولُها المحرَّرةُ (`_HAND_EDITED`) — تُكتب فقط عند
الإنشاء — ما لم يُطلَب `overwrite=True` صراحةً. والمؤشّراتُ تُكتب دائماً: تحديثُها هو الغرض.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.db import transaction

from core.models import AuditLog
from roadmap.models import (
    DecisionStatus,
    ItemStatus,
    KpiDirection,
    RoadmapChecklistItem,
    RoadmapDecision,
    RoadmapItem,
    RoadmapKpi,
    RoadmapMeta,
    RoadmapRisk,
)
from roadmap.services import RoadmapError, _clean_effort, stamp_user


@dataclass
class ImportReport:
    """أعدادُ ما أُنشئ وما حُدِّث لكلّ نوع."""

    created: dict[str, int] = field(default_factory=dict)
    updated: dict[str, int] = field(default_factory=dict)

    def count(self, kind: str, created: bool) -> None:
        bucket = self.created if created else self.updated
        bucket[kind] = bucket.get(kind, 0) + 1

    def lines(self) -> list[str]:
        kinds = sorted(set(self.created) | set(self.updated))
        return [
            f"{kind}: أُنشئ {self.created.get(kind, 0)} - حُدِّث {self.updated.get(kind, 0)}"
            for kind in kinds
        ]


_KPI_KNOWN = frozenset(
    {
        "code", "lane", "name", "baseline", "current", "target", "baselineText", "targetText",
        "dir", "unit", "source", "why", "textMode", "measuredAt", "history", "order",
    }
)  # fmt: skip
#: حقولُ الصفوف المحرَّرة من الواجهة (`ITEM_EDITABLE` وأخواتُها) بأسمائها في النموذج.
_HAND_EDITED: dict[str, frozenset[str]] = {
    "items": frozenset(
        {"status", "progress", "start_date", "end_date", "date_basis", "note", "pr"}
    ),
    "decisions": frozenset({"status", "decision_date"}),
    "checklist": frozenset({"done"}),
}
_SNAPSHOT_KINDS = ("items", "kpis", "decisions", "risks", "checklist")


def _text(record: Mapping[str, Any], key: str) -> str:
    value = record.get(key, "")
    return "" if value is None else str(value)


def _order(record: Mapping[str, Any]) -> int:
    value = record.get("order") or 0
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _number(record: Mapping[str, Any], key: str, where: str, errors: list[str]) -> float | None:
    value = record.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int | float):
        errors.append(f"{where}: {key} ليس رقماً")
        return None
    return float(value)


def _snapshot_date(
    record: Mapping[str, Any], key: str, where: str, errors: list[str]
) -> date | None:
    value = record.get(key)
    if value in (None, ""):
        return None
    try:
        return date.fromisoformat(str(value))
    except ValueError:
        errors.append(f"{where}: {key} تاريخٌ غيرُ صالح")
        return None


def _item_defaults(rec: Mapping[str, Any], where: str, errors: list[str]) -> dict[str, Any]:
    status = _text(rec, "status") or ItemStatus.TODO
    if status not in ItemStatus.values:
        errors.append(f"{where}: حالةٌ غيرُ معروفة")
    progress = rec.get("progress", 0)
    if isinstance(progress, bool) or not isinstance(progress, int) or not 0 <= progress <= 100:
        errors.append(f"{where}: progress ليس عدداً بين 0 و100")
        progress = 0
    effort_errors: dict[str, str] = {}
    raw_effort = rec.get("effort")
    effort = 1.0 if raw_effort in (None, "") else _clean_effort(raw_effort, effort_errors)
    errors.extend(f"{where}: effort — {reason}" for reason in effort_errors.values())
    defaults: dict[str, Any] = {
        "src": _text(rec, "src"),
        "lane": _text(rec, "lane"),
        "title": _text(rec, "title"),
        "status": status,
        "progress": progress,
        "start_date": _snapshot_date(rec, "start", where, errors),
        "end_date": _snapshot_date(rec, "end", where, errors),
        "date_basis": _text(rec, "dateBasis"),
        "effort": effort,
        "deps": _text(rec, "deps"),
        "criterion": _text(rec, "criterion"),
        "note": _text(rec, "note"),
        "gate": _text(rec, "gate"),
        "ref": _text(rec, "ref"),
        "sort_order": _order(rec),
    }
    if "pr" in rec:  # لا يمحو استيرادٌ بلا الحقل ما سُجّل من الواجهة
        defaults["pr"] = _text(rec, "pr")
    return defaults


def _kpi_defaults(rec: Mapping[str, Any], where: str, errors: list[str]) -> dict[str, Any]:
    direction = _text(rec, "dir") or KpiDirection.DOWN
    if direction not in KpiDirection.values:
        errors.append(f"{where}: اتّجاهٌ غيرُ معروف")
    history = rec.get("history") or []
    if not isinstance(history, list):
        errors.append(f"{where}: history ليس قائمة")
        history = []
    return {
        "lane": _text(rec, "lane"),
        "name": _text(rec, "name"),
        "baseline": _number(rec, "baseline", where, errors),
        "current": _number(rec, "current", where, errors),
        "target": _number(rec, "target", where, errors),
        "baseline_text": _text(rec, "baselineText"),
        "target_text": _text(rec, "targetText"),
        "direction": direction,
        "unit": _text(rec, "unit"),
        "source": _text(rec, "source"),
        "why": _text(rec, "why"),
        "text_mode": bool(rec.get("textMode", False)),
        "measured_at": _snapshot_date(rec, "measuredAt", where, errors),
        "history": history,
        "extra": {k: v for k, v in rec.items() if k not in _KPI_KNOWN},
        "sort_order": _order(rec),
    }


def _decision_defaults(rec: Mapping[str, Any], where: str, errors: list[str]) -> dict[str, Any]:
    status = _text(rec, "status") or DecisionStatus.OPEN
    if status not in DecisionStatus.values:
        errors.append(f"{where}: حالةٌ غيرُ معروفة")
    return {
        "src": _text(rec, "src"),
        "title": _text(rec, "title"),
        "status": status,
        "decider": _text(rec, "decider"),
        "due": _text(rec, "due"),
        "decision_date": _snapshot_date(rec, "date", where, errors),
        "blocks": _text(rec, "blocks"),
        "options": _text(rec, "options"),
        "recommendation": _text(rec, "recommendation"),
        "sort_order": _order(rec),
    }


def _risk_defaults(rec: Mapping[str, Any], where: str, errors: list[str]) -> dict[str, Any]:
    return {
        "src": _text(rec, "src"),
        "risk": _text(rec, "risk"),
        "prob": _text(rec, "prob"),
        "impact": _text(rec, "impact"),
        "mitigation": _text(rec, "mitigation"),
        "sort_order": _order(rec),
    }


def _checklist_defaults(rec: Mapping[str, Any], where: str, errors: list[str]) -> dict[str, Any]:
    return {
        "src": _text(rec, "src"),
        "text": _text(rec, "text"),
        "done": bool(rec.get("done", False)),
        "sort_order": _order(rec),
    }


#: نوعٌ ← (النموذج، مفتاحُ الرمز في اللقطة، دالّةُ القيم)
_IMPORT_PLAN: tuple[tuple[str, Any, str, Any], ...] = (
    ("items", RoadmapItem, "id", _item_defaults),
    ("kpis", RoadmapKpi, "code", _kpi_defaults),
    ("decisions", RoadmapDecision, "id", _decision_defaults),
    ("risks", RoadmapRisk, "id", _risk_defaults),
    ("checklist", RoadmapChecklistItem, "id", _checklist_defaults),
)

_Row = tuple[str, Any, str, dict[str, Any]]


def _build_import(data: Mapping[str, Any]) -> tuple[list[_Row], list[str]]:
    """يبني القيمَ ويتحقّق منها كلَّها قبل أيّ كتابة — فلا يُكتب نصفُ لقطة."""
    errors: list[str] = []
    rows: list[_Row] = []
    for kind, model, key, build in _IMPORT_PLAN:
        records = data.get(kind, [])
        if not isinstance(records, list):
            errors.append(f"{kind}: ليست قائمة")
            continue
        seen: set[str] = set()
        for index, rec in enumerate(records):
            if not isinstance(rec, Mapping) or not rec.get(key):
                errors.append(f"{kind}[{index}]: سجلٌّ بلا {key}")
                continue
            code = str(rec[key])
            if code in seen:
                errors.append(f"{kind}: الرمزُ {code} مكرَّر")
                continue
            seen.add(code)
            rows.append((kind, model, code, build(rec, f"{kind}/{code}", errors)))
    return rows, errors


def import_snapshot(data: object, *, user: Any = None, overwrite: bool = False) -> ImportReport:
    """يستورد لقطةَ الخارطة: update_or_create بالرمز، ذرّيّاً، بتدقيقٍ بالأعداد لا بالمحتوى.

    `overwrite=False` (الافتراضيّ): الصفوفُ الموجودةُ تُحدَّث حقولُها البنيويّةُ وحدَها ولا تُمسّ
    حقولُها المحرَّرةُ من الواجهة (`_HAND_EDITED`). `overwrite=True` يعيدها إلى ما في اللقطة.
    """
    if not isinstance(data, Mapping) or not any(kind in data for kind in _SNAPSHOT_KINDS):
        raise RoadmapError({"snapshot": "لقطةٌ بلا items/kpis/decisions/risks/checklist"})
    rows, errors = _build_import(data)
    meta = data.get("meta")
    if meta is not None and not isinstance(meta, Mapping):
        errors.append("meta: ليست كائناً")
    if errors:
        raise RoadmapError({f"خطأ {i + 1}": e for i, e in enumerate(errors[:20])})

    stamp = stamp_user(user)
    report = ImportReport()
    with transaction.atomic():
        for kind, model, code, defaults in rows:
            if not overwrite and model.objects.filter(code=code).exists():
                protected = _HAND_EDITED.get(kind, frozenset())
                defaults = {k: v for k, v in defaults.items() if k not in protected}
            _, created = model.objects.update_or_create(
                code=code, defaults={**defaults, "updated_by": stamp}
            )
            report.count(kind, created)
        if isinstance(meta, Mapping):
            _, created = RoadmapMeta.objects.update_or_create(
                key=RoadmapMeta.KEY, defaults={"data": dict(meta), "updated_by": stamp}
            )
            report.count("meta", created)
        AuditLog.log(  # type: ignore[no-untyped-call]
            user=stamp,
            action="update",
            model_name="other",
            object_id="roadmap",
            object_repr="خارطة التجويد: استيرادُ لقطة",
            changes={
                "event": "roadmap_snapshot_import",
                "created": report.created,
                "updated": report.updated,
                "overwrite": overwrite,
            },
        )
    return report
