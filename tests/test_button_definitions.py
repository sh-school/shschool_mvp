"""[DESIGN] المفاتيحُ تُعرَّف في موضعٍ واحد — قرارُ المالك 2026-09-20.

كان `btn-sm` معرَّفاً في ثلاثة مواضعَ بقيمٍ متعارضة، فيتوقّف مظهرُ مئات المفاتيح على ترتيب الملفّات.
فالمقاساتُ وأنواعُ المفتاح الدلاليّة تُعرَّف في `20-components.css` وحدَه، وما وراءها صيغٌ خاصّةٌ بوحداتها
مجمَّدةُ الأسماء: صيغةٌ جديدةٌ تعني أنّ نوعاً دلاليّاً موجوداً لم يُستعمل — يُستعمل هو ولا تُعرَّف صيغة.
"""

import pathlib
import re

CSS = pathlib.Path("static/css/custom")
CENTRAL = "20-components.css"

#: مفاتيحٌ دلاليّةٌ ومقاسات — تعريفُها الأساسيّ (قاعدةٌ بمحدِّدٍ واحدٍ هو الصنفُ نفسُه) في الملفّ المركزيّ وحدَه.
CENTRAL_ONLY = (
    "btn-primary",
    "btn-secondary",
    "btn-danger",
    "btn-warning",
    "btn-ghost",
    "btn-success",
    "btn-sm",
    "btn-xs",
)

#: صيغُ الوحدات القائمةُ يومَ التجميد (2026-09-20) — لا تزيد. تُحذف إذا رُحِّلت إلى نوعٍ دلاليّ.
FROZEN_VARIANTS = {
    "btn-export",
}

_RULE_HEAD = re.compile(r"(?m)^[ \t]*([^{}@/\n][^{}\n]*)\{")


def _css_files():
    return sorted(CSS.glob("*.css"))


def test_semantic_buttons_and_sizes_are_defined_only_in_the_components_file():
    offenders = []
    for path in _css_files():
        if path.name == CENTRAL:
            continue
        for head in _RULE_HEAD.findall(path.read_text(encoding="utf-8")):
            # قاعدةٌ مجمَّعةٌ (إخفاءُ المفاتيح عند الطباعة مثلاً) ليست تعريفاً؛ التعريفُ محدِّدٌ واحدٌ هو الصنفُ نفسُه.
            selector = head.strip()
            if any(selector == f".{name}" for name in CENTRAL_ONLY):
                offenders.append(f"{path.name}: {selector}")
    assert not offenders, (
        "تعريفٌ أساسيٌّ لمفتاحٍ دلاليٍّ أو مقاسٍ خارج 20-components.css — يتعارض مع المركزيّ ويتبع ترتيبَ الملفّات:\n  "
        + "\n  ".join(offenders)
    )


def test_no_new_module_button_variant_appears():
    seen = set()
    for path in _css_files():
        seen |= set(re.findall(r"\.(btn-[\w-]+)", path.read_text(encoding="utf-8")))
    central = set(CENTRAL_ONLY)
    new = sorted(seen - central - FROZEN_VARIANTS)
    assert not new, (
        "صيغةُ مفتاحٍ جديدةٌ خارج الأنواع الدلاليّة: "
        + ", ".join(new)
        + " — استعمل primary/secondary/danger/success/warning/ghost بدل تعريف صيغة"
    )


def test_a_disabled_button_looks_disabled_in_one_place():
    css = (CSS / CENTRAL).read_text(encoding="utf-8")
    assert ":disabled" in css and "not-allowed" in css
