"""أنماطُ المنصّة ثمانيةُ ملفّاتٍ على حدود الطبقات — وهذه بنيتُها (ADR-0003).

القسمةُ ميكانيكيّةٌ آمنةٌ ما دام: (1) لا قاعدةَ خارج `@layer` (فترتيبُ التطبيق بين
الطبقات تحسمه جملةُ الترتيب لا موضعُ الكتلة)، (2) جملةُ الترتيب في أوّل ملفٍّ
يُحمَّل، (3) تسلسلُ كتل `modules` محفوظ. وكلُّ واحدةٍ منها تُثبَّت هنا، كي لا
يفسدها أحدٌ بإضافةٍ عاديّة: قاعدةٌ بلا طبقةٍ في ملفٍّ جديد كانت ستغلب كلَّ ما
في `@layer` مهما ضعفت نوعيّتُها، بصمتٍ.
"""

import importlib.util
import pathlib
import re

from core.css_files import CSS_FILES
from tests.css_source import CSS_ROOT, ROOT, css_paths

#: الطبقاتُ التي يحقّ لكلّ ملفٍّ أن يحملها — الاسمُ العدديّ يحدّد الجواب.
ALLOWED_LAYERS = {
    "10": {"reset", "base", "tokens", "layout"},
    "20": {"components"},
    "30": {"modules"},
    "31": {"modules"},
    "32": {"modules"},
    "33": {"modules"},
    "40": {"themes"},
    "50": {"utilities"},
}

ORDER_RE = re.compile(r"^@layer\s+([\w\s,-]+);", re.M)

#: مسارٌ نصّيٌّ للملفّ القديم — قراءتُه بعد التقسيم تنكسر أو، أسوأ، تقرأ نسخةً منسيّة.
LEGACY_PATH_RE = re.compile(r"""["']/?(?:static/)?css/custom\.css["']""")


def _parser():
    spec = importlib.util.spec_from_file_location(
        "split_custom_css", ROOT / "scripts" / "split_custom_css.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_file_on_disk_is_listed_and_every_listed_file_exists():
    on_disk = {p.name for p in CSS_ROOT.glob("*.css")}
    assert on_disk == set(CSS_FILES), (
        f"static/css/custom/ ≠ core/css_files.py:CSS_FILES\n"
        f"  على القرص وليس في القائمة: {sorted(on_disk - set(CSS_FILES))}\n"
        f"  في القائمة وليس على القرص: {sorted(set(CSS_FILES) - on_disk)}"
    )


def test_the_layer_order_statement_lives_in_the_first_file_loaded():
    first = css_paths()[0].read_text(encoding="utf-8")
    match = ORDER_RE.search(re.sub(r"/\*.*?\*/", "", first, flags=re.S))
    assert match, "10-foundation.css لا يحمل جملةَ `@layer a, b, c;` — الترتيبُ سيحدّده أوّلُ ظهور"
    order = [name.strip() for name in match.group(1).split(",")]
    assert order == [
        "tailwind",
        "reset",
        "base",
        "tokens",
        "layout",
        "components",
        "modules",
        "utilities",
        "themes",
    ]
    for path in css_paths()[1:]:
        text = re.sub(r"/\*.*?\*/", "", path.read_text(encoding="utf-8"), flags=re.S)
        assert not ORDER_RE.search(text), f"{path.name} يكرّر جملةَ الترتيب — موضعُها الوحيد في الأوّل"


def test_no_rule_lives_outside_a_layer_and_each_file_keeps_to_its_own_layers():
    parser = _parser()
    for path in css_paths():
        text = path.read_text(encoding="utf-8")
        allowed = ALLOWED_LAYERS[path.name[:2]]
        for head, _start, _end in parser.top_level_blocks(text):
            assert head.startswith(
                "@layer "
            ), f"{path.name}: كتلةٌ عليا خارج @layer (`{head[:40]}`) — تغلب كلَّ قاعدةٍ في الطبقات"
            layer = head.removeprefix("@layer ").strip()
            assert (
                layer in allowed
            ), f"{path.name} يحمل @layer {layer} وحقُّه {sorted(allowed)} — الملفُّ على حدّ طبقته"


def test_nothing_reads_the_retired_single_file_by_path():
    offenders = []
    for base, patterns in (
        (ROOT / "tests", ("*.py",)),
        (ROOT / "core", ("*.py",)),
        (ROOT / "templates", ("*.html", "*.js")),
        (ROOT / "static" / "js", ("*.js",)),
    ):
        for pattern in patterns:
            for path in base.rglob(pattern):
                if path.name == pathlib.Path(__file__).name:
                    continue
                if LEGACY_PATH_RE.search(path.read_text(encoding="utf-8", errors="ignore")):
                    offenders.append(path.relative_to(ROOT).as_posix())
    assert not offenders, (
        "مسارُ `static/css/custom.css` القديم مكتوبٌ نصّاً — اقرأ عبر "
        "`tests.css_source.read_css()` أو `core.css_files`:\n  " + "\n  ".join(sorted(offenders))
    )


#: `url(...)` بلا `data:` ولا `#fragment` ولا `var()` ولا مطلَق.
URL_RE = re.compile(r"""url\(\s*['"]?([^'")\s]+)['"]?\s*\)""")


def test_every_relative_url_in_the_stylesheets_resolves_to_a_real_file():
    """الملفّاتُ مستوىً أعمق من `custom.css` القديم، فمسارٌ نسبيٌّ لم يُصعَّد يُحلّ إلى 404.

    وهذا صامتٌ في المتصفّح (الخطُّ يرتدّ إلى بديله والأنماطُ المحسوبةُ لا تتغيّر)،
    وصاخبٌ في الإنتاج: `collectstatic` يفشل على ملفٍّ مرجعيٍّ غير موجود.
    """
    static = CSS_ROOT.parent.parent
    missing = []
    for path in css_paths():
        for target in URL_RE.findall(path.read_text(encoding="utf-8")):
            if target.startswith(("data:", "#", "http:", "https:", "//", "/", "var(")):
                continue
            resolved = (path.parent / target.split("?")[0].split("#")[0]).resolve()
            if not resolved.is_relative_to(static.resolve()) or not resolved.is_file():
                missing.append(f"{path.name}: url({target})")
    assert not missing, "مسارٌ نسبيٌّ لا يبلغ ملفّاً في static/:\n  " + "\n  ".join(missing)
