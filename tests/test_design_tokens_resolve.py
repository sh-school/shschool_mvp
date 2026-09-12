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

#: جذورٌ لا تُمسح: ليست شيفرةَ المنصّة.
#:
#: و`.claude` منها لأنّ شجراتِ العمل المتوازية تسكنها — نسخةٌ كاملةٌ من
#: المستودع لكلّ محادثة. فحارسٌ يمسح من الجذر كان يعدّ `custom.css` في كلّ
#: شجرةٍ ملفَّ أنماطٍ ثانياً، ويعدّ `core/brand.py` فيها ناسخاً للألوان —
#: فيسقط محلّيّاً لمن يستعمل التوازي، ويمرّ في CI حيث السحبُ نظيف. وحارسٌ
#: يسقط لسببٍ ليس في العمل يُعلَّم أن يُتجاهَل، ثمّ لا يُقرأ حين يصدق.
#:
#: و`AAdocs` كذلك: مجلَّدٌ في `.gitignore` لا يُتتبَّع منه إلّا ملفّا خارطةٍ
#: أُضيفا بالإجبار. فما فيه من سكربتاتٍ لا يُشحن ولا تراه CI — وحارسٌ يمنع
#: نسخَ الألوان إنّما يحرس ما يُشحن.
SKIP_ROOTS = {".local", ".venv", ".claude", "AAdocs", "tests", "node_modules"}

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


#: قيمُ الرموز اللونيّة في `:root` — الرمزُ اسماً والقيمةُ رقماً.
def _root_colours():
    text = CSS.read_text(encoding="utf-8")
    root = text[text.index(":root {") : text.index("@layer layout")]
    return {
        name: value.strip().lower()
        for name, value in re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", root)
        if value.strip().startswith("#")
    }


def test_the_python_mirror_matches_the_stylesheet():
    """`core/brand.py` مرآةُ `:root` لا مصدرٌ ثانٍ — فإن تباعدا أخفق البناء.

    ما يُبنى في بايثون — CSS الـPDF ولوحاتُ Chart.js وترويسةُ التصدير — لا يمرّ
    بمتصفّحٍ يحلّ `var()`، فيحتاج القيمةَ رقماً. وهذا الفحصُ يمنع أن تصير تلك
    الحاجةُ نسخةً تنجرف.
    """
    from core import brand

    colours = _root_colours()
    drifted = []
    for const, token in brand.TOKEN_OF.items():
        mine = getattr(brand, const).lower()
        theirs = colours.get(token)
        if theirs is None:
            drifted.append(f"{const}: لا رمزَ اسمُه --{token} في :root")
        elif mine != theirs:
            drifted.append(f"{const}: بايثون {mine} و--{token} {theirs}")
    assert not drifted, "مرآةُ الألوان انجرفت عن custom.css:\n  " + "\n  ".join(drifted)


def test_no_module_copies_a_colour_the_stylesheet_already_names():
    """لونٌ له رمزٌ لا يُكتب رقماً في بايثون — يُقرأ من `core.brand`."""
    named = set(_root_colours().values())
    offenders = {}
    for module in sorted(pathlib.Path(".").rglob("*.py")):
        parts = module.parts
        if parts[0] in SKIP_ROOTS or "migrations" in parts:
            continue
        if module == pathlib.Path("core/brand.py"):
            continue
        found = sorted(
            {
                literal.lower()
                for literal in re.findall(r"#[0-9a-fA-F]{6}\b", module.read_text(encoding="utf-8"))
            }
            & named
        )
        if found:
            offenders[str(module)] = found
    assert not offenders, "ألوانٌ منسوخةٌ ولها رمز — اقرأها من core.brand:\n" + "\n".join(
        f"  {path}: " + ", ".join(colours) for path, colours in sorted(offenders.items())
    )


#: كتلةٌ داخليّةٌ واحدة: محدِّدٌ بلا أقواسٍ ثمّ جسمٌ بلا أقواس.
BLOCK_RE = re.compile(r"([^{}]*)\{([^{}]*)\}", re.S)
COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _dark_palette():
    """قيمُ رموز الوضع الداكن — ما تُعيد `html.dark` تعريفَه في `:root`."""
    text = CSS.read_text(encoding="utf-8")
    block = re.search(r"html\.dark \{(.*?)\}", text, re.S).group(1)
    return {
        value.strip().lower(): name
        for name, value in re.findall(r"--([a-z0-9-]+)\s*:\s*([^;]+);", block)
        if value.strip().startswith("#")
    }


def test_dark_rules_name_their_colours_instead_of_repeating_them():
    """داخلَ `html.dark` تُقرأ القيمةُ بـ`var()` لا تُكتب رقماً.

    كان في القسم 35 وأخواتِه 218 موضعاً يكتب `#1e293b` و`#334155` وأخواتِهما
    حرفيّاً — وهي بعينها قيمُ `--surface` و`--border` في الوضع الداكن. فكان
    تغييرُ لونِ السطح يقتضي تعديلَ مئتَي سطرٍ بدل سطرٍ واحد.
    """
    palette = _dark_palette()
    text = CSS.read_text(encoding="utf-8")
    offenders = []
    for match in BLOCK_RE.finditer(text):
        selector = COMMENT_RE.sub("", match.group(1)).strip()
        if not selector or "html.dark" not in selector:
            continue
        parts = [part.strip() for part in selector.split(",") if part.strip()]
        if not all("html.dark" in part for part in parts):
            continue
        for declaration in match.group(2).split(";"):
            if ":" not in declaration:
                continue
            prop = COMMENT_RE.sub("", declaration).split(":", 1)[0].strip()
            if prop.startswith("--"):
                continue
            for literal in re.findall(r"#[0-9a-fA-F]{6}\b", declaration):
                if literal.lower() in palette:
                    offenders.append(
                        f"{parts[0][:50]} — {prop}: {literal} (= --{palette[literal.lower()]})"
                    )
    assert not offenders, "ألوانٌ داكنةٌ مكتوبةٌ رقماً ولها رمز:\n  " + "\n  ".join(offenders[:20])


def test_no_page_carries_a_stylesheet_of_its_own():
    """صفحةٌ تمتدّ من الأساس لا تحمل `<style>` — المصدرُ واحد.

    كانت عشرون صفحةً تحمل 1361 سطراً من CSS في رؤوسها. وكتلةُ `<style>` غيرُ
    مُطبَّقةٍ في `@layer`، فتغلب كلَّ قاعدةٍ في الملفّ المركزيّ مهما بلغت
    نوعيّتُها: بقيت `.qmy-alert` صفراءَ فاتحةً في الوضع الداكن رغم أنّ
    `html.dark .qmy-alert` مكتوبةٌ هناك — نصٌّ فاتحٌ على أصفرَ بنسبة 1.33.
    """
    offenders = []
    for template in _live_templates():
        text = template.read_text(encoding="utf-8")
        if "{% extends" not in text or "<style" not in text:
            continue
        # قوالبُ لوحة الإدارة ترث قالبَ جانغو ولا تحمّل custom.css
        if "templates/admin/" in template.as_posix():
            continue
        offenders.append(str(template))
    assert not offenders, (
        "صفحاتٌ تحمل CSS في رأسها — انقلها إلى static/css/custom.css:\n  " + "\n  ".join(offenders)
    )


def test_the_platform_keeps_one_stylesheet():
    """ملفُّ أنماطٍ واحدٌ للمنصّة، ومدخلُ تايلويند وناتجُه.

    كان `developer_feedback` يحمّل ملفَّه (957 سطراً، 75 لوناً مميّزاً،
    وأربعون `var()` فقط) فوقَ المركزيّ، فيغلبه بلا نوعيّة.
    """
    allowed = {
        pathlib.Path("static/css/custom.css"),
        pathlib.Path("static/css/tailwind_input.css"),
        pathlib.Path("static/css/tailwind.min.css"),
    }
    found = {
        path
        for path in pathlib.Path(".").rglob("*.css")
        if not any(part in SKIP_ROOTS | {"staticfiles"} for part in path.parts)
    }
    extra = sorted(str(p) for p in found - allowed)
    assert not extra, "ملفّاتُ أنماطٍ خارج المصدر الواحد:\n  " + "\n  ".join(extra)
