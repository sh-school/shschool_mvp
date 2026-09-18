"""[A11Y] حارسُ axe-core الحيّ — راجع `tests/a11y_axe_ratchet.py` للسبب والطريقة.

تسجيلُ الدخول عبر متصفّحٍ حقيقيّ لا عميل Django — حقلُ الهويّة اسمُه `identifier`
(الرقم الوظيفي أو الشخصي)، لا `national_id` كما كان في `tests/e2e/conftest.py`
القديم (كان يفشل صامتاً: `pytest-playwright` نفسُه لم يكن مثبَّتاً فلا يُجمَع
الملفُّ أصلاً — أُصلح الاثنان معاً هنا).
"""

from __future__ import annotations

import os

import pytest

from tests import a11y_axe_ratchet as ratchet
from tests.test_a11y_live_pages import PAGES, _url

pytestmark = pytest.mark.django_db

UPDATE_CMD = (
    "AXE_UPDATE=1 pytest tests/test_a11y_axe_ratchet.py::test_axe_violations_have_not_grown"
)


def _login(page, live_server, user, password="testpass123"):
    page.goto(f"{live_server.url}/auth/login/")
    page.fill('input[name="identifier"]', user.national_id)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")


def _measure_all(request, page, live_server) -> dict[str, dict[str, int]]:
    """كلُّ صفحات `PAGES` (تُسجَّل الدخول مرّةً — جميعُها principal_user اليوم)."""
    results: dict[str, dict[str, int]] = {}
    logged_in_as = None
    for name, who in PAGES:
        user = request.getfixturevalue(who)
        if logged_in_as != who:
            _login(page, live_server, user)
            logged_in_as = who
        page.goto(f"{live_server.url}{_url(name)}")
        page.wait_for_load_state("networkidle")
        counts = ratchet.measure_page(page)
        if counts:
            results[name] = counts
    return results


def test_axe_violations_have_not_grown(request, page, live_server, school_bus, library_book):
    current = _measure_all(request, page, live_server)

    if os.environ.get("AXE_UPDATE"):
        ratchet.write_baseline(current)
        for rule, n in ratchet.totals(current).items():
            print(f"{rule}: {n}")
        pytest.skip("حُدِّث الخطّ الأساس — راجع tests/a11y_axe_ratchet_baseline.json وأودعه")

    baseline = ratchet.read_baseline()
    worse, stale = ratchet.compare(baseline, current)
    assert not worse, "زادت مخالفاتُ axe-core — لا تُودَع:\n  " + "\n  ".join(worse)
    assert not stale, (
        f"نقصت مخالفاتٌ ولم يُسجَّل نقصُها — أحسنت؛ ثبّته بـ `{UPDATE_CMD}` وأودع الملفّ:\n  "
        + "\n  ".join(stale)
    )


class TestTheRatchetItself:
    """الحارسُ يحرس ما يقول إنّه يحرسه — منطقُ المقارنة لا يحتاج متصفّحاً لاختباره."""

    def test_a_new_violation_on_a_known_page_is_worse(self):
        before = {"ui_components": {"scrollable-region-focusable": 1}}
        after = {"ui_components": {"scrollable-region-focusable": 2}}
        worse, stale = ratchet.compare(before, after)
        assert len(worse) == 1 and not stale

    def test_a_new_page_with_a_violation_is_worse(self):
        before: dict = {}
        after = {"new_page": {"image-alt": 1}}
        worse, _ = ratchet.compare(before, after)
        assert worse and "new_page" in worse[0]

    def test_a_fixed_violation_must_be_recorded(self):
        before = {"ui_components": {"scrollable-region-focusable": 1}}
        after = {"ui_components": {}}
        worse, stale = ratchet.compare(before, after)
        assert not worse and len(stale) == 1

    def test_totals_sum_across_pages(self):
        data = {"a": {"rule1": 2}, "b": {"rule1": 1, "rule2": 3}}
        assert ratchet.totals(data) == {"rule1": 3, "rule2": 3}
