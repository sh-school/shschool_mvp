"""كلُّ PDF سلوكيّ يحمل عنوانًا يسمّيه في ترويسة الإطار المركزيّ (W-20261108-024)."""

from __future__ import annotations

import datetime
from types import SimpleNamespace

import pytest
from django.template.loader import render_to_string

from behavior.views import BEHAVIOR_PDF_TITLES, _behavior_pdf_context

DAY = datetime.date(2026, 11, 8)


def _ctx(template: str) -> dict:
    infraction = SimpleNamespace(date=DAY)
    school = SimpleNamespace(name="مدرسة الاختبار النموذجية")
    return _behavior_pdf_context(template, {"school": school, "infraction": infraction})


@pytest.mark.parametrize("template", sorted(BEHAVIOR_PDF_TITLES))
def test_header_names_file_with_school_and_date(template):
    ctx = _ctx(template)
    # الإطارُ وحده: نرسم ترويسته بالسياق نفسه الذي يمرّره القالبُ الأب
    html = render_to_string(
        "behavior/pdf/base_form.html",
        ctx,
    )
    head = html.split('id="print-header"', 1)[1].split("</div>\n</div>", 1)[0]
    assert f'class="pf-title">{BEHAVIOR_PDF_TITLES[template]}<' in head
    assert "مدرسة الاختبار النموذجية" in head
    assert "2026/11/08" in head


def test_file_without_title_is_refused():
    with pytest.raises(ValueError):
        _behavior_pdf_context("behavior/pdf/unknown.html", {})
