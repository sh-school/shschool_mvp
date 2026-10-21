"""[DESIGN] سياسةُ اتّجاه الطباعة والشعار (W-20261021-007): أفقيٌّ للقوائم والكشوف، عموديٌّ للنماذج والخطابات، والشعارُ إلزاميٌّ.

الجدولُ في `core/print_policy.py`؛ والحارسُ يطابقه بالقوالب والشيفرة، ويمنع ازديادَ الدَّين، ويُلزم كلَّ قالبٍ مطبوعٍ جديدٍ بسطرٍ فيه.
"""

import pathlib

from core import print_policy as pp

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: قوالبُ طباعةٍ لم تُصنَّف بعد (لم تُقرأ في W-20261021-007) — سقّاطةٌ تنقص ولا تزيد.
UNCLASSIFIED = {
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
    unknown = sorted(found - set(pp.DOCUMENTS) - UNCLASSIFIED)
    assert not unknown, f"قوالبُ طباعةٍ بلا سطرٍ في core/print_policy.py: {unknown}"


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
    assert (
        DEFAULT_ORIENT["actions"] == "portrait"
    )  # استثناءٌ بقرار 2026-10-17 (core.print_policy.ACTION_SHEET_NOTE)
    from wings.views_register import _orientation

    class R:
        GET: dict = {}

    assert _orientation(R()) == "landscape"


def test_the_four_student_lists_include_the_manual_stamp_box():
    for name in ("student_list", "attendance_overview", "behavior_overview", "tardiness"):
        assert "components/print/stamp_box.html" in _text(
            f"templates/student_affairs/{name}_pdf.html"
        ), name


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


def test_stamp_box_is_a_manual_empty_box():
    text = _text("templates/components/print/stamp_box.html")
    assert "الختم" in text
    assert (
        "{{" not in text.split("{% endcomment %}")[-1]
    ), "الختمُ خانةٌ يدويّةٌ فارغة: لا قيمةَ مولَّدةً فيها"
