"""
tests/test_contrast_ratios.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
لا نصَّ يُكتب على خلفيّةٍ لا تحمله — يُقاس عند الإيداع لا على الشاشة.

قِيس التباينُ مرّةً بيدٍ يومَ 2026-09-11 عبر المتصفّح على اثنتين وستّين صفحةً
في الوضعين، فنزل الإخفاقُ من 193 إلى صفر. ثمّ لا شيء يمنع أوّلَ لونٍ جديدٍ
من إعادته: القياسُ اليدويُّ يقع مرّةً، والرموزُ تُضاف كلَّ أسبوع.

فهذا الحارس يقرأ الرموزَ من `custom.css` نفسِه — لا من جدولٍ يُكتب بيدٍ
فيشيخ — ويحسب النسبةَ في الوضعين، ويفشل دون حدّ WCAG AA.

**ما يُقاس**: كلُّ قاعدةٍ تُعلن `color` وخلفيّةً صمّاءَ معاً، وأزواجُ الرموز
المقصودةُ أدناه. **وما لا يُقاس** مذكورٌ في `tests/css_contrast.py`: الخلفيّةُ
الشفّافةُ والتدرّجُ لا يحكمهما الملفّ وحدَه.

وحدُّ AA: 4.5 للنصّ العاديّ، و3 للكبير (24px، أو 18.66px بخطٍّ عريض).
"""

import pathlib
import re

from tests.css_contrast import iter_rules, over, ratio, resolve, token_table

CSS_PATH = pathlib.Path("static/css/custom.css")

#: حدُّ WCAG AA للنصّ العاديّ، وللكبير.
AA_NORMAL = 4.5
AA_LARGE = 3.0

BG_PROPS = ("background", "background-color")


# ══════════════════════════════════════════════════════════════════
# أزواجُ الرموز المقصودة
# ══════════════════════════════════════════════════════════════════
#
# لا قاعدةَ واحدةً تجمع بعضَ هذه الأزواج، فلا يراها المسحُ الآليّ — لكنّها
# تقع على الشاشة: نصٌّ بهذا الرمز فوق سطحٍ بذاك. فتُذكر صراحةً.
#
#: (رمزُ النصّ، رمزُ السطح)
TOKEN_PAIRS = [
    ("--text-primary", "--surface"),
    ("--text-primary", "--surface-alt"),
    ("--text-secondary", "--surface"),
    ("--text-secondary", "--surface-alt"),
    ("--text-muted", "--surface"),
    ("--text-muted", "--surface-alt"),
    ("--maroon-fg", "--surface"),
    ("--maroon-fg", "--surface-alt"),
    ("--maroon-fg", "--maroon-bg"),
    ("--status-danger-fg", "--surface"),
    ("--status-danger-fg", "--status-danger-bg"),
    ("--status-warning-fg", "--surface"),
    ("--status-warning-fg", "--status-warning-bg"),
    ("--status-success-fg", "--surface"),
    ("--status-success-fg", "--status-success-bg"),
    ("--status-info-fg", "--surface"),
    ("--status-info-fg", "--status-info-bg"),
    ("--accent-teal-fg", "--surface"),
    ("--accent-orange-fg", "--surface"),
    ("--accent-purple-fg", "--surface"),
    ("--accent-sky-fg", "--surface"),
    ("--skyline-fg", "--surface"),
]

#: ألوانُ الرسوم تُقرأ على سطحِ البطاقة — وهي أشكالٌ لا نصّ، فحدُّها 3.
CHART_TOKENS = [f"--chart-{i}" for i in range(1, 7)]


def _css():
    return CSS_PATH.read_text(encoding="utf-8")


def _themes():
    light, dark = token_table(_css())
    return [("النهار", light), ("الليل", dark)]


# ══════════════════════════════════════════════════════════════════
# ١. أزواجُ الرموز
# ══════════════════════════════════════════════════════════════════


def test_every_named_pair_is_readable_in_both_themes():
    """رمزُ نصٍّ على رمزِ سطحٍ يبلغ 4.5 نهاراً وليلاً."""
    offenders = []
    for theme, tokens in _themes():
        for fg_name, bg_name in TOKEN_PAIRS:
            fg = resolve(f"var({fg_name})", tokens)
            bg = resolve(f"var({bg_name})", tokens)
            assert fg is not None, f"{fg_name} لا يُحَلّ في {theme}"
            assert bg is not None, f"{bg_name} لا يُحَلّ في {theme}"
            got = ratio(fg, bg)
            if got < AA_NORMAL:
                offenders.append(f"  {got:5.2f}  {theme}  {fg_name} على {bg_name}")
    assert not offenders, "أزواجٌ دون حدّ AA:\n" + "\n".join(offenders)


def test_the_chart_palette_stays_visible_on_its_surface():
    """لونُ الرسم شكلٌ لا نصّ، فحدُّه 3 — وكان العنّابيُّ 1.91 على الداكن."""
    offenders = []
    for theme, tokens in _themes():
        surface = resolve("var(--surface)", tokens)
        alt = resolve("var(--surface-alt)", tokens)
        for name in CHART_TOKENS:
            colour = resolve(f"var({name})", tokens)
            assert colour is not None, f"{name} لا يُحَلّ في {theme}"
            for label, bg in (("السطح", surface), ("سطحِ الصفحة", alt)):
                got = ratio(colour, bg)
                if got < AA_LARGE:
                    offenders.append(f"  {got:5.2f}  {theme}  {name} على {label}")
    assert not offenders, "ألوانُ رسمٍ لا تُرى:\n" + "\n".join(offenders)


# ══════════════════════════════════════════════════════════════════
# ٢. المسحُ الآليّ — كلُّ قاعدةٍ تجمع نصّاً وخلفيّةً صمّاء
# ══════════════════════════════════════════════════════════════════


def _large_text(decls) -> bool:
    """نصٌّ كبيرٌ بمعيار WCAG: 24px، أو 18.66px بخطٍّ عريض."""
    raw = decls.get("font-size", "")
    m = re.match(r"^\s*([\d.]+)(px|rem)\s*$", raw)
    if not m:
        return False
    px = float(m.group(1)) * (16 if m.group(2) == "rem" else 1)
    weight = decls.get("font-weight", "").strip()
    bold = weight in {"bold", "bolder"} or (weight.isdigit() and int(weight) >= 700)
    return px >= 24 or (px >= 18.66 and bold)


def _scan():
    """(النسبة، الوضع، المُحدِّد، النصّ، الخلفيّة) لكلّ زوجٍ يقع دون حدّه."""
    css = _css()
    light, dark = token_table(css)
    rules = [(s, d, c) for s, d, c in iter_rules(css) if not any("print" in x for x in c)]
    dark_selectors = {s for s, _d, _c in rules if s.startswith("html.dark")}

    def themes_of(selector):
        # قاعدةُ الليل تُقاس ليلاً وحدَها. وقاعدةٌ بلا بادئةٍ تُقاس في الوضعين،
        # إلّا أن تكون لها نظيرةٌ ليليّةٌ تُبدّل لونَها — فتلك تحكم الليل.
        if selector.startswith("html.dark"):
            return [("الليل", dark)]
        shadowed = any(
            d == "html.dark " + part.strip() for part in selector.split(",") for d in dark_selectors
        )
        return [("النهار", light)] + ([] if shadowed else [("الليل", dark)])

    found = []
    for selector, decls, _ctx in rules:
        if "color" not in decls:
            continue
        bg_value = next((decls[k] for k in BG_PROPS if k in decls), None)
        if bg_value is None:
            continue
        need = AA_LARGE if _large_text(decls) else AA_NORMAL
        for theme, tokens in themes_of(selector):
            fg = resolve(decls["color"], tokens)
            bg = resolve(bg_value, tokens)
            if fg is None or bg is None or bg[3] < 1:
                continue  # لا يحكمه الملفّ وحدَه — انظر css_contrast
            if fg[3] < 1:
                fg = (*over(fg, bg), 1.0)
            got = ratio(fg, bg)
            if got < need:
                found.append((round(got, 2), theme, selector, decls["color"], bg_value))
    return found


def test_no_rule_writes_text_on_a_surface_that_hides_it():
    """قاعدةٌ تجمع نصّاً وخلفيّةً: النسبةُ بينهما تبلغ حدَّها في الوضعين.

    أكثرُ ما يقع هنا شكلٌ واحد: خلفيّةٌ مكتوبةٌ رقماً فاتحاً (`white`،
    `#FEF3C7`) مع نصٍّ برمزٍ ينقلب — فيصير الفاتحُ على الفاتح ليلاً. أو
    عكسُه: رمزُ سطحٍ ينقلب مع نصٍّ مكتوبٍ رقماً فيبقى داكناً على داكن.
    """
    found = _scan()
    lines = [
        f"  {r:5.2f}  {theme}  {sel[:62]}\n           color: {fg[:40]}   bg: {bg[:40]}"
        for r, theme, sel, fg, bg in sorted(found)
    ]
    assert not found, f"{len(found)} زوجاً دون حدّ AA:\n" + "\n".join(lines)


def test_the_scan_actually_reaches_the_stylesheet():
    """حارسُ الحارس: مسحٌ لا يقيس شيئاً ينجح كاذباً.

    خطأٌ في التفكيك (تعليقٌ لا يُغلق، أو `var()` لا يُحَلّ) يُفرغ المسحَ من
    مادّته فيمرّ صامتاً. فيُشترط عددٌ أدنى ممّا قِيس فعلاً.
    """
    css = _css()
    light, _dark = token_table(css)
    assert len(light) >= 90, f"رموزُ `:root` {len(light)} — التفكيكُ لم يبلغها"

    measured = 0
    for selector, decls, ctx in iter_rules(css):
        if any("print" in x for x in ctx) or "color" not in decls:
            continue
        bg_value = next((decls[k] for k in BG_PROPS if k in decls), None)
        if bg_value is None:
            continue
        fg = resolve(decls["color"], light)
        bg = resolve(bg_value, light)
        if fg is not None and bg is not None and bg[3] >= 1:
            measured += 1
    assert measured >= 150, f"لم يُقَس إلّا {measured} زوجاً — المسحُ فارغ"
