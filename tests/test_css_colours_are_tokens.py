"""[DESIGN] مصدرُ اللون الوحيد رموزُ `:root` — لا لونَ حرفيّاً داخل قاعدة.

صارت القوالبُ صفراً، وبقي `custom.css` نفسُه يكتب نحو 380 لوناً حرفيّاً داخل
قواعده، ولكثيرٍ منها نظيرةٌ في `html.dark` تكرّر القاعدةَ بلونٍ ليليّ. فمن أراد
أن يعرف «ما لونُ حدِّ القائمة ليلاً؟» قرأ قاعدتين في طبقتين، وربّما ثالثةً
أخصَّ منهما تغلبهما.

فالقاعدةُ الآن تقرأ رمزاً، والرمزُ له قيمتان: في `:root` للنهار وفي `html.dark`
لليل. والحرفيُّ مسموحٌ في موضعٍ واحد: تعريفُ الرمز نفسه. و`transparent`
و`currentColor` و`inherit` ليست ألواناً تُنسخ.

والشطرُ الثاني: `static/js/*.js` — لونٌ يكتبه السكربتُ في `style` أو في لوحة
رسمٍ رقمٌ ثانٍ لا يتبع الرمز؛ يُقرأ بـ`var(--x)` أو بـ`chartColor`/`chartAlpha`.
"""

import pathlib
import re

from tests.css_contrast import iter_rules

CSS = pathlib.Path("static/css/custom.css")
JS_ROOT = pathlib.Path("static/js")

#: أسماءُ ألوان CSS — ومنها ألوانُ النظام (`canvas`، `canvastext`).
NAMED = frozenset(
    """aliceblue antiquewhite aqua aquamarine azure beige bisque black blanchedalmond blue
    blueviolet brown burlywood cadetblue chartreuse chocolate coral cornflowerblue cornsilk
    crimson cyan darkblue darkcyan darkgoldenrod darkgray darkgreen darkgrey darkkhaki
    darkmagenta darkolivegreen darkorange darkorchid darkred darksalmon darkseagreen
    darkslateblue darkslategray darkslategrey darkturquoise darkviolet deeppink deepskyblue
    dimgray dimgrey dodgerblue firebrick floralwhite forestgreen fuchsia gainsboro ghostwhite
    gold goldenrod gray grey green greenyellow honeydew hotpink indianred indigo ivory khaki
    lavender lavenderblush lawngreen lemonchiffon lightblue lightcoral lightcyan
    lightgoldenrodyellow lightgray lightgreen lightgrey lightpink lightsalmon lightseagreen
    lightskyblue lightslategray lightslategrey lightsteelblue lightyellow lime limegreen linen
    magenta maroon mediumaquamarine mediumblue mediumorchid mediumpurple mediumseagreen
    mediumslateblue mediumspringgreen mediumturquoise mediumvioletred midnightblue mintcream
    mistyrose moccasin navajowhite navy oldlace olive olivedrab orange orangered orchid
    palegoldenrod palegreen paleturquoise palevioletred papayawhip peru pink plum powderblue
    purple rebeccapurple red rosybrown royalblue saddlebrown salmon sandybrown seagreen
    seashell sienna silver skyblue slateblue slategray slategrey snow springgreen steelblue
    tan teal thistle tomato turquoise violet wheat white whitesmoke yellow yellowgreen
    canvas canvastext""".split()
)

_HEX = r"#(?:[0-9a-fA-F]{8}|[0-9a-fA-F]{6}|[0-9a-fA-F]{3,4})(?![\w-])"
_FUNC = r"\b(?:rgba?|hsla?)\("
_NAME = r"(?<![\w.#$@-])(?:" + "|".join(sorted(NAMED, key=len, reverse=True)) + r")(?![\w(-])"
CSS_LITERAL = re.compile(f"{_HEX}|{_FUNC}|{_NAME}", re.I)

#: خاصّيّاتٌ قيمُها أسماءٌ لا ألوان — `font-family: Tan` خطٌّ، و`animation: pulse` حركة.
NOT_COLOUR_PROPS = frozenset(
    {
        "font-family",
        "font",
        "animation",
        "animation-name",
        "transition",
        "transition-property",
        "will-change",
        "grid-template-areas",
        "grid-area",
        "counter-reset",
        "counter-increment",
        "list-style-type",
        "content",
        "src",
        "unicode-range",
        "container-name",
        "view-transition-name",
    }
)

#: مُحدِّداتُ كتل الرموز — نهاراً وليلاً.
TOKEN_BLOCK = frozenset({":root", "html.dark", "html.dark :root"})


def _is_token_block(selector: str) -> bool:
    return all(" ".join(part.split()) in TOKEN_BLOCK for part in selector.split(","))


def _scrub_value(value: str) -> str:
    """السلاسلُ و`url()` ليست ألواناً — `url(#grad)` مرجعٌ لا لون."""
    value = re.sub(r"\"[^\"]*\"|'[^']*'", '""', value)
    return re.sub(r"url\([^)]*\)", "url()", value, flags=re.I)


def css_literals(css: str) -> list[str]:
    """كلُّ لونٍ حرفيٍّ خارج تعريف رمزٍ في كتلة رموز — «مُحدِّد { خاصّيّة: القيمة }»."""
    found = []
    for selector, decls, _ctx in iter_rules(css):
        token_block = _is_token_block(selector)
        for prop, value in decls.items():
            if prop.startswith("--") and token_block:
                continue
            clean = _scrub_value(value)
            for match in CSS_LITERAL.finditer(clean):
                literal = match.group(0)
                if prop in NOT_COLOUR_PROPS and not literal.startswith(("#", "rgb", "hsl")):
                    continue
                found.append(f"{' '.join(selector.split())[:60]} {{ {prop}: {literal} }}")
    return found


_JS_COMMENT = re.compile(r"/\*.*?\*/|(?<![:\\\"'])//[^\n]*", re.S)
_JS_NAMED_STYLE = re.compile(
    r"(?:color|background|border|fill|stroke|outline|shadow)[\w-]*\s*[:=]\s*['\"`]?\s*("
    + "|".join(sorted(NAMED, key=len, reverse=True))
    + r")\b",
    re.I,
)
JS_LITERAL = re.compile(f"(?<![\\w&]){_HEX}|{_FUNC}", re.I)


def js_literals(js: str) -> list[str]:
    code = _JS_COMMENT.sub("", js)
    found = [m.group(0) for m in JS_LITERAL.finditer(code)]
    found += [m.group(1) for m in _JS_NAMED_STYLE.finditer(code)]
    return found


def _live_scripts():
    return sorted(p for p in JS_ROOT.glob("*.js") if not p.name.endswith(".min.js"))


# ══════════════════════════════════════════════════════════════════
# ١. الملفّان الحيّان
# ══════════════════════════════════════════════════════════════════


def test_no_rule_in_the_stylesheet_writes_a_colour_by_hand():
    offenders = css_literals(CSS.read_text(encoding="utf-8"))
    assert not offenders, (
        f"{len(offenders)} لوناً حرفيّاً داخل قواعد custom.css — اكتب `var(--رمز)`، وإن لم يوجد "
        "فأضِفه في `:root` وفي `html.dark` باسمٍ بما يعنيه:\n  " + "\n  ".join(offenders[:30])
    )


def test_no_live_script_writes_a_colour_by_hand():
    offenders = {
        path.as_posix(): hits
        for path in _live_scripts()
        if (hits := js_literals(path.read_text(encoding="utf-8")))
    }
    assert not offenders, (
        "لونٌ حرفيٌّ في سكربتٍ حيّ — اقرأه من الرمز (`var(--x)` أو `chartColor`):\n"
        + "\n".join(f"  {path}: {', '.join(hits)}" for path, hits in offenders.items())
    )


# ══════════════════════════════════════════════════════════════════
# ٢. حرّاسُ الحارس
# ══════════════════════════════════════════════════════════════════


def test_the_scan_reaches_the_stylesheet_and_the_scripts():
    """مسحٌ لا يرى شيئاً ينجح كاذباً."""
    rules = list(iter_rules(CSS.read_text(encoding="utf-8")))
    assert len(rules) >= 2000, f"لم يُفكَّك إلّا {len(rules)} قاعدة"
    tokens = sum(
        1 for sel, decls, _c in rules if _is_token_block(sel) for k in decls if k.startswith("--")
    )
    assert tokens >= 300, f"تعريفاتُ الرموز {tokens} — كتلُ `:root`/`html.dark` لم تُقرأ"
    assert len(_live_scripts()) >= 5


def test_each_kind_of_literal_is_caught_and_token_definitions_are_spared():
    css = """
    :root { --a: #8A1538; --b: rgba(0,0,0,.1); }
    html.dark { --a: #f9a8c9; }
    @media (prefers-contrast: more) { :root { --c: #555; } }
    .ok { color: var(--a); border: 1px solid transparent; fill: currentColor; font-family: 'Tan', serif; }
    .ok::after { content: "#fff"; background: url(#grad); animation: tan 1s; }
    .hex { color: #fff; }
    .fn { background: rgba(255, 255, 255, .2); }
    .hsl { border-color: hsl(0 0% 50%); }
    .name { outline: 2px solid white; }
    .local { --tw-ring-color: #475569; }
    html.dark .twin { color: red; }
    .fallback { color: var(--missing, #666); }
    """
    got = css_literals(css)
    joined = "\n".join(got)
    for expected in ("#fff", "rgba(", "hsl(", "white", "#475569", "red", "#666"):
        assert expected in joined, f"لم يُمسَك {expected}:\n{joined}"
    assert len(got) == 7, joined


def test_script_literals_are_caught_but_ids_and_entities_are_not():
    js = """
    // #dc2626 في تعليقٍ لا يُعدّ
    el.innerHTML = '<span style="color:#dc2626">' + x;
    ctx.fillStyle = 'rgba(0,0,0,.5)';
    node.style.color = 'red';
    document.querySelector('#add-form');
    const amp = '&#123;';
    node.style.color = 'var(--status-danger)';
    """
    assert sorted(js_literals(js)) == sorted(["#dc2626", "rgba(", "red"])
