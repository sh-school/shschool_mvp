"""استيرادُ سجلّ القرارات باتجاهٍ واحدٍ وفحصُ الانجراف (W-20260928-019).

الاستيرادُ يدويٌّ من ملفٍّ خارجَ git؛ لا سحبَ ولا مفتاحَ ولا كتابةَ في المصدر.
idempotent بمعرّف القرار: الموجودُ المطابقُ يُترك، والموجودُ المختلفُ يُفشل الاستيرادَ كلَّه قبل أيّ كتابة.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from django.db import transaction

from .models import Decision, ImportBatch
from .parsing import file_fingerprint, fingerprint, parse_decisions_md, parse_meta
from .scrub import mask_personal


class DecisionsImportError(Exception):
    """فشلٌ يوقف الاستيراد كلَّه بلا كتابة (تكرارُ معرّف، أو اختلافُ قرارٍ موجود)."""


@dataclass(frozen=True)
class ImportResult:
    total: int
    created: int
    unchanged: int
    batch_id: int | None


def _build_rows(decisions_md: str, meta_text: str, names: tuple[str, ...]) -> list[dict]:
    meta = parse_meta(meta_text)
    seen: set[str] = set()
    rows = []
    for item in parse_decisions_md(decisions_md):
        if item.decision_id in seen:
            raise DecisionsImportError(
                f"معرّفٌ مكرَّر في الملف: {item.decision_id} (السطر {item.line_no})"
            )
        seen.add(item.decision_id)
        info = meta.get(item.decision_id, {})
        text = mask_personal(item.text, names)
        effect = mask_personal(item.effect, names)
        reference = mask_personal(item.reference, names)
        kind = info.get("type", "")
        location = mask_personal(info.get("location", ""), names)
        rows.append(
            {
                "decision_id": item.decision_id,
                "decided_at_text": item.decided_at_text,
                "text": text,
                "effect": effect,
                "reference": reference,
                "kind": kind,
                "location": location,
                "source_ts": info.get("ts", ""),
                "fingerprint": fingerprint(
                    item.decision_id, item.decided_at_text, text, effect, reference, kind, location
                ),
            }
        )
    return rows


def import_decisions(
    decisions_path: Path, meta_path: Path | None = None, names: tuple[str, ...] = ()
) -> ImportResult:
    decisions_bytes = Path(decisions_path).read_bytes()
    meta_bytes = Path(meta_path).read_bytes() if meta_path else b""
    rows = _build_rows(
        decisions_bytes.decode("utf-8"), meta_bytes.decode("utf-8") if meta_bytes else "", names
    )
    existing = dict(Decision.objects.values_list("decision_id", "fingerprint"))
    changed = [
        r["decision_id"]
        for r in rows
        if r["decision_id"] in existing and existing[r["decision_id"]] != r["fingerprint"]
    ]
    if changed:
        raise DecisionsImportError(
            f"انجراف: {len(changed)} قرارٌ موجودٌ يختلف عن المصدر (أوّلها {changed[0]}) — لا يُعدَّل قرارٌ مخزَّن"
        )
    new_rows = [r for r in rows if r["decision_id"] not in existing]
    if not new_rows:
        return ImportResult(len(rows), 0, len(rows), None)
    with transaction.atomic():
        batch = ImportBatch.objects.create(
            file_fingerprint=file_fingerprint(decisions_bytes, meta_bytes),
            row_count=len(rows),
            created_count=len(new_rows),
            names_masked=bool(names),
        )
        Decision.objects.bulk_create([Decision(batch=batch, **r) for r in new_rows])
    return ImportResult(len(rows), len(new_rows), len(rows) - len(new_rows), batch.pk)


def check_drift() -> list[str]:
    """معرّفاتُ القرارات التي لا تطابق بصمتُها المخزَّنةُ حقولَها الحاليّة — سلامةٌ محلّيّة، لا مقارنةَ بمستودع."""
    drifted = []
    for d in Decision.objects.all().iterator():
        current = fingerprint(
            d.decision_id, d.decided_at_text, d.text, d.effect, d.reference, d.kind, d.location
        )
        if current != d.fingerprint:
            drifted.append(d.decision_id)
    return drifted
