"""E3 — ملاءمةُ المناطق لصفحةٍ واحدة: أكبرُ خطٍّ يتّسع له ما كُتب فعلاً، ولا نزولَ دون الحدّ، ولا قصَّ صامتاً (المواصفة §٣-١ و§٣-٤ و§٣-٦).

    fit(zones, page, min_pt, prefs, rows) -> Layout | NotFit

دالّةٌ **نقيّةٌ** بلا request ولا قاعدة ولا رسم (مقاييسُ الخطّ في `text_metrics` وسعةُ الفقرات في `capacity`)؛ WeasyPrint نفسُه هو الحَكَم
في `tests/test_print_fit_render.py`. تتوقّف عند **أوّل خطوةٍ تكفي** والحدُّ الأدنى للخطّ ثابتٌ في كلّ خطوة:

    0  قياسُ المحتوى بمقاييس الخطّ الفعليّة
    1  الخطُّ المثاليُّ لكلّ منطقة — فإن اتّسعت الصفحةُ يأخذ الفائضَ المناطقُ المرنةُ بنسبة أوزانها
    2  تقليلُ البياض والحشو (حشوُ المنطقة/الصفّ وفاصلُ ما بين المناطق) إلى حدّه الأدنى
    3  عمودان للمناطق القابلة (`columns_ok`: قوائمُ لا جداولُ ولا نصوصٌ متّصلة)
    4  تدرُّجُ الخطّ بخطواتٍ **نصفِ نقطة**: مجموعةُ الأولويّة الأدنى أوّلاً (النصوصُ الحرّةُ قبل الجداول) حتى حدّها ثمّ التي بعدها
    7  «تتمّة» موسومةٌ للبيانات القديمة (`prefs.allow_continuation`): ما لم يتّسع **كاملاً** بلا قصٍّ ولا نزولٍ دون الحدّ، مع تقريرٍ باستعمالها
    8  فشلٌ بصوتٍ عالٍ: `NotFit(limit_mm, …)` — لا قصَّ صامتاً أبداً

والخطوتان 5 (اتّجاهُ الصفحة) و6 (سلّمُ محتوى الخليّة) **خارجَ هذا المحرّك**: الأولى قرارُ المستهلك (الورقُ يُختار قبل النداء)، والثانيةُ اختيارُ محتوى الخليّة
لكلّ درجةٍ — يستدعي المستهلكُ `fit` مرّةً لكلّ درجةٍ (ر1 ثمّ ر3) بـ`cell_texts` المناسبة، ويقرّر أيَّها يقبل.

**أسوأُ خليّةٍ في الأسبوع المعروض** مُدخَلٌ لا الخطّة (§٣-٤-١): `TableZone.cell_texts` تحمل كلَّ الأنماط الفعليّة في الأسبوع (خليّةٌ منقسمةٌ، تعويضٌ، إحلال)،
وارتفاعُ الصفّ من أطولها التفافاً؛ و`rows` معاملٌ لا ثابت (25 اليوم وقد يكون 26). و**اختصارٌ غائبٌ** لمادّةٍ في `terms` يرفع `MissingAbbreviationError` معلَّلاً.
"""

from __future__ import annotations

import logging
import math
from collections import Counter
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, replace
from typing import Literal

from core import print_frame
from core.print_fit import capacity as cap
from core.print_fit import text_metrics as tm

log = logging.getLogger("schoolos.print_fit")

Kind = Literal["fixed", "text", "table", "fill"]

STEP_MEASURE = 0
STEP_IDEAL = 1
STEP_WHITESPACE = 2
STEP_COLUMNS = 3
STEP_GRADIENT = 4
STEP_CONTINUATION = 7
STEP_FAIL = 8

_EPS = 1e-6

#: عدّاداتُ التشغيل (`fit_step{template,step}` و`fit_continuation{template}`) — يُغذّيها `record_report` وتقرؤها لوحةُ الجودة.
COUNTERS: Counter[str] = Counter()


class FitInputError(ValueError):
    """مُدخَلٌ ناقصٌ أو متناقض — يفشل بصوتٍ عالٍ لا بافتراضٍ صامت."""


class MissingAbbreviationError(FitInputError):
    def __init__(self, missing: Sequence[str]) -> None:
        self.missing = tuple(missing)
        super().__init__(
            f"لا اختصارَ للمادّة/المواد: {'، '.join(self.missing)} — أضِفه في قاموس الاختصارات (المواصفة ٦-٤)؛ لا قصَّ صامتاً لاسمٍ لا يتّسع."
        )


def abbreviate(names: Iterable[str], table: Mapping[str, str]) -> dict[str, str]:
    """اختصارُ كلّ اسمٍ من جدولٍ مفتوح؛ اسمٌ بلا اختصارٍ ⇒ `MissingAbbreviationError` (المُدخَل ٣-٤-٣)."""
    unique = sorted(set(names))
    missing = [n for n in unique if not table.get(n)]
    if missing:
        raise MissingAbbreviationError(missing)
    return {n: table[n] for n in unique}


@dataclass(frozen=True)
class Page:
    """ما يتبقّى للمتن: عرضٌ وارتفاعٌ بالملّيمتر (من `core.print_frame.frame` — لا رقمَ ارتفاعٍ في المستهلك)."""

    body_width_mm: float
    body_height_mm: float
    paper: str = ""
    orient: str = ""

    @classmethod
    def from_frame(cls, paper: str, orient: str) -> Page:
        fr = print_frame.frame(paper, orient)
        return cls(fr.body_width, fr.body_height, paper, orient)


@dataclass(frozen=True)
class FitPrefs:
    template: str = "unnamed"
    gap_mm: float = 4.0  # فاصلُ ما بين المناطق المثاليّ (يُخفَّف في الخطوة 2)
    min_gap_mm: float = 2.0  # المواصفة ٤-٢
    step_pt: float = 0.5
    allow_continuation: bool = False  # للبيانات القديمة وحدَها — الجديدةُ يمنعها العدّاد (§٧-١)
    continuation_header_mm: float = 12.0  # عنوانُ صفحة «التتمّة» (يُخصم من ارتفاعها)
    continuation_label: str = "تتمّة — الصفحة {page}"
    engine: str = "weasyprint"


@dataclass(frozen=True)
class FitZone:
    """منطقةٌ في الصفحة. `kind`:

    - `fixed`: ارتفاعٌ ثابتٌ `height_mm` (توقيعات، عنوان) — لا خطَّ ولا تدرُّج.
    - `text`: نصٌّ حرٌّ مرنٌ (توصيات مرقَّمة، ملاحظات، تعليق): يأخذ الفائضَ بوزنه، ويتدرّج خطُّه، ويقبل «التتمّة» إن `continuable`.
    - `table`: جدولٌ بـ`rows` صفوفٍ (أو معاملُ `fit`)؛ ارتفاعُ الصفّ من أسوأ خليّةٍ في `cell_texts` بعرض `cell_width_mm`.
    - `fill`: منطقةُ كتابةٍ باليد: بحدٍّ أدنى `height_mm` وتأخذ **كلَّ** الفائض.
    """

    key: str
    kind: Kind
    width_mm: float = 0.0
    height_mm: float = 0.0  # fixed: الارتفاعُ؛ fill: الحدُّ الأدنى
    ideal_pt: float = 11.0
    min_pt: float | None = None  # وإلّا معاملُ `fit`
    font: str = "tajawal"
    weight: int = 400
    line_height: float = 1.2
    paragraphs: tuple[str, ...] = ()
    numbered: bool = False
    paragraph_gap_mm: float = 0.0
    pad_mm: float = 0.0  # حشوٌ عموديٌّ للمنطقة كلّها (مثاليّ)
    min_pad_mm: float | None = None  # الخطوة 2 (وإلّا `pad_mm`)
    flex_weight: float = 1.0  # حصّةُ الفائض (ملاحظات 1، توصيات 1.5، تعليق 1)
    shrink_priority: int | None = None  # الأدنى يتدرّج أوّلاً؛ وإلّا النصُّ 0 والجدولُ 1
    columns_ok: bool = False
    column_gap_mm: float = 4.0
    continuable: bool = False
    min_lines: int = 2  # ما لا تنزل عنه منطقةٌ مقطوعةٌ بالتتمّة
    cell_texts: tuple[str, ...] = ()  # أسوأُ محتوى للخليّة في الأسبوع المعروض
    cell_width_mm: float = 0.0
    header_mm: float = 0.0
    rows: int | None = None  # وإلّا معاملُ `fit`
    row_pad_mm: float = 0.8
    min_row_pad_mm: float | None = None
    terms: tuple[str, ...] = ()  # أسماءٌ يلزمها اختصارٌ
    abbreviations: Mapping[str, str] | None = None

    @property
    def has_font(self) -> bool:
        return self.kind in ("text", "table")

    def floor_pt(self, min_pt: float) -> float:
        return self.min_pt if self.min_pt is not None else min_pt

    def priority(self) -> int:
        if self.shrink_priority is not None:
            return self.shrink_priority
        return 0 if self.kind == "text" else 1


@dataclass(frozen=True)
class ZoneLayout:
    key: str
    kind: Kind
    font_pt: float | None
    lines: int
    height_mm: float
    extra_mm: float = 0.0  # حصّةُ الفائض
    columns: int = 1
    paragraphs: tuple[str, ...] = ()  # ما بقي في الصفحة (بعد اقتطاع التتمّة إن وُجدت)


@dataclass(frozen=True)
class Continuation:
    zone: str
    paragraphs: tuple[str, ...]
    first_number: int  # رقمُ أوّل فقرةٍ تحملها التتمّة (للترقيم المتّصل)
    continues_paragraph: bool  # الفقرةُ الأولى تكملةٌ لفقرةٍ قُطعت في الصفحة الأولى
    lines: int
    height_mm: float
    label: str


@dataclass(frozen=True)
class FitReport:
    template: str
    paper: str
    orient: str
    ideal_used: bool
    steps_taken: tuple[int, ...]
    final_font_by_zone: Mapping[str, float]
    ladder_rung: str | None  # الخطوةُ 6 خارجَ المحرّك؛ يملؤها المستهلكُ
    pages: int
    continuation_used: bool
    engine: str
    fits: bool

    @property
    def guaranteed(self) -> bool:
        """ما رُسم بمحرّكٍ غيرِ WeasyPrint لا يُحسب ضمن ضمان الملاءمة."""
        return self.engine == "weasyprint"


@dataclass(frozen=True)
class Layout:
    zones: tuple[ZoneLayout, ...]
    gap_mm: float
    used_mm: float
    free_mm: float
    pages: int
    continuation: tuple[Continuation, ...]
    report: FitReport

    def zone(self, key: str) -> ZoneLayout:
        for z in self.zones:
            if z.key == key:
                return z
        raise KeyError(key)


@dataclass(frozen=True)
class NotFit:
    """لا يتّسع: `limit_mm` هو المتاحُ للمناطق المرنة بعد الثابتة، و`needed_mm` ما تطلبه عند حدودها الدنيا."""

    limit_mm: float
    needed_mm: float
    deficit_mm: float
    reason: str
    report: FitReport


@dataclass
class _State:
    fonts: dict[str, float]
    tight: bool = False
    columns: bool = False


@dataclass(frozen=True)
class _Measured:
    zone: FitZone
    height: float
    lines: int
    columns: int


def _validate(zones: Sequence[FitZone], rows: int | None) -> None:
    seen: set[str] = set()
    for z in zones:
        if z.key in seen:
            raise FitInputError(f"مفتاحُ منطقةٍ مكرَّر: {z.key!r}")
        seen.add(z.key)
        if z.kind not in ("fixed", "text", "table", "fill"):
            raise FitInputError(f"نوعُ منطقةٍ غيرُ معروف: {z.kind!r} ({z.key})")
        if z.kind == "table" and z.rows is None and rows is None:
            raise FitInputError(f"الجدولُ {z.key!r}: عددُ الصفوف معاملٌ لا ثابت — مرِّر `rows`.")
        if z.kind == "table" and (not z.cell_texts or z.cell_width_mm <= 0):
            raise FitInputError(
                f"الجدولُ {z.key!r}: يلزمه `cell_texts` (أسوأُ ما في الأسبوع المعروض) و`cell_width_mm`."
            )
        if z.kind == "text" and z.width_mm <= 0:
            raise FitInputError(f"المنطقةُ {z.key!r}: عرضٌ غيرُ موجب.")
        if z.columns_ok and z.continuable:
            raise FitInputError(
                f"المنطقةُ {z.key!r}: `columns_ok` و`continuable` لا يجتمعان (قائمةٌ بعمودين لا تُقطع)."
            )
        if z.terms:
            abbreviate(z.terms, z.abbreviations or {})


def _cap_zone(z: FitZone, width_mm: float | None = None) -> cap.Zone:
    return cap.Zone(
        width_mm=width_mm if width_mm is not None else z.width_mm,
        height_mm=1e9,
        font=z.font,
        weight=z.weight,
        line_height=z.line_height,
        paragraph_gap_mm=z.paragraph_gap_mm,
        numbered=z.numbered,
    )


def _text_height(z: FitZone, pt: float, tight: bool, columns: bool) -> tuple[float, int, int]:
    """(الارتفاع، الأسطر، الأعمدة) لمنطقة نصٍّ عند `pt`."""
    pad = z.min_pad_mm if (tight and z.min_pad_mm is not None) else z.pad_mm
    lh = tm.line_height_mm(pt, z.font, z.line_height)
    single_h = cap.used_height_mm(_cap_zone(z), z.paragraphs, pt) + pad
    single_lines = sum(
        cap.paragraph_lines(_cap_zone(z), p, pt, _prefix(z, pt)) for p in z.paragraphs if p.strip()
    )
    best = (single_h, single_lines, 1)
    if columns and z.columns_ok and len(z.paragraphs) >= 2:
        col_w = (z.width_mm - z.column_gap_mm) / 2
        zone = _cap_zone(z, col_w)
        prefix = _prefix(z, pt, col_w)
        counts = [cap.paragraph_lines(zone, p, pt, prefix) for p in z.paragraphs]
        two = min(
            (
                max(
                    _col_h(counts[:k], lh, z.paragraph_gap_mm),
                    _col_h(counts[k:], lh, z.paragraph_gap_mm),
                )
                for k in range(1, len(counts))
            ),
            default=single_h,
        )
        if two + pad < best[0] - _EPS:
            best = (two + pad, sum(counts), 2)
    return best


def _col_h(counts: Sequence[int], lh: float, gap: float) -> float:
    return sum(counts) * lh + max(len(counts) - 1, 0) * gap


def _prefix(z: FitZone, pt: float, width_mm: float | None = None) -> float:
    return cap.prefix_mm(_cap_zone(z, width_mm), len([p for p in z.paragraphs if p.strip()]), pt)


def _table_height(z: FitZone, pt: float, tight: bool, rows: int | None) -> tuple[float, int]:
    n_rows = z.rows if z.rows is not None else int(rows or 0)
    lh = tm.line_height_mm(pt, z.font, z.line_height)
    worst = max(len(tm.wrap(t, z.cell_width_mm, pt, z.font, z.weight)) for t in z.cell_texts)
    pad = z.min_row_pad_mm if (tight and z.min_row_pad_mm is not None) else z.row_pad_mm
    return z.header_mm + n_rows * (worst * lh + pad), worst


def _measure(z: FitZone, state: _State, rows: int | None) -> _Measured:
    if z.kind == "fixed" or z.kind == "fill":
        return _Measured(z, z.height_mm, 0, 1)
    pt = state.fonts[z.key]
    if z.kind == "table":
        h, lines = _table_height(z, pt, state.tight, rows)
        return _Measured(z, h, lines, 1)
    h, lines, cols = _text_height(z, pt, state.tight, state.columns)
    return _Measured(z, h, lines, cols)


def _total(measured: Sequence[_Measured], gap: float) -> float:
    return sum(m.height for m in measured) + gap * max(len(measured) - 1, 0)


def _fonts_at_ideal(zones: Sequence[FitZone], min_pt: float) -> dict[str, float]:
    return {z.key: max(z.ideal_pt, z.floor_pt(min_pt)) for z in zones if z.has_font}


def _report(
    prefs: FitPrefs,
    page: Page,
    steps: Sequence[int],
    fonts: Mapping[str, float],
    *,
    pages: int,
    continued: bool,
    fits: bool,
) -> FitReport:
    return FitReport(
        template=prefs.template,
        paper=page.paper,
        orient=page.orient,
        ideal_used=tuple(steps) == (STEP_MEASURE, STEP_IDEAL) and fits,
        steps_taken=tuple(steps),
        final_font_by_zone=dict(fonts),
        ladder_rung=None,
        pages=pages,
        continuation_used=continued,
        engine=prefs.engine,
        fits=fits,
    )


def _layout(
    measured: Sequence[_Measured],
    state: _State,
    page: Page,
    prefs: FitPrefs,
    steps: Sequence[int],
    gap: float,
    kept: Mapping[str, tuple[str, ...]] | None = None,
    continuation: tuple[Continuation, ...] = (),
) -> Layout:
    used = _total(measured, gap)
    surplus = max(page.body_height_mm - used, 0.0)
    fills = [m for m in measured if m.zone.kind == "fill"]
    receivers = fills or [m for m in measured if m.zone.kind == "text"]
    total_w = sum(m.zone.flex_weight for m in receivers)
    extra = {
        m.zone.key: (surplus * m.zone.flex_weight / total_w if total_w > 0 else 0.0)
        for m in receivers
    }
    zones = tuple(
        ZoneLayout(
            key=m.zone.key,
            kind=m.zone.kind,
            font_pt=state.fonts.get(m.zone.key),
            lines=m.lines,
            height_mm=round(m.height + extra.get(m.zone.key, 0.0), 3),
            extra_mm=round(extra.get(m.zone.key, 0.0), 3),
            columns=m.columns,
            paragraphs=(kept or {}).get(m.zone.key, m.zone.paragraphs),
        )
        for m in measured
    )
    carried_h = sum(c.height_mm for c in continuation)
    room = max(page.body_height_mm - prefs.continuation_header_mm, 1.0)
    pages = 1 + (math.ceil(carried_h / room - _EPS) if continuation else 0)
    fits_surplus = surplus if not continuation else 0.0
    report = _report(
        prefs, page, steps, state.fonts, pages=pages, continued=bool(continuation), fits=True
    )
    return Layout(
        zones=zones,
        gap_mm=gap,
        used_mm=round(used, 3),
        free_mm=round(fits_surplus, 3),
        pages=pages,
        continuation=continuation,
        report=report,
    )


def fit(
    zones: Sequence[FitZone],
    page: Page,
    min_pt: float,
    prefs: FitPrefs | None = None,
    rows: int | None = None,
) -> Layout | NotFit:
    """أكبرُ خطٍّ يتّسع له المحتوى في `page` — أو `NotFit` بصوتٍ عالٍ. انظر وصفَ الوحدة للخطوات."""
    prefs = prefs or FitPrefs()
    _validate(zones, rows)
    steps = [STEP_MEASURE]
    state = _State(fonts=_fonts_at_ideal(zones, min_pt))
    gap = prefs.gap_mm

    def evaluate() -> list[_Measured]:
        return [_measure(z, state, rows) for z in zones]

    def fits(measured: Sequence[_Measured]) -> bool:
        return _total(measured, gap) <= page.body_height_mm + _EPS

    steps.append(STEP_IDEAL)
    measured = evaluate()
    if fits(measured):
        return _layout(measured, state, page, prefs, steps, gap)

    steps.append(STEP_WHITESPACE)
    state.tight = True
    gap = min(prefs.gap_mm, prefs.min_gap_mm)
    measured = evaluate()
    if fits(measured):
        return _layout(measured, state, page, prefs, steps, gap)

    if any(z.columns_ok for z in zones):
        steps.append(STEP_COLUMNS)
        state.columns = True
        measured = evaluate()
        if fits(measured):
            return _layout(measured, state, page, prefs, steps, gap)

    floors = {z.key: z.floor_pt(min_pt) for z in zones if z.has_font}
    shrinkable = [z for z in zones if z.has_font and state.fonts[z.key] > floors[z.key] + _EPS]
    if shrinkable:
        steps.append(STEP_GRADIENT)
        for priority in sorted({z.priority() for z in shrinkable}):
            group = [z for z in shrinkable if z.priority() == priority]
            while any(state.fonts[z.key] > floors[z.key] + _EPS for z in group):
                for z in group:
                    state.fonts[z.key] = max(
                        floors[z.key], round(state.fonts[z.key] - prefs.step_pt, 4)
                    )
                measured = evaluate()
                if fits(measured):
                    return _layout(measured, state, page, prefs, steps, gap)

    measured = evaluate()
    overflow = _total(measured, gap) - page.body_height_mm
    if prefs.allow_continuation:
        steps.append(STEP_CONTINUATION)
        carried = _continue(zones, measured, state, page, prefs, overflow)
        if carried is not None:
            kept, continuation, adjusted = carried
            return _layout(adjusted, state, page, prefs, steps, gap, kept, continuation)

    steps.append(STEP_FAIL)
    fixed_need = _total(measured, gap) - sum(
        m.height for m in measured if m.zone.kind in ("text", "table")
    )
    flex_need = sum(m.height for m in measured if m.zone.kind in ("text", "table"))
    limit = max(page.body_height_mm - fixed_need, 0.0)
    reason = (
        f"لا يتّسع عند الحدّ الأدنى للخطّ: المطلوبُ {flex_need:.1f} ملم للمناطق المرنة والمتاحُ {limit:.1f} ملم (عجزٌ {overflow:.1f} ملم)"
        + ("؛ والتتمّةُ لا تكفي" if prefs.allow_continuation else "؛ التتمّةُ غيرُ مسموحةٍ لهذه الوثيقة")
    )
    return NotFit(
        limit_mm=round(limit, 2),
        needed_mm=round(flex_need, 2),
        deficit_mm=round(overflow, 2),
        reason=reason,
        report=_report(prefs, page, steps, state.fonts, pages=1, continued=False, fits=False),
    )


def _continue(
    zones: Sequence[FitZone],
    measured: list[_Measured],
    state: _State,
    page: Page,
    prefs: FitPrefs,
    overflow: float,
) -> tuple[dict[str, tuple[str, ...]], tuple[Continuation, ...], list[_Measured]] | None:
    """الخطوةُ 7: يُقتطع من ذيل المناطق `continuable` (الأخيرةُ أوّلاً) ما يلزم لتتّسع الصفحةُ، ويُحمل **كاملاً** إلى «تتمّة»."""
    kept: dict[str, tuple[str, ...]] = {}
    carried: list[Continuation] = []
    by_key = {m.zone.key: m for m in measured}
    remaining = overflow
    page_no = 2
    for z in reversed(zones):
        if remaining <= _EPS:
            break
        if not (z.kind == "text" and z.continuable):
            continue
        pt = state.fonts[z.key]
        lh = tm.line_height_mm(pt, z.font, z.line_height)
        czone = _cap_zone(z)
        prefix = _prefix(z, pt)
        paragraphs = [p for p in z.paragraphs if p.strip()]
        wrapped = [
            tm.wrap(p, max(z.width_mm - prefix, 0.0), pt, z.font, z.weight) for p in paragraphs
        ]
        total_lines = sum(len(w) for w in wrapped)
        removed = 0
        # نزيل سطراً سطراً من الذيل حتى يزول العجزُ أو نبلغ `min_lines`
        last = len(wrapped) - 1
        idx_lines = [len(w) for w in wrapped]
        while remaining > _EPS and total_lines - removed > z.min_lines:
            if last < 0:
                break
            removed += 1
            idx_lines[last] -= 1
            saved = lh
            if idx_lines[last] == 0:
                saved += z.paragraph_gap_mm  # اختفت فقرةٌ كاملةٌ فسقط فاصلُها
                last -= 1
            remaining -= saved
        if removed == 0:
            continue
        keep_paras: list[str] = []
        carry_paras: list[str] = []
        first_number = 0
        continues = False
        for i, w in enumerate(wrapped):
            kept_n = idx_lines[i]
            if kept_n == len(w):
                keep_paras.append(paragraphs[i])
            elif kept_n > 0:
                keep_paras.append(" ".join(w[:kept_n]))
                carry_paras.append(" ".join(w[kept_n:]))
                first_number = first_number or i + 1
                continues = True
            else:
                carry_paras.append(paragraphs[i])
                first_number = first_number or i + 1
        c_lines = sum(
            len(tm.wrap(p, max(z.width_mm - prefix, 0.0), pt, z.font, z.weight))
            for p in carry_paras
        )
        c_h = cap.used_height_mm(czone, carry_paras, pt) + z.pad_mm
        carried.append(
            Continuation(
                zone=z.key,
                paragraphs=tuple(carry_paras),
                first_number=first_number,
                continues_paragraph=continues,
                lines=c_lines,
                height_mm=round(c_h, 3),
                label=prefs.continuation_label.format(page=page_no),
            )
        )
        kept[z.key] = tuple(keep_paras)
        old = by_key[z.key]
        new_h = cap.used_height_mm(czone, keep_paras, pt) + (
            z.min_pad_mm if z.min_pad_mm is not None else z.pad_mm
        )
        by_key[z.key] = _Measured(z, new_h, sum(idx_lines), old.columns)
    if remaining > _EPS:
        return None
    return kept, tuple(reversed(carried)), [by_key[m.zone.key] for m in measured]


def record_report(report: FitReport) -> None:
    """سطرُ سجلٍّ عاديّ، وتحذيرٌ عند الخطوة 6 فما فوق (التتمّة/الفشل)، وعدّاداتُ `fit_step` و`fit_continuation` (§٣-٦). تُستدعى من المستهلك — `fit` نفسُها نقيّة."""
    last = max(report.steps_taken) if report.steps_taken else 0
    COUNTERS[f"fit_step{{template={report.template},step={last}}}"] += 1
    if report.continuation_used:
        COUNTERS[f"fit_continuation{{template={report.template}}}"] += 1
    message = "print_fit template=%s paper=%s/%s steps=%s fonts=%s pages=%s continuation=%s engine=%s fits=%s"
    args = (
        report.template,
        report.paper,
        report.orient,
        list(report.steps_taken),
        dict(report.final_font_by_zone),
        report.pages,
        report.continuation_used,
        report.engine,
        report.fits,
    )
    if last >= STEP_CONTINUATION or not report.fits or not report.guaranteed:
        log.warning(message, *args)
    else:
        log.info(message, *args)


def with_rows(zone: FitZone, rows: int) -> FitZone:
    """نسخةٌ من جدولٍ بعددِ صفوفٍ صريح (شعبةُ 26 في عامٍ آخر) — مساعدٌ للاختبارات والمستهلكين."""
    return replace(zone, rows=rows)


__all__ = [
    "COUNTERS",
    "Continuation",
    "FitInputError",
    "FitPrefs",
    "FitReport",
    "FitZone",
    "Layout",
    "MissingAbbreviationError",
    "NotFit",
    "Page",
    "ZoneLayout",
    "abbreviate",
    "fit",
    "record_report",
    "with_rows",
]
