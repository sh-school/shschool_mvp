"""E1 — قياسُ النصّ بمقاييس الخطّ الفعليّة: عرضُ السطر بالإم والملّيمتر، ومباعدةُ الأسطر، والالتفافُ بحدود الكلمات.

المواصفة §٣-٣: عدُّ الأحرف يخطئ ±20% بين نصٍّ وآخر (الحرفُ العربيّ 0.34–0.49em بحسب الخطّ والسياق، والرقمُ 0.55em)؛ فالعرضُ هنا
**مجموعُ تقدُّمات الحروف الفعليّة** من ملفّ الخطّ (`hmtx`) بعد إعادة التشكيل (`arabic_reshaper`) إلى صور العرض (البدائيّة/الوسطيّة/النهائيّة/المفردة)،
وهذا يكفي لحسابٍ سريعٍ (ميكروثوانٍ لألف حرف) في وقت الحفظ. **WeasyPrint نفسُه هو الحَكَم**: `tests/test_print_fit_metrics.py` يعاير هذا النموذجَ
عليه (≥ 200 نصٍّ: خطأُ العرض ≤ 5% وعددُ الأسطر مطابقٌ في ≥ 95%) — فما زاد فيه يُصحَّح بمعاملٍ مقيسٍ لكلّ خطٍّ (`CALIBRATION`) لا مخمَّن.

لا يُحاكي: التقنينَ (kerning) ولا وصلاتِ الحروف الخاصّة خارجَ ما تعيده إعادةُ التشكيل، ولا قطعَ الكلمة الأطولَ من السطر (تبقى على سطرها كاملةً — كما يفعل
المحرّكُ حين لا يجد موضعَ فصل)؛ فمن احتاج دقّةً أعلى فبتمريرة رسمٍ فعليّة (المواصفة §٣-٣). وهو **تقريبٌ محافظٌ** لا يقلّ عن المرسوم بأكثر من معامل المعايرة.
"""

from __future__ import annotations

import functools
import pathlib
import unicodedata
from dataclasses import dataclass

import arabic_reshaper
from fontTools.ttLib import TTFont

FONTS_DIR = pathlib.Path(__file__).resolve().parents[2] / "static" / "fonts"

_PT_MM = 25.4 / 72  # النقطةُ بالملّيمتر

#: (الخطّ، الوزن) ← ملفٌّ. Tajawal للجداول والشبكات، وNoto Naskh وAmiri للنصوص المتّصلة والنماذج الرسميّة (المواصفة §٣-٥).
_FILES: dict[tuple[str, int], str] = {
    ("tajawal", 400): "Tajawal-Regular.ttf",
    ("tajawal", 500): "Tajawal-Medium.ttf",
    ("tajawal", 700): "Tajawal-Bold.ttf",
    ("noto-naskh", 400): "NotoNaskhArabic-Regular.ttf",
    ("noto-naskh", 700): "NotoNaskhArabic-Bold.ttf",
    ("amiri", 400): "Amiri-Regular.ttf",
    ("amiri", 700): "Amiri-Bold.ttf",
}

#: مباعدةُ الأسطر الطبيعيّة (`hhea.ascent − descent + lineGap` على `unitsPerEm`، مقيسةٌ بـfontTools): Noto Naskh 1.703 تُبدّد ثلثَ الارتفاع فتُثبَّت صراحةً (§٣-٥).
NATURAL_LINE_HEIGHT = {"tajawal": 1.2, "noto-naskh": 1.703, "amiri": 1.207}
#: المباعدةُ الصريحةُ المعتمدة للطباعة: Tajawal 1.2، والنصوصُ المتّصلةُ 1.2–1.35 (والتشكيلُ ≥ 1.35 للنصوص الحرّة وحدَها).
DEFAULT_LINE_HEIGHT = {"tajawal": 1.2, "noto-naskh": 1.2, "amiri": 1.2}

#: معاملُ المعايرة لكلّ خطٍّ = وسيطُ (المرسومُ ÷ المحسوب) على مجموعة المعايرة في الاختبار — يُثبَّت من القياس (1.0 = بلا تصحيح).
CALIBRATION: dict[str, float] = {"tajawal": 1.0, "noto-naskh": 1.0, "amiri": 1.0}


class UnknownFontError(KeyError):
    pass


@dataclass(frozen=True)
class _Metrics:
    upem: int
    advance: dict[int, int]  # نقطةُ الرمز ← التقدُّم (وحداتُ الخطّ)
    zero_width: frozenset[int]  # العلاماتُ (تشكيل…) بلا تقدُّم


@functools.cache
def _load(font: str, weight: int) -> _Metrics:
    key = (font, weight)
    if key not in _FILES:
        # أقربُ وزنٍ متاحٍ للخطّ نفسِه (Noto/Amiri بلا 500)
        candidates = sorted(w for (f, w) in _FILES if f == font)
        if not candidates:
            raise UnknownFontError(
                f"خطٌّ غيرُ معروف: {font!r} — المتاح: {sorted({f for f, _ in _FILES})}"
            )
        weight = min(candidates, key=lambda w: abs(w - weight))
        key = (font, weight)
    tt = TTFont(str(FONTS_DIR / _FILES[key]), lazy=True)
    cmap = tt.getBestCmap()
    hmtx = tt["hmtx"].metrics
    advance = {cp: hmtx[name][0] for cp, name in cmap.items() if name in hmtx}
    marks = frozenset(cp for cp in cmap if unicodedata.category(chr(cp)) in ("Mn", "Me", "Cf"))
    return _Metrics(tt["head"].unitsPerEm, advance, marks)


def _cluster_em(char: str, metrics: _Metrics) -> float:
    cp = ord(char)
    if cp in metrics.zero_width:
        return 0.0
    adv = metrics.advance.get(cp)
    if adv is not None:
        return adv / metrics.upem
    # صورةُ عرضٍ غيرُ موجودةٍ في الخطّ (Tajawal يغطّي 89 من 143): نرجع إلى الحرف الأساسيّ من تفكيكها
    decomposition = unicodedata.decomposition(char)
    if decomposition.startswith("<"):
        base = decomposition.split()[1:]
        return sum(metrics.advance.get(int(b, 16), 0) for b in base) / metrics.upem
    return metrics.advance.get(0x0020, 500) / metrics.upem  # حرفٌ مجهولٌ: عرضُ فراغ


@functools.lru_cache(maxsize=8192)
def text_em(text: str, font: str = "tajawal", weight: int = 400) -> float:
    """عرضُ سطرٍ واحدٍ بالإم: مجموعُ تقدُّمات صور الحروف بعد إعادة التشكيل، مضروباً بمعامل معايرة الخطّ."""
    if not text:
        return 0.0
    metrics = _load(font, weight)
    shaped = (
        arabic_reshaper.reshape(text)
        if any("؀" <= c <= "ۿ" or "ݐ" <= c <= "ݿ" for c in text)
        else text
    )
    total = sum(_cluster_em(c, metrics) for c in shaped)
    return round(total * CALIBRATION.get(font, 1.0), 4)


def text_mm(text: str, pt: float, font: str = "tajawal", weight: int = 400) -> float:
    """عرضُ سطرٍ واحدٍ بالملّيمتر عند خطٍّ `pt`."""
    return text_em(text, font, weight) * pt * _PT_MM


def line_height_mm(pt: float, font: str = "tajawal", line_height: float | None = None) -> float:
    """ارتفاعُ السطر بالملّيمتر: الخطُّ × المباعدةُ الصريحة (لا الطبيعيّة — Noto Naskh 1.703 تُبدّد ثلثَ الارتفاع)."""
    return (
        pt
        * _PT_MM
        * (line_height if line_height is not None else DEFAULT_LINE_HEIGHT.get(font, 1.2))
    )


def wrap(
    text: str, width_mm: float, pt: float, font: str = "tajawal", weight: int = 400
) -> list[str]:
    """التفافٌ جشعٌ بحدود الكلمات؛ سطرٌ لكلّ فقرةٍ (`\\n`) على الأقلّ. كلمةٌ أطولُ من السطر تبقى على سطرٍ وحدَها كاملةً (لا قطعَ).

    العرضُ المتاحُ هو ما يُترك للنصّ (بعد حشو الخلية) — والمستهلكُ يطرح الحشوَ قبل النداء.
    """
    space = text_mm(" ", pt, font, weight)
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = ""
        used = 0.0
        for word in words:
            w = text_mm(word, pt, font, weight)
            if not current:
                current, used = word, w
            elif used + space + w <= width_mm:
                current += " " + word
                used += space + w
            else:
                lines.append(current)
                current, used = word, w
        lines.append(current)
    return lines
