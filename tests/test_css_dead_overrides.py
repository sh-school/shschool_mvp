"""[CSS] لا تصريحٌ ميّتٌ بالتتالي — ما تكتبه قاعدةٌ ويمحوه لاحقٌ لها بالمُحدِّد نفسِه لا يُرسم أبداً.

قاعدةٌ مثل `.quality-page { width: 98%; padding: 1rem 0 }` تلاها في الملفّ نفسِه
`.quality-page { width: 100%; padding: 0.5rem }` بلا شرطٍ (ثمّ `@media (min-width: 641px)` تُعيد
القيمَ للأوسع): الأولى ميّتةٌ في كلّ نافذة، لكنّها تبقى في الملفّ تُضلّل من يقرؤها ويظنّ أنّ
`98%` هي الجاريةُ، وتُحسب في السقف الخامّ لحمولة الأنماط. وجد قياسُ 2026-09-25 من هذا الصنف
ثماني قواعدَ ميّتةً كلّيّاً وثلاثَ عشرةَ قاعدةً ميّتةً جزئيّاً في الحزمة (≈1KB)، حُذفت كلُّها.

القاعدةُ التي يُحكم بها: تصريحٌ (خاصّيّةٌ + قيمة) في قاعدةٍ لمُحدِّدٍ **مطابقِ النصّ** وسياقِ كتلٍ
**مطابقٍ** (`@media`/`@container`… بالشرط نفسِه) يموت إذا كان في **القاعدة اللاحقة** — بترتيب الطبقات
(`10-foundation.css`) ثمّ ترتيب المصدر — تصريحٌ للخاصّيّة نفسِها أو لاختصارٍ يشملها (`padding` تشمل
`padding-inline`)، وكلاهما بلا `!important` (المهمُّ يقلب ترتيبَ الطبقات فلا يُحكم عليه ساكناً).
ويموت لكلِّ مُحدِّدٍ في قائمة القاعدة، لا لواحدٍ منها.

وما لا يحكم به الحارس مقصود: قاعدةٌ لاحقةٌ داخل `@media` أضيق لا تُميت السابقةَ خارجه (تلك أزواجُ
«الجوّال أوّلاً» الصحيحة)، و`@supports` (احتياطٌ للمتصفّحات القديمة)، وتكرارُ الخاصّيّة داخل القاعدة
الواحدة (`height: 100vh; height: 100dvh` احتياطٌ مقصود). واستثناءٌ مبرَّرٌ يُكتب في `INTENTIONAL` بسببه.

وقاعدةٌ ثانيةٌ من الصنف نفسِه في `40-themes.css`: نظيرٌ ليليٌّ (`html.dark X`) يكرّر **القيمةَ النهاريّةَ**
نفسَها لقاعدةٍ نهاريّةٍ مطابقة (`X`) — والرموزُ تنقلب ليلاً بنفسها فلا حاجةَ إليه. وجد القياسُ 40 نظيراً
كهذا؛ حُذف 29 منها بعد أن أثبت مراجعان مستقلّان وقياسُ الأنماط المحسوبة على 164 صفحةً أنّه لا أثر،
وبقيت 11 يتنازعها ما يغلبها لو حُذفت (قاعدةٌ ثالثةٌ بالنوعيّة أو الطبقة تتسرّب إلى الليل، أو لم يُثبَت
غيابُها)؛ فهي **سقّاطةٌ** لا تزيد: نظيرٌ جديدٌ مطابقٌ يُكتب فقط إن كانت له قاعدةٌ ثالثةٌ تستدعيه،
وحينها يُرفع الحدُّ بسببه.
"""

from __future__ import annotations

import re
from collections import defaultdict

from tests.css_contrast import iter_rules
from tests.css_selectors import split_top_level
from tests.css_source import read_css

#: خاصّيّاتٌ تشملها اختصاراتٌ: كتابةُ الاختصار لاحقاً تمحو الطويلة قبلها.
COVERED_BY = {
    "margin": (
        "margin-top",
        "margin-right",
        "margin-bottom",
        "margin-left",
        "margin-block",
        "margin-inline",
        "margin-block-start",
        "margin-block-end",
        "margin-inline-start",
        "margin-inline-end",
    ),
    "padding": (
        "padding-top",
        "padding-right",
        "padding-bottom",
        "padding-left",
        "padding-block",
        "padding-inline",
        "padding-block-start",
        "padding-block-end",
        "padding-inline-start",
        "padding-inline-end",
    ),
    "margin-inline": ("margin-inline-start", "margin-inline-end"),
    "margin-block": ("margin-block-start", "margin-block-end"),
    "padding-inline": ("padding-inline-start", "padding-inline-end"),
    "padding-block": ("padding-block-start", "padding-block-end"),
    "gap": ("row-gap", "column-gap"),
    "overflow": ("overflow-x", "overflow-y"),
    "inset": (
        "top",
        "right",
        "bottom",
        "left",
        "inset-inline",
        "inset-block",
        "inset-inline-start",
        "inset-inline-end",
        "inset-block-start",
        "inset-block-end",
    ),
    "border-radius": (
        "border-top-left-radius",
        "border-top-right-radius",
        "border-bottom-left-radius",
        "border-bottom-right-radius",
    ),
}

#: (المُحدِّد، الخاصّيّة) ← السبب. فارغةٌ لأنّ كلَّ ما وجده القياسُ حُذف؛ وأيُّ إدخالٍ جديدٌ يحتاج سبباً.
INTENTIONAL: dict[tuple[str, str], str] = {}

#: حدٌّ أدنى لما يراه الحارس — قيسَ نحو 2,600 قاعدةٍ يومَ كتابته. إن سقط تحته فالقارئ معطوب
#: فصار الحارسُ يمرّ بلا أن يفحص شيئاً.
MIN_RULES = 1500

#: نظائرُ ليليّةٌ تطابق قيمتَها النهاريّة وتبقى لأنّ قاعدةً ثالثةً تغلب النهاريّةَ فتتسرّب ليلاً لو حُذفت
#: (`.action-card` و`.pagination a:hover` و`.per-grid thead th`…) أو لم يُثبَت غيابُها (`.breadcrumbs .bc-sep`).
#: لا يزيد العدد؛ ويُخفَّض إن حُذف نظيرٌ.
MAX_IDENTICAL_DARK_TWINS = 11
DARK_PREFIX = "html.dark "

LAYER_ORDER_RE = re.compile(r"@layer\s+([\w\s,-]+?)\s*;")


def _layer_order(css: str) -> list[str]:
    match = LAYER_ORDER_RE.search(css)
    assert match, "لم أجد جملةَ ترتيب الطبقات (`@layer a, b, c;`) — ينتظرها الحارسُ في أوّل ملفّ"
    return [name.strip() for name in match.group(1).split(",")]


def _layer_of(stack: list[str], order: list[str]) -> int:
    for head in stack:
        if head.startswith("@layer "):
            name = head[len("@layer ") :].strip()
            return order.index(name) if name in order else -1
    return -1


def dead_declarations(css: str) -> list[tuple[str, str, str, str]]:
    """(المُحدِّد، الخاصّيّة، القيمة الميّتة، سياق الكتل) لكلّ تصريحٍ يموت بالتتالي."""
    order = _layer_order(css)
    rules = []
    for position, (head, decls, stack) in enumerate(iter_rules(css)):
        if head.startswith("@"):
            continue
        context = tuple(h for h in stack if not h.startswith("@layer"))
        if any(h.startswith("@supports") for h in context):
            continue
        selectors = tuple(" ".join(s.split()) for s in split_top_level(head, ",") if s.strip())
        rules.append((_layer_of(stack, order), position, selectors, context, decls))

    by_selector: dict[tuple[str, tuple[str, ...]], list[tuple[int, int, dict[str, str]]]] = (
        defaultdict(list)
    )
    for layer, position, selectors, context, decls in rules:
        for selector in selectors:
            by_selector[(selector, context)].append((layer, position, decls))

    found = []
    for layer, position, selectors, context, decls in rules:
        for prop, value in decls.items():
            if "!important" in value.replace(" ", "").lower():
                continue
            if all(
                _overridden_later(by_selector[(s, context)], layer, position, prop)
                for s in selectors
            ):
                found.append((", ".join(selectors), prop, value, " > ".join(context)))
    return found


def _overridden_later(group, layer: int, position: int, prop: str) -> bool:
    for other_layer, other_position, other in group:
        if (other_layer, other_position) <= (layer, position):
            continue
        for other_prop, other_value in other.items():
            if "!important" in other_value.replace(" ", "").lower():
                continue
            if other_prop == prop or prop in COVERED_BY.get(other_prop, ()):
                return True
    return False


def test_no_declaration_is_overridden_by_a_later_rule_of_the_same_selector():
    dead = [d for d in dead_declarations(read_css()) if (d[0], d[1]) not in INTENTIONAL]
    listing = "\n  ".join(
        f"{sel[:70]}  {prop}: {value[:30]}" + (f"   داخل: {ctx}" if ctx else "")
        for sel, prop, value, ctx in dead[:30]
    )
    assert not dead, (
        "تصريحاتٌ يمحوها لاحقٌ بالمُحدِّد نفسِه — احذفها (أو اكتب استثناءً مبرَّراً في INTENTIONAL):\n  "
        + listing
    )


def test_the_guard_reads_enough_rules_to_mean_something():
    assert sum(1 for head, _, _ in iter_rules(read_css()) if not head.startswith("@")) >= MIN_RULES


def test_the_detector_sees_what_it_claims_to_see():
    """فحصٌ ذاتيٌّ على أنماطٍ مصطنعة: ما يجب أن يُلتقط يُلتقط، وما يجب ألّا يُلمس لا يُلمس."""
    css = """
    @layer base, modules, themes;
    @layer modules {
      .a { width: 98%; color: red; }
      .a { width: 100%; }
      .b { padding-inline: 4px; }
      .b { padding: 8px; }
      .c { width: 10px; }
      @media (min-width: 641px) { .c { width: auto; } }
      .d { height: 1px !important; }
      .d { height: 2px; }
      .e, .f { top: 0; }
      .e { top: 1px; }
    }
    @layer themes { .a { color: blue; } }
    @supports (display: grid) { @layer modules { .g { display: block; } .g { display: flex; } } }
    """
    found = {(sel, prop) for sel, prop, _, _ in dead_declarations(css)}
    assert (".a", "width") in found  # التالي في الطبقة نفسِها
    assert (".a", "color") in found  # الطبقةُ الأعلى تحسم ولو كان مصدرُها أسبق
    assert (".b", "padding-inline") in found  # الاختصارُ اللاحق يشمل الطويلة
    assert (".c", "width") not in found  # لاحقٌ داخل @media لا يُميت ما خارجه
    assert (".d", "height") not in found  # !important يقلب الحكم فلا يُحكم ساكناً
    assert (".e, .f", "top") not in found  # يموت لمُحدِّدٍ واحدٍ فقط من القائمة
    assert (".g", "display") not in found  # @supports مستثنى


def identical_dark_twins(css: str) -> list[str]:
    """المُحدِّداتُ (بلا `html.dark `) التي تكرّر كلُّ تصريحاتِها قيمةَ قاعدةٍ نهاريّةٍ لنفس المُحدِّد."""
    order = _layer_order(css)
    themes = order.index("themes")
    light: dict[tuple[str, tuple[str, ...]], list[dict[str, str]]] = defaultdict(list)
    dark = []
    for head, decls, stack in iter_rules(css):
        if head.startswith("@"):
            continue
        context = tuple(h for h in stack if not h.startswith("@layer"))
        selectors = [" ".join(s.split()) for s in split_top_level(head, ",") if s.strip()]
        if (
            _layer_of(stack, order) == themes
            and len(selectors) == 1
            and selectors[0].startswith(DARK_PREFIX)
        ):
            dark.append((selectors[0][len(DARK_PREFIX) :].strip(), context, decls))
            continue
        normalised = {prop: " ".join(value.split()) for prop, value in decls.items()}
        for selector in selectors:
            light[(selector, context)].append(normalised)
    twins = []
    for base, context, decls in dark:
        candidates = light.get((base, context), [])
        if decls and all(
            any(other.get(prop) == " ".join(value.split()) for other in candidates)
            for prop, value in decls.items()
        ):
            twins.append(base)
    return twins


def test_identical_dark_twins_do_not_grow():
    twins = identical_dark_twins(read_css())
    assert len(twins) <= MAX_IDENTICAL_DARK_TWINS, (
        f"{len(twins)} نظيراً ليليّاً يكرّر القيمةَ النهاريّةَ (الحدّ {MAX_IDENTICAL_DARK_TWINS}) — الرموزُ تنقلب "
        "ليلاً بنفسها فلا حاجةَ إليه إلّا إن غلبت النهاريّةَ قاعدةٌ ثالثة. المطابقةُ اليوم:\n  "
        + "\n  ".join(sorted(twins))
    )


def test_the_twin_detector_sees_what_it_claims_to_see():
    css = """
    @layer base, modules, themes;
    @layer modules { .a { color: red; } .b { color: red; } .c { color: red; } }
    @layer themes {
      html.dark .a { color: red; }
      html.dark .b { color: blue; }
      html.dark .c { color: red; background: black; }
    }
    """
    assert identical_dark_twins(css) == [".a"]
