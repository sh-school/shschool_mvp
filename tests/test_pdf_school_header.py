"""اسمُ المدرسة تحت شعار الوزارة في ترويسة كل PDF (W-20261107-023، قرار المالك 2026-11-07).

الحارسُ: كلُّ مسار توليد (WeasyPrint وPlaywright وxhtml2pdf) يخرج باسم المدرسة الحقيقيّ — حتى من قالبٍ بلا `report-header` —
ولا يظهر «SchoolOS» اسماً للمدرسة في أيّ ترويسة.
"""

from __future__ import annotations

import re
from types import SimpleNamespace

from core import pdf_utils as pu
from core.print_school import FALLBACK_NAME, resolve_school_name, use_school

BARE = "<html><head><style>p{}</style></head><body><p>محتوى</p></body></html>"
NAME = "مدرسة الاختبار النموذجية"


def _request(name: str = NAME) -> SimpleNamespace:
    return SimpleNamespace(school=SimpleNamespace(name=name))


def test_request_school_beats_template():
    html = '<div class="report-header"><h1>اسم من القالب</h1></div>'
    with use_school(_request()):
        assert resolve_school_name(html) == NAME
    assert resolve_school_name(html) == "اسم من القالب"


def test_never_platform_name():
    assert resolve_school_name(BARE) == FALLBACK_NAME
    assert (
        resolve_school_name('<div class="report-header"><h1>SchoolOS</h1></div>') == FALLBACK_NAME
    )


def test_user_resolved_lazily():
    req = SimpleNamespace(user=SimpleNamespace(get_school=lambda: SimpleNamespace(name=NAME)))
    with use_school(req):
        assert resolve_school_name(BARE) == NAME


def test_meta_school_without_report_header():
    with use_school(_request()):
        assert pu._extract_pdf_meta(BARE)["school"] == NAME
    assert pu._extract_pdf_meta(BARE)["school"] != "SchoolOS"


def test_weasyprint_logo_school_title_order():
    with use_school(_request()):
        meta = pu._extract_pdf_meta(BARE)
    out = pu._inject_wp_page_header_css(BARE, meta["school"], "تقرير", "A4")
    m = re.search(r'<div class="wp-page-header">(.*?)</div>\n', out, re.S)
    assert m, "الترويسةُ الجارية غير محقونة"
    block = out[out.index('<div class="wp-page-header">') :]
    assert block.index("<img") < block.index(NAME) < block.index("تقرير")


def test_playwright_school_on_own_line():
    html = pu._playwright_header_template(NAME, "تقرير", "A4")
    assert f'class="ph-school">{NAME}</div>' in html
    assert html.index("<img") < html.index(NAME) < html.index("تقرير")
    assert "SchoolOS" not in html


def test_xhtml2pdf_injects_header():
    meta = {"school": NAME, "title": "تقرير", "year": ""}
    out = pu._inject_xhtml_header(BARE, meta, "A4")
    assert NAME in out and out.index("<img") < out.index(NAME) < out.index("تقرير")
    # قالبٌ يحمل الاسمَ في جسمه لا يُكرَّر
    own = f"<html><body><h1>{NAME}</h1></body></html>"
    assert pu._inject_xhtml_header(own, meta, "A4") == own


def test_scale_proportional():
    for paper in ("A4", "A3"):
        logo, name = pu._header_scale(paper)
        assert name < logo / 2
    assert pu._header_scale("A3")[1] > pu._header_scale("A4")[1]
    assert pu._header_scale("A3")[0] > pu._header_scale("A4")[0]


def test_guard_every_path_has_school_name():
    """المسارات الثلاثة تحمل الاسمَ نفسَه وليس فيها «SchoolOS» ترويسةً."""
    with use_school(_request()):
        school = pu._extract_pdf_meta(BARE)["school"]
    wp = pu._inject_wp_page_header_css(BARE, school, "ع", "A3")
    pw = pu._playwright_header_template(school, "ع", "A3")
    xh = pu._inject_xhtml_header(BARE, {"school": school, "title": "ع", "year": ""}, "A3")
    for path in (wp, pw, xh):
        assert NAME in path
    assert 'wp-school">SchoolOS' not in wp
    assert 'ph-school">SchoolOS' not in pw
    assert 'xh-school">SchoolOS' not in xh
