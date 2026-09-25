"""[BUG] SOS-20260922: حصصُ المعلّمين لا تحمَّل إلّا بتحديث الصفحة (Ctrl+Shift+R).

`static/js/page-nav.js` يبدّل `#main-content` يدويّاً (`main.replaceWith(fresh)`) بدل
تحميلٍ كامل — لكنّ هذا التبديل ليس عبر آليّة HTMX الخاصّة بالتبديل، وملفَّ
`static/js/htmx.min.js` المُستخدَم هنا بلا MutationObserver يكتشف عناصر جديدةً من
نفسه. فأيُّ `hx-get`/`hx-trigger` داخل صفحةٍ وصلها المستخدمُ بنقرةٍ (لا بتحميلٍ كامل)
يبقى خرساء — لا يستجيب لتفاعل المستخدم ولا لـ`hx-trigger="load"` — حتى صفحةً تُحمَّل
كاملةً تعيد HTMX بناءَ نفسِه من الصفر. هذا ما رآه المستخدمُ حيّاً: يفتح استمارة
الزيارة الصفّية بنقرةٍ من القائمة، يختار معلّماً، ولا يظهر جدولُه — والتحديثُ الكامل
يُصلحه فوراً، وهو ما دلّ على أنّ العلّة في التبديل اليدويّ لا في الخادم.

الإصلاحُ سطرٌ واحد: `htmx.process(fresh)` فور التبديل — كما توصي وثائقُ HTMX لكلّ
كودٍ يبدّل الـDOM بنفسه. مركزيٌّ في `page-nav.js`، فيُصلح الصفحاتِ الـ26 كلَّها
التي تحمل `hx-get`/`hx-trigger`، لا استمارة الزيارة الصفّية وحدها.
"""

from __future__ import annotations

import datetime as dt

import pytest

pytest.importorskip("pytest_playwright")

from django.urls import reverse  # noqa: E402

from operations.models import Session, Subject  # noqa: E402
from operations.school_days import is_school_day  # noqa: E402
from quality.observation_selectors import default_observation_date  # noqa: E402

pytestmark = pytest.mark.django_db


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


@pytest.fixture
def day(school):
    """اليومُ الذي تفتح عليه الاستمارةُ افتراضيّاً: أقربُ يومِ دراسةٍ للخلف من اليوم.

    كان التاريخُ مثبَّتاً (`dt.date(2026, 9, 20)`) — فلا يمرّ الاختبارُ إلّا في ذلك اليوم نفسِه، وفيما
    عداه تفتح الاستمارةُ على تاريخٍ لا حصّةَ فيه فيُهلَك الانتظارُ عند `[data-period="1"]`. ولم يظهر ذلك
    حتّى صار يُشغَّل معزولاً في Nightly (2026-09-25) فسقط أوّلَ تشغيل. فتُزرع الحصّةُ في التاريخ الذي
    تحسبه الاستمارةُ نفسُه بالدالّة نفسِها، لا في تاريخٍ يُفترض أنّه سيوافقها.
    """
    picked = default_observation_date(school)
    if not is_school_day(school, picked):
        pytest.skip("لا يومَ دراسةٍ في آخر 14 يوماً (إجازةٌ طويلة) — الاستمارةُ تفتح على تاريخٍ بلا حصص")
    return picked


@pytest.fixture
def a_session(school, class_group, teacher_user, subject, day):
    return Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher_user,
        subject=subject,
        date=day,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )


def test_a_link_click_navigation_still_wires_up_htmx_on_the_swapped_content(
    browser, live_server, principal_user, teacher_user, a_session
):
    """النقلةُ الحرجة: الوصولُ للاستمارة بنقرةٍ (لا `page.goto` مباشرةً على رابطها)،
    فيمرّ التبديلُ فعلاً عبر `page-nav.js` كما يفعله متصفّحُ المستخدم الحقيقيّ."""
    base = live_server.url
    context = browser.new_context()
    page = context.new_page()
    try:
        page.goto(f"{base}/auth/login/")
        page.fill('input[name="identifier"]', principal_user.national_id)
        page.fill('input[name="password"]', "testpass123")  # pragma: allowlist secret
        page.click('button[type="submit"]')
        page.wait_for_load_state("networkidle")

        # وصولٌ بنقرةٍ حقيقيّة — الطريقُ الوحيدُ الذي يُشغّل `page-nav.js` فعلاً.
        page.goto(f"{base}{reverse('observation_list')}")
        with page.expect_response(
            lambda r: "observation_teacher_schedule" in r.url or "teacher-schedule" in r.url
        ):
            page.click('a[href="{}"]'.format(reverse("observation_create")))

        # `hx-trigger="load"` على الحقل المخفيّ يجب أن يكون قد جلب الجدولَ فور
        # التبديل، بلا أيّ تفاعلٍ من المستخدم — هذا بعينه ما كان معطوباً.
        teacher_field = page.locator("#qobs-teacher")
        teacher_field.evaluate(
            "(el, v) => { el.value = v; el.dispatchEvent(new Event('change', {bubbles: true})); }",
            str(teacher_user.id),
        )
        page.wait_for_selector('[data-period="1"]', timeout=5000)
        assert "الرياضيات" in page.locator("#teacher-schedule-row").inner_text()
    finally:
        context.close()
