"""محلّلُ سجلّ القرارات وبصماتُه — دوالُّ نقيّةٌ بلا قاعدةٍ (W-20260928-019).

المصدرُ ملفّان خارجَ المستودع (علنيّ على GitHub فلا يُرفع إليه نصُّ القرارات): `decisions.md` بصيغة
`- المعرّف | التاريخ | النصّ | الأثر | المرجع`، و`decisions_meta.jsonl` (id وtype وlocation وts).
بعض الصفوف ناقصةُ الحقول أو بنصٍّ فيه شرطةٌ رأسيّة؛ فالمعرّفُ والتاريخُ أوّلُ حقلين، والمرجعُ والأثرُ آخرُ حقلين
إن وُجد خمسةٌ فأكثر، وما بينهما نصٌّ.
"""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass

_SPACES = re.compile(r"\s+")
FIELD_SEP = "\x1f"


@dataclass(frozen=True)
class ParsedDecision:
    decision_id: str
    decided_at_text: str
    text: str
    effect: str
    reference: str
    line_no: int


def normalize(value: str) -> str:
    """تطبيعٌ للبصمة: NFC وطيُّ الفراغات وقصُّ الأطراف — فلا يتغيّر المعنى ولا تتأثّر البصمةُ بتنسيقٍ."""
    return _SPACES.sub(" ", unicodedata.normalize("NFC", value or "")).strip()


def parse_decisions_md(content: str) -> list[ParsedDecision]:
    rows: list[ParsedDecision] = []
    for number, raw in enumerate(content.splitlines(), 1):
        if not raw.startswith("- D-"):
            continue
        parts = [p.strip() for p in raw[2:].split("|")]
        decision_id = parts[0]
        date = parts[1] if len(parts) > 1 else ""
        if len(parts) >= 5:
            text, effect, reference = "|".join(parts[2:-2]).strip(), parts[-2], parts[-1]
        elif len(parts) == 4:
            text, effect, reference = parts[2], parts[3], ""
        else:
            text, effect, reference = (parts[2] if len(parts) > 2 else ""), "", ""
        rows.append(ParsedDecision(decision_id, date, text, effect, reference, number))
    return rows


def parse_meta(content: str) -> dict[str, dict[str, str]]:
    """id ← {type, location, ts}؛ الأخيرُ يغلب إن تكرّر المعرّف؛ سطرٌ معيبٌ يُتخطّى."""
    meta: dict[str, dict[str, str]] = {}
    for raw in content.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        try:
            item = json.loads(raw)
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("id"):
            meta[str(item["id"])] = {
                "type": str(item.get("type") or ""),
                "location": str(item.get("location") or ""),
                "ts": str(item.get("ts") or ""),
            }
    return meta


def fingerprint(
    decision_id: str,
    decided_at_text: str,
    text: str,
    effect: str,
    reference: str,
    kind: str = "",
    location: str = "",
) -> str:
    """sha256 على الحقول المطبَّعة كما هي مخزَّنة (بعد الحجب) — فيعيد الفحصُ اليوميُّ حسابَها من الجدول."""
    joined = FIELD_SEP.join(
        normalize(v)
        for v in (decision_id, decided_at_text, text, effect, reference, kind, location)
    )
    return hashlib.sha256(joined.encode("utf-8")).hexdigest()


def file_fingerprint(*contents: bytes) -> str:
    digest = hashlib.sha256()
    for blob in contents:
        digest.update(hashlib.sha256(blob).digest())
    return digest.hexdigest()
