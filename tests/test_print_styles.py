"""[PRINT] الورقُ نهاريٌّ، وقواعدُ الطباعة تغلب ما تحتها، ولا تكتب ما لا يقع.

ثلاثُ عللٍ قيست بطباعة مكوّنات المنصّة (2026-09-14):

1. من طبع وهو في الوضع الداكن خرجت بطاقاتٌ كحليّةٌ بنصٍّ #f1f5f9 على ورقٍ
   أبيض — قواعدُ `html.dark` لا تعرف الطباعة. فيُنزع الصنفُ في `beforeprint`.
2. كتلةُ الطباعة العامّة كانت في طبقة components، فتخسر أمام modules وthemes:
   بقي ظلُّ `.table-wrap` في الورق رغم `box-shadow: none`.
3. ترويسةُ الموقع طُبعت بأزرارها (تبديلُ الوضع، الجرس، المستخدم) بياضاً على
   عنّابيٍّ يسقط حين تُطفأ «رسومُ الخلفيّة». وقواعدُ `:hover` داخل الطباعة
   لا تقع أبداً — لا مؤشّرَ على الورق.
"""

import pathlib
import re

from tests.css_contrast import iter_rules

CSS = pathlib.Path("static/css/custom.css")
BASE_JS = pathlib.Path("static/js/base.js")


def _print_rules():
    for selector, decls, ctx in iter_rules(CSS.read_text(encoding="utf-8")):
        if any(re.match(r"@media\s+print\b", head) for head in ctx):
            yield selector, decls, ctx


def _layer(ctx):
    return next((head.split()[1] for head in ctx if head.startswith("@layer ")), None)


def test_dark_mode_is_lifted_before_printing_and_restored_after():
    js = BASE_JS.read_text(encoding="utf-8")
    before = re.search(
        r"addEventListener\('beforeprint',\s*function\s*\(\)\s*\{(.*?)\}\);", js, re.S
    )
    after = re.search(r"addEventListener\('afterprint',\s*function\s*\(\)\s*\{(.*?)\}\);", js, re.S)
    assert before and "classList.remove('dark')" in before.group(
        1
    ), "base.js لا ينزع الوضعَ الداكن قبل الطباعة — فتُطبع البطاقاتُ كحليّةً بنصٍّ فاتح"
    assert after and "classList.add('dark')" in after.group(
        1
    ), "base.js لا يُعيد الوضعَ الداكن بعد الطباعة"
    assert "localStorage" not in before.group(1) + after.group(1), "الطباعةُ لا تمسّ التفضيلَ المحفوظ"


def test_the_global_print_block_sits_above_components_and_modules():
    layers = {_layer(ctx) for selector, _, ctx in _print_rules() if selector == "body"}
    assert layers == {"utilities"}, (
        f"كتلةُ الطباعة العامّة (قاعدةُ body) في {sorted(map(str, layers))} — "
        "في طبقةٍ تحت modules تخسر قواعدُها أمام كلّ وحدة"
    )


def test_the_site_chrome_does_not_reach_paper():
    hidden = set()
    for selector, decls, _ in _print_rules():
        if decls.get("display", "").startswith("none"):
            hidden |= {" ".join(part.split()) for part in selector.split(",")}
    wanted = {
        ".site-header .theme-toggle",
        ".site-header .nav-bell",
        ".site-header .nav-user-btn",
        ".msgs-wrap",
        ".btn-primary",
        ".btn-secondary",
        ".btn-ghost",
    }
    assert not wanted - hidden, "عناصرُ تفاعليّةٌ تُطبع: " + ", ".join(sorted(wanted - hidden))


def test_print_rules_style_no_state_paper_cannot_have():
    offenders = sorted(
        {
            selector
            for selector, _, _ in _print_rules()
            if re.search(r":(hover|focus|focus-visible|active)\b", selector)
        }
    )
    assert not offenders, "قواعدُ حالةٍ داخل الطباعة لا تقع على الورق:\n  " + "\n  ".join(offenders)
