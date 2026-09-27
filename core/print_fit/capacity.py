"""E2 — سعةُ منطقةٍ نصّيّةٍ: ما يتبقّى من الأحرف والأسطر عند الخطّ الأدنى. مصدرُ **العدّاد الحيّ** الذي يمنع الحفظَ فوق السعة (المواصفة §٣-٢ و§٧-١).

**عقدُ الاستمارات — لا تُغيَّر أسماءُ الحقول دون إبلاغ «منصّة · فحص الإدارة»** (تبني عليها العدّادَ ومنعَ الحفظ):

    capacity(zone, paragraphs, min_pt) -> Capacity{remaining_chars, remaining_lines, font_pt, fits}

- `zone`: المنطقةُ **مدخلٌ** (عرضٌ وارتفاعٌ صافيان بالملّيمتر) — لا رسمَ داخل المحرّك؛ والمستهلكُ يقيس «الجسمَ الفارغ» برسم القالب مرّةً لكلّ عمليّةٍ ويحرسه اختبار.
- `paragraphs`: قائمةُ فقراتٍ (بنودُ توصيات)، أو سلسلةٌ واحدةٌ تُعامَل فقرةً. **الالتفافُ لكلّ فقرةٍ على حدة** — فلا يُقرَّب كلُّ بندٍ إلى سطرٍ كامل.
- `Zone.numbered`: بادئةٌ مرقَّمةٌ ببادئٍ **معلَّق** («1.» «12.» …): عرضُ أعرض البوادئ (+ فراغ) يُخصم من كلّ سطرٍ من كلّ فقرةٍ (الأوّل وما بعده)،
  كما يفعل العمودُ المعلَّق في القالب. و`prefix_width_mm` يُمرَّر صريحاً إن قاسه المستهلكُ من قالبه.
- `Zone.paragraph_gap_mm`: مباعدةُ الفقرات المضبوطة (بين الفقرات لا بعد الأخيرة).

دالّةٌ **نقيّةٌ** بلا request ولا قاعدة ولا تخطيطٍ كامل (مقاييسُ الخطّ في `text_metrics`): ألفُ حرفٍ في أجزاءٍ من الملّيثانية (اختبارُ الزمن < 300ms).
`remaining_chars` **تقديرٌ محافظٌ** بمتوسّط عرض الحرف من النصّ الحاليّ نفسِه (وإلّا 0.5em)؛ والحَكَمُ الذي يمنع الحفظَ هو `fits` (التفافٌ فعليٌّ عند كلّ ضغطة).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

from core.print_fit import text_metrics as tm

_DEFAULT_CHAR_EM = 0.5  # متوسّطُ حرفٍ عربيٍّ مع الفراغات حين لا نصَّ يُقاس منه
_MM_PT = 25.4 / 72


@dataclass(frozen=True)
class Zone:
    """منطقةُ نصٍّ حرٍّ: العرضُ والارتفاعُ **الصافيان** (بعد حشو الخليّة) بالملّيمتر، والخطُّ ومباعدتُه الصريحة."""

    width_mm: float
    height_mm: float
    font: str = "tajawal"
    weight: int = 400
    line_height: float | None = (
        None  # مباعدةٌ صريحة؛ وإلّا الافتراضيّةُ للخطّ (والتشكيلُ ≥ 1.35 يمرّره المستهلكُ)
    )
    paragraph_gap_mm: float = 0.0  # فراغٌ مضبوطٌ بين الفقرات (لا بعد الأخيرة)
    numbered: bool = False  # بادئةٌ مرقَّمةٌ ببادئٍ معلَّق
    prefix_width_mm: float | None = (
        None  # عرضُ عمود البادئة كما قاسه القالب؛ وإلّا يُحسب من أعرض بادئةٍ + فراغ
    )
    prefix_gap_em: float = 0.3  # فراغٌ بين البادئة والنصّ (em)


@dataclass(frozen=True)
class Capacity:
    remaining_chars: int  # ما يتّسع بعدُ (تقديرٌ محافظ) — صفرٌ إن امتلأت المنطقة
    remaining_lines: int  # أسطرٌ كاملةٌ فارغةٌ تحت النصّ الحاليّ (بعد مباعدة فقرةٍ جديدة إن وُجد نصّ)
    font_pt: float  # الخطُّ الذي حُسبت عنده السعةُ (= min_pt)
    fits: bool  # هل يتّسع النصُّ الحاليُّ نفسُه؟ — الحَكَمُ الذي يمنع الحفظَ
    used_lines: int = 0
    total_lines: int = 0  # سعةُ المنطقة بالأسطر كاملةً (فارغةً، بلا مباعدة فقرات)


def _as_list(paragraphs: str | Sequence[str] | None) -> list[str]:
    if paragraphs is None:
        return []
    if isinstance(paragraphs, str):
        return [paragraphs] if paragraphs.strip() else []
    return [p for p in paragraphs if p and p.strip()]


def _prefix_mm(zone: Zone, n_paragraphs: int, pt: float) -> float:
    if not zone.numbered:
        return 0.0
    if zone.prefix_width_mm is not None:
        return zone.prefix_width_mm
    widest = max(
        (
            tm.text_mm(f"{i}.", pt, zone.font, zone.weight)
            for i in range(1, max(n_paragraphs, 1) + 1)
        ),
        default=0.0,
    )
    return widest + zone.prefix_gap_em * pt * _MM_PT


def paragraph_lines(zone: Zone, paragraph: str, pt: float, prefix_mm: float = 0.0) -> int:
    """أسطرُ فقرةٍ واحدةٍ بعرض المنطقة بعد خصم عمود البادئة المعلَّقة."""
    if not paragraph.strip():
        return 1
    return len(tm.wrap(paragraph, max(zone.width_mm - prefix_mm, 0.0), pt, zone.font, zone.weight))


def used_height_mm(zone: Zone, paragraphs: str | Sequence[str] | None, pt: float) -> float:
    """الارتفاعُ الذي تشغله الفقراتُ عند `pt` (أسطرٌ × مباعدةٌ + مباعدةُ الفقرات)."""
    items = _as_list(paragraphs)
    prefix = _prefix_mm(zone, len(items), pt)
    lh = tm.line_height_mm(pt, zone.font, zone.line_height)
    lines = sum(paragraph_lines(zone, p, pt, prefix) for p in items)
    return lines * lh + max(len(items) - 1, 0) * zone.paragraph_gap_mm


def capacity(zone: Zone, paragraphs: str | Sequence[str] | None, min_pt: float) -> Capacity:
    """ما يتبقّى في `zone` بعد `paragraphs` عند الخطّ الأدنى `min_pt`. القائمةُ الفارغةُ سعتُها كاملة."""
    items = _as_list(paragraphs)
    lh = tm.line_height_mm(min_pt, zone.font, zone.line_height)
    total_lines = max(int((zone.height_mm + 1e-6) // lh), 0)
    prefix = _prefix_mm(
        zone, len(items) + 1, min_pt
    )  # البادئةُ تُقاس بحسب ما ستبلغه القائمةُ بعد إضافة بندٍ
    line_w = max(zone.width_mm - prefix, 0.0)

    counts = [paragraph_lines(zone, p, min_pt, prefix) for p in items]
    used_lines = sum(counts)
    used_h = used_lines * lh + max(len(items) - 1, 0) * zone.paragraph_gap_mm
    fits = used_h <= zone.height_mm + 1e-6

    free_h = zone.height_mm - used_h - (zone.paragraph_gap_mm if items else 0.0)
    remaining_lines = max(int((free_h + 1e-6) // lh), 0) if fits else 0

    body = " ".join(items)
    if body.strip():
        char_mm = tm.text_mm(body, min_pt, zone.font, zone.weight) / len(body)
    else:
        char_mm = _DEFAULT_CHAR_EM * min_pt * _MM_PT
    per_line = max(int(line_w // char_mm), 1) if char_mm > 0 else 0
    last_line = tm.wrap(items[-1], line_w, min_pt, zone.font, zone.weight)[-1] if items else ""
    partial = (
        max(int((line_w - tm.text_mm(last_line, min_pt, zone.font, zone.weight)) // char_mm), 0)
        if fits and items and char_mm > 0
        else 0
    )
    remaining_chars = partial + remaining_lines * per_line if fits else 0
    return Capacity(
        remaining_chars=max(remaining_chars, 0),
        remaining_lines=remaining_lines,
        font_pt=min_pt,
        fits=fits,
        used_lines=used_lines,
        total_lines=total_lines,
    )


def ceil_lines(
    height_mm: float, pt: float, font: str = "tajawal", line_height: float | None = None
) -> int:
    """كم سطراً كاملاً يسعه `height_mm` عند `pt`."""
    return max(math.floor((height_mm + 1e-6) / tm.line_height_mm(pt, font, line_height)), 0)
