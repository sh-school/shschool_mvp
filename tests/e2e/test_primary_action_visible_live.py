"""[DESKTOP] زرُّ الإجراء الرئيسيّ لا يُحجب خلف تمريرٍ داخليّ (D-24، قرارُ المالك 2026-09-25).

في صفحةٍ `page-noscroll` تُمرَّر بطاقةُ النموذج داخلَها، فيقع زرُّ «إضافة الطالب» و«إرسال الاستدعاء» و«عيّن بديلاً» تحت الطيّ ولا يبلغه من لا يعرف أنّ
البطاقةَ تُمرَّر (قيس 97 من 945 خليّةً). والقرارُ معيارُ «الإجراءُ مرئيّ» في `fitNoscroll` بلا CSS جديد: فإن قصّ الزرَّ سلفٌ يُمرَّر نُزع `page-noscroll`
فمُرِّرت الصفحةُ كلُّها.

يقيس ما يُرسم: أيُّ سلفٍ يُمرَّر (`overflow-y: auto|scroll` وله فيضٌ) يقصّ الزرَّ؟ والصفحةُ نفسُها بعد تمريرها ليست حجباً (الزرُّ يُبلَغ بتمرير الصفحة).
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_playwright")

from tests.test_a11y_live_pages import _url  # noqa: E402
from tests.test_mobile_audit import _signed_in_state  # noqa: E402

pytestmark = pytest.mark.django_db

#: عرضُ لابتوبٍ وارتفاعاتٌ قصيرةٌ (بشريط أدواتٍ ثقيل) تُقصّ فيها بطاقاتُ النماذج قبل القرار: 500 و560 و620 و680 (قيس أنّ الزرَّ يُحجب عند بعضها لا كلِّها).
WIDTH = 1366
HEIGHTS = (500, 560, 620, 680)
#: صفحاتُ النماذج المسمّاةُ في القرار (تُتخطّى صفحةٌ لا يظهر فيها زرٌّ لهذا الحساب).
PAGES = ("student_affairs:student_add", "behavior:summon_parent", "wings:coverage")

MEASURE = """
() => {
  const main = document.getElementById('main-content');
  const hidden = [];
  let found = 0;
  for (const btn of main.querySelectorAll('form button[type=submit].btn-primary')) {
    if (btn.closest('table, .plain-list')) continue;
    const r = btn.getBoundingClientRect();
    if (!r.height) continue;
    found += 1;
    for (let p = btn.parentElement; p && p !== document.body; p = p.parentElement) {
      const oy = getComputedStyle(p).overflowY;
      if ((oy === 'auto' || oy === 'scroll') && p.scrollHeight > p.clientHeight + 1) {
        const pr = p.getBoundingClientRect();
        if (r.bottom > pr.bottom + 1 || r.top < pr.top - 1) {
          hidden.push(btn.innerText.trim().slice(0, 24) + ' ← ' + p.tagName + '.' + String(p.className).slice(0, 24));
          break;
        }
      }
    }
  }
  return { found, hidden };
}
"""


def test_the_primary_action_of_a_form_page_is_not_hidden_behind_an_inner_scroll(
    playwright, live_server, principal_user
):
    browser = playwright.chromium.launch()
    failures: list[str] = []
    measured = 0
    try:
        state = _signed_in_state(browser, live_server.url, principal_user)
        context = browser.new_context(storage_state=state, locale="ar")
        try:
            page = context.new_page()
            for height in HEIGHTS:
                page.set_viewport_size({"width": WIDTH, "height": height})
                for name in PAGES:
                    response = page.goto(f"{live_server.url}{_url(name)}", wait_until="load")
                    if not (response and response.ok):
                        continue
                    page.evaluate("document.fonts.ready.then(() => 1)")
                    page.wait_for_timeout(500)  # `fitNoscroll` يُشدَّد بعد جهوز الخطوط
                    result = page.evaluate(MEASURE)
                    if not result["found"]:
                        continue
                    measured += 1
                    if result["hidden"]:
                        failures.append(f"{name} @ {WIDTH}×{height}: {result['hidden']}")
        finally:
            context.close()
    finally:
        browser.close()
    assert measured >= 2 * len(
        HEIGHTS
    ), "قِيست أقلُّ من صفحتين لكلّ ارتفاع — الحارسُ يمرّ بلا أن يفحص شيئاً"
    assert not failures, "زرُّ الإجراء الرئيسيّ محجوبٌ خلف تمريرٍ داخليّ:\n  " + "\n  ".join(failures)
