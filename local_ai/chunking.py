"""تقطيعُ النصّ إلى مقاطعَ للتضمين — يحترم الفقراتِ ثمّ الجملَ العربيّة، بتداخلٍ بين المقاطع.

لماذا بالحروف لا بالرموز (tokens)؟ لأنّ عدّادَ رموز النموذج غيرُ متاحٍ هنا، و1500 حرفاً عربيّاً
تقارب 500–700 رمزٍ في bge-m3، وهو حجمٌ مناسبٌ للاسترجاع. التداخلُ (200 حرف) يمنع ضياعَ
جملةٍ تقع على حدّ القطع.
"""

from __future__ import annotations

import re

DEFAULT_MAX_CHARS = 1500
DEFAULT_OVERLAP = 200

#: نهاياتُ الجمل: نقطةٌ، علامةُ استفهامٍ عربيّة/لاتينيّة، تعجّب، فاصلةٌ منقوطةٌ عربيّة، سطرٌ جديد.
_SENTENCE_END = re.compile(r"(?<=[\.\!\?؟؛])\s+|\n+")


def split_sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENTENCE_END.split(text) if s and s.strip()]


def _tail(text: str, overlap: int) -> str:
    """آخرُ `overlap` حرفاً من المقطع مبتدئاً من حدّ كلمةٍ — لا من منتصف كلمة."""
    if overlap <= 0 or len(text) <= overlap:
        return text if overlap > 0 else ""
    tail = text[-overlap:]
    space = tail.find(" ")
    return tail[space + 1 :] if 0 <= space < len(tail) - 1 else tail


def split_into_chunks(
    text: str,
    *,
    max_chars: int = DEFAULT_MAX_CHARS,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """مقاطعُ لا يتجاوز أحدُها `max_chars` (إلّا جملةً واحدةً أطولَ منه فتُقطع قسراً)."""
    if max_chars <= 0:
        raise ValueError("max_chars يجب أن يكون موجباً")
    overlap = max(0, min(overlap, max_chars // 2))
    sentences = split_sentences(text)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        # جملةٌ وحدها أطولُ من الحدّ: تُقطع إلى أجزاءٍ ثابتة.
        while len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            chunks.append(sentence[:max_chars])
            sentence = sentence[max_chars:]
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue
        chunks.append(current)
        current = f"{_tail(current, overlap)} {sentence}".strip()
        if len(current) > max_chars:  # التداخلُ وحدَه أطول من الحدّ — ابدأ بالجملة فقط
            current = sentence
    if current:
        chunks.append(current)
    return [c for c in chunks if c.strip()]
