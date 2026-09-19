"""
tests/test_brand_literals.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━
هويّةٌ بصريّةٌ واحدة: كلُّ لونٍ في المنصّة يُقرأ من مصدرٍ واحد، أينما رُسم.

  - الصفحةُ الحيّة: من رمزها في `custom.css` (`var()` أو صنفٌ كـ`text-maroon`).
  - الرسومُ البيانيّة: من الرموز بمساعدات رأس `base.html` — canvas لا يحلّ `var()`.
  - ملفّاتُ Excel: من `core.export_utils` (خطٌّ واحدٌ ونمطُ جدولٍ واحد).
  - الوثائقُ (PDF والطباعة والبريد وصفحاتُ الخطأ): من `core.brand` عبر
    `{% brand_color %}` — فمولّدُ الـPDF الاحتياطيّ والبريدُ لا يحلّان `var()`.

و`core.brand` مرآةُ `:root` و`html.dark` يحرسها `test_design_tokens_resolve`.
"""

import pathlib
import re

from tests.css_source import read_css

ROOTS = [pathlib.Path("templates")] + sorted(pathlib.Path(".").glob("*/templates"))
EXTENDS_BASE = re.compile(r"""\{%\s*extends\s+["'](base\.html|base/base\.html)["']""")
INLINE_MAROON = re.compile(r"""style\s*=\s*["'][^"']*#8a1538""", re.I)


def _live_templates():
    for root in ROOTS:
        for path in root.rglob("*.html"):
            text = path.read_text(encoding="utf-8", errors="ignore")
            if EXTENDS_BASE.search(text):
                yield path, text


def test_live_pages_read_the_maroon_from_its_token():
    offenders = [
        f"  {path.as_posix()}:{text[: m.start()].count(chr(10)) + 1}"
        for path, text in _live_templates()
        for m in INLINE_MAROON.finditer(text)
    ]
    assert not offenders, (
        "العنّابيُّ مكتوبٌ رقماً في `style=` بصفحةٍ حيّة — استعمل `text-maroon` "
        "أو `var(--maroon-fg)`:\n" + "\n".join(offenders)
    )


def test_the_scan_reaches_the_live_pages():
    """مسحٌ لا يجد قوالبَ ينجح كاذباً."""
    assert sum(1 for _ in _live_templates()) >= 150


# ══════════════════════════════════════════════════════════════════
# الرسوم — Chart.js يرسم على canvas، وcanvas لا يحلّ `var()`
# ══════════════════════════════════════════════════════════════════
#
# كان خطُّ اتّجاه المخالفات في لوحة السلوك `borderColor:'var(--chart-1,#8A1538)'`
# — فرفضه canvas وبقي على لونه الافتراضيّ: رُسم أسودَ (قِيس بالبكسل يومَ
# 2026-09-13). والرقمُ المكتوبُ يُرسم، لكنّه لا ينقلب ليلاً ويتباعد عن
# لوحة الرموز (`--chart-4` عُمِّق إلى #A8801F والقوالبُ بقيت على #D4A843).
# فالرسومُ تقرأ الرموزَ بمساعدات رأس `base.html`: `chartColor` و`chartPalette`
# و`chartAlpha`.

#: وسمُ الإغلاق يُقبل بأيّ محارفَ بعد اسمه (`</script foo>`) كما يقبله المتصفّح.
SCRIPT = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script\b[^>]*>", re.S | re.I)
CHART_KEYS = r"(?:border|background|pointBackground|pointBorder|hoverBackground|hoverBorder)Color"
LITERAL_CHART_COLOUR = re.compile(CHART_KEYS + r"""\s*:\s*['"](?:#|rgba?\(|hsla?\(|var\()""")
LITERAL_PALETTE = re.compile(r"""\[\s*['"]#[0-9a-fA-F]{3,8}['"]\s*,""")
HELPER_CALL = re.compile(r"""chart(?:Color|Alpha)\(\s*['"]([a-z0-9-]+)['"]""")


def _chart_scripts():
    for path, text in _live_templates():
        for m in SCRIPT.finditer(text):
            if "new Chart(" in text:
                yield path, text, m


def test_charts_read_their_colours_from_the_tokens():
    offenders = []
    for path, text, m in _chart_scripts():
        body = m.group(1)
        for hit in list(LITERAL_CHART_COLOUR.finditer(body)) + list(LITERAL_PALETTE.finditer(body)):
            line = text[: m.start(1) + hit.start()].count("\n") + 1
            offenders.append(f"  {path.as_posix()}:{line}  {hit.group(0)[:48]}")
    assert not offenders, (
        "لونُ رسمٍ مكتوبٌ رقماً أو `var()` — canvas لا يحلّ `var()`، والرقمُ لا ينقلب. "
        "استعمل chartColor/chartPalette/chartAlpha:\n" + "\n".join(offenders)
    )


def test_every_chart_colour_names_a_real_token():
    """اسمٌ لا رمزَ له يُرجع سلسلةً فارغة — فيُرسم الشكلُ أسودَ بلا خطأ."""
    from tests.css_contrast import token_table

    light, _dark = token_table(read_css())
    missing, used = [], 0
    for path, _text, m in _chart_scripts():
        for name in HELPER_CALL.findall(m.group(1)):
            used += 1
            if f"--{name}" not in light:
                missing.append(f"  {path.as_posix()}: --{name}")
    assert used >= 30, f"لم يُرَ إلّا {used} استدعاءً — المسحُ لم يبلغ الرسوم"
    assert not missing, "رموزُ رسمٍ غيرُ معرَّفة:\n" + "\n".join(sorted(set(missing)))


# ══════════════════════════════════════════════════════════════════
# ملفّات Excel — هويّةٌ واحدةٌ من `core.export_utils`
# ══════════════════════════════════════════════════════════════════
#
# كانت ستُّ نسخٍ من نمط الجدول بثلاثة خطوط (Tajawal وArial وخطِّ Excel
# الافتراضيّ)، وشبكاتٍ بثلاثة ألوان، وترويستين بتصميمين، وترويسةٍ كحليّةٍ في
# تصدير الدرجات. فصار كلُّ لونٍ وخطٍّ يمرّ بـ`xl_fill` و`xl_font`
# و`excel_table_styles` و`add_excel_title_rows` — ولا مولّدَ يكتبهما بيده.

EXCEL_SKIP = {"scripts", "tests", ".claude", ".venv", ".local", "AAdocs", "node_modules"}
HEX_LITERAL = re.compile(r"""["'](?:FF)?[0-9A-Fa-f]{6}["']""")
FONT_BY_HAND = re.compile(r"""Font\([^)]*\bname\s*=\s*["']""")


def _excel_writers():
    for module in sorted(pathlib.Path(".").rglob("*.py")):
        if module.parts[0] in EXCEL_SKIP or "migrations" in module.parts:
            continue
        if module.as_posix() in {"core/brand.py", "core/export_utils.py"}:
            continue
        text = module.read_text(encoding="utf-8", errors="ignore")
        if "openpyxl" in text or "core.export_utils import" in text:
            yield module, text


def test_no_excel_writer_paints_by_hand():
    offenders = []
    for module, text in _excel_writers():
        for pattern, what in ((HEX_LITERAL, "لون"), (FONT_BY_HAND, "خط")):
            for m in pattern.finditer(text):
                line = text[: m.start()].count("\n") + 1
                offenders.append(f"  {module.as_posix()}:{line}  {what}: {m.group(0)[:40]}")
    assert not offenders, (
        "مولّدُ Excel يكتب لوناً أو خطّاً بيده — استعمل xl_fill/xl_font/excel_table_styles "
        "من core.export_utils:\n" + "\n".join(offenders)
    )


def test_the_excel_scan_reaches_the_writers():
    names = {m.as_posix() for m, _ in _excel_writers()}
    assert {"student_affairs/views.py", "reports/services.py", "core/views_students.py"} <= names


# ══════════════════════════════════════════════════════════════════
# الوثائق — PDF والطباعة والبريد وصفحاتُ الخطأ وتطبيقُ الوليّ
# ══════════════════════════════════════════════════════════════════
#
# قالبٌ لا يرث قالبَ المنصّة لا يحمّل `custom.css`، ومولّدُ الـPDF الاحتياطيّ
# وعملاءُ البريد لا يحلّون `var()`. فلونُه يُكتب رقماً — لكن من `core.brand`
# عبر `{% brand_color "…" %}`، لا بيدٍ في القالب. وكانت 662 لوناً بـ138 قيمةً
# في ثلاثةٍ وثلاثين قالباً.

#: قوالبُ بألوانٍ ليست ألوانَ المنصّة **بقصد** — ولكلٍّ سببُه.
DOCUMENT_EXCEPTIONS = {
    # طبقُ الأصل من استمارة الوزارة — ألوانُها ألوانُ النموذج الرسميّ لا العلامة،
    # ويحرسها `tests/test_observation_pdf_form.py`.
    "templates/quality/observation_pdf.html",
}

#: سطورٌ مستثناةٌ داخل قالبٍ محروس: لوحةُ ألوان الأقسام في ورقة الجدول العامّ
#: ترمز إلى القسم لا إلى العلامة — وتوحيدُها يمحو الفرقَ بين قسمٍ وقسم.
DOCUMENT_LINE_EXCEPTIONS = {"templates/schedule/print_schedule.html": re.compile(r"tr\.dept-")}

HEX_IN_DOC = re.compile(r"(?<![&\w])#[0-9a-fA-F]{3}(?:[0-9a-fA-F]{3})?\b")
COMMENTS = re.compile(
    r"\{#.*?#\}|\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}|/\*.*?\*/|<!--.*?-->", re.S
)


def _all_templates():
    found = {}
    for root in ROOTS:
        for path in root.rglob("*"):
            if path.suffix in {".html", ".json"}:
                found[path.relative_to(root).as_posix()] = path
    return found


def _documents():
    """ما لا يرث `base.html` — مباشرةً أو عبر سلسلة وراثة."""
    found = _all_templates()
    parent = re.compile(r"""\{%\s*extends\s+["']([^"']+)["']""")

    def inherits_platform(name, depth=0):
        if depth > 8 or name not in found:
            return False
        m = parent.search(found[name].read_text(encoding="utf-8", errors="ignore"))
        return bool(m) and (
            m.group(1) in {"base.html", "base/base.html"}
            or inherits_platform(m.group(1), depth + 1)
        )

    for name, path in sorted(found.items()):
        if not inherits_platform(name) and path.as_posix() not in {"templates/base/base.html"}:
            yield path


def test_documents_take_their_colours_from_the_brand():
    offenders = []
    for path in _documents():
        posix = path.as_posix()
        if posix in DOCUMENT_EXCEPTIONS:
            continue
        text = COMMENTS.sub(
            lambda m: "\n" * m.group(0).count("\n"), path.read_text(encoding="utf-8")
        )
        skip_line = DOCUMENT_LINE_EXCEPTIONS.get(posix)
        for n, line in enumerate(text.splitlines(), start=1):
            if skip_line and skip_line.search(line):
                continue
            for m in HEX_IN_DOC.finditer(line):
                offenders.append(f"  {posix}:{n}  {m.group(0)}  «{line.strip()[:60]}»")
    assert not offenders, (
        'لونٌ مكتوبٌ بيدٍ في وثيقة — استعمل {% brand_color "…" %} من core.brand:\n'
        + "\n".join(offenders)
    )


def test_the_document_scan_reaches_the_documents():
    names = {p.as_posix() for p in _documents()}
    assert {
        "templates/reports/base_qatar_report.html",
        "templates/notifications/email/behavior_html.html",
        "templates/errors/_error_page.html",
        "templates/auth/login.html",
    } <= names
