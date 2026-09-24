"""[MOBILE] سقّاطةُ الجوال الحيّة (M-00) — راجع `tests/mobile_audit.py` للسبب والطريقة.

الرحلاتُ خمسةُ أدوارٍ بخمس صفحاتٍ لكلٍّ (Q-01)، مرتّبةً كما يمرّ بها صاحبُها في يومه؛
وتُقاس على الجوال بـChromium وWebKit (Q-02) وعلى سطح المكتب بـChromium.

`pytest-playwright` مثبَّتٌ في وظيفة `axe-a11y` في CI وحدها؛ ويتخطّى الملفُّ نفسَه حيث غاب.
وإعادةُ القياس وتثبيتُ المكسب:

    MOBILE_AUDIT_UPDATE=1 pytest tests/test_mobile_audit.py -s
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("pytest_playwright")

from tests import mobile_audit as audit  # noqa: E402
from tests.test_a11y_live_pages import _url  # noqa: E402

pytestmark = pytest.mark.django_db

UPDATE_CMD = "MOBILE_AUDIT_UPDATE=1 pytest tests/test_mobile_audit.py -s"

#: ما تُحال إليه جلسةٌ لم تثبت — فصفحةٌ انتهت إليه لم تُقَس.
LOGIN_PATH = "/auth/login/"

#: رحلاتُ الأدوار (Q-01): الحسابُ المبذور، ثمّ صفحاتُه بترتيب يومه.
JOURNEYS = {
    "leadership": (
        "principal_user",
        (
            "dashboard",
            "student_affairs:student_list",
            "staff_affairs:staff_list",
            "daily_report",
            "notification_inbox",
        ),
    ),
    "wing_supervisor": (
        "admin_supervisor_user",
        (
            "dashboard",
            "wings:floors",
            "wings:record_index",
            "student_affairs:student_list",
            "notification_inbox",
        ),
    ),
    "teacher": (
        "teacher_user",
        ("dashboard", "teacher_schedule", "swap_list", "my_evaluations", "notification_inbox"),
    ),
    "parent": (
        "parent_user",
        (
            "parent_dashboard",
            "parent_all_attendance",
            "parent_all_grades",
            "parent_behavior",
            "notification_preferences",
        ),
    ),
    "nurse": (
        "nurse_user",
        (
            "dashboard",
            "clinic:dashboard",
            "clinic:visits_list",
            "clinic:record_visit",
            "clinic:statistics",
        ),
    ),
}


def _signed_in_state(browser, base: str, user) -> dict:
    """جلسةُ دخولٍ تُعاد لكلّ مِلفّ — الدخولُ مرّةً لكلّ دورٍ ومحرّك."""
    context = browser.new_context()
    try:
        page = context.new_page()
        page.goto(f"{base}/auth/login/")
        page.fill('input[name="identifier"]', user.national_id)
        page.fill('input[name="password"]', "testpass123")  # pragma: allowlist secret
        page.click('button[type="submit"]')
        # الانتظارُ لمغادرة صفحة الدخول لا لسكون الشبكة: WebKit يبدأ الانتقالَ بعد النقر متأخّراً،
        # فـ`networkidle` يجد الصفحةَ ساكنةً قبله ويعود وهي صفحةُ الدخول. وصفحةُ الدخول تردّ 200
        # كغيرها، فكانت تُقاس على أنّها صفحةُ الدور «تحسّناً» كاذباً (رحلةُ القيادة، 2026-09-23).
        page.wait_for_url(lambda url: LOGIN_PATH not in url, timeout=30_000)
        page.wait_for_load_state("networkidle")
        return context.storage_state()
    finally:
        context.close()


def _measure_all(request, playwright, base: str) -> dict[str, dict]:
    results: dict[str, dict] = {}
    engines = {e for names in audit.ENGINES.values() for e in names}
    for engine in sorted(engines):
        browser = getattr(playwright, engine).launch()
        try:
            for role, (fixture, pages) in JOURNEYS.items():
                state = _signed_in_state(browser, base, request.getfixturevalue(fixture))
                for profile, options in audit.PROFILES.items():
                    if engine not in audit.ENGINES[profile]:
                        continue
                    context = browser.new_context(storage_state=state, **options)
                    try:
                        page = context.new_page()
                        for name in pages:
                            # `load` لا `networkidle`: الأنماطُ والخطوطُ هي ما يُقاس، ونصفُ ثانيةٍ
                            # سكونٍ بعد كلّ صفحةٍ كان يضاعف الزمنَ فوق ميزانية CI (90 ث).
                            response = page.goto(f"{base}{_url(name)}", wait_until="load")
                            assert (
                                response and response.ok
                            ), f"{role}:{name} {response and response.status}"
                            assert (
                                LOGIN_PATH not in page.url
                            ), f"{engine}/{role}:{name} أُحيل إلى الدخول — الجلسةُ لم تثبت"
                            page.evaluate("document.fonts.ready.then(() => 1)")
                            results[f"{engine}/{profile}/{role}:{name}"] = audit.measure_page(page)
                    finally:
                        context.close()
        finally:
            browser.close()
    return results


def test_touch_targets_and_text_have_not_regressed(request, playwright, live_server):
    current = _measure_all(request, playwright, live_server.url)

    if os.environ.get("MOBILE_AUDIT_UPDATE"):
        audit.write_baseline(current)
        for run, s in audit.summary(current).items():
            print(
                f"{run}: {s['pages']} صفحة، {s['targets']} هدفاً — K1 {s['k1_pct']}% "
                f"({s['small44']}) · K2 {s['k2_pct']}% ({s['small24']}) · "
                f"K3 {s['k3']} · K4 {s['k4']} · K5 {s['k5']}"
            )
        pytest.skip("حُدِّث الخطّ الأساس — راجع tests/mobile_audit_baseline.json وأودعه")

    worse, stale = audit.compare(audit.read_baseline(), current)
    assert not worse, "ساءت أهدافُ اللمس أو النصّ — لا تُودَع:\n  " + "\n  ".join(worse)
    assert not stale, (
        f"تحسّنت صفحاتٌ ولم يُسجَّل تحسّنُها — ثبّته بـ `{UPDATE_CMD}` وأودع الملفّ:\n  "
        + "\n  ".join(stale)
    )


class TestTheRatchetItself:
    """الحارسُ يحرس ما يقول إنّه يحرسه — المقارنةُ لا تحتاج متصفّحاً."""

    def test_a_new_small_target_is_worse(self):
        worse, stale = audit.compare({"p": {"small44": 3}}, {"p": {"small44": 4}})
        assert len(worse) == 1 and not stale

    def test_a_fixed_target_must_be_recorded(self):
        worse, stale = audit.compare({"p": {"small44": 3}}, {"p": {"small44": 1}})
        assert not worse and len(stale) == 1

    def test_unguarded_counts_move_freely(self):
        assert audit.compare(
            {"p": {"targets": 30, "min_font": 11}}, {"p": {"targets": 90, "min_font": 9}}
        ) == (
            [],
            [],
        )

    def test_desktop_guards_text_not_touch(self):
        before = {"chromium/desktop/a:b": {"small44": 3, "tiny_text": 1}}
        after = {"chromium/desktop/a:b": {"small44": 9, "tiny_text": 2}}
        worse, _ = audit.compare(before, after)
        assert worse == ["chromium/desktop/a:b: tiny_text 1 → 2"]

    def test_a_new_page_with_overflow_is_worse(self):
        worse, _ = audit.compare({}, {"chromium/mobile/x:y": {"h_overflow": 12}})
        assert worse and "h_overflow" in worse[0]

    def test_summary_gives_the_plan_kpis_per_run(self):
        data = {
            "chromium/mobile/a:b": {
                "targets": 10,
                "small44": 4,
                "small24": 1,
                "min_font": 10,
                "h_overflow": 0,
                "inputs_under_16": 0,
                "tiny_text": 2,
            },
            "chromium/mobile/a:c": {
                "targets": 10,
                "small44": 2,
                "small24": 0,
                "min_font": 12,
                "h_overflow": 5,
                "inputs_under_16": 1,
                "tiny_text": 0,
            },
        }
        s = audit.summary(data)["chromium/mobile"]
        assert (s["k1_pct"], s["k2_pct"], s["k3"], s["k4"], s["k5"]) == (30.0, 5.0, 1, 1, 1)
