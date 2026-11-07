"""[DESIGN] سياسةُ اتّجاه الطباعة والشعار (W-20261021-007): أفقيٌّ للقوائم والكشوف، عموديٌّ للنماذج والخطابات، والشعارُ إلزاميٌّ.

الجدولُ في `core/print_policy.py`؛ والحارسُ يطابقه بالقوالب والشيفرة، ويمنع ازديادَ الدَّين، ويُلزم كلَّ قالبٍ مطبوعٍ جديدٍ بسطرٍ فيه.
"""

import pathlib

from core import print_policy as pp

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: عرضا شاشةٍ لا PDF مستقلّ (W-20261021-012): يمتدّان من `base/base.html` ويُدمجان في صفحة المنصّة؛ والـPDF الفعليّ
#: لكلٍّ منهما قالبٌ آخر مصنَّفٌ في `core/print_policy.py`. يتحقّق الاختبارُ أدناه من الادّعاء.
SCREEN_VIEWS = {
    "templates/schedule/print_view.html",
    "templates/quality/observation_pdf_view.html",
}
DEBT_BASELINE = (
    0  # صُفّر في W-20261021-007: القوائمُ الأربع صارت أفقيّةً، والشعارُ يرثه الكلُّ من `base_qatar_report`
)


def _text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_every_listed_template_exists():
    missing = [p for p in pp.DOCUMENTS if not (ROOT / p).exists()]
    assert not missing, f"قوالبُ في سياسة الطباعة غيرُ موجودة: {missing}"


def test_every_print_template_is_classified():
    found = {
        p.relative_to(ROOT).as_posix()
        for p in (ROOT / "templates").rglob("*.html")
        if (p.stem.endswith("_pdf") or p.stem.startswith(("print_", "pdf_")))
        and "components" not in p.parts
    }
    unknown = sorted(found - set(pp.DOCUMENTS) - SCREEN_VIEWS)
    assert not unknown, f"قوالبُ طباعةٍ بلا سطرٍ في core/print_policy.py: {unknown}"


def test_screen_views_are_really_screen_pages():
    for path in SCREEN_VIEWS:
        assert 'extends "base/base.html"' in _text(path), path


def test_kind_decides_the_expected_orientation():
    assert pp.KIND_ORIENT == {"sheet": "landscape", "form": "portrait", "letter": "portrait"}


def test_declared_status_matches_the_orientation():
    for path, d in pp.DOCUMENTS.items():
        matches = d.default_orient == d.expected_orient
        assert matches == (d.status != pp.DEBT) or d.status == pp.EXCEPTION, path


def test_the_debt_never_grows():
    debt = pp.debt()
    assert len(debt) <= DEBT_BASELINE, f"دَينٌ جديد: {debt}"


def test_logo_claims_are_true_in_the_templates():
    for path, d in pp.DOCUMENTS.items():
        text = _text(path)
        if d.logo == pp.LOGO_BASE:
            assert 'extends "reports/base_qatar_report.html"' in text, path
        elif d.logo == pp.LOGO_FRAME:
            assert "print_frame_header" in text, path
        elif d.logo == pp.LOGO_TAG:
            assert "ministry_logo" in text, path
        elif d.logo == pp.LOGO_OUTSIDE:
            assert "data-pdf-own-page" in text and "ministry_logo" in text, path


def test_landscape_sheets_that_extend_the_base_declare_their_page():
    for path, d in pp.DOCUMENTS.items():
        if d.logo == pp.LOGO_BASE and d.kind == pp.SHEET:
            assert "landscape" in _text(path), f"{path}: كشفٌ أفقيٌّ بلا @page أفقيّ"


def test_the_base_report_carries_the_logo():
    assert "ministry_logo" in _text("templates/reports/base_qatar_report.html")


def test_supervision_form_stays_outside_the_frame():
    text = _text("templates/quality/observation_pdf.html")
    assert "{% print_frame_" not in text


def test_defaults_in_code_match_the_table():
    from operations.absence_followup_print import DEFAULT_ORIENT

    assert DEFAULT_ORIENT["contact"] == "landscape"
    assert DEFAULT_ORIENT["actions"] == "landscape"  # D-449م: الإجراءات أفقيّة كالقوائم
    from wings.views_register import _orientation

    class R:
        GET: dict = {}

    assert _orientation(R()) == "landscape"


def test_no_template_brings_back_a_stamp_box():
    # قرار المالك 2026-11-07: لا خانةَ ختمٍ ولا مربّعَ متقطّعًا في أيّ طباعة (ختمُ التصدير export-stamp نصٌّ مختلف)
    import re
    from pathlib import Path

    banned = re.compile(r"stamp_box|pf-stamp|والختم|>\s*الختم( الرسمي)?\s*<")
    root = Path(__file__).resolve().parent.parent / "templates"
    assert not (root / "components/print/stamp_box.html").exists()
    offenders = [
        str(p.relative_to(root))
        for p in root.rglob("*.html")
        if banned.search(p.read_text(encoding="utf-8"))
    ]
    assert offenders == [], f"قوالبُ تعيد خانةَ الختم: {offenders}"


def test_a_student_list_renders_as_a_landscape_a4_pdf():
    from django.template.loader import render_to_string

    html = render_to_string(
        "student_affairs/student_list_pdf.html",
        {
            "rows": [],
            "total_students": 0,
            "exported_by": "-",
            "exporter_role_ar": "-",
            "export_datetime": "-",
            "academic_year": "-",
        },
    )
    from weasyprint import HTML

    page = HTML(string=html).render().pages[0]
    assert page.width > page.height, f"الصفحةُ عموديّة {page.width}x{page.height} والمطلوب أفقيّ"


# ── اتجاهُ الورق المختار من شريط التصدير الموحَّد (W-20261107-021) ──────────────────────────────────


def test_clean_orient_keeps_the_two_known_values_and_drops_the_rest():
    assert pp.clean_orient("portrait") == "portrait"
    assert pp.clean_orient(" Landscape ") == "landscape"
    assert pp.clean_orient("diagonal") is None
    assert pp.clean_orient("") is None and pp.clean_orient(None) is None


def test_use_orient_scopes_the_request_value_and_restores_it():
    assert pp.requested_orient() is None
    with pp.use_orient("portrait"):
        assert pp.requested_orient() == "portrait"
        with pp.use_orient("bogus"):
            assert pp.requested_orient() is None  # قيمةٌ مجهولةٌ تُهمل فيحكم الافتراضيّ
        assert pp.requested_orient() == "portrait"
    assert pp.requested_orient() is None


def test_default_orient_matches_the_document_table():
    assert pp.default_orient("sheet") == "landscape"
    assert pp.default_orient("form") == pp.default_orient("letter") == "portrait"
    for path, document in pp.DOCUMENTS.items():
        assert pp.default_orient(doc=path) == document.default_orient


def test_orient_param_is_read_from_the_query_and_the_job_query_string():
    from django.http import QueryDict

    assert pp.orient_from(QueryDict("a=1&orient=portrait")) == "portrait"
    assert pp.orient_from(QueryDict("orient=zzz")) is None
    assert pp.orient_from(None) is None


def test_middleware_sets_the_orient_for_the_request_only():
    from django.test import RequestFactory

    from core.middleware import ExportOrientMiddleware

    seen: list[str | None] = []

    def view(_request):
        seen.append(pp.requested_orient())
        return None

    factory = RequestFactory()
    ExportOrientMiddleware(view)(factory.get("/", {"orient": "portrait"}))
    ExportOrientMiddleware(view)(factory.get("/", {"orient": "nonsense"}))
    ExportOrientMiddleware(view)(factory.post("/", {"orient": "landscape"}))
    ExportOrientMiddleware(view)(factory.get("/"))
    assert seen == ["portrait", None, "landscape", None]
    assert pp.requested_orient() is None


def _page_sizes(orient, paper_size="A4"):
    from weasyprint import HTML

    from core.pdf_utils import _force_page_orient

    html = _force_page_orient(
        "<html><head><style>@page { size: A4 landscape; }</style></head><body>x</body></html>",
        paper_size,
        orient,
    )
    page = HTML(string=html).render().pages[0]
    return page.width, page.height


def test_pdf_is_portrait_for_portrait_and_landscape_for_landscape_keeping_the_paper():
    width, height = _page_sizes("portrait")
    assert height > width
    width, height = _page_sizes("landscape")
    assert width > height
    a3_width, a3_height = _page_sizes("portrait", "A3")
    assert a3_height > a3_width and a3_height > height  # A3 يبقى A3 لا A4


def test_pdf_without_a_chosen_orient_keeps_the_template_default():
    from core.pdf_utils import _force_page_orient

    html = "<html><head></head><body>x</body></html>"
    assert _force_page_orient(html, "A4", None) == html


def test_excel_carries_the_chosen_print_orientation_on_every_sheet():
    from openpyxl import Workbook

    from core.export_utils import apply_print_footer

    wb = Workbook()
    wb.create_sheet("second")
    apply_print_footer(wb)
    assert [ws.page_setup.orientation for ws in wb.worksheets] == [
        None,
        None,
    ]  # بلا اختيارٍ: كما بناه البانيّ
    with pp.use_orient("portrait"):
        apply_print_footer(wb)
    assert [ws.page_setup.orientation for ws in wb.worksheets] == ["portrait", "portrait"]
    with pp.use_orient("landscape"):
        apply_print_footer(wb)
    assert {ws.page_setup.orientation for ws in wb.worksheets} == {"landscape"}
