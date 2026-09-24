"""محدِّداتُ CSS الناقصة — مركِّبٌ بلا مُحدِّدٍ على أحد جانبيه.

قاعدةُ CSS محدِّدُها غيرُ صالحٍ يُسقطها المتصفّحُ **كلَّها**، بما فيها المحدِّداتُ الصحيحةُ في
القائمة نفسِها — فلا خطأَ في الكونسول ولا أثرَ في `git diff` يلفت النظر. وقد كانت قاعدةُ
انتقال الصفحات (`20-components.css`) بهذه الحال منذ #423: السطرُ `#main-content > .exec-dash >  {`
سقط منه `*`، فسقطت القاعدةُ كلُّها حتى `:not(.exec-dash)` الصحيحةُ في قائمتها، والتلاشي لا يعمل
أصلاً بينما `page-nav.js` يضيف `.is-leaving` وينتظر مدّتَه بلا أثر. وقد ثبت في Chromium
(`CSSStyleSheet.replaceSync`): القاعدةُ بالمحدِّد الناقص = 0 قاعدة، وبإضافة `*` = 1.

هذا المحلِّلُ يجد أربعةَ أشكالٍ من العطل نفسِه:

- `trailing`: ينتهي بمركِّبٍ (`a >`، `a +`، `a ~`) — العطلُ الفعليّ في #423.
- `leading`: يبدأ بمركِّبٍ (`> a`) خارجَ `:has()` — الجهةُ الأخرى للعطل نفسِه.
- `double`: مركِّبان متجاوران (`a > > b`) — مُحدِّدٌ ناقصٌ في الوسط.
- `empty`: عنصرٌ فارغٌ في قائمة المحدِّدات (`a, , b`، أو `a,` بلا ما بعدها).

ما لا يُعدّ مركِّباً: `>` `+` `~` داخل `[…]` (`[a~=b]`) وداخل أقواس الدوالّ التي ليست قوائمَ
محدِّدات (`:nth-child(2n+1)`) وداخل النصوص والمُهرَّب (`\\>`). أمّا الدوالُّ التي تأخذ قائمةَ
محدِّدات (`:is` `:where` `:not` `:has`) فتُفحَص وسائطُها بالقواعد نفسِها، و`:has(> a)` صالحٌ
لأنّ وسيطَه محدِّدٌ نسبيّ.

ولا يفحص ما هو أبعدُ من الشكل (وجودُ الصنف، صحّةُ اسم الخاصّيّة): ذلك حرّاسٌ أخرى. والتداخلُ
الأصليّ (`.a { > .b {} }`) غيرُ مستعملٍ في المنصّة — فمن استعمله فليُعدَّل هذا المحلِّلُ لئلّا
يُبلَّغ عن `> .b` بأنّه `leading`.
"""

from __future__ import annotations

from typing import NamedTuple

COMBINATORS = ">+~"

#: دوالُّ الأصناف الكاذبة التي وسيطُها قائمةُ محدِّدات ← هل وسيطُها نسبيٌّ (يجوز أن يبدأ بمركِّب).
SELECTOR_LIST_FUNCTIONS = {
    ":is": False,
    ":where": False,
    ":not": False,
    ":matches": False,
    ":-webkit-any": False,
    ":-moz-any": False,
    ":has": True,
}


class Finding(NamedTuple):
    kind: str  # trailing | leading | double | empty
    selector: str  # المحدِّدُ المعطوب وحدَه (لا القائمةُ كلُّها)


def split_top_level(text: str, separators: str) -> list[str]:
    """يقسم النصَّ على أحد `separators` خارجَ الأقواس والنصوص والمُهرَّب.

    `[` و`(` يُعدّان قوسين معاً: `[a~=b]` و`:nth-child(2n+1)` لا يقسمان.
    """
    parts: list[str] = []
    buf: list[str] = []
    depth = 0
    quote = ""
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch == "\\":  # حرفٌ مُهرَّب: يُؤخذ ومعه ما بعده كما هو
            buf.append(text[i : i + 2])
            i += 2
            continue
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
        elif ch in "([":
            depth += 1
        elif ch in ")]":
            depth = max(0, depth - 1)
        elif depth == 0 and ch in separators:
            parts.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))
    return parts


def _closing_paren(text: str, opening: int) -> int:
    """موضعُ القوس الذي يغلق `text[opening]` (أو نهايةُ النصّ إن لم يُغلَق)."""
    depth, i, n = 0, opening, len(text)
    while i < n:
        if text[i] == "\\":
            i += 2
            continue
        depth += {"(": 1, ")": -1}.get(text[i], 0)
        if depth == 0:
            return i
        i += 1
    return n


def _functional_arguments(compound: str) -> list[tuple[bool, str]]:
    """(نسبيّ؟، وسيطٌ) لكلّ دالّةِ قائمةِ محدِّدات في المركَّب — `:not(.a, .b)` ← (False، `.a, .b`)."""
    found: list[tuple[bool, str]] = []
    i, n = 0, len(compound)
    while i < n:
        if compound[i] == "\\":
            i += 2
            continue
        if compound[i] == ":":
            j = i + 1
            while j < n and (compound[j].isalnum() or compound[j] in "-_"):
                j += 1
            name = compound[i:j].lower()
            if j < n and compound[j] == "(" and name in SELECTOR_LIST_FUNCTIONS:
                end = _closing_paren(compound, j)
                found.append((SELECTOR_LIST_FUNCTIONS[name], compound[j + 1 : end]))
                i = end
        i += 1
    return found


def _check_complex(selector: str, relative: bool) -> list[Finding]:
    """محدِّدٌ مركَّبٌ واحد — لا فواصلَ على أعلى مستوًى فيه."""
    found: list[Finding] = []
    compounds = split_top_level(selector, COMBINATORS)
    last = len(compounds) - 1
    for index, compound in enumerate(compounds):
        if compound.strip():
            for arg_relative, argument in _functional_arguments(compound):
                if argument.strip():  # `:is()` فارغةٌ صالحة (لا تطابق شيئاً)
                    found.extend(check_list(argument, relative=arg_relative))
        elif last == 0:
            continue  # لا مركِّبَ في المحدِّد أصلاً؛ الفارغُ تعالجه `check_list`
        elif index == 0:
            if not relative:
                found.append(Finding("leading", selector.strip()))
        elif index == last:
            found.append(Finding("trailing", selector.strip()))
        else:
            found.append(Finding("double", selector.strip()))
    return found


def check_list(selector_list: str, relative: bool = False) -> list[Finding]:
    """قائمةُ محدِّداتٍ مفصولةٌ بفواصل — ما يُعثَر فيها من عطل."""
    found: list[Finding] = []
    for item in split_top_level(selector_list, ","):
        if item.strip():
            found.extend(_check_complex(item, relative))
        else:
            found.append(Finding("empty", selector_list.strip()))
    return found


def scan(css: str) -> tuple[int, list[tuple[Finding, str]]]:
    """(عددُ قوائم المحدِّدات المفحوصة، [(عطل، سياقُه)]) لنصّ CSS كامل.

    السياقُ رؤوسُ الكتل الحاوية (`@layer components › @media …`) ليُعرَف موضعُ القاعدة بلا أرقام أسطر.
    """
    from tests.css_contrast import iter_rules

    checked = 0
    bad: list[tuple[Finding, str]] = []
    for head, _decls, ctx in iter_rules(css):
        if head.startswith("@"):
            continue
        checked += 1
        where = " › ".join(c[:40] for c in ctx)
        bad.extend((finding, where) for finding in check_list(head))
    return checked, bad
