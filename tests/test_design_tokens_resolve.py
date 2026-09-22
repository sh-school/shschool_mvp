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

import os
import pathlib
import re

from core.css_files import CSS_FILES
from tests.css_source import read_css

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
    text = read_css()
    missing = sorted(set(USE_RE.findall(text)) - _defined_in(text))
    assert not missing, "رموزٌ تُستعمَل في custom.css ولا تُعرَّف فيه — والتصريحُ كلُّه يسقط: " + ", ".join(
        "--" + name for name in missing
    )


def test_the_templates_use_no_token_the_platform_never_defines():
    known = _defined_in(read_css())
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


#: درجاتُ السلالم الأساسيّة — تبقى وإن لم تُستعمل بعد، فالسلّمُ الناقص درجةً
#: يُلجئ أوّلَ من يحتاجها إلى كتابة `40px` بيده. وتحويلُ مقاساتِ البكسل إلى
#: رموزٍ سيأخذ منها.
SCALE_TOKENS = {
    "sp-10",
    "sp-12",
    "sp-16",
    "dur-fast",
    "dur-slow",
    "ease-default",
    "transition-slow",
    "lh-tight",
    "z-sticky",
    "shadow-modal",
}


#: أحبارُ ألوان العلامة — نصُّ اللون على السطح، مقيسُ التباين في
#: `tests/test_contrast_ratios.py`. تبقى وإن خلا منها قارئ: `--skyline-fg`
#: فقد قارئَيه حين حُذف `btn-preview` و`kpi-value--primary` الميّتان، والعائلةُ
#: (`--maroon-fg`، `--accent-*-fg`) لا تُكسر حرفاً حرفاً.
PALETTE_INKS = {"skyline-fg"}


#: جذورٌ لا تقرأ رموزَ الواجهة: وثائقُ وسجلّاتٌ وإعداداتُ خوادم.
NOT_CODE_ROOTS = {"docs", "logs", "grafana", "nginx"}


def _consumer_sources():
    """ما يقرأ الرموز: القوالبُ والسكربتاتُ وبايثون وإعدادُ تايلويند.

    وتُطلب الرموزُ فيها باسمها المجرّد أحياناً — `chartColor('chart-2')`،
    وقائمةُ ألوان الأقسام في `core/brand.py` — فالاسمُ وحدَه استعمال.
    """
    for directory, subdirs, files in os.walk("."):
        parts = pathlib.Path(directory).parts
        if parts and (
            parts[0] in SKIP_ROOTS | NOT_CODE_ROOTS
            or parts[0].startswith(".")
            or {"vendor", "migrations", "__pycache__"} & set(parts)
        ):
            subdirs[:] = []
            continue
        for name in files:
            if name.endswith((".html", ".js", ".py")) and not name.endswith(".min.js"):
                yield pathlib.Path(directory, name)


def test_no_token_is_defined_that_nothing_reads():
    """رمزٌ لا يقرؤه شيءٌ دَينٌ صامت.

    كان في `custom.css` خمسون رمزاً كهذه، أكثرُها بقايا مكوّناتٍ رحلت إلى
    مكوّنات الواجهة (`--caution-*`، `--paper-*`، `--status-*-mark`)، ولكلٍّ
    منها نظيرٌ ليليّ. فمن يبحث عن لون «التنبيه» يجد رمزين ولا يدري أيّهما
    الحيّ، ومن يغيّر الميّتَ لا يرى أثراً فيظنّ الخللَ في غيره.
    """
    css = COMMENT_RE.sub("", read_css())
    defined = _defined_in(css)
    read_in_css = set(re.findall(r"var\(\s*--([a-zA-Z0-9_-]+)", css))
    words = set()
    for source in _consumer_sources():
        text = source.read_text(encoding="utf-8", errors="ignore")
        words |= {word.lstrip("-") for word in re.findall(r"[a-zA-Z0-9_-]+", text)}
    idle = sorted(defined - read_in_css - words - SCALE_TOKENS - PALETTE_INKS)
    assert not idle, "رموزٌ معرَّفةٌ لا يقرؤها شيء — احذفها أو استعملها:\n  " + "\n  ".join(
        "--" + name for name in idle
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
    text = read_css()
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


def test_the_dark_mirror_matches_the_stylesheet():
    """`brand.DARK` قيمُ الليل لصفحات الخطأ ولون شريط المتصفّح — تُقارَن بكتلة `html.dark`."""
    from core import brand
    from tests.css_contrast import dark_overrides

    dark = dark_overrides(read_css())
    drifted = []
    for const, value in brand.DARK.items():
        token = brand.TOKEN_OF.get(const)
        theirs = (dark.get(f"--{token}") or "").split()[0].rstrip(";").lower() if token else None
        if theirs != value.lower():
            drifted.append(f"{const}: بايثون {value} و--{token} ليلاً {theirs}")
    assert not drifted, "مرآةُ الليل انجرفت عن custom.css:\n  " + "\n  ".join(drifted)


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


def test_no_excel_writer_copies_a_brand_colour_without_its_hash():
    """openpyxl يأخذ اللونَ بلا `#` — `"8A1538"` — فكان يفلت من الحارس السابق.

    خمسُ نسخٍ في `student_affairs/views.py` وأخواتٌ في ثلاثة ملفّات كتبت
    العنّابيَّ والعنّابيَّ الفاتحَ هكذا. تُقرأ الآن بـ`brand.excel(brand.MAROON)`.
    والأبيضُ مستثنى: لونٌ عامٌّ يُكتب في كلّ ملفٍّ لا علامةٌ تُنسخ.
    """
    from core import brand

    identity = {getattr(brand, const).lstrip("#").lower() for const in brand.TOKEN_OF} - {"ffffff"}
    offenders = {}
    for module in sorted(pathlib.Path(".").rglob("*.py")):
        parts = module.parts
        if (
            parts[0] in SKIP_ROOTS
            or "migrations" in parts
            or module == pathlib.Path("core/brand.py")
        ):
            continue
        text = module.read_text(encoding="utf-8")
        found = sorted(
            {m.lower() for m in re.findall(r"""["']([0-9a-fA-F]{6})["']""", text)} & identity
        )
        if found:
            offenders[str(module)] = found
    assert not offenders, "لونُ علامةٍ منسوخٌ بلا `#` — استعمل brand.excel(...):\n" + "\n".join(
        f"  {path}: " + ", ".join(colours) for path, colours in sorted(offenders.items())
    )


#: كتلةٌ داخليّةٌ واحدة: محدِّدٌ بلا أقواسٍ ثمّ جسمٌ بلا أقواس.
BLOCK_RE = re.compile(r"([^{}]*)\{([^{}]*)\}", re.S)
COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)


def _dark_palette():
    """قيمُ رموز الوضع الداكن — ما تُعيد `html.dark` تعريفَه في `:root`."""
    text = read_css()
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
    text = read_css()
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
        "صفحاتٌ تحمل CSS في رأسها — انقلها إلى static/css/custom/:\n  " + "\n  ".join(offenders)
    )


def test_the_platform_keeps_one_stylesheet():
    """ملفُّ أنماطٍ واحدٌ للمنصّة، ومدخلُ تايلويند وناتجُه.

    كان `developer_feedback` يحمّل ملفَّه (957 سطراً، 75 لوناً مميّزاً،
    وأربعون `var()` فقط) فوقَ المركزيّ، فيغلبه بلا نوعيّة.
    """
    allowed = {
        *(pathlib.Path("static/css/custom") / name for name in CSS_FILES),
        pathlib.Path("static/css/tailwind_input.css"),
        pathlib.Path("static/css/tailwind.min.css"),
        # لوحةُ الإدارة لا تحمل custom.css (تَرِث قالبَ جانغو) فلها ورقةٌ واحدةٌ بألوان المنصّة منقولةً حرفيّاً؛
        # وحارسُ tests/test_admin_theme.py يفشل إن انجرفت قيمُها عن رموز المنصّة.
        pathlib.Path("static/css/admin_theme.css"),
    }
    found = {
        path
        for path in pathlib.Path(".").rglob("*.css")
        if not any(part in SKIP_ROOTS | {"staticfiles"} for part in path.parts)
    }
    extra = sorted(str(p) for p in found - allowed)
    assert not extra, "ملفّاتُ أنماطٍ خارج المصدر الواحد:\n  " + "\n  ".join(extra)
