"""فاحصُ الصفحات (`scripts/page_smoke.py`) — W-20261106-025.

دوالُّ نقيّةٌ على نصوص HTML وقياسات: بلا متصفّحٍ ولا Playwright.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("page_smoke", ROOT / "scripts" / "page_smoke.py")
smoke = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(smoke)

GOOD = {"status": 200, "scroll_width": 375, "viewport_width": 375, "html": "<form></form>"}


def test_healthy_page_passes():
    assert smoke.judge_page("/ok/", GOOD) == []


def test_required_inside_hidden_container_fails():
    html = '<form><div hidden><input name="reason" required></div></form>'
    problems = smoke.judge_page("/x/", {**GOOD, "html": html})
    assert any("reason" in p for p in problems)


def test_required_in_nested_display_none_fails_but_visible_passes():
    nested = (
        '<div style="display: none"><p><span><textarea id="t" required></textarea></span></p></div>'
    )
    assert smoke.required_in_hidden(nested) == ["t"]
    assert smoke.required_in_hidden('<div><input name="a" required></div>') == []


def test_hidden_state_does_not_leak_to_siblings_after_close():
    html = '<div hidden><b>x</b></div><input name="after" required>'
    assert smoke.required_in_hidden(html) == []


def test_type_hidden_input_is_not_flagged():
    assert smoke.required_in_hidden('<div hidden><input type="hidden" required></div>') == []


def test_status_500_console_network_and_overflow_fail():
    bad = {
        **GOOD,
        "status": 500,
        "console_errors": ["boom"],
        "failed_requests": ["http://x/a.js"],
        "scroll_width": 420,
    }
    assert len(smoke.judge_page("/x/", bad)) == 4


def test_chart_needs_object_and_data():
    base = {**GOOD}
    assert smoke.judge_page("/c/", {**base, "charts": {"canvases": 1, "chart_defined": False}})
    assert smoke.judge_page(
        "/c/", {**base, "charts": {"canvases": 2, "chart_defined": True, "with_data": 1}}
    )
    assert (
        smoke.judge_page(
            "/c/", {**base, "charts": {"canvases": 1, "chart_defined": True, "with_data": 1}}
        )
        == []
    )
    assert smoke.judge_page("/c/", {**base, "charts": {"canvases": 0}}) == []
