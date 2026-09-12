"""
tests/test_dark_parity.py
━━━━━━━━━━━━━━━━━━━━━━━━━
الوضعُ الداكن يصدق: لا نصَّ يموت في الليل، ولا سطحَ يبقى فاتحاً فيه.

`tests/test_contrast_ratios.py` يقيس القاعدةَ التي تجمع لونَ نصٍّ وخلفيّةً
**معاً**. وأكثرُ ما يقع ليس كذلك: قاعدةٌ تُعلن `color` وحدَه وخلفيّتُها من
سلفها، أو تُعلن خلفيّةً وحدَها ونصُّها من سلفه. فتمرّ بين الأصابع.

وهذان الحارسان يسدّان الجهتين بفرضٍ واحدٍ مُعلَن: **ما لم تُعلن القاعدةُ
خلفيّتَها، فهي على سطح البطاقة** (`--surface`) — وهو أعمُّ ما يقع تحته نصٌّ
في هذه المنصّة. فرضٌ قد يخطئ في موضع، فيُكتب الموضعُ استثناءً بسببه لا
يُخفَّض الحدُّ للجميع.

قِيس يومَ 2026-09-12 فوجد ثمانيةَ نصوصٍ تموت ليلاً (أدناها 1.76) وخمسةَ عشرَ
سطحاً يبقى فاتحاً. وأُصلحت.
"""

import pathlib
import re

from tests.css_contrast import (
    dark_overrides,
    iter_rules,
    luminance,
    over,
    ratio,
    resolve,
    token_table,
)

CSS_PATH = pathlib.Path("static/css/custom.css")

AA_NORMAL = 4.5
#: فوقها يُعدّ اللونُ «فاتحاً» — أبيضُ 1.0، و`--surface` الليليُّ 0.018.
LIGHT = 0.5
BG_PROPS = ("background", "background-color")

#: حشواتٌ لا تنقلب بقصد: لونُ العلامة وألوانُ الحالات وما يحمل نصّاً أبيض.
#: الأبيضُ فوقها لا ينقلب، فلو انقلبت هي لانكسر الزوج.
FILL_TOKENS = {
    "--maroon",
    "--maroon-dark",
    "--maroon-light",
    "--gold",
    "--skyline",
    "--palm",
    "--sea",
    "--accent-orange",
    "--accent-purple",
    "--accent-sky",
    "--accent-teal",
    "--status-danger",
    "--status-warning",
    "--status-success",
    "--status-info",
    "--status-danger-dark",
    "--status-warning-dark",
    "--status-success-dark",
    "--status-info-dark",
    "--status-success-solid",
    "--neutral-solid",
    "--chart-1",
    "--chart-2",
    "--chart-3",
    "--chart-4",
    "--chart-5",
    "--chart-6",
}

#: أسطحٌ فاتحةٌ في الليل **بقصد**، ولكلٍّ سببُها.
LIGHT_ON_PURPOSE = {
    # ورقةٌ تُطبع: الطباعةُ على أبيض قرارٌ قائم، والمعاينةُ تُريه كما يخرج.
    ".report-page",
    # قرصٌ أبيضُ على شريطٍ عنّابيّ — والشريطُ عنّابيٌّ في الوضعين.
    ".child-action-btn--solid:hover",
}


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _screen_rules(css):
    return [(s, d, c) for s, d, c in iter_rules(css) if not any("print" in x for x in c)]


def _dark_selectors(rules):
    """مُحدِّدات الليل مفكَّكةً — فالقاعدةُ تُكتب أحياناً قائمةً بفواصل."""
    out = set()
    for sel, _d, _c in rules:
        for part in sel.split(","):
            p = " ".join(part.split())
            if p.startswith("html.dark"):
                out.add(p)
    return out


def _has_twin(selector, dark_sels):
    return any("html.dark " + " ".join(p.split()) in dark_sels for p in selector.split(","))


# ══════════════════════════════════════════════════════════════════
# ١. الحبر — نصٌّ برمزٍ لا ينقلب
# ══════════════════════════════════════════════════════════════════


def test_no_rule_paints_text_with_a_colour_that_dies_at_night():
    """رمزٌ لا يُبدَّل في `html.dark` لا يصلح نصّاً إلّا أن يُقرأ على سطح الليل.

    وهذا ما أفلت من حارس التباين: `.ap-err` تُعلن `color` بلا خلفيّة، فلا
    زوجَ فيها يُقاس — ولونُها `--status-danger-dark` لا ينقلب، فيصير أحمرَ
    داكناً على سطحٍ داكنٍ نسبتُه 1.76.
    """
    css = _css()
    _light, dark = token_table(css)
    fixed = {k for k in _light if k not in dark_overrides(css)}
    rules = _screen_rules(css)
    dark_sels = _dark_selectors(rules)

    offenders = []
    for sel, decls, _ctx in rules:
        flat = " ".join(sel.split())
        if flat.startswith("html.dark") or "color" not in decls:
            continue
        if not any(t in fixed for t in re.findall(r"var\((--[\w-]+)", decls["color"])):
            continue
        if _has_twin(flat, dark_sels):
            continue
        bg_decl = next((decls[k] for k in BG_PROPS if k in decls), None)
        bg = resolve(bg_decl, dark) if bg_decl else resolve("var(--surface)", dark)
        fg = resolve(decls["color"], dark)
        if fg is None or bg is None:
            continue
        if bg[3] < 1:
            bg = (*over(bg, resolve("var(--surface)", dark)), 1.0)
        if fg[3] < 1:
            fg = (*over(fg, bg), 1.0)
        got = ratio(fg, bg)
        if got < AA_NORMAL:
            offenders.append(f"  {got:5.2f}  {flat[:58]}\n           color: {decls['color'][:44]}")

    assert not offenders, (
        f"{len(offenders)} قاعدةً تكتب نصّاً يموت في الليل — رمزُها لا ينقلب ولا نظيرةَ لها:\n"
        + "\n".join(sorted(offenders))
    )


# ══════════════════════════════════════════════════════════════════
# ٢. السطح — أرضيّةٌ تبقى فاتحةً بعد إطفاء الضوء
# ══════════════════════════════════════════════════════════════════


def test_no_surface_stays_light_when_the_lamp_goes_out():
    """«الفاتحُ للنصّ والإطار، لا للخلفيّة» — قرارُ المستخدم في الوضع الداكن.

    والحشواتُ المعلَنة مستثناة: `--maroon` و`--gold` وأخواتُهما تحمل نصّاً
    أبيضَ لا ينقلب، فلو انقلبت هي لانكسر الزوج.
    """
    css = _css()
    _light, dark = token_table(css)
    rules = _screen_rules(css)
    dark_sels = _dark_selectors(rules)

    offenders = []
    for sel, decls, _ctx in rules:
        flat = " ".join(sel.split())
        if flat.startswith("html.dark") or flat in LIGHT_ON_PURPOSE:
            continue
        val = next((decls[k] for k in BG_PROPS if k in decls), None)
        if val is None:
            continue
        if any(t in FILL_TOKENS for t in re.findall(r"var\((--[\w-]+)", val)):
            continue
        if _has_twin(flat, dark_sels):
            continue
        col = resolve(val, dark)
        if col is None or col[3] < 1:
            continue  # الشفّافُ يُحلّ على ما تحته — لا يحكمه الملفّ
        lum = luminance(col)
        if lum >= LIGHT:
            offenders.append(f"  {lum:5.3f}  {flat[:58]}   {val[:34]}")

    assert not offenders, (
        f"{len(offenders)} أرضيّةً تبقى فاتحةً في الليل:\n"
        + "\n".join(sorted(offenders, reverse=True))
        + "\n\nإمّا رمزٌ ينقلب، أو نظيرةٌ `html.dark`، أو تُعلَن في LIGHT_ON_PURPOSE بسببها."
    )


# ══════════════════════════════════════════════════════════════════
# ٣. حرّاسُ الحارس
# ══════════════════════════════════════════════════════════════════


def test_a_comma_written_dark_block_still_counts_as_an_override():
    """`html.dark :root, html.dark { … }` صيغةٌ قائمةٌ في الملفّ.

    وكانت `token_table` تقارن المُحدِّدَ كلَّه بـ`html.dark` فتُفوّتها، فتُحسب
    قيمةُ النهار قيمةً لليل. خطأٌ صامتٌ يجعل الحارسَ يقيس ما ليس على الشاشة.
    """
    over_map = dark_overrides(_css())
    assert "--swap-fg" in over_map, "رمزٌ مُبدَّلٌ في كتلةٍ بفواصل لم يُرَ"
    _light, dark = token_table(_css())
    assert dark["--swap-fg"] != _light["--swap-fg"], "قيمةُ الليل لم تُطبَّق"


def test_the_scan_actually_reaches_the_stylesheet():
    """مسحٌ لا يقيس شيئاً ينجح كاذباً."""
    css = _css()
    light, _dark = token_table(css)
    assert len(light) >= 90, f"رموزُ `:root` {len(light)} — التفكيكُ لم يبلغها"
    fixed = {k for k in light if k not in dark_overrides(css)}
    assert 20 <= len(fixed) <= 100, f"الرموزُ غيرُ المنقلبة {len(fixed)} — رقمٌ لا يُصدَّق"

    rules = _screen_rules(css)
    surfaces = sum(1 for _s, d, _c in rules if any(k in d for k in BG_PROPS))
    assert surfaces >= 300, f"لم يُفحَص إلّا {surfaces} سطحاً — المسحُ فارغ"
