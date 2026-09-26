"""[DESKTOP] لوحةُ القيادة تسع لابتوب 1366×768 بلا تمرير (LAY-03).

على 1366×768 كانت اللوحةُ تُمرَّر 126px، وعلّتان مركزيّتان: شبكةُ البلاطات `.ui-actions` بحدٍّ أدنى 160px للبلاطة فتنزل الثامنةُ إلى
صفٍّ ثانٍ (8×160 + 7×8 = 1336 > 1328px المتاحة)، والرسمُ `.dash-chart-wrap` بارتفاعٍ ثابتٍ 220px. فصار الحدُّ 148px والرسمُ يتبع ارتفاعَ
النافذة (`clamp(150px, 20vh, 220px)`) فوق 1024px.

يقيس ما يُرسم لا نصَّ CSS: صفوفَ البلاطات وارتفاعَ الرسم وتمريرَ المستند. وارتفاعُ الرسم ونسبتُه للنافذة آليّتان لا تتبعان حجمَ البيانات، فتُحرسان
هنا؛ أمّا التمريرُ الكلّيّ فمعه بيانُ CI المبذورة (مدرسةٌ شبهُ فارغة) — أقلُّ من الإنتاج، فهو حدٌّ أدنى لا بديلَ عن قياس الإنتاج.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_playwright")

from tests.test_a11y_live_pages import _url  # noqa: E402
from tests.test_mobile_audit import _signed_in_state  # noqa: E402

pytestmark = pytest.mark.django_db

VIEWPORT = {"width": 1366, "height": 768}

MEASURE = """
() => {
  const tileRows = [...document.querySelectorAll('.ui-actions')].map(
    (grid) => new Set([...grid.children].map((tile) => Math.round(tile.getBoundingClientRect().top))).size
  );
  return {
    tileRows,
    charts: [...document.querySelectorAll('.dash-chart-wrap')].map((el) => Math.round(el.getBoundingClientRect().height)),
    scroll: Math.max(0, document.scrollingElement.scrollHeight - window.innerHeight),
    overflow: document.documentElement.scrollWidth - window.innerWidth,
  };
}
"""


def test_the_leadership_dashboard_fits_a_1366_by_768_window(
    playwright, live_server, principal_user
):
    browser = playwright.chromium.launch()
    try:
        state = _signed_in_state(browser, live_server.url, principal_user)
        context = browser.new_context(storage_state=state, locale="ar", viewport=VIEWPORT)
        try:
            page = context.new_page()
            response = page.goto(f"{live_server.url}{_url('dashboard')}", wait_until="load")
            assert response and response.ok, response and response.status
            page.evaluate("document.fonts.ready.then(() => 1)")
            page.wait_for_timeout(500)  # `fitNoscroll` يُشدَّد بعد جهوز الخطوط
            result = page.evaluate(MEASURE)
        finally:
            context.close()
    finally:
        browser.close()
    assert result["tileRows"], "لا شبكةَ بلاطاتٍ في لوحة القيادة"
    assert all(
        rows == 1 for rows in result["tileRows"]
    ), f"بلاطاتُ الانتقال في أكثر من سطرٍ على 1366px: {result['tileRows']} — الحدُّ الأدنى للبلاطة 148px (8×148 + 7×8 ≤ 1328)"
    limit = round(VIEWPORT["height"] * 0.2) + 1
    assert all(
        height <= limit for height in result["charts"]
    ), f"رسمٌ أطولُ من 20% من النافذة ({limit}px): {result['charts']} — `.dash-chart-wrap` يتبع الارتفاعَ فوق 1024px"
    assert result["scroll"] == 0, f"تُمرَّر لوحةُ القيادة {result['scroll']}px على 1366×768"
    assert result["overflow"] <= 0, f"تفيض اللوحةُ أفقيّاً {result['overflow']}px"
