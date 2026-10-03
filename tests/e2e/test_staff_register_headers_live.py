"""[DESKTOP] عناوينُ أعمدة سجلّ الموظفين تسع أطولَ كلمةٍ فيها بأيّ عرضٍ (DBT-46).

كان `.staff-register` جدولاً بـ`table-layout: fixed` ونسبٍ مجموعُها 99% وغلافُه `overflow-x: hidden`: فدون 1000px تضيق الأعمدةُ
عن عناوينها — 9 من 12 عند 641px و8 عند 768 و5 عند 900 — وتُقصّ الكلماتُ بلا مهربٍ ولا شريط. والعلاجُ حدٌّ أدنى لعرض الجدول
دون 1024px (`50-utilities.css`) يُمرَّر داخل غلافه، فتبقى العناوينُ كاملةً ولا تفيض الصفحةُ (D2).

القياسُ على المتصفّح لأنّ ما يُقاس عرضٌ مرسومٌ لا نصُّ CSS: أضيقُ عمودٍ يُقاس مقابل أطولِ كلمةٍ في عنوانه بخطّه الفعليّ.
"""

from __future__ import annotations

import pytest

pytest.importorskip("pytest_playwright")

from tests.test_a11y_live_pages import _url  # noqa: E402
from tests.test_mobile_audit import _signed_in_state  # noqa: E402

pytestmark = pytest.mark.django_db

#: العروضُ التي كانت تُضيّق العناوين (641–900) وحدُّها (1000) وما فوقه لا يجوز أن يتراجع.
WIDTHS = (375, 641, 700, 768, 820, 900, 1000, 1024, 1280, 1366)

#: حتّى هذا العرض (≤ 640px، فئةُ compact) يحلّ البطاقاتُ محلَّ الجدول — انظر 50-utilities.css.
PHONE_MAX = 640

#: بطاقاتُ الجوال: ظاهرةٌ والجدولُ مخفيّ، لا اسمَ يلتفّ (سطرٌ واحد)، ولا فيضَ أفقيّاً للمستند.
CARD_MEASURE = """
() => {
  const table = document.querySelector('.staff-register');
  const wrap = table && table.closest('.table-wrap-scroll');
  const cards = [...document.querySelectorAll('.staff-card')];
  const wrappedNames = cards.map((c) => c.querySelector('.staff-card__name')).filter((a) => {
    const line = parseFloat(getComputedStyle(a).lineHeight) || 20;
    return a.getBoundingClientRect().height > line * 1.6;
  }).map((a) => a.textContent.trim());
  return {
    cards: cards.length,
    tableHidden: !wrap || getComputedStyle(wrap).display === 'none',
    wrappedNames,
    overflow: document.documentElement.scrollWidth - window.innerWidth,
  };
}
"""

#: لكلّ عنوانٍ: العرضُ المتاحُ لنصّه (دون الحشو) وعرضُ أطولِ كلمةٍ فيه بخطّه؛ ثمّ فيضُ المستند الأفقيّ.
MEASURE = """
() => {
  const table = document.querySelector('.staff-register');
  const narrow = [];
  for (const th of table.querySelectorAll('thead th')) {
    const style = getComputedStyle(th);
    const text = th.innerText.replace(/\\s+/g, ' ').trim();
    let widest = 0;
    for (const word of text.split(' ')) {
      if (!word) continue;
      const probe = document.createElement('span');
      probe.textContent = word;
      probe.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:' + style.font + ';letter-spacing:' + style.letterSpacing;
      document.body.appendChild(probe);
      widest = Math.max(widest, probe.getBoundingClientRect().width);
      probe.remove();
    }
    const room = th.clientWidth - parseFloat(style.paddingInlineStart) - parseFloat(style.paddingInlineEnd);
    if (room + 0.5 < widest) narrow.push(text + ' (' + Math.round(room) + ' < ' + Math.round(widest) + ')');
  }
  return {
    columns: table.querySelectorAll('thead th').length,
    narrow,
    overflow: document.documentElement.scrollWidth - window.innerWidth,
  };
}
"""


def test_staff_register_headers_fit_their_longest_word_at_every_width(
    request, playwright, live_server, principal_user
):
    browser = playwright.chromium.launch()
    try:
        state = _signed_in_state(browser, live_server.url, principal_user)
        context = browser.new_context(storage_state=state, locale="ar")
        try:
            page = context.new_page()
            page.set_viewport_size({"width": 1366, "height": 900})
            response = page.goto(
                f"{live_server.url}{_url('staff_affairs:staff_list')}", wait_until="load"
            )
            assert response and response.ok, response and response.status
            assert page.locator(".staff-register").count() == 1, "الجدولُ لم يُرسم — لا صفَّ في السجلّ"
            page.evaluate("document.fonts.ready.then(() => 1)")
            failures = []
            for width in WIDTHS:
                page.set_viewport_size({"width": width, "height": 900})
                page.wait_for_timeout(80)
                if width <= PHONE_MAX:
                    # الجوال: بطاقةٌ لكلّ منتسب والجدولُ مخفيّ (W-20261002-044) — فلا عناوينَ تُقاس؛
                    # يُقاس أنّ البطاقات تُرسم وأنّ الصفحةَ لا تفيض أفقيّاً ولا اسمَ يلتفّ.
                    cards = page.evaluate(CARD_MEASURE)
                    if not cards["tableHidden"]:
                        failures.append(f"{width}px: الجدولُ ظاهرٌ على الجوال (يجب البطاقات)")
                    if not cards["cards"]:
                        failures.append(f"{width}px: لا بطاقاتٍ على الجوال")
                    if cards["wrappedNames"]:
                        failures.append(
                            f"{width}px: أسماءٌ تلتفّ في البطاقات — {cards['wrappedNames'][:5]}"
                        )
                    if cards["overflow"] > 0:
                        failures.append(f"{width}px: تفيض الصفحةُ أفقيّاً {cards['overflow']}px (D2)")
                    continue
                result = page.evaluate(MEASURE)
                assert result["columns"] >= 9, result  # تسعةٌ بعد دمج الأعمدة (W-20261002-044)
                if result["narrow"]:
                    failures.append(
                        f"{width}px: {len(result['narrow'])} عنواناً أضيقُ من أطول كلمةٍ — {result['narrow']}"
                    )
                if result["overflow"] > 0:
                    failures.append(f"{width}px: تفيض الصفحةُ أفقيّاً {result['overflow']}px (D2)")
        finally:
            context.close()
    finally:
        browser.close()
    assert not failures, "\n".join(failures)


#: اسمُ المنتسب سطرٌ واحدٌ دائماً (W-20261002-044): كلُّ اسمٍ ارتفاعُه سطرٌ لا سطران.
NAME_LINES = """
() => [...document.querySelectorAll('.staff-register a.staff-name')].filter((a) => {
  const line = parseFloat(getComputedStyle(a).lineHeight) || 20;
  return a.getBoundingClientRect().height > line * 1.6;
}).map((a) => a.textContent.trim())
"""


def test_staff_names_stay_on_one_line_at_laptop_widths(
    request, playwright, live_server, principal_user
):
    browser = playwright.chromium.launch()
    try:
        state = _signed_in_state(browser, live_server.url, principal_user)
        context = browser.new_context(storage_state=state, locale="ar")
        try:
            page = context.new_page()
            failures = []
            for width in (1280, 1366):
                page.set_viewport_size({"width": width, "height": 768})
                page.goto(f"{live_server.url}{_url('staff_affairs:staff_list')}", wait_until="load")
                page.evaluate("document.fonts.ready.then(() => 1)")
                wrapped = page.evaluate(NAME_LINES)
                if wrapped:
                    failures.append(
                        f"{width}px: {len(wrapped)} اسماً التفّت على سطرين — {wrapped[:5]}"
                    )
        finally:
            context.close()
    finally:
        browser.close()
    assert not failures, "\n".join(failures)
