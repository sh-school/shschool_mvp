"""
tests/test_css_layers.py
━━━━━━━━━━━━━━━━━━━━━━━━
لا قاعدةَ تحكم بالصدفة — كلُّ قاعدةٍ في طبقةٍ معلَنة.

القاعدةُ خارجَ الطبقات تغلب كلَّ قاعدةٍ داخلَها **مهما علا وزنُ تلك**. فما
دام في الملفّ سطرٌ خارجَ الطبقات، فترتيبُ `@layer` أعلاه لا يصف الملفَّ
وصفاً صادقاً: مَن يقرؤه يظنّ الحكمَ للترتيب، والحكمُ في الحقيقة لموضعِ
السطر.

وقد كان في الملفّ يومَ 2026-09-12 ثلاثُ كتلٍ خارجَ الطبقات — 1874 سطراً
(خُمسَ الملفّ) و443 قاعدةَ `html.dark`. فأُدخلت في طبقاتها، وهذا الحارس
يمنع عودتَها.

وما لا يُقاس هنا: الأثرُ المرئيّ. تحوُّلُ قاعدةٍ إلى طبقةٍ قد يُضعفها أمام
ما يليها ترتيباً، وذلك يُقاس في المتصفّح بفرقِ الأنماط المحسوبة قبلَ وبعد
— لا بقراءة الملفّ. وقد قِيس يومَها على اثنتَي عشرةَ صفحةً في الوضعين.
"""

import pathlib
import re

from tests.css_contrast import iter_rules, strip_noise

CSS_PATH = pathlib.Path("static/css/custom.css")

#: `tailwind` مُعلَنةٌ لورقةٍ أخرى (`tailwind.min.css`) تُحمَّل قبل هذه،
#: فلا كتلةَ لها في هذا الملفّ — وهذا مقصود.
DECLARED_ELSEWHERE = {"tailwind"}

#: طبقةُ الثيم يجب أن تكون الأخيرة: قواعدُ `html.dark` تغلب ما قبلها،
#: وكانت تغلبه وهي خارجَ الطبقات.
THEME_LAYER = "themes"


def _css() -> str:
    return CSS_PATH.read_text(encoding="utf-8")


def _layer_of(context) -> str | None:
    """اسمُ الطبقة الحاوية، أو None إن كانت القاعدةُ خارجَ كلّ طبقة.

    و`search` لا `match`: سطرُ الترتيب `@layer a, b, …;` ينتهي بفاصلةٍ
    منقوطةٍ لا بقوس، فيلتصق برأس الكتلة التي تليه في قراءة `iter_rules`
    — فيصير الرأسُ «… themes; @layer reset». والاسمُ آخرُه.
    """
    for head in context:
        m = re.search(r"@layer\s+([\w-]+)\s*$", head)
        if m:
            return m.group(1)
    return None


def _declared_order(css: str) -> list[str]:
    m = re.search(r"@layer\s+([^{;]+);", strip_noise(css))
    assert m, "لا سطرَ `@layer a, b, …;` في الملفّ — الترتيبُ غيرُ معلَن"
    return [n.strip() for n in m.group(1).split(",") if n.strip()]


# ══════════════════════════════════════════════════════════════════
# ١. لا قاعدةَ خارج الطبقات
# ══════════════════════════════════════════════════════════════════


def test_no_rule_lives_outside_a_layer():
    """كلُّ قاعدةٍ في طبقة — وإلّا غلبت الملفَّ كلَّه بلا قصدٍ من كاتبها."""
    orphans = [(sel, ctx) for sel, _decls, ctx in iter_rules(_css()) if _layer_of(ctx) is None]
    lines = [
        f"  {sel[:74]}" + (f"   داخل: {ctx[-1][:40]}" if ctx else "") for sel, ctx in orphans[:25]
    ]
    more = f"\n  … و{len(orphans) - 25} غيرُها" if len(orphans) > 25 else ""
    assert not orphans, (
        f"{len(orphans)} قاعدةً خارجَ الطبقات — تغلب كلَّ مطبَّقةٍ مهما علا وزنُها:\n"
        + "\n".join(lines)
        + more
    )


# ══════════════════════════════════════════════════════════════════
# ٢. الترتيبُ المعلَن يصف الملفَّ فعلاً
# ══════════════════════════════════════════════════════════════════


def test_the_declared_order_names_every_layer_used():
    """طبقةٌ تُفتح ولم تُعلَن تُرتَّب بموضع أوّل ظهورها — أي بالصدفة ثانيةً."""
    css = _css()
    declared = set(_declared_order(css))
    used = {m.group(1) for m in re.finditer(r"@layer\s+([\w-]+)\s*\{", strip_noise(css))}
    undeclared = used - declared
    assert not undeclared, "طبقاتٌ تُستعمل ولم تُعلَن في سطر الترتيب: " + ", ".join(sorted(undeclared))
    unused = declared - used - DECLARED_ELSEWHERE
    assert not unused, (
        "طبقاتٌ مُعلَنةٌ بلا كتلةٍ في الملفّ: "
        + ", ".join(sorted(unused))
        + " — إمّا أن تُملأ أو تُحذف من السطر"
    )


def test_the_theme_layer_is_last():
    """`html.dark` يجب أن تغلب كلَّ ما قبلها — فطبقتُها آخرُ الترتيب."""
    order = _declared_order(_css())
    assert THEME_LAYER in order, f"`{THEME_LAYER}` ليست في سطر الترتيب"
    assert order[-1] == THEME_LAYER, (
        f"`{THEME_LAYER}` ليست الأخيرة (الترتيب: {' → '.join(order)}) — "
        "فما بعدها يغلب قواعدَ الوضع الداكن"
    )


# ══════════════════════════════════════════════════════════════════
# ٣. ترويسةُ الجدول العنّابيّة نصُّها أبيض — والغلبةُ مقصودة
# ══════════════════════════════════════════════════════════════════


def test_the_maroon_header_keeps_its_white_text_over_the_dark_override():
    """القاعدتان بوزنٍ واحد (0,1,4)، فالحكمُ للطبقة لا للوزن.

    قبل الطبقات كان الحكمُ لترتيب المصدر وحدَه: قاعدةُ الأبيض مكتوبةٌ بعد
    قاعدةِ الليل في الملفّ فتغلبها. وهذا حكمٌ يزول بنقلِ سطر. فصارت قاعدةُ
    الأبيض في آخر `themes`، والغلبةُ مكتوبةٌ لا مصادَفة.
    """
    white_layer = dark_layer = None
    white_i = dark_i = -1
    order = _declared_order(_css())
    for n, (sel, decls, ctx) in enumerate(iter_rules(_css())):
        flat = " ".join(sel.split())
        if "data-plain-head" in flat and decls.get("color"):
            white_layer, white_i = _layer_of(ctx), n
        elif flat.startswith("html.dark table thead th") and decls.get("color"):
            dark_layer, dark_i = _layer_of(ctx), n

    assert white_layer, "قاعدةُ «ترويسةٌ عنّابيّةٌ نصُّها أبيض» غير موجودة"
    assert dark_layer, "قاعدةُ `html.dark table thead th` غير موجودة"

    if white_layer == dark_layer:
        assert white_i > dark_i, (
            f"القاعدتان في طبقةٍ واحدة (`{white_layer}`) وقاعدةُ الأبيض تسبق قاعدةَ الليل "
            "— فيبهت نصُّ الترويسة"
        )
    else:
        assert order.index(white_layer) > order.index(dark_layer), (
            f"قاعدةُ الأبيض في `{white_layer}` وقاعدةُ الليل في `{dark_layer}` — "
            f"والترتيب {' → '.join(order)} يجعل الليلَ يغلب، فيبهت نصُّ الترويسة"
        )


# ══════════════════════════════════════════════════════════════════
# ٤. حارسُ الحارس
# ══════════════════════════════════════════════════════════════════


def test_the_scan_actually_reaches_the_stylesheet():
    """تفكيكٌ يُخفق يُنتج صفرَ قواعدَ فينجح الحارسُ كاذباً."""
    rules = list(iter_rules(_css()))
    assert len(rules) >= 2000, f"لم يُفكَّك إلّا {len(rules)} قاعدةً — المسحُ فارغ"
    layered = sum(1 for _s, _d, c in rules if _layer_of(c))
    assert layered >= 2000, f"{layered} قاعدةً في طبقات — التفكيكُ لا يرى الطبقات"
