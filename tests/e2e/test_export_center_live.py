"""[DESKTOP] مركزُ التصدير الواحد (VI-30أ): ملفٌّ مباشرٌ بلا وميض، ومهمّةٌ خلفيّةٌ بإشعارٍ ثمّ تنزيل، وفشلٌ ظاهرٌ لا صامت.

المشاهدُ في `tests/export_center_probe.py` (تُعترَض فيها الطلباتُ بأجوبةٍ مصنوعةٍ، فلا تعتمد على بياناتٍ ولا على خادمِ تصدير)؛
وهنا تُشغَّل على لوحةِ المنصّة الحيّة بعد الدخول — فيها `base.js` (`showToast`) و`export-center.js` كما يصلان المستخدم.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_playwright")

from tests import export_center_probe  # noqa: E402
from tests.test_a11y_live_pages import _url  # noqa: E402
from tests.test_mobile_audit import _signed_in_state  # noqa: E402

pytestmark = pytest.mark.django_db


def test_every_export_flow_behaves_on_the_live_dashboard(playwright, live_server, principal_user):
    browser = playwright.chromium.launch()
    try:
        state = _signed_in_state(browser, live_server.url, principal_user)
        context = browser.new_context(
            storage_state=state,
            locale="ar",
            viewport={"width": 1366, "height": 800},
            accept_downloads=True,
            # عاملُ الخدمة (`/sw.js`) يجلس بين الصفحة والشبكة، وPlaywright يُبلغ اعتراضَه عن طلباتِ العامل نفسِه (بلا ترويسات
            # الصفحة) فيُرى الطلبُ الفاشلُ المُجهَض مرّتين، الثانيةَ بلا `X-Requested-With` — وليس هذا ما يصنعه العاملُ فعلاً
            # (`fetch(e.request)` يحفظ الترويسات). قيسَ 2026-09-26: بحجبه تمرّ المشاهدُ الأحدَ عشرَ كلُّها على اللوحة الحيّة.
            service_workers="block",
        )
        try:
            page = context.new_page()
            response = page.goto(f"{live_server.url}{_url('dashboard')}", wait_until="load")
            assert response and response.ok, response and response.status
            page.wait_for_function("typeof window.showToast === 'function'", timeout=10_000)
            export_center_probe.run_all(page)
        finally:
            context.close()
    finally:
        browser.close()
