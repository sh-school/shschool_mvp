"""[LAYOUT] بطاقاتُ الإجراء تسع نصَّها على الهواتف الضيّقة (P3-5).

مسبارٌ على لوحات 21 دوراً وجد أنّ بطاقتَين لدور «فنّي تقنية المعلومات» تفيضان عند 375px:
عمودان يجعلان البطاقةَ 151px، منها 90px مساحةٌ ثابتة (حشو + حدّ + فجوة + أيقونة 42)،
فيبقى للنصّ 61px وكلمةُ «المستخدمين» 78px. وعند 320px يبقى 33px فتفيض الثلاثُ كلُّها.

جُرِّبت خمسةُ علاجاتٍ على ثلاثة عروض: `overflow-wrap:anywhere` يكسر العربيّةَ وسطَها ويضخّم
البطاقةَ (116→143px)؛ تقليلُ الحشو والأيقونة يفشل عند 360 و320؛ إخفاءُ الأيقونة يُصلح
لكنّه يُفقدها؛ **عمودٌ واحدٌ عند ≤400px** يُصلح الكلَّ والبطاقةُ 60px. فهذا الحارسُ يثبّت
الثابتَ لا العلاج: لا نصَّ يفيض خارجَ بطاقته — فلو بدّل أحدٌ العلاجَ بأفضلَ منه مرّ،
ولو ضخّم الأيقونةَ أو الحشوَ فأعاد الفيضانَ سقط.

`pytest-playwright` مثبَّتٌ في وظيفة `axe-a11y` في CI وحدها؛ ويتخطّى الملفُّ نفسَه حيث غاب.
"""

import re

import pytest

pytest.importorskip("pytest_playwright")

from tests.css_source import read_css  # noqa: E402

pytestmark = pytest.mark.django_db

#: العروضُ الضيّقة الشائعة للهواتف: 375 (iPhone)، 360 (أندرويد)، 320 (الأصغر).
WIDTHS = (375, 360, 320)

#: العنصرُ يفيض إن زاد `scrollWidth` عن `clientWidth` — عنوانُ البطاقة ووصفُها وجسمُها.
OVERFLOWING = r"""() => {
  const bad = [];
  for (const card of document.querySelectorAll('.action-card')) {
    const body = card.querySelector('.action-card-body'); if (!body) continue;
    for (const el of [body, ...body.children]) {
      if (el.scrollWidth > el.clientWidth + 1) {
        bad.push({text: el.textContent.trim().replace(/\s+/g, ' ').slice(0, 40), cw: el.clientWidth, sw: el.scrollWidth});
      }
    }
  }
  return {bad, cards: document.querySelectorAll('.action-card').length};
}"""


def test_no_action_card_text_overflows_its_card_on_a_narrow_phone(
    request, browser, live_server, it_technician_user
):
    base = live_server.url
    login = browser.new_context()
    page = login.new_page()
    page.goto(f"{base}/auth/login/")
    page.fill('input[name="identifier"]', it_technician_user.national_id)
    page.fill('input[name="password"]', "testpass123")  # pragma: allowlist secret
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")
    state = login.storage_state()
    login.close()

    failures = []
    for width in WIDTHS:
        context = browser.new_context(storage_state=state, viewport={"width": width, "height": 900})
        try:
            page = context.new_page()
            page.goto(f"{base}/dashboard/")
            page.wait_for_load_state("networkidle")
            result = page.evaluate(OVERFLOWING)
        finally:
            context.close()
        assert result["cards"] >= 2, "لوحةُ هذا الدور لا تعرض بطاقاتِ إجراءٍ — الحارسُ لا يحرس شيئاً"
        failures += [
            f"{width}px: «{item['text']}» {item['sw']}px في {item['cw']}px"
            for item in result["bad"]
        ]
    assert not failures, "نصٌّ يفيض خارجَ بطاقة الإجراء:\n  " + "\n  ".join(failures)


def test_the_single_column_rule_for_narrow_phones_exists():
    """السببُ نفسُه بلا متصفّح: قاعدةُ العمود الواحد ≤400px بعد قاعدة العمودين ≤640px."""
    css = read_css()
    two = css.index("@media (max-width: 640px) { .ui-actions")
    one = re.search(
        r"@media \(max-width: 400px\)\s*\{\s*\.ui-actions\s*\{\s*grid-template-columns:\s*1fr;", css
    )
    assert one, "لا قاعدةَ عمودٍ واحدٍ لـ.ui-actions عند ≤400px — تفيض بطاقاتُ الإجراء عند 375px"
    assert one.start() > two, "قاعدةُ 400px قبل قاعدة 640px فتُبطلها الأخيرةُ (الأحدثُ يغلب)"
