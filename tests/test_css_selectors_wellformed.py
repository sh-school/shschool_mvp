"""
tests/test_css_selectors_wellformed.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
لا مُحدِّدَ في أنماط المنصّة يُقطع بعد رابطٍ (`>` `+` `~`) أو يترك مركَّباً فارغاً.

**لماذا حارسٌ لهذا:** المتصفّحُ يُسقط القاعدةَ **كلَّها** إن كان في قائمة مُحدِّداتها مُحدِّدٌ
غيرُ صالح — فلا يُطبَّق منها حتى الجزءُ الصالح. وقد بقيت ثلاثُ قواعد في `20-components.css`
(`#main-content > .exec-dash >  {…}`) مقطوعةً بعد `>` منذ #423 (2026-09-21): سقطت معها
`:not(.exec-dash)` الصالحةُ في القائمة نفسِها، فلم يعمل تلاشي الانتقال بين الصفحات (`page-in` و`.is-leaving`)
على أيّ صفحةٍ ثلاثةَ أيّام — وكلُّ حارسٍ آخر يمرّ: لا `test_css_layers` ولا `test_css_split` ولا
تصغيرُ `collectstatic` يرفض ملفّاً فيه قاعدةٌ لا يفهمها المتصفّح، والخطأُ لا يصل الطرفيّةَ
ولا وحدةَ التحكّم. (كان الأصلُ `> *` والنجمةُ سقطت في النسخ.)

**ما يُفحص:** كلُّ قاعدةٍ ورقيّة (بما في `@media` و`@supports` و`@layer`) بمُحدِّداتها كلِّها:
  - رابطٌ في آخر المُحدِّد (`a >`) أو مركَّبٌ فارغٌ بين رابطَين (`a > > b`، `a + ~ b`)؛
  - رابطٌ في أوّله (`> a`) خارجَ `:has()` — حيث الرابطُ الأوّلُ صالحٌ (`:has(> img)`)؛
  - عنصرٌ فارغٌ في القائمة (`a, , b` أو فاصلةٌ أخيرة)؛
  - قوسٌ أو معقوفٌ غيرُ مغلَق.
ويُفحص ما داخل `:is()` و`:where()` و`:not()` و`:has()` كذلك.

**وما لا يُفحص مقصوداً:** صحّةُ أسماء الأصناف والأشباه (`:hover` يتّصل به `test_dead_classes`)، ولا
مُحدِّداتُ `@keyframes` (`from`/`to`/`50%`) فليست مُحدِّدات عناصر. والبناءُ يدويٌّ لا `cssselect`: هذا
يرفض `:has()` و`:is()` و`::part()` وهي صالحةٌ في المتصفّحات الحديثة فيُنتج إنذاراً كاذباً.
"""

import re

from tests.css_contrast import iter_rules
from tests.css_source import css_paths

#: أشباهُ الأصناف التي تحمل قائمةَ مُحدِّداتٍ فيُفحص ما بين قوسيها. `has` وحدَها تقبل رابطاً أوّل (مُحدِّدٌ نسبيّ).
#: `nth-child(… of S)` و`lang()` و`dir()` و`host()` لا تدخل: حجّتُها ليست قائمةَ مُحدِّدات بسيطة.
SELECTOR_LIST_PSEUDOS = {"is", "where", "not", "has", "matches", "-webkit-any", "-moz-any"}
RELATIVE_PSEUDOS = {"has"}

COMBINATORS = ">+~"

#: أقلُّ ما يُتوقَّع أن تُقرأ من قواعد — يمنع أن ينجح الحارسُ لأنّ القراءةَ لم تُخرج شيئاً.
MIN_RULES = 1500


def _read_group(text: str, start: int) -> int:
    """موضعُ القوس/المعقوف المغلِق للمفتوح عند `start`، أو -1 إن لم يُغلَق. تُتجاوز السلاسلُ والهروب."""
    opener = text[start]
    closer = ")" if opener == "(" else "]"
    depth = 0
    i = start
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            i += 2
            continue
        if ch in "\"'":
            i = _skip_string(text, i)
            continue
        if ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _skip_string(text: str, start: int) -> int:
    """الموضعُ بعد إغلاق السلسلة التي تبدأ عند `start` (أو نهايةُ النصّ إن لم تُغلَق)."""
    quote = text[start]
    i = start + 1
    while i < len(text):
        if text[i] == "\\":
            i += 2
            continue
        if text[i] == quote:
            return i + 1
        i += 1
    return len(text)


def _split_list(text: str) -> list[str]:
    """يقسم على الفاصلة في المستوى الأعلى فقط (لا داخل قوسٍ أو معقوفٍ أو سلسلة)."""
    parts, buf, i = [], "", 0
    while i < len(text):
        ch = text[i]
        if ch == "\\":
            buf += text[i : i + 2]
            i += 2
            continue
        if ch in "\"'":
            j = _skip_string(text, i)
            buf += text[i:j]
            i = j
            continue
        if ch in "([":
            j = _read_group(text, i)
            j = len(text) - 1 if j < 0 else j
            buf += text[i : j + 1]
            i = j + 1
            continue
        if ch == ",":
            parts.append(buf)
            buf = ""
            i += 1
            continue
        buf += ch
        i += 1
    parts.append(buf)
    return parts


def _pseudo_name(compound: str) -> str:
    """اسمُ شبه الصنف الوظيفيّ الذي ينتهي به النصّ قبل `(` (`a:not` → `not`)، أو فارغٌ."""
    m = re.search(r":([\w-]+)$", compound)
    return m.group(1).lower() if m else ""


def selector_defects(selector: str, relative: bool = False) -> list[str]:
    """عيوبُ قائمةِ مُحدِّدات (نصٌّ واحد بفواصله): قائمةُ رسائل، فارغةٌ إن سلمت.

    `relative`: قائمةُ `:has()` — يجوز لكلّ مُحدِّدٍ فيها أن يبدأ برابط.
    """
    defects: list[str] = []
    for item in _split_list(selector):
        if not item.strip():
            defects.append("عنصرٌ فارغٌ في قائمة المُحدِّدات (فاصلةٌ زائدةٌ أو مكرَّرة)")
            continue
        defects += _complex_defects(item, relative)
    return defects


def _complex_defects(text: str, relative: bool) -> list[str]:
    defects: list[str] = []
    seq: list[str] = []  # "C" مركَّب، وإلّا حرفُ الرابط
    cur = ""
    i = 0

    def flush() -> None:
        nonlocal cur
        if cur:
            seq.append("C")
        cur = ""

    while i < len(text):
        ch = text[i]
        if ch == "\\":
            cur += text[i : i + 2]
            i += 2
        elif ch in "\"'":
            j = _skip_string(text, i)
            cur += text[i:j]
            i = j
        elif ch in "([":
            j = _read_group(text, i)
            if j < 0:
                defects.append(f"«{ch}» بلا إغلاق")
                return defects
            if ch == "(" and _pseudo_name(cur) in SELECTOR_LIST_PSEUDOS:
                name = _pseudo_name(cur)
                inner = text[i + 1 : j]
                sub = selector_defects(inner, relative=name in RELATIVE_PSEUDOS)
                defects += [f"داخل :{name}() — {d}" for d in sub]
            cur += text[i : j + 1]
            i = j + 1
        elif ch in COMBINATORS:
            flush()
            seq.append(ch)
            i += 1
        elif ch.isspace():
            flush()
            i += 1
        else:
            cur += ch
            i += 1
    flush()

    if not seq:
        defects.append("مُحدِّدٌ فارغ")
        return defects
    if seq[-1] != "C":
        defects.append(f"ينتهي برابطٍ «{seq[-1]}» بلا مركَّبٍ بعده")
    if seq[0] != "C" and not relative:
        defects.append(f"يبدأ برابطٍ «{seq[0]}» بلا مركَّبٍ قبله")
    for a, b in zip(seq, seq[1:]):
        if a != "C" and b != "C":
            defects.append(f"مركَّبٌ فارغٌ بين رابطَين «{a}» «{b}»")
    return defects


def _in_keyframes(ctx: list[str]) -> bool:
    """`from` و`to` و`50%` مواقيتُ إطارٍ لا مُحدِّداتُ عناصر."""
    return any(re.search(r"@(-\w+-)?keyframes\b", head) for head in ctx)


def _rules():
    for path in css_paths():
        for selector, decls, ctx in iter_rules(path.read_text(encoding="utf-8")):
            if not _in_keyframes(ctx):
                yield path.name, selector, decls


# ══════════════════════════════════════════════════════════════════
# ١. الحارسُ على أنماط المنصّة
# ══════════════════════════════════════════════════════════════════


def test_no_platform_selector_is_truncated_or_has_an_empty_compound():
    broken = []
    total = 0
    for name, selector, decls in _rules():
        total += 1
        for defect in selector_defects(selector):
            first = next(iter(decls.items()), ("", ""))
            broken.append(f"  {name}: `{selector}` {{ {first[0]}: {first[1][:40]}… }} — {defect}")
    assert (
        total >= MIN_RULES
    ), f"قرأ الحارسُ {total} قاعدةً فقط — أخفق تفكيكُ الملفّات، فما يلي لا يُعتدّ به"
    assert not broken, (
        "مُحدِّداتٌ غيرُ صالحةٍ في أنماط المنصّة — المتصفّحُ يُسقط القاعدةَ كلَّها بجزئها الصالح أيضاً "
        "(كان `> *` فسقطت النجمةُ في النسخ، #423):\n" + "\n".join(broken)
    )


# ══════════════════════════════════════════════════════════════════
# ٢. الحارسُ نفسُه — لا يمرّ على غير ما يفهم ولا يرفض الصالح
# ══════════════════════════════════════════════════════════════════

MALFORMED = [
    "#main-content > .exec-dash >",
    "#main-content > :not(.exec-dash), #main-content > .exec-dash >",
    ".a >",
    ".a +",
    ".a ~",
    ".a > > .b",
    ".a + ~ .b",
    "> .a",
    ".a, , .b",
    ".a,",
    ".a:not(.b >)",
    ".a:is(.b, .c >) .d",
    ".a:has(.b >)",
    ".a:not(",
    '.a[data-x="y"',
]

WELL_FORMED = [
    "#main-content > .exec-dash > *",
    "#main-content > :not(.exec-dash)",
    ".a .b",
    ".a>.b+.c~.d",
    ".a:has(> img)",
    ".a:has(> img, + .b)",
    ".a:is(.b, .c) > .d",
    ".a:not(.b, .c):hover::before",
    ".a:nth-child(2n+1)",
    ".a:nth-child(2n + 1 of .b)",
    '.a[data-x=">"] .b',
    '.a[data-x="a,b"] > .b',
    ".a[data-x~=y] > .b",
    ".md\\:flex > .b",
    "html.dark :root, html.dark",
    ":root",
    "*",
    "*, *::before, *::after",
    ".a:lang(ar)",
]


def test_the_guard_flags_every_known_malformed_selector():
    missed = [s for s in MALFORMED if not selector_defects(s)]
    assert not missed, f"الحارسُ لم يرفض: {missed}"


def test_the_guard_accepts_every_known_well_formed_selector():
    rejected = {s: selector_defects(s) for s in WELL_FORMED if selector_defects(s)}
    assert not rejected, f"الحارسُ رفض مُحدِّداً صالحاً: {rejected}"


def test_comments_and_declaration_values_never_count_as_selectors():
    """`iter_rules` تُسقط التعليقات؛ و`>` في `content` أو في تعليقٍ ليس مُحدِّداً."""
    css = '/* .a > */ .b { color: red } .c::after { content: ">" } @media print { .d > .e { color: red } }'
    heads = [selector for selector, _, _ in iter_rules(css)]
    assert heads == [".b", ".c::after", ".d > .e"]
    assert all(not selector_defects(h) for h in heads)
