"""خدماتُ الخارطة — كلُّ الكتابة والتحقّق والحساب هنا، والعروضُ تستقبل وتردّ.

* **التحديث** (`update_item`، `update_decision`، `set_checklist_done`): يتحقّق من كلّ
  قيمةٍ قبل أيّ كتابة (قائمةٌ بيضاءُ من الحقول، وحالةٌ من المعرَّف، وتقدّمٌ 0..100، وتاريخٌ
  ISO)، ويكتب سطراً في سجلّ التدقيق بما تغيّر وحدَه (قبل/بعد) — لا بالمحتوى كلِّه.
* **الحساب** (`weighted_progress`): الجهدُ × التقدّم، والمؤجَّلُ وزنُه صفر، والمُغلَقُ 100.
  وتنفيذُه في `static/js/roadmap.js` مرآةٌ لهذا؛ والاختبارُ يقيس أنّهما يتّفقان.
* **الاستيراد**: في `import_services.py`.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from datetime import date
from typing import Any

from django.db import IntegrityError, transaction
from django.http import HttpRequest

from core.dashboard_presentation import chunk_for_grid
from core.models import AuditLog
from roadmap import selectors
from roadmap.models import (
    DecisionStatus,
    ItemStatus,
    RoadmapChecklistItem,
    RoadmapDecision,
    RoadmapItem,
    RoadmapKpi,
    RoadmapRisk,
)

#: الحقولُ التي يجوز تحريرُها من الواجهة — ما سواها يُرفض لا يُتجاهَل.
ITEM_EDITABLE = frozenset({"status", "progress", "start", "end", "pr", "note"})
DECISION_EDITABLE = frozenset({"status", "date"})
#: حقولُ البند الجديد — وبعد الإنشاء لا يُحرَّر منها إلّا `ITEM_EDITABLE`.
ITEM_CREATABLE = frozenset(
    {"title", "lane", "status", "start", "end", "effort", "deps", "criterion", "note", "gate", "ref", "pr"}
)
NEW_ITEM_SRC = "NEW"
TITLE_MAX = 500

MANUAL_DATE_BASIS = "محدَّث يدوياً"
NOTE_MAX = 2000
PR_MAX = 64
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_PR_RE = re.compile(r"^[#\w\s,+/.\-،]*$")


class RoadmapError(ValueError):
    """قيمةٌ مرفوضة — `errors` حقلٌ ← سببٌ بالعربيّة، تُعاد كما هي إلى الواجهة."""

    def __init__(self, errors: Mapping[str, str]) -> None:
        super().__init__("؛ ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = dict(errors)


class RoadmapNotFoundError(LookupError):
    """رمزٌ لا يقابله صفّ."""


# ── الحساب ────────────────────────────────────────────────────────────────


def weighted_progress(rows: Iterable[tuple[str, float, float]]) -> int:
    """التقدّمُ المرجَّحُ بالجهد لصفوفٍ `(الحالة، الجهد، التقدّم)`، مقرَّباً إلى أقرب عدد صحيح.

    المؤجَّلُ وزنُه صفر (لا يُحسب لا له ولا عليه)، والجهدُ الفارغُ أو الصفرُ يعادل 1،
    والمُغلَقُ يُحسب 100 مهما كان تقدّمُه المخزَّن. والتقريبُ لأعلى عند المنتصف كما
    يفعل `Math.round` في الواجهة (لا تقريبُ المصرفيّ في `round`).
    """
    total_weight = 0.0
    total = 0.0
    for status, effort, progress in rows:
        weight = 0.0 if status == ItemStatus.DEFERRED else (float(effort) or 1.0)
        total_weight += weight
        total += weight * (100.0 if status == ItemStatus.DONE else float(progress))
    return int(total / total_weight + 0.5) if total_weight else 0


def _progress_of(objects: Iterable[RoadmapItem]) -> int:
    return weighted_progress((o.status, o.effort, o.progress) for o in objects)


# ── التسلسل إلى الشكل الذي تقرؤه الواجهة (نفسُ مفاتيح اللقطة) ─────────────────


def _iso(value: date | None) -> str | None:
    return value.isoformat() if value else None


def _num(value: float | None) -> int | float | None:
    if value is None:
        return None
    return int(value) if float(value).is_integer() else value


def serialize_item(o: RoadmapItem) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": o.code,
        "src": o.src,
        "lane": o.lane,
        "title": o.title,
        "status": o.status,
        "progress": o.progress,
        "start": _iso(o.start_date),
        "end": _iso(o.end_date),
        "dateBasis": o.date_basis,
        "effort": _num(o.effort),
        "deps": o.deps,
        "criterion": o.criterion,
        "note": o.note,
        "gate": o.gate,
        "ref": o.ref,
        "order": o.sort_order,
        "updated": o.updated_at.date().isoformat(),
    }
    if o.pr:
        data["pr"] = o.pr
    return data


def serialize_kpi(o: RoadmapKpi) -> dict[str, Any]:
    data: dict[str, Any] = {
        "code": o.code,
        "lane": o.lane,
        "name": o.name,
        "baseline": _num(o.baseline),
        "current": _num(o.current),
        "target": _num(o.target),
        "baselineText": o.baseline_text,
        "targetText": o.target_text,
        "dir": o.direction,
        "unit": o.unit,
        "source": o.source,
        "why": o.why,
        "textMode": o.text_mode,
        "measuredAt": _iso(o.measured_at),
        "history": o.history,
        "order": o.sort_order,
    }
    data.update(o.extra or {})
    return data


def serialize_decision(o: RoadmapDecision) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": o.code,
        "src": o.src,
        "title": o.title,
        "status": o.status,
        "decider": o.decider,
        "due": o.due,
        "date": _iso(o.decision_date) or "",
        "blocks": o.blocks,
        "recommendation": o.recommendation,
        "order": o.sort_order,
    }
    if o.options:
        data["options"] = o.options
    return data


def serialize_risk(o: RoadmapRisk) -> dict[str, Any]:
    return {
        "id": o.code,
        "src": o.src,
        "risk": o.risk,
        "prob": o.prob,
        "impact": o.impact,
        "mitigation": o.mitigation,
        "order": o.sort_order,
    }


def serialize_checklist(o: RoadmapChecklistItem) -> dict[str, Any]:
    return {"id": o.code, "src": o.src, "text": o.text, "done": o.done, "order": o.sort_order}


def _texts(value: object) -> list[str]:
    return [str(v) for v in value] if isinstance(value, list) else []


def _pairs(value: object, width: int) -> list[list[str]]:
    """صفوفٌ من أزواجٍ أو ثلاثيّاتٍ (المعايير والمسؤوليّات والترقيم) — ما شذّ عن العرض يُهمَل."""
    rows = value if isinstance(value, list) else []
    return [[str(c) for c in r] for r in rows if isinstance(r, list) and len(r) >= width]


def static_sections(meta: Mapping[str, Any]) -> dict[str, Any]:
    """ما لا يتغيّر من الواجهة يُرسم في القالب لا في الجافاسكربت: قوائمُ ضيّقةٌ تُقسَّم أعمدةً.

    القسمةُ في الخدمة لا في القالب (`chunk_for_grid` — معيارُ تخطيط الصفحات)، وكلُّ قائمةٍ
    بعمودين، والمعاييرُ بثلاثة (صفُّها أعرض). والاتّجاهُ في الأعمدة متتابعٌ لا تبادليّ.
    """
    standards = [
        {"domain": r[0], "standard": r[1], "where": r[2], "status": r[3] if len(r) > 3 else ""}
        for r in _pairs(meta.get("standards"), 3)
    ]
    ownership = [{"role": r[0], "who": r[1], "duty": r[2]} for r in _pairs(meta.get("ownership"), 3)]
    mapping = [{"old": r[0], "new": r[1]} for r in _pairs(meta.get("mapping"), 2)]
    return {
        "limits": str(meta.get("limits") or ""),
        "as_of": str(meta.get("asOf") or ""),
        "horizon_end": str(meta.get("horizonEnd") or ""),
        "standards_cols": chunk_for_grid(standards, 3),
        "ownership_cols": chunk_for_grid(ownership, 2),
        "mapping_cols": chunk_for_grid(mapping, 2),
        **{
            f"{key}_cols": chunk_for_grid(_texts(meta.get(source)), 2)
            for key, source in (
                ("rules", "rules"),
                ("dod", "dod"),
                ("critical", "criticalPath"),
                ("windows", "windows"),
                ("rollback", "rollback"),
                ("sources", "sources"),
            )
        },
    }


def page_context() -> dict[str, Any]:
    """كلُّ ما تحتاجه الصفحةُ في استعلاماتٍ ست، والتقدّمُ العامّ محسوباً هنا لا في القالب."""
    item_rows = list(selectors.items())
    meta = selectors.meta_data()
    return {
        "overall_progress": _progress_of(item_rows),
        "item_count": len(item_rows),
        **static_sections(meta),
        "roadmap_data": {
            "meta": meta,
            "items": [serialize_item(o) for o in item_rows],
            "kpis": [serialize_kpi(o) for o in selectors.kpis()],
            "decisions": [serialize_decision(o) for o in selectors.decisions()],
            "risks": [serialize_risk(o) for o in selectors.risks()],
            "checklist": [serialize_checklist(o) for o in selectors.checklist()],
        },
    }


# ── التحقّق ───────────────────────────────────────────────────────────────


def _clean_date(value: object, field_name: str, errors: dict[str, str]) -> date | None:
    """تاريخٌ ISO صارم YYYY-MM-DD، والفراغُ يمسح — وغيرُ ذلك يُسجَّل خطأً."""
    if value is None or value == "":
        return None
    if not isinstance(value, str) or not _DATE_RE.match(value):
        errors[field_name] = "صيغةُ التاريخ YYYY-MM-DD"
        return None
    try:
        parsed = date.fromisoformat(value)
    except ValueError:
        errors[field_name] = "تاريخٌ غيرُ موجود"
        return None
    if not 2020 <= parsed.year <= 2100:
        errors[field_name] = "تاريخٌ خارجَ المدى المعقول"
        return None
    return parsed


def _clean_progress(value: object, errors: dict[str, str]) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | str):
        errors["progress"] = "عددٌ صحيحٌ بين 0 و100"
        return None
    try:
        number = int(value)
    except ValueError:
        errors["progress"] = "عددٌ صحيحٌ بين 0 و100"
        return None
    if not 0 <= number <= 100:
        errors["progress"] = "بين 0 و100"
        return None
    return number


def _clean_text(value: object, field_name: str, limit: int, errors: dict[str, str]) -> str:
    if not isinstance(value, str):
        errors[field_name] = "نصٌّ"
        return ""
    text = value.strip()
    if len(text) > limit:
        errors[field_name] = f"أقصاه {limit} حرفاً"
    return text


def _clean_status(value: object, allowed: Iterable[str], errors: dict[str, str]) -> str:
    if not isinstance(value, str) or value not in set(allowed):
        errors["status"] = "قيمةٌ غيرُ مسموحة"
        return ""
    return value


def _reject_unknown(payload: object, allowed: frozenset[str]) -> Mapping[str, Any]:
    if not isinstance(payload, Mapping) or not payload:
        raise RoadmapError({"payload": "لا تعديلَ مطلوب"})
    unknown = sorted(set(payload) - allowed)
    if unknown:
        raise RoadmapError(dict.fromkeys(unknown, "حقلٌ غيرُ قابلٍ للتعديل"))
    return payload


# ── التدقيق ───────────────────────────────────────────────────────────────


def _audit(
    user: Any, request: HttpRequest | None, event: str, code: str, changes: dict[str, Any]
) -> None:
    """أثرٌ بما تغيّر وحدَه (قبل/بعد) لا بمحتوى البند."""
    AuditLog.log(  # type: ignore[no-untyped-call]
        user=user,
        action="update",
        model_name="other",
        object_id=code,
        object_repr=f"خارطة التجويد: {code}",
        changes={"event": event, "code": code, **changes},
        request=request,
    )


def _diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    keys = [k for k in after if before.get(k) != after[k]]
    return {"before": {k: before.get(k) for k in keys}, "after": {k: after[k] for k in keys}}


def stamp_user(user: Any) -> Any:
    return user if getattr(user, "pk", None) else None


# ── التحديث ───────────────────────────────────────────────────────────────


def _tracked_item(item: RoadmapItem) -> dict[str, Any]:
    return {
        "status": item.status,
        "progress": item.progress,
        "start": _iso(item.start_date),
        "end": _iso(item.end_date),
        "pr": item.pr,
        "note": item.note,
    }


def _next_progress(
    item: RoadmapItem, fields: Mapping[str, Any], status: str, errors: dict[str, str]
) -> int:
    """التقدّمُ الجديد: الصريحُ إن وُجد، وإلّا يتبع الحالةَ (المُغلَقُ 100، ولم يبدأ 0)."""
    progress = item.progress
    if "progress" in fields:
        cleaned = _clean_progress(fields["progress"], errors)
        progress = item.progress if cleaned is None else cleaned
    elif "status" in fields:
        if status == ItemStatus.DONE:
            progress = 100
        elif status == ItemStatus.TODO:
            progress = 0
    return 100 if status == ItemStatus.DONE else progress


def _next_dates(
    item: RoadmapItem, fields: Mapping[str, Any], errors: dict[str, str]
) -> tuple[date | None, date | None]:
    start, end = item.start_date, item.end_date
    if "start" in fields:
        start = _clean_date(fields["start"], "start", errors)
    if "end" in fields:
        end = _clean_date(fields["end"], "end", errors)
    if start and end and start > end and not {"start", "end"} & set(errors):
        errors["end"] = "النهايةُ قبل البداية"
    return start, end


@transaction.atomic
def update_item(
    code: str, payload: object, *, user: Any, request: HttpRequest | None = None
) -> dict[str, Any]:
    """يعدّل بنداً: الحالةَ والتقدّمَ والبدايةَ والنهايةَ وطلبَ الدمج والملاحظة."""
    fields = _reject_unknown(payload, ITEM_EDITABLE)
    item = selectors.items().select_for_update().filter(code=code).first()
    if item is None:
        raise RoadmapNotFoundError(code)

    errors: dict[str, str] = {}
    before = _tracked_item(item)
    status = item.status
    if "status" in fields:
        status = _clean_status(fields["status"], ItemStatus.values, errors) or item.status
    progress = _next_progress(item, fields, status, errors)
    start, end = _next_dates(item, fields, errors)
    pr = item.pr
    if "pr" in fields:
        pr = _clean_text(fields["pr"], "pr", PR_MAX, errors)
        if pr and not _PR_RE.match(pr):
            errors["pr"] = "رقمُ طلب الدمج فقط (مثل #446)"
    note = _clean_text(fields["note"], "note", NOTE_MAX, errors) if "note" in fields else item.note
    if errors:
        raise RoadmapError(errors)

    if (start, end) != (item.start_date, item.end_date):
        item.date_basis = MANUAL_DATE_BASIS
    item.status, item.progress, item.pr, item.note = status, progress, pr, note
    item.start_date, item.end_date = start, end
    delta = _diff(before, _tracked_item(item))
    if delta["after"]:
        item.updated_by = stamp_user(user)
        item.save()
        _audit(user, request, "roadmap_item_update", code, delta)
    return serialize_item(item)


def _clean_effort(value: object, errors: dict[str, str]) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float | str):
        errors["effort"] = "عددٌ موجبٌ (أيّام)"
        return 1.0
    try:
        number = float(value)
    except ValueError:
        errors["effort"] = "عددٌ موجبٌ (أيّام)"
        return 1.0
    if not 0 < number <= 365:
        errors["effort"] = "بين 0 و365 يوماً"
        return 1.0
    return number


@transaction.atomic
def create_item(payload: object, *, user: Any, request: HttpRequest | None = None) -> dict[str, Any]:
    """يضيف بنداً جديداً (مهمّةً مستقبليّة): الرمزُ يُولَّد `N-001…` والمصدرُ `NEW`."""
    fields = _reject_unknown(payload, ITEM_CREATABLE)
    errors: dict[str, str] = {}

    title = _clean_text(fields.get("title", ""), "title", TITLE_MAX, errors)
    if not title and "title" not in errors:
        errors["title"] = "العنوانُ مطلوب"
    lanes = {str(lane.get("key")) for lane in selectors.meta_data().get("lanes", []) if isinstance(lane, dict)}
    lane = fields.get("lane")
    if not isinstance(lane, str) or lane not in lanes:
        errors["lane"] = "مسارٌ غيرُ معروف"
    status = (
        _clean_status(fields["status"], ItemStatus.values, errors) if "status" in fields else ItemStatus.TODO
    )
    start = _clean_date(fields.get("start"), "start", errors)
    end = _clean_date(fields.get("end"), "end", errors)
    if start and end and start > end and not {"start", "end"} & set(errors):
        errors["end"] = "النهايةُ قبل البداية"
    effort = _clean_effort(fields["effort"], errors) if "effort" in fields else 1.0
    deps = _clean_text(fields.get("deps", ""), "deps", 255, errors)
    ref = _clean_text(fields.get("ref", ""), "ref", 255, errors)
    criterion = _clean_text(fields.get("criterion", ""), "criterion", NOTE_MAX, errors)
    note = _clean_text(fields.get("note", ""), "note", NOTE_MAX, errors)
    pr = _clean_text(fields.get("pr", ""), "pr", PR_MAX, errors)
    if pr and not _PR_RE.match(pr):
        errors["pr"] = "رقمُ طلب الدمج فقط (مثل #446)"
    gate = fields.get("gate", "")
    if gate not in ("", "owner"):
        errors["gate"] = "قيمةٌ غيرُ مسموحة"
    if errors:
        raise RoadmapError(errors)

    code = selectors.next_new_item_code()
    try:
        item = RoadmapItem.objects.create(
            code=code, src=NEW_ITEM_SRC, lane=str(lane), title=title, status=status,
            progress=100 if status == ItemStatus.DONE else 0, start_date=start, end_date=end,
            date_basis=MANUAL_DATE_BASIS if (start or end) else "", effort=effort, deps=deps,
            criterion=criterion, note=note, gate=gate, ref=ref, pr=pr,
            sort_order=selectors.next_item_sort_order(), updated_by=stamp_user(user),
        )
    except IntegrityError as exc:  # سباقٌ على الرمز نفسِه
        raise RoadmapError({"code": "تعارضٌ في الرمز — أعِد المحاولة"}) from exc
    _audit(user, request, "roadmap_item_create", code,
           {"before": {}, "after": {"title": title, "lane": str(lane), "status": status}})
    return serialize_item(item)


@transaction.atomic
def update_decision(
    code: str, payload: object, *, user: Any, request: HttpRequest | None = None
) -> dict[str, Any]:
    """يعدّل قراراً: الحالةَ وتاريخَ الحسم."""
    fields = _reject_unknown(payload, DECISION_EDITABLE)
    decision = selectors.decisions().select_for_update().filter(code=code).first()
    if decision is None:
        raise RoadmapNotFoundError(code)

    errors: dict[str, str] = {}
    before = {"status": decision.status, "date": _iso(decision.decision_date)}
    status = decision.status
    if "status" in fields:
        status = _clean_status(fields["status"], DecisionStatus.values, errors) or status
    when = decision.decision_date
    if "date" in fields:
        when = _clean_date(fields["date"], "date", errors)
    if errors:
        raise RoadmapError(errors)

    decision.status, decision.decision_date = status, when
    delta = _diff(before, {"status": status, "date": _iso(when)})
    if delta["after"]:
        decision.updated_by = stamp_user(user)
        decision.save()
        _audit(user, request, "roadmap_decision_update", code, delta)
    return serialize_decision(decision)


@transaction.atomic
def set_checklist_done(
    code: str, done: object, *, user: Any, request: HttpRequest | None = None
) -> dict[str, Any]:
    """يؤشّر بنداً من قائمة الفحص أو يزيل تأشيرَه — قيمةٌ منطقيّةٌ صريحة لا نصٌّ."""
    if not isinstance(done, bool):
        raise RoadmapError({"done": "true أو false"})
    entry = selectors.checklist().select_for_update().filter(code=code).first()
    if entry is None:
        raise RoadmapNotFoundError(code)
    if entry.done != done:
        entry.done = done
        entry.updated_by = stamp_user(user)
        entry.save()
        change = {"before": {"done": not done}, "after": {"done": done}}
        _audit(user, request, "roadmap_checklist_update", code, change)
    return serialize_checklist(entry)
