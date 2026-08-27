"""[BRAND] رؤية الوزارة في ذيل الوثائق وفوتر المنصّة — من مصدرٍ واحد.

كانت مكتوبةً نصّاً في قالبَي طباعة وغائبةً عن الباقي. وتكرار النصّ يعني أن
تعديله لاحقاً يُصيب بعض الوثائق دون بعض — فوُحِّد في `components/ministry_vision.html`.
"""

import pathlib

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

VISION = "تعليم ريادي مبتكر لمجتمع واعٍ ومنتج"

PARTIAL = pathlib.Path("templates/components/ministry_vision.html")

#: قوالب الطباعة المستقلّة — لا ترث ذيلاً من غيرها.
STANDALONE_DOCS = [
    "templates/quality/observation_pdf.html",
    "templates/reports/base_report.html",
    "templates/schedule/print_schedule.html",
    "templates/behavior/pdf/policy_doc.html",
    "templates/behavior/pdf/base_form.html",
    "templates/reports/base_qatar_report.html",
]


def test_the_vision_has_one_source():
    """النصّ يُكتب مرّةً واحدة — في الجزئيّة وحدها."""
    holders = [
        f.as_posix()
        for f in pathlib.Path("templates").rglob("*.html")
        if VISION in f.read_text(encoding="utf-8", errors="ignore")
    ]

    assert holders == [PARTIAL.as_posix()], f"النصّ مكرّر في: {holders}"


@pytest.mark.parametrize("doc", STANDALONE_DOCS)
def test_every_standalone_document_footer_carries_the_vision(doc):
    assert 'include "components/ministry_vision.html"' in pathlib.Path(doc).read_text(
        encoding="utf-8"
    )


def test_the_partial_renders_the_vision_itself():
    """الجزئيّة تُصيَّر نصّاً لا تعليقاً — التعليق `{% comment %}` لا يظهر."""
    rendered = render_to_string("components/ministry_vision.html").strip()

    assert rendered == VISION


@pytest.mark.django_db
def test_the_platform_footer_carries_the_vision(client, principal_user):
    """يُقاس على صفحةٍ مُصيَّرة عبر مكدّس العرض، لا على نصّ القالب.

    فوتر المنصّة في `base.html`، ولا يظهر إلا لمستخدمٍ داخل النظام.
    """
    client.force_login(principal_user)

    html = client.get(reverse("observation_list")).content.decode()

    assert VISION in html
    assert "site-footer-vision" in html
