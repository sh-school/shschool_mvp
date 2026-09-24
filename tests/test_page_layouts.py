"""[DESIGN] أنماطُ التخطيط السبعة (LAY-03، قرار D-16) — الوسمُ والسقّاطة.

راجع `docs/design/page_layouts.md` للأنماط، و`tests/page_layout_ratchet.py` للسقّاطة.
"""

import json

import pytest
from django import template
from django.template import Context, Template

from core.templatetags.ui import PAGE_LAYOUTS
from tests import page_layout_ratchet as ratchet

UPDATE = "python -m tests.page_layout_ratchet --update"


def _render(src: str) -> str:
    return Template("{% load ui %}" + src).render(Context({})).strip()


def test_the_seven_layouts_and_the_controlled_exit():
    assert set(PAGE_LAYOUTS) == {
        "dashboard", "hub", "list", "detail", "form", "sheet", "report", "custom",
    }  # fmt: skip


@pytest.mark.parametrize("name", ["dashboard", "list", "sheet"])
def test_viewport_layouts_reuse_page_noscroll(name):
    """«بلا تمرير» هو `page-noscroll` القائم لا نسخةٌ منه — فلا يزيد الحِملُ المشحون."""
    assert _render(f'{{% page_layout "{name}" %}}') == f"layout-{name} page-noscroll"


@pytest.mark.parametrize("name", ["hub", "detail", "form", "report", "custom"])
def test_scrolling_layouts_add_only_their_name(name):
    assert _render(f'{{% page_layout "{name}" %}}') == f"layout-{name}"


def test_extra_existing_classes_are_appended():
    assert (
        _render('{% page_layout "sheet" "page-wide" %}') == "layout-sheet page-noscroll page-wide"
    )


def test_an_unknown_layout_is_refused():
    with pytest.raises(template.TemplateSyntaxError, match="غيرُ معروف"):
        _render('{% page_layout "grid" %}')


def test_every_new_page_declares_its_layout():
    baseline = json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))
    new, stale = ratchet.compare(baseline, ratchet.undeclared())
    assert not new, (
        "صفحاتٌ جديدةٌ بلا نمط تخطيط — أضف "
        '`{% block main_class %}{% page_layout "…" %}{% endblock %}` '
        "(الأنماطُ في docs/design/page_layouts.md):\n  " + "\n  ".join(new)
    )
    assert not stale, (
        f"صفحاتٌ أعلنت نمطَها أو حُذفت — أحسنت؛ ثبّت بـ `{UPDATE}` وأودع الملفّ:\n  "
        + "\n  ".join(stale)
    )


def test_the_ratchet_finds_the_platform_pages():
    found = ratchet.pages()
    assert len(found) > 100
    assert "dashboard/main.html" in found
    assert "base/base.html" not in found
    # قالبُ تقريرٍ مطبوع يرث قاعدتَه الخاصّة، لا الغلاف.
    assert not any(name.startswith("reports/pdf") for name in found)


class TestCompare:
    def test_a_new_undeclared_page_is_reported(self):
        assert ratchet.compare(["a.html"], ["a.html", "b.html"]) == (["b.html"], [])

    def test_a_migrated_page_must_leave_the_baseline(self):
        assert ratchet.compare(["a.html", "b.html"], ["a.html"]) == ([], ["b.html"])
