"""
E2E: حارس الجلسة — لا يضيع ما أدخله المستخدم بانتهاء جلسته (W-20261005-003، س١)
════════════════════════════════════════════════════════════════════════════════
المعيار (١): نموذجٌ مفتوحٌ تُنهى جلستُه من الخادم ثمّ «حفظ» ← تظهر نافذةُ إعادة الدخول،
يُعاد الدخول، **وتُحفظ البيانات نفسُها** دون فقدٍ. (٣) تحذيرٌ قبل الانتهاء بدقيقتين يمدّد.
(٤) نبضٌ لا يعمل بلا إدخالٍ فعليّ. والجانبُ الخادميّ في tests/test_session_expiry.py.
"""

import re
import time
from datetime import time as dt_time

import pytest

pytest.importorskip("pytest_playwright")
from playwright.sync_api import expect  # noqa: E402

from core.session_policy import limits_for  # noqa: E402
from notifications.models import UserNotificationPreference  # noqa: E402

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

PASSWORD = "TestPass123!"  # pragma: allowlist secret
FORM_URL = "/notifications/preferences/"


def _end_every_session():
    """ما يفعله انتهاءُ الجلسة على الخادم: لا صفَّ في جدول الجلسات."""
    from django.contrib.sessions.models import Session

    Session.objects.all().delete()


def _age_the_session(seconds_left):
    """يُقدِّم ختمَ آخر تجديدٍ ليبقى للخمول `seconds_left` ثانية."""
    from django.contrib.sessions.backends.db import SessionStore
    from django.contrib.sessions.models import Session

    for row in Session.objects.all():
        store = SessionStore(session_key=row.session_key)
        store["_last_touch"] = int(time.time()) - (limits_for("teacher").idle - seconds_left)
        store.save()


def _requests_to(page, fragment):
    seen = []
    page.on("request", lambda req: seen.append(req.url) if fragment in req.url else None)
    return seen


class TestTheEnteredDataSurvivesAnExpiredSession:
    def test_save_after_the_session_ended_reopens_login_then_saves_the_same_data(
        self, page, live_server, login, e2e_teacher
    ):
        login(e2e_teacher)
        page.goto(f"{live_server.url}{FORM_URL}")
        page.fill("#quiet-start", "22:15")
        page.fill("#quiet-end", "05:45")

        _end_every_session()
        page.click("button.btn-primary:has-text('حفظ التفضيلات')")

        dialog = page.locator("#session-relogin")
        expect(dialog).to_be_visible()
        expect(dialog).to_contain_text("ما أدخلتَه ما زال في هذه الصفحة")

        frame = page.frame_locator("#session-relogin iframe")
        frame.locator('input[name="identifier"]').fill(e2e_teacher.national_id)
        frame.locator('input[name="password"]').fill(PASSWORD)
        frame.locator('button[type="submit"]').click()

        expect(dialog).to_be_hidden(timeout=15000)
        # `body` لا `#page-msgs, main`: المحدِّد المركّب يطابق عنصرَين فيفشل Playwright في الوضع الصارم.
        expect(page.locator("body")).to_contain_text("تم حفظ تفضيلات الإشعارات")
        prefs = UserNotificationPreference.objects.get(user=e2e_teacher)
        assert prefs.quiet_hours_start == dt_time(22, 15)
        assert prefs.quiet_hours_end == dt_time(5, 45)

    def test_cancelling_keeps_the_page_and_the_typed_values(
        self, page, live_server, login, e2e_teacher
    ):
        login(e2e_teacher)
        page.goto(f"{live_server.url}{FORM_URL}")
        page.fill("#quiet-start", "21:00")
        _end_every_session()
        page.click("button.btn-primary:has-text('حفظ التفضيلات')")
        expect(page.locator("#session-relogin")).to_be_visible()

        page.click("#session-relogin [data-sg-cancel]")

        expect(page.locator("#session-relogin")).to_be_hidden()
        expect(page.locator("#quiet-start")).to_have_value("21:00")

    def test_logging_in_as_somebody_else_does_not_send_the_old_users_data(
        self, page, live_server, login, e2e_teacher, e2e_principal
    ):
        login(e2e_teacher)
        page.goto(f"{live_server.url}{FORM_URL}")
        page.fill("#quiet-start", "20:30")
        _end_every_session()
        page.click("button.btn-primary:has-text('حفظ التفضيلات')")

        frame = page.frame_locator("#session-relogin iframe")
        frame.locator('input[name="identifier"]').fill(e2e_principal.national_id)
        frame.locator('input[name="password"]').fill(PASSWORD)
        frame.locator('button[type="submit"]').click()

        expect(page.locator("[data-sg-status]")).to_contain_text("حسابٍ مختلف", timeout=15000)
        assert not UserNotificationPreference.objects.filter(
            user=e2e_principal, quiet_hours_start=dt_time(20, 30)
        ).exists()


class TestWarningBeforeExpiry:
    def test_warns_two_minutes_before_and_stay_connected_extends(
        self, page, live_server, login, e2e_teacher
    ):
        login(e2e_teacher)
        page.goto(f"{live_server.url}{FORM_URL}")
        page.wait_for_load_state("networkidle")
        # تقديمُ الختم بعد تحميل الصفحة لا قبله: طلبُ التصفّح الحقيقيّ يجدّد الخمول (س٢)،
        # فتقديمُه قبل `goto` كان يُمحى بالتحميل نفسِه ولا يظهر التحذير. ثمّ نُعيد قراءة الحالة
        # كما تفعل الصفحةُ عند عودتها للظهور (الحالةُ قراءةٌ لا تجدّد).
        _age_the_session(seconds_left=100)
        page.evaluate("document.dispatchEvent(new Event('visibilitychange'))")

        warning = page.locator("#session-warning")
        expect(warning).to_be_visible(timeout=10000)
        expect(warning).to_have_attribute("role", "alertdialog")
        expect(warning.locator("[data-sg-countdown]").first).to_have_text(
            re.compile(r"^[01]:\d\d$")
        )

        warning.locator("[data-sg-stay]").click()

        expect(warning).to_be_hidden()
        status = page.evaluate("fetch('/auth/session/status/').then(r => r.json())")
        assert status["idle_remaining"] > 600


class TestPulseNeedsRealInput:
    def test_no_touch_without_input_and_one_touch_with_input(
        self, page, live_server, login, e2e_teacher
    ):
        login(e2e_teacher)
        page.clock.install()
        page.goto(f"{live_server.url}{FORM_URL}")
        page.wait_for_load_state("networkidle")
        touches = _requests_to(page, "/auth/session/touch/")

        page.clock.run_for(6 * 60 * 1000)
        assert touches == [], "نبضٌ بلا إدخالٍ فعليّ"

        page.fill("#quiet-start", "10:00")
        page.clock.run_for(2 * 60 * 1000)
        page.wait_for_timeout(300)
        assert len(touches) == 1, "نبضةٌ واحدةٌ بعد إدخالٍ فعليّ، لا نبضةٌ كلَّ ثانية"
