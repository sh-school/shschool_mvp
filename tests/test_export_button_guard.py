"""
tests/test_export_button_guard.py — زرُّ التصدير الموحَّد (W-20261021-006)

لا زرَّ تصديرٍ مكتوباً بيدٍ في القوالب: يمرّ كلُّه على الوسم `{% export_button %}` بالأسماء الثلاثة المعتمدة.
رُحِّلت القوالبُ كلُّها (ستة وثلاثون): لا أساسَ ولا سقّاطة، فأيُّ زرٍّ يدويٍّ جديدٍ يُرفض. ويُستثنى مرفقٌ مرفوعٌ
(«تحميل» له بقرار المالك) وقالبان في `EXEMPT` بسببيهما.
"""

import pathlib
import re

import pytest
from django.template import Context, Template, TemplateSyntaxError

from core.templatetags.ui import EXPORT_KINDS

ROOT = pathlib.Path(__file__).resolve().parent.parent
HAND_WRITTEN = re.compile(
    r"data-app-file|تصدير (?:PDF|Excel|CSV)|تحميل PDF|تقرير PDF|الاستمارة PDF|>\s*(?:PDF|Excel)\s*<"
)
#: سطرٌ يخصّ **مرفقاً مرفوعاً** (دليل، مستند عذر، إثبات) لا تصديراً من المنصّة: «تحميل» له مسموح بقرار المالك،
#: أو سطرُ JS يضبط الوسم ديناميكياً على رابطٍ يملكه الوسم أصلاً.
ATTACHMENT_LINE = re.compile(
    r"\.file\.url|evidence_file|excuse_file|\.document|excuse_document_export|protected_media|setAttribute"
)
#: قوالبُ مستثناةٌ كلُّها بسببها: مرحَّلةٌ جميعُ أزرارها إلا ما هنا.
EXEMPT = {
    "components/credentials_sheet.html": "زرُّ CSV يبنيه JS في المتصفّح لورقة بيانات الدخول — لا نوعَ CSV بين الأسماء الثلاثة؛ يُرفع لـ0101",
    "schedule/print_schedule.html": "صفحةٌ مستقلّةٌ بأنماطها (ورقةُ المنسّق) لا تحمّل أنماطَ المنصّة؛ الأسماءُ معتمدةٌ فيها نصّاً",
}


def _render(src: str) -> str:
    return Template("{% load ui %}" + src).render(Context({}))


def _hand_written() -> dict[str, list[int]]:
    found: dict[str, list[int]] = {}
    for path in (ROOT / "templates").rglob("*.html"):
        rel = path.relative_to(ROOT / "templates").as_posix()
        if rel in EXEMPT:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if HAND_WRITTEN.search(line) and not ATTACHMENT_LINE.search(line):
                found.setdefault(rel, []).append(number)
    return found


def test_only_the_three_approved_names_exist():
    assert [label for _icon, label in EXPORT_KINDS.values()] == [
        "تصدير PDF",
        "تصدير Excel",
        "طباعة",
    ]


def test_no_hand_written_export_button_outside_the_component():
    found = _hand_written()
    assert not found, f"زرُّ تصديرٍ مكتوبٌ بيدٍ — استعمل {{% export_button %}} (قالب ← أسطره): {found}"


def test_every_exemption_is_still_needed():
    stale = [
        rel
        for rel in EXEMPT
        if not HAND_WRITTEN.search((ROOT / "templates" / rel).read_text(encoding="utf-8"))
    ]
    assert not stale, f"استثناءٌ لم يعد لازماً — احذفه من EXEMPT: {stale}"


def test_pdf_button_has_name_icon_and_file_hook():
    html = _render('{% export_button "pdf" "absence_followup_xlsx" %}?q=1{% endexport_button %}')
    assert "data-app-file" in html and "تصدير PDF" in html and '?q=1"' in html
    assert "btn-secondary btn-sm" in html


def test_primary_and_id_are_applied():
    html = _render(
        '{% export_button "xlsx" "absence_followup_xlsx" primary=True id="x1" %}{% endexport_button %}'
    )
    assert "btn-primary btn-sm" in html and 'id="x1"' in html and "تصدير Excel" in html


def test_print_is_a_button_without_a_link():
    html = _render('{% export_button "print" %}{% endexport_button %}')
    assert "<button" in html and "window.print()" in html and "طباعة" in html and "<a " not in html


def test_unknown_kind_is_refused():
    with pytest.raises(TemplateSyntaxError):
        _render('{% export_button "csv" "absence_followup_xlsx" %}{% endexport_button %}')


def test_title_keeps_the_visible_name_and_labels_the_button():
    html = _render(
        '{% export_button "pdf" "absence_followup_xlsx" title="لائحة السلوك" %}{% endexport_button %}'
    )
    assert "تصدير PDF" in html and 'title="لائحة السلوك"' in html
    assert 'aria-label="تصدير PDF — لائحة السلوك"' in html


def test_href_form_and_inline_link():
    html = _render('{% export_button "xlsx" href="?" %}a=1&export=excel{% endexport_button %}')
    assert 'href="?a=1&amp;export=excel"' in html and "data-app-file" in html
    inline = _render(
        '{% export_button "pdf" "absence_followup_xlsx" inline=True %}{% endexport_button %}'
    )
    assert "data-app-file" not in inline and "تصدير PDF" in inline


def test_submit_button_form_carries_name_and_value():
    html = _render('{% export_button "xlsx" name="format" value="xlsx" %}{% endexport_button %}')
    assert 'type="submit"' in html and 'name="format"' in html and 'value="xlsx"' in html
    assert "data-app-file" in html and "تصدير Excel" in html


def test_xs_size_and_job_and_download():
    html = _render(
        '{% export_button "pdf" "absence_followup_xlsx" size="xs" job="pdf" download=True %}{% endexport_button %}'
    )
    assert (
        "btn-secondary btn-xs" in html and 'data-export-job="pdf"' in html and " download" in html
    )


# ── شريطُ التصدير الموحَّد: الاتجاه ثم Excel ثم PDF (W-20261107-021) ──────────────────────────────────

_LOCAL_ORIENT_MENU = re.compile(r'<select[^>]*name="orient"')
_TOKEN = re.compile(r'\{% export_group\b|\{% endexport_group %\}|\{% export_button "(?:pdf|xlsx)"')


def _outside_group() -> dict[str, list[int]]:
    """قوالبُ فيها تصدير pdf أو xlsx خارج `{% export_group %}` (قالب ← أسطره)."""
    found: dict[str, list[int]] = {}
    for path in (ROOT / "templates").rglob("*.html"):
        depth = 0
        rel = path.relative_to(ROOT / "templates").as_posix()
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for token in _TOKEN.finditer(line):
                text = token.group(0)
                if text.startswith("{% export_group"):
                    depth += 1
                elif text.startswith("{% endexport_group"):
                    depth -= 1
                elif depth <= 0:
                    found.setdefault(rel, []).append(number)
    return found


def test_every_pdf_or_xlsx_export_sits_inside_the_group():
    found = _outside_group()
    assert not found, f"تصديرٌ خارج export_group — لفّه بالشريط الموحَّد (قالب ← أسطره): {found}"


def test_no_local_orientation_menu_remains():
    found = [
        path.relative_to(ROOT / "templates").as_posix()
        for path in (ROOT / "templates").rglob("*.html")
        if _LOCAL_ORIENT_MENU.search(path.read_text(encoding="utf-8"))
    ]
    assert not found, f"قائمةُ اتجاهٍ محلّيّةٌ — الاتجاهُ من export_group وحدَه: {found}"


_PDF = '{% export_button "pdf" "absence_followup_xlsx" %}{% endexport_button %}'
_XLSX = '{% export_button "xlsx" "absence_followup_xlsx" %}{% endexport_button %}'


def test_group_order_is_orientation_then_excel_then_pdf():
    html = _render('{% export_group kind="sheet" %}' + _PDF + _XLSX + "{% endexport_group %}")
    assert html.index("data-export-orient") < html.index("تصدير Excel") < html.index("تصدير PDF")
    assert html.count("<select") == 1
    assert html.index("أفقي") < html.index("رأسي")


def test_group_default_follows_print_policy():
    sheet = _render('{% export_group kind="sheet" %}' + _XLSX + "{% endexport_group %}")
    assert '<option value="landscape" selected>' in sheet
    form = _render('{% export_group kind="form" %}' + _PDF + "{% endexport_group %}")
    assert '<option value="portrait" selected>' in form
    doc = _render(
        '{% export_group doc="templates/breach/pdf_report.html" %}' + _PDF + "{% endexport_group %}"
    )
    assert '<option value="portrait" selected>' in doc


def test_single_kind_page_shows_orientation_with_its_own_button_only():
    html = _render("{% export_group %}" + _PDF + "{% endexport_group %}")
    assert "data-export-orient" in html and "تصدير PDF" in html and "تصدير Excel" not in html


def test_group_without_pdf_or_xlsx_draws_no_menu():
    html = _render(
        '{% export_group %}{% export_button "print" %}{% endexport_button %}{% endexport_group %}'
    )
    assert "data-export-orient" not in html and "طباعة" in html


def test_group_rejects_unknown_kind_and_document():
    with pytest.raises(TemplateSyntaxError):
        _render('{% export_group kind="poster" %}{% endexport_group %}')
    with pytest.raises(TemplateSyntaxError):
        _render('{% export_group doc="templates/none.html" %}{% endexport_group %}')


def test_requested_orient_preselects_the_menu():
    from django.test import RequestFactory

    request = RequestFactory().get("/", {"orient": "portrait"})
    html = Template(
        '{% load ui %}{% export_group kind="sheet" %}' + _XLSX + "{% endexport_group %}"
    ).render(Context({"request": request}))
    assert '<option value="portrait" selected>' in html
