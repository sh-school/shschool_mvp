"""[IDENTITY] تجميدُ Tailwind (VI-03، قرارُ المالك D-14 2026-09-25) — لا صنفَ Tailwind جديدٌ.

**Tailwind يُزال على مرحلتين** (D-14): المرحلةُ الأولى تجميدُ ما يُستعمل اليوم، والثانيةُ (VI-12، بعد لقطات VI-13) إعادةُ كتابته في
`50-utilities.css` وحذفُ `tailwind.min.css` وخطوةِ البناء. وبين المرحلتين كان الاستعمالُ ينمو: 250 ← 261 صنفاً في أربعة أيّامٍ
(قوالبُ المنتج: `password_reset` و`exemption_rows` و`observation_form`…) — وكلُّ صنفٍ جديدٍ صنفٌ آخرُ يُعاد كتابتُه في المرحلة الثانية.

**الحارسُ يقرأ الناتجَ لا القوالب.** `tailwind.min.css` ناتجُ JIT من المحتوى (`tailwind.config.js:content`)، فكلُّ صنفٍ فيه مستعملٌ فعلاً
في قالبٍ أو سكربت؛ وصنفٌ جديدٌ في أيّ قالبٍ يُغيّر الناتجَ (وفحصُ CI `tailwind-build` يُجبر على التزامه)، فيسقط هذا الحارسُ عليه —
بلا مسحٍ ثانٍ للقوالب قد يخطئ ما يبنيه Tailwind فعلاً (`@apply`، والأصنافُ المركَّبةُ وقتَ التشغيل).

**التعريف (يُنقل إلى الخارطة بنصّه):** «صنفُ Tailwind» = اسمُ صنفٍ يظهر مُحدِّداً في `static/css/tailwind.min.css` (بعد فكّ الهروب)، بما فيه
مُعدِّلاتُ المتغيّرات (`md:flex`) والقيمُ الاعتباطيّة (`bg-[var(--x)]`) وأصنافُ الأساس التي يولّدها البناءُ؛ ولا يُحسب ما في `[…]` من محدِّدات
السمات. وقد يزيد على «الأصناف المستعملة في القوالب» لأنّ الناتجَ يحمل أصنافاً يولّدها Tailwind نفسُه (`container`، والمعدِّلاتُ بـ`!`).

**يمنع الزيادةَ ولا يفرض تسجيلَ النقصان** (خلافَ السقّاطات): الهدفُ الصفرُ (VI-12) فكلُّ نقصٍ مطلوب، ولا نُثقل طلباتِ الإزالة بتعديل ملفٍّ.
وإضافةُ اسمٍ إلى خطّ الأساس **قرارٌ يُسأل عنه في المراجعة** لا ضجيج — والبديلُ الأصلُ: صنفٌ في `50-utilities.css` أو رمزٌ.
"""

from __future__ import annotations

import json
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
COMPILED = ROOT / "static" / "css" / "tailwind.min.css"
BASELINE = ROOT / "tests" / "tailwind_freeze_baseline.json"

NAME_CHARS = re.compile(r"[A-Za-z0-9_\-]")
HEX = re.compile(r"[0-9a-fA-F]")

#: أقلُّ ما يجب أن يراه الحارس — قيسَ 150+ اسماً يومَ كتابته. إن سقط تحته فقد عطب القارئُ فصار الحارسُ يمرّ بلا أن يفحص شيئاً.
MIN_CLASSES = 100


def unescape_at(text: str, i: int) -> tuple[str, int]:
    """يفكّ هروبَ CSS الذي يبدأ بـ`\\` عند الفهرس i؛ يُعيد (الحرف، الفهرس التالي)."""
    j = i + 1
    if j >= len(text):
        return "", j
    if HEX.match(text[j]):
        k = j
        while k < len(text) and k - j < 6 and HEX.match(text[k]):
            k += 1
        char = chr(int(text[j:k], 16))
        if k < len(text) and text[k] in " \t\n\r":
            k += 1  # فراغٌ واحدٌ يُنهي الهروبَ السداسيّ
        return char, k
    return text[j], j + 1


def class_names(selector_list: str) -> set[str]:
    """أسماءُ الأصناف في قائمة محدِّدات — يتخطّى `[…]` ويفكّ الهروب."""
    found: set[str] = set()
    i, n = 0, len(selector_list)
    while i < n:
        c = selector_list[i]
        if c == "\\":
            _, i = unescape_at(selector_list, i)
        elif c == "[":
            depth = 0
            while i < n:
                if selector_list[i] == "\\":
                    _, i = unescape_at(selector_list, i)
                    continue
                if selector_list[i] == "[":
                    depth += 1
                elif selector_list[i] == "]":
                    depth -= 1
                    if depth == 0:
                        i += 1
                        break
                i += 1
        elif c == ".":
            i += 1
            name = []
            while i < n:
                if selector_list[i] == "\\":
                    char, i = unescape_at(selector_list, i)
                    name.append(char)
                elif NAME_CHARS.match(selector_list[i]):
                    name.append(selector_list[i])
                    i += 1
                else:
                    break
            if name:
                found.add("".join(name))
        else:
            i += 1
    return found


def compiled_classes(css: str) -> set[str]:
    """كلُّ اسمِ صنفٍ يُستعمل مُحدِّداً في ناتج Tailwind (بما فيه ما داخل `@media` و`@supports`)."""
    names: set[str] = set()
    css = re.sub(r"/\*.*?\*/", "", css, flags=re.DOTALL)  # تعليقُ الترخيص يحمل `v3.4.19` و`.com`
    for prelude in re.findall(r"([^{};]+)\{", css):
        if prelude.lstrip().startswith("@"):
            continue
        names |= class_names(prelude)
    return names


def frozen() -> set[str]:
    return set(json.loads(BASELINE.read_text(encoding="utf-8")))


def test_no_new_tailwind_class_appears():
    used = compiled_classes(COMPILED.read_text(encoding="utf-8"))
    new = sorted(used - frozen())
    assert not new, (
        f"{len(new)} صنفَ Tailwind جديداً (D-14: Tailwind يُزال — VI-12) — اكتب الأمرَ بصنفٍ في `50-utilities.css` أو برمز، "
        "ولا تُضِفه إلى `tests/tailwind_freeze_baseline.json` إلّا بقرارٍ يُسأل عنه:\n  "
        + "\n  ".join(new)
    )


def test_the_guard_reads_enough_classes_to_mean_something():
    assert len(compiled_classes(COMPILED.read_text(encoding="utf-8"))) >= MIN_CLASSES


def test_the_baseline_is_a_sorted_list_without_duplicates():
    names = json.loads(BASELINE.read_text(encoding="utf-8"))
    assert names == sorted(
        set(names)
    ), "خطُّ الأساس قائمةٌ مرتَّبةٌ بلا تكرار — كي يقرأ المراجعُ فرقَه سطراً سطراً"


class TestTheParserItself:
    def test_variants_arbitrary_values_and_escapes(self):
        css = (
            r".md\:flex{display:flex}.gap-2\.5{gap:.625rem}.\32xl\:grid{display:grid}"
            r".bg-\[var\(--x\)\]:hover{color:red}"
        )
        assert compiled_classes(css) == {"md:flex", "gap-2.5", "2xl:grid", "bg-[var(--x)]"}

    def test_attribute_selectors_at_rules_and_nesting(self):
        css = (
            '[type="text"],[href$=".com"]{color:red}'
            "@media (min-width:640px){.sm\\:flex{display:flex}}"
            "@supports (display:grid){.grid{display:grid}}"
            "@keyframes spin{to{transform:rotate(360deg)}}"
            ".group:hover .group-hover\\:x{color:red}"
        )
        assert compiled_classes(css) == {"sm:flex", "grid", "group", "group-hover:x"}

    def test_a_hex_escape_ends_with_one_space(self):
        assert compiled_classes(r".\31 9{width:1px}") == {"19"}
