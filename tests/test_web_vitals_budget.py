"""[PERF] ميزانيةُ Core Web Vitals والحمولة — على صفحاتٍ حيّةٍ في Chromium حقيقيّ (P3-3).

قبل هذا لم يكن شيءٌ يقيس LCP أو CLS أو INP، فتراجعٌ في الأداء لا يظهر إلّا حين
يشتكي مستخدم. والأرقامُ وأسبابُ سقوفها في `tests/web_vitals.py:BUDGET`.

الخادمُ يُسخَّن بطلبٍ أوّلَ قبل القياس: أوّلُ طلبٍ على `live_server` كان يبلغ
**10.5 ثانيةً** (TTFB وحدَه؛ الموارد بعده نصفُ ثانية) — تسخينُ قوالب وقاعدة، لا
صفحةٌ بطيئة — فقياسُه كان سيُسقط كلَّ بناءٍ كذباً. وكلُّ قياسٍ في سياق متصفّحٍ نظيف
(بلا كاشٍ) بجلسةٍ محفوظةٍ من تسجيل دخولٍ واحد، فيُقاس «الزائرُ الأوّل» لا «الرابع».

`pytest-playwright` مثبَّتٌ في وظيفة `axe-a11y` في CI وحدها؛ ويتخطّى الملفُّ نفسَه
حيث غاب (كوظيفة `pytest — تغطية`).
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("pytest_playwright")

from tests import web_vitals  # noqa: E402
from tests.test_a11y_live_pages import _url  # noqa: E402

pytestmark = pytest.mark.django_db

#: صفحاتٌ مسجَّلة الدخول: لوحةُ التحكّم (Chart.js)، وقائمةٌ طويلة، وصندوقُ الإشعارات.
PAGES = [
    ("dashboard", "/dashboard/"),
    ("student_list", None),
    ("notification_inbox", None),
]
RUNS = 3


def _path(name: str, path: str | None) -> str:
    return path or _url(name if name != "student_list" else "student_affairs:student_list")


def _measure(browser, url: str, state, *, interact: bool) -> dict:
    context = browser.new_context(storage_state=state) if state else browser.new_context()
    try:
        page = context.new_page()
        load = web_vitals.install(page)
        page.goto(url)
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(800)
        if interact:
            web_vitals.interact(page)
        return web_vitals.read(page, load)
    finally:
        context.close()


def _table(results: dict[str, dict]) -> str:
    columns = ["lcp_ms", "cls", "inp_ms", "requests", "blocking_stylesheets", "css_kb", "js_kb"]
    rows = ["| الصفحة | " + " | ".join(columns) + " |", "|---|" + "---|" * len(columns)]
    for name, metrics in results.items():
        rows.append(f"| {name} | " + " | ".join(str(metrics[c]) for c in columns) + " |")
    return "\n".join(rows)


def test_the_pages_stay_within_the_web_vitals_budget(browser, live_server, principal_user):
    base = live_server.url
    warm = browser.new_context()
    warm.new_page().goto(f"{base}/auth/login/")
    warm.close()

    login_ctx = browser.new_context()
    login_page = login_ctx.new_page()
    login_page.goto(f"{base}/auth/login/")
    login_page.fill('input[name="identifier"]', principal_user.national_id)
    login_page.fill('input[name="password"]', "testpass123")  # pragma: allowlist secret
    login_page.click('button[type="submit"]')
    login_page.wait_for_load_state("networkidle")
    state = login_ctx.storage_state()
    login_ctx.close()

    results = {
        "login": web_vitals.median_of(
            [_measure(browser, f"{base}/auth/login/", None, interact=False) for _ in range(RUNS)]
        )
    }
    for name, path in PAGES:
        url = f"{base}{_path(name, path)}"
        results[name] = web_vitals.median_of(
            [_measure(browser, url, state, interact=True) for _ in range(RUNS)]
        )

    table = _table(results)
    print("\n" + table)
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as summary:
            summary.write("### Core Web Vitals — ميزانية الصفحات الحيّة\n\n" + table + "\n")

    assert results["login"]["lcp_ms"] > 0, (
        "صفحةُ الدخول لا تُبلِّغ LCP — عادت بطاقتُها تدخل من opacity: 0 "
        "(`@keyframes loginCardIn`)، فيُفقد قياسُ أوّل ما يراه كلُّ مستخدم.\n\n" + table
    )
    found = [
        line for name, metrics in results.items() for line in web_vitals.violations(name, metrics)
    ]
    assert not found, "تجاوزت الصفحاتُ ميزانيةَ الأداء:\n  " + "\n  ".join(found) + "\n\n" + table


def test_the_login_card_enters_without_an_opacity_fade():
    """السببُ نفسُه بلا متصفّح: مفتاحُ الأنيميشن لا يحمل `opacity`."""
    import re

    from tests.css_source import read_css

    match = re.search(r"@keyframes loginCardIn\s*\{(.*?)\n\}", read_css(), re.S)
    assert match, "لا @keyframes loginCardIn"
    assert "opacity" not in match.group(
        1
    ), "loginCardIn يبدأ من opacity: 0 — لا يُبلَّغ FCP/LCP على صفحة الدخول"


class TestTheBudgetItself:
    """الميزانيةُ تحرس ما تقول — منطقُها لا يحتاج متصفّحاً."""

    def test_a_value_over_its_ceiling_is_reported(self):
        found = web_vitals.violations("p", {"cls": 0.2, "js_kb": 500, "requests": 10})
        assert any("cls" in line for line in found) and any("js_kb" in line for line in found)
        assert not any("requests" in line for line in found)

    def test_a_value_exactly_at_the_ceiling_passes(self):
        assert not web_vitals.violations("p", {"lcp_ms": 2500, "css_kb": 460})

    def test_an_unreported_lcp_or_inp_is_not_a_violation(self):
        assert not web_vitals.violations("login", {"lcp_ms": 0, "inp_ms": 0})

    def test_a_zero_in_a_deterministic_metric_still_counts(self):
        assert not web_vitals.violations("p", {"cls": 0, "requests": 0})

    def test_the_median_of_three_ignores_one_outlier(self):
        runs = [{"lcp_ms": 300, "cls": 0}, {"lcp_ms": 10800, "cls": 0}, {"lcp_ms": 320, "cls": 0}]
        assert web_vitals.median_of(runs)["lcp_ms"] == 320

    def test_the_stylesheet_count_ceiling_stops_unbounded_splitting(self):
        assert web_vitals.violations("p", {"blocking_stylesheets": 11})
        assert not web_vitals.violations("p", {"blocking_stylesheets": 8})
