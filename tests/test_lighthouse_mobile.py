"""[MOBILE] Lighthouse للجوال ليلاً (Q-03) — راجع `tests/lighthouse_audit.py` للسبب والطريقة.

لا يعمل إلّا حين يُطلب صراحةً بـ`LIGHTHOUSE_RUN=1` (سيرُ العمل الليليّ `nightly.yml`)،
فلا يُبطئ بوّابةَ الجودة ولا التشغيلَ المحلّيّ. وإعادةُ القياس وتثبيتُ الأساس:

    LIGHTHOUSE_RUN=1 LIGHTHOUSE_UPDATE=1 pytest tests/test_lighthouse_mobile.py -s
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("pytest_playwright")

from tests import lighthouse_audit as lighthouse  # noqa: E402
from tests.test_a11y_live_pages import _url  # noqa: E402
from tests.test_mobile_audit import _signed_in_state  # noqa: E402

pytestmark = pytest.mark.django_db

#: خمسُ صفحاتٍ رئيسة — الأكثرُ زيارةً لكلّ دورٍ من رحلات M-00.
PAGES = (
    ("leadership:dashboard", "principal_user", "dashboard"),
    ("leadership:student_list", "principal_user", "student_affairs:student_list"),
    ("wing_supervisor:record_index", "admin_supervisor_user", "wings:record_index"),
    ("teacher:teacher_schedule", "teacher_user", "teacher_schedule"),
    ("parent:parent_dashboard", "parent_user", "parent_dashboard"),
)


@pytest.mark.skipif(not os.environ.get("LIGHTHOUSE_RUN"), reason="ليليٌّ وحده — LIGHTHOUSE_RUN=1")
def test_mobile_lighthouse_scores_have_not_regressed(request, playwright, live_server):
    base = live_server.url
    browser = playwright.chromium.launch()
    try:
        cookies = {}
        for _, fixture, _ in PAGES:
            if fixture not in cookies:
                state = _signed_in_state(browser, base, request.getfixturevalue(fixture))
                cookies[fixture] = "; ".join(f"{c['name']}={c['value']}" for c in state["cookies"])
    finally:
        browser.close()

    current = {
        key: lighthouse.run(
            f"{base}{_url(name)}", cookies[fixture], playwright.chromium.executable_path
        )
        for key, fixture, name in PAGES
    }
    for key, scores in current.items():
        print(f"{key}: {scores}")

    if os.environ.get("LIGHTHOUSE_UPDATE"):
        lighthouse.write_baseline(current)
        pytest.skip("حُدِّث الخطّ الأساس — راجع tests/lighthouse_baseline.json وأودعه")

    regressions = lighthouse.compare(lighthouse.read_baseline(), current)
    assert not regressions, "انحدرت درجاتُ Lighthouse للجوال:\n  " + "\n  ".join(regressions)


class TestTheComparison:
    """منطقُ السقّاطة يُختبر بلا متصفّح — ويعمل في كلّ تشغيل."""

    BASE = {"p": {"performance": 60, "accessibility": 99}}

    def test_accessibility_may_not_drop_at_all(self):
        assert lighthouse.compare(self.BASE, {"p": {"performance": 60, "accessibility": 98}})

    def test_performance_noise_within_tolerance_passes(self):
        assert not lighthouse.compare(self.BASE, {"p": {"performance": 46, "accessibility": 99}})

    def test_performance_drop_beyond_tolerance_fails(self):
        assert lighthouse.compare(self.BASE, {"p": {"performance": 44, "accessibility": 99}})

    def test_improvement_never_fails(self):
        assert not lighthouse.compare(self.BASE, {"p": {"performance": 90, "accessibility": 100}})

    def test_a_page_without_baseline_is_reported(self):
        assert "لا أساسَ" in lighthouse.compare({}, {"q": {"performance": 1, "accessibility": 1}})[0]
