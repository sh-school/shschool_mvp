"""قياسُ قيم `px` الحرفيّة في التباعد والتقوّس وترحيلُها إلى رموزها (P3-4).

الرموزُ (`--sp-*`، `--radius-*`) معرَّفةٌ مرّةً في `:root`، وقيمةُ `var(--sp-2)` هي عينُها
`8px` — فالترحيلُ الحرفيُّ بلا أيّ فرقٍ في الرسم. وقد قِيس على الملفّات وقت كتابته:
750 قيمةَ تباعدٍ حرفيّة، **328 منها فقط** تطابق درجةً في السلّم (4·8·12·16·20·24·32…)؛
والباقي (6 و10 و2 و14 و18) كان الأكثرَ استعمالاً — فأُضيفت له درجاتٌ نصفيّة
(`--sp-1-5` = 6px…) بلا فرقٍ بصريّ (317 موضعاً). أمّا 3 و5 و1 و28 و7 و9… (92 موضعاً)
فتبقى حرفيّةً: نادرةٌ وربّما غيرُ مقصودة، وتحويلُها إلى أقرب درجةٍ تغييرٌ بصريٌّ.

ما لا يدخل هنا عمداً:

- `font-size`: يُعالَج بدالّتَيه أدناه (rem) لا بجدول الرموز.
- القيمُ السالبة (`-8px`): لا رمزَ سالب، و`calc(var(--x) * -1)` أثقلُ من القيمة.
- `@page`/`@font-face`: لا عناصرَ فيها تُحلّ منها `var()`.
- شروطُ `@media`: الرموزُ لا تعمل في الاستعلامات.
"""

from __future__ import annotations

import re

#: قيمةُ px ← الرمز. من `:root` في `10-foundation.css` (أيُّ تغييرٍ فيها يُعدّل هنا).
SPACING_TOKENS = {
    2: "--sp-0-5",
    4: "--sp-1",
    6: "--sp-1-5",
    8: "--sp-2",
    10: "--sp-2-5",
    12: "--sp-3",
    14: "--sp-3-5",
    16: "--sp-4",
    18: "--sp-4-5",
    20: "--sp-5",
    24: "--sp-6",
    32: "--sp-8",
    40: "--sp-10",
    48: "--sp-12",
    64: "--sp-16",
}
RADIUS_TOKENS = {4: "--radius-sm", 8: "--radius-md", 14: "--radius-lg", 16: "--radius-xl"}

SPACING_PROP = re.compile(
    r"(margin|padding)(-(top|bottom|left|right|inline|block)(-(start|end))?)?$|(row-|column-)?gap$"
)
RADIUS_PROP = re.compile(
    r"border(-(top|bottom|start|end)){0,2}(-(left|right))?-radius$|border-radius$"
)

#: كتلٌ لا تُحلّ فيها `var()`.
NO_VAR_CONTEXTS = ("@page", "@font-face", "@property", "@counter-style")

_COMMENT = re.compile(r"/\*.*?\*/", re.S)
_STRING = re.compile(r"\"(?:\\.|[^\"\\])*\"|'(?:\\.|[^'\\])*'")
_DECL = re.compile(r"[;{]\s*([a-z-]+)\s*:\s*([^;{}]+?)\s*(?=[;}])")
#: px صحيحٌ موجب لا يسبقه رقمٌ ولا نقطةٌ ولا شرطة (فلا `-8px` ولا `0.5px` ولا `1.25px`).
_PX = re.compile(r"(?<![\w.\-])(\d+)px\b")


def _mask(css: str) -> str:
    """نصٌّ بطول الأصل تُستبدل فيه التعليقاتُ والنصوصُ بفراغ — فتطابق الإزاحاتُ الأصلَ."""

    def blank(match: re.Match) -> str:
        return "".join(ch if ch == "\n" else " " for ch in match.group(0))

    return _STRING.sub(blank, _COMMENT.sub(blank, css))


def _contexts(masked: str, starts: list[int]) -> list[tuple[str, ...]]:
    """لكلّ بدايةِ تصريحٍ رؤوسُ الكتل المحيطة به من الخارج إلى الداخل."""
    stack: list[str] = []
    out: list[tuple[str, ...]] = []
    pos = 0
    header_from = 0
    for start in starts:
        while pos < start:
            ch = masked[pos]
            if ch == "{":
                stack.append(masked[header_from:pos].strip())
                header_from = pos + 1
            elif ch == "}":
                if stack:
                    stack.pop()
                header_from = pos + 1
            elif ch == ";":
                header_from = pos + 1
            pos += 1
        out.append(tuple(stack))
    return out


def _class_of(prop: str) -> str | None:
    if SPACING_PROP.match(prop):
        return "spacing"
    if RADIUS_PROP.match(prop):
        return "radius"
    return None


def declarations(css: str):
    """(نوعُ الخاصّية، بدايةُ القيمة، نهايتُها) لكلّ تصريحِ تباعدٍ أو تقوّسٍ يصلح لـ`var()`."""
    masked = _mask(css)
    matches = list(_DECL.finditer(masked))
    # +1: التصريحُ الأوّلُ في كتلةٍ يبدأ بالقوس `{` نفسِه، فسياقُه يشمل تلك الكتلة
    contexts = _contexts(masked, [m.start() + 1 for m in matches])
    for match, ctx in zip(matches, contexts, strict=True):
        prop = match.group(1)
        kind = _class_of(prop)
        if kind is None or prop.startswith("--"):
            continue
        if any(h.startswith(NO_VAR_CONTEXTS) for h in ctx):
            continue
        yield kind, match.start(2), match.end(2)


def _table(kind: str) -> dict[int, str]:
    return SPACING_TOKENS if kind == "spacing" else RADIUS_TOKENS


def count_literals(css: str) -> dict[str, int]:
    """كم قيمةَ px حرفيّةً في التباعد والتقوّس؛ على السلّم (تُرحَّل) وخارجه (قرارُ تصميم)."""
    counts = {
        "spacing_on_scale": 0,
        "spacing_off_scale": 0,
        "radius_on_scale": 0,
        "radius_off_scale": 0,
    }
    for kind, start, end in declarations(css):
        for match in _PX.finditer(css[start:end]):
            side = "on_scale" if int(match.group(1)) in _table(kind) else "off_scale"
            counts[f"{kind}_{side}"] += 1
    return counts


def migrate(css: str) -> str:
    """كلُّ px على السلّم في التباعد والتقوّس ← `var(--token)` — لا غير."""
    edits: list[tuple[int, int, str]] = []
    for kind, start, end in declarations(css):
        table = _table(kind)
        for match in _PX.finditer(css[start:end]):
            value = int(match.group(1))
            if value in table:
                edits.append((start + match.start(), start + match.end(), f"var({table[value]})"))
    for begin, stop, text in sorted(edits, reverse=True):
        css = css[:begin] + text + css[stop:]
    return css


def revert(css: str) -> str:
    """عكسُ `migrate` — يُثبت أنّ ما تغيّر هو الاستبدالُ وحده (اختبارُ التكافؤ الحرفيّ)."""
    for table in (SPACING_TOKENS, RADIUS_TOKENS):
        for value, token in table.items():
            css = css.replace(f"var({token})", f"{value}px")
    return css


# ── font-size: px ← rem (D-12، 2026-09-21) ─────────────────────────────────────
# `html` بلا `font-size` في المنصّة (16px الافتراضيّ) ولا JS يغيّره، فالقيمةُ `0.75rem`
# هي عينُ `12px` عند الإعداد الافتراضيّ، وتتبع تكبيرَ المستخدم في المتصفّح (WCAG 1.4.4).

_FONT_SIZE_PX = re.compile(r"(\d+(?:\.\d+)?)px(\s*!important)?")


def _rem(px_value: str) -> str:
    """px ← rem على أساس 16 بلا ضجيجٍ عشريّ: 12 → 0.75rem، 12.5 → 0.78125rem."""
    return f"{format(float(px_value) / 16, 'f').rstrip('0').rstrip('.')}rem"


def _font_size_spans(css: str):
    """(بدايةُ القيمة، نهايتُها، النصُّ) لكلّ `font-size` قيمتُه px بسيطةٌ وحدَها (لا `max()` ولا `calc()`)."""
    masked = _mask(css)
    for match in _DECL.finditer(masked):
        if match.group(1) != "font-size":
            continue
        value = match.group(2)
        if _FONT_SIZE_PX.fullmatch(value):
            yield match.start(2), match.end(2), value


def count_font_size_px(css: str) -> int:
    """كم `font-size` بـpx بسيطٍ ما زال حرفيّاً — يجب أن يبلغ صفراً."""
    return sum(1 for _ in _font_size_spans(css))


def migrate_font_size(css: str) -> str:
    """كلُّ `font-size: Npx` بسيطٍ ← rem — لا غير."""
    edits = []
    for start, end, value in _font_size_spans(css):
        m = _FONT_SIZE_PX.fullmatch(value)
        edits.append((start, end, _rem(m.group(1)) + (m.group(2) or "")))
    for begin, stop, text in sorted(edits, reverse=True):
        css = css[:begin] + text + css[stop:]
    return css
