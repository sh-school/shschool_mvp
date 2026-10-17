"""شعارُ الوزارة للمخرجات وحدَها — لا يظهر في المنصّة أبداً (W-20261014-009، قرار المالك 10-14؛ يُنهي D-409م).

الأصلُ `core/assets/ministry_logo.png` خارجَ `static/` فلا رابطَ يخدمه. ويُستعمل بالوسم `{% ministry_logo %}` أو بـ`core.ministry_logo`
في قوالب المخرجات المسمّاة وحدَها (PDF والطباعة) وشيفرةِ التصدير (Excel وPDF)، ولا في قالبٍ حيٍّ من المنصّة.
والصنفُ `ministry-logo` مخفيٌّ على الشاشة ويظهر عند الطباعة وحدَها.
"""

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: القوالبُ التي تُنتج وثيقةً مطبوعةً أو PDF — وحدَها تحمل شعارَ الوزارة.
EXPORT_TEMPLATES = {
    "templates/reports/base_qatar_report.html",
    "templates/quality/observation_pdf.html",
    "templates/components/print/frame_header.html",
    "templates/components/print/frame_css.html",
}
#: شيفرةُ المخرجات المسموح لها باستيراد الأصل.
EXPORT_CODE = {
    "core/ministry_logo.py",
    "core/templatetags/ministry_logo.py",
    "core/export_utils.py",
    "core/pdf_utils.py",
}
REFERENCE = re.compile(r"ministry_logo|ministry-logo")
#: استيرادُ الأصل (لا ذكرُ الاسم في تعليق).
IMPORT = re.compile(
    r"^\s*(?:from core import [^\n]*\bministry_logo\b|from core\.ministry_logo import|import core\.ministry_logo)",
    re.M,
)


def _files(*patterns):
    for pattern in patterns:
        for path in ROOT.glob(pattern):
            posix = path.relative_to(ROOT).as_posix()
            if path.is_file() and not posix.startswith(
                ("tests/", "docs/", ".claude/", "node_modules/", "staticfiles/")
            ):
                yield path, posix


def test_the_ministry_logo_is_not_under_static():
    assert (ROOT / "core/assets/ministry_logo.png").is_file()
    stray = [
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "static").rglob("*")
        if "ministry" in p.name.lower()
    ]
    assert stray == [], f"شعارُ الوزارة داخل static فيخدمه رابط: {stray}"


def test_only_export_templates_reference_the_ministry_logo():
    offenders = [
        posix
        for path, posix in _files("templates/**/*.html", "templates/**/*.js")
        if posix not in EXPORT_TEMPLATES and REFERENCE.search(path.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"قالبٌ حيٌّ يشير إلى شعار الوزارة: {offenders}"


def test_only_export_code_imports_the_ministry_logo():
    offenders = [
        posix
        for path, posix in _files("**/*.py")
        if posix not in EXPORT_CODE
        and "/migrations/" not in posix
        and IMPORT.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert offenders == [], f"شيفرةٌ خارج المخرجات تستورد شعارَ الوزارة: {offenders}"


def test_the_ministry_logo_class_is_print_only_in_css():
    css = "".join(p.read_text(encoding="utf-8") for p, _ in _files("static/css/custom/*.css"))
    block = re.search(r"\.ministry-logo\s*\{([^}]*)\}", css)
    assert block and "display: none" in block.group(1).replace(
        "display:none", "display: none"
    ), "مخفيٌّ على الشاشة"
    assert re.search(r"@media print[^{]*\{[^@]*\.ministry-logo", css, re.S), "ظاهرٌ عند الطباعة"


def test_no_static_url_names_the_ministry_logo():
    offenders = [
        posix
        for path, posix in _files("templates/**/*", "static/js/**/*.js", "static/css/**/*.css")
        if re.search(
            r"""(?:static\s+['"]|/static/)[^'"\s%)]*ministry""",
            path.read_text(encoding="utf-8", errors="ignore"),
            re.I,
        )
    ]
    assert offenders == [], offenders
