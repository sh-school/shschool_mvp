"""[DESIGN] كلُّ رمزٍ يُستعمَل معرَّفٌ — و`tailwind.config.js` لا ينسخ لوناً.

`var(--x)` الذي لا يُحَلّ لا يسقط قيمتَه وحدَها: المواصفة تُبطل التصريحَ
بأكملِه («invalid at computed-value time») فيرتدّ إلى `unset`. فـ:

    border: 1px solid var(--border-default);   /* لا وجودَ له */

لا تعني «إطارٌ بلونٍ افتراضيّ» بل `border-style: none` — أي لا إطارَ أصلاً.
وهكذا كان زرُّ الرجوع في فتات الخبز بلا إطارٍ في كلّ صفحةٍ من المنصّة.
و:

    class="text-[var(--muted)]"                /* لا وجودَ له */

لا تعني «رماديّ» بل `color: unset` — واللونُ موروثٌ، فيُطبع النصُّ الخافت
أسودَ كاملَ التباين. كان ذلك في 24 قالباً.

ولأنّ الخطأ صامتٌ — لا استثناء، ولا سطرَ في السجلّ، ولا صفحةَ تُخفق — فلا
يُمسك إلّا بفحصٍ كهذا.

والشطرُ الثاني: `tailwind.config.js` كان ينسخ ألوانَ العلامة أرقاماً
سداسيّةً، فتباعد الملفّان — `gold` فيه `#C9A84C` و`--gold` في `custom.css`
`#D4A843`. فالنسخُ ممنوعٌ: كلُّ لونٍ هناك نافذةٌ على رمزٍ عبر `var()`.
"""

import pathlib
import re

CSS = pathlib.Path("static/css/custom.css")
TW_CONFIG = pathlib.Path("tailwind.config.js")

#: جذورُ القوالب الحيّة — `docs/` وثائقُ مستقلّةٌ لا تُقدَّم من المنصّة.
TEMPLATE_ROOTS = (pathlib.Path("templates"),)

#: تعريفُ رمز: `--name:`
DEF_RE = re.compile(r"--([a-zA-Z0-9_-]+)\s*:")

#: استعمالُ رمزٍ بلا قيمةٍ بديلة: `var(--name)` — وما له بديلٌ يُحَلّ دائماً.
USE_RE = re.compile(r"var\(\s*--([a-zA-Z0-9_-]+)\s*\)")


def _app_template_dirs():
    """قوالبُ التطبيقات — `APP_DIRS` تراها بعد `DIRS`."""
    return sorted(pathlib.Path(".").glob("*/templates"))


def _live_templates():
    for root in TEMPLATE_ROOTS:
        yield from sorted(root.rglob("*.html"))
    for root in _app_template_dirs():
        yield from sorted(root.rglob("*.html"))


def _defined_in(text):
    return set(DEF_RE.findall(text))


def test_the_stylesheet_defines_every_token_it_uses():
    text = CSS.read_text(encoding="utf-8")
    missing = sorted(set(USE_RE.findall(text)) - _defined_in(text))
    assert not missing, "رموزٌ تُستعمَل في custom.css ولا تُعرَّف فيه — والتصريحُ كلُّه يسقط: " + ", ".join(
        "--" + name for name in missing
    )


def test_the_templates_use_no_token_the_platform_never_defines():
    known = _defined_in(CSS.read_text(encoding="utf-8"))
    offenders = {}
    for template in _live_templates():
        text = template.read_text(encoding="utf-8")
        # رمزٌ يُعرَّف في القالب نفسه — في `<style>` أو في `style="--x:…"` — معرَّف.
        local = _defined_in(text)
        unknown = sorted(set(USE_RE.findall(text)) - known - local)
        if unknown:
            offenders[str(template)] = unknown
    assert not offenders, "رموزٌ لا وجودَ لها، والتصريحُ معها يسقط صامتاً:\n" + "\n".join(
        f"  {path}: " + ", ".join("--" + name for name in names)
        for path, names in sorted(offenders.items())
    )


def test_tailwind_copies_no_colour_of_its_own():
    text = TW_CONFIG.read_text(encoding="utf-8")
    literals = sorted(set(re.findall(r"#[0-9a-fA-F]{3,8}\b", text)))
    assert not literals, (
        "ألوانٌ منسوخةٌ في tailwind.config.js — مصدرُ الحقيقةِ `:root` في custom.css، "
        "والقيمةُ تُقرأ بـ var(): " + ", ".join(literals)
    )


def test_no_app_template_is_shadowed_by_a_root_one():
    """`DIRS` تسبق `APP_DIRS`، فالمكرَّرُ في التطبيق ميّتٌ يُحرَّر بلا أثر."""
    shadowed = []
    for root in _app_template_dirs():
        for template in sorted(root.rglob("*.html")):
            name = template.relative_to(root)
            if (pathlib.Path("templates") / name).exists():
                shadowed.append(str(template))
    assert not shadowed, (
        "قوالبُ تطبيقٍ يحجبها مثيلُها في templates/ — تُحرَّر ولا تُعرَض:\n  " + "\n  ".join(shadowed)
    )
