"""[A11Y] حارسُ axe-core الحيّ — راجع `tests/a11y_axe_ratchet.py` للسبب والطريقة.

تسجيلُ الدخول عبر متصفّحٍ حقيقيّ لا عميل Django — حقلُ الهويّة اسمُه `identifier`
(الرقم الوظيفي أو الشخصي)، لا `national_id` كما كان في `tests/e2e/conftest.py`
القديم (كان يفشل صامتاً: `pytest-playwright` نفسُه لم يكن مثبَّتاً فلا يُجمَع
الملفُّ أصلاً — أُصلح الاثنان معاً هنا).

`axe-playwright-python` مثبَّتٌ في وظيفة `axe-a11y` في CI وحدها (`quality-gate.yml`)
— لا في `pytest — تغطية` التي تجمع `tests/` كلَّه بحزمٍ أخفّ. فغيابُ الحزمة هناك
تخطٍّ متوقَّعٌ لا خطأَ استيراد.
"""

from __future__ import annotations

import os

import pytest

pytest.importorskip("axe_playwright_python")

from tests import a11y_axe_ratchet as ratchet  # noqa: E402
from tests.test_a11y_live_pages import EVALUATION_PAGES, PAGES, _evaluation_case, _url  # noqa: E402

pytestmark = pytest.mark.django_db

UPDATE_CMD = (
    "AXE_UPDATE=1 pytest tests/test_a11y_axe_ratchet.py::test_axe_violations_have_not_grown"
)


def _login(page, live_server, user, password="testpass123"):  # pragma: allowlist secret
    # مستخدمٌ سابقٌ ما زال داخلاً: صفحةُ الدخول تحوّله إلى اللوحة فلا يجد `fill` الحقلَ (انتهت مهلتُه 30 ثانية).
    page.context.clear_cookies()
    page.goto(f"{live_server.url}/auth/login/")
    page.fill('input[name="identifier"]', user.national_id)
    page.fill('input[name="password"]', password)
    page.click('button[type="submit"]')
    page.wait_for_load_state("networkidle")


#: صفحاتُ تقييم الأداء تُقاس على عامٍ ثابتٍ تُنشأ عليه بياناتُها (`_seed_evaluations`)، لا على عامٍ يشتقّه الطلب.
EVALUATION_YEAR = "2026-2027"


def _target(name: str) -> str:
    query = f"?year={EVALUATION_YEAR}" if name.startswith("evaluation_") else ""
    return f"{_url(name)}{query}"


def _seed_evaluations(request) -> None:
    """
    حقولُ التظلّم (سببُ التظلّم؛ قرارُ اللجنة وتاريخاه) لا تُرسم إلّا ببيانات: تقريرٌ بابُ تظلّمه مفتوحٌ
    لحساب المعلّم في «تقييماتي»، وآخرُ قُدِّم تظلّمُه لشاشة المدير — وإلّا قِيست صفحاتٌ فارغةٌ.
    """
    from tests.test_evaluation_review_round1 import _staff

    school = request.getfixturevalue("school")
    principal = request.getfixturevalue("principal_user")
    _evaluation_case(school, request.getfixturevalue("teacher_user"), principal)
    _evaluation_case(school, _staff(school, "teacher", "زميل"), principal, grievance=True)


def _measure_all(request, page, live_server) -> dict[str, dict[str, int]]:
    """
    كلُّ صفحات `PAGES` ثمّ صفحاتِ التقييم. يُسجَّل الدخولُ عند كلّ تبديلِ حساب، **بعد مسح الكوكيز**:
    الدخولُ وهو مسجَّلٌ يُحيل صفحةَ الدخول إلى اللوحة فينتظر `page.fill` حقلاً لا وجودَ له (سقط CI بذلك).
    """
    results: dict[str, dict[str, int]] = {}
    logged_in_as = None
    for name, who in [*PAGES, *EVALUATION_PAGES]:
        user = request.getfixturevalue(who)
        if logged_in_as != who:
            page.context.clear_cookies()
            _login(page, live_server, user)
            logged_in_as = who
        page.goto(f"{live_server.url}{_target(name)}")
        page.wait_for_load_state("networkidle")
        counts = ratchet.measure_page(page)
        if counts:
            results[name] = counts
    return results


def test_axe_violations_have_not_grown(request, page, live_server, school_bus, library_book):
    _seed_evaluations(request)
    current = _measure_all(request, page, live_server)

    if os.environ.get("AXE_UPDATE"):
        ratchet.write_baseline(current)
        for rule, n in ratchet.totals(current).items():
            print(f"{rule}: {n}")
        pytest.skip("حُدِّث الخطّ الأساس — راجع tests/a11y_axe_ratchet_baseline.json وأودعه")

    baseline = ratchet.read_baseline()
    worse, stale = ratchet.compare(baseline, current)
    assert not worse, "زادت مخالفاتُ axe-core — لا تُودَع:\n  " + "\n  ".join(worse)
    assert not stale, (
        f"نقصت مخالفاتٌ ولم يُسجَّل نقصُها — أحسنت؛ ثبّته بـ `{UPDATE_CMD}` وأودع الملفّ:\n  "
        + "\n  ".join(stale)
    )


#: صفحاتُ إدارةٍ تجمع أدواتِ جانغو التي تُرسم بلا اسمٍ يقرؤه قارئُ الشاشة (OWN-21): حقولُ التحرير داخل القائمة
#: (الأقسام، العضويّات)، وشقّا التاريخ والوقت والجدولُ المضمَّن (المستخدم)، والاختيارُ بين قائمتين (المجموعات)،
#: وselect2 (باقاتُ التقييم). يسمّيها `static/js/admin_a11y.js` — كانت 620 عقدةً على 237 صفحةَ إدارة.
def _admin_pages(teacher) -> list[str]:
    return [
        "/admin/core/department/",
        "/admin/core/membership/",
        f"/admin/core/customuser/{teacher.pk}/change/",
        "/admin/auth/group/add/",
        "/admin/assessments/assessmentpackage/add/",
        # مسحُ الإدارة كلِّها (OWN-21، 2026-09-25) وجد فئاتٍ لم تُغطَّ: صفحةُ الخطأ 403 لنموذجٍ بلا إضافة (تباينُ زرّ
        # الرجوع)، وقائمةٌ فيها رابطُ «أظهر الكل» داخل نصّ (يميّزه اللونُ وحدَه). والمسحُ الكامل: tests/e2e/test_admin_sweep.py.
        "/admin/axes/accessattempt/add/",
        "/admin/roadmap/roadmapitem/",
    ]


def test_the_command_center_has_no_axe_violations_in_any_state_or_theme(
    page, live_server, developer_user
):
    """QCC-01b: الصفحةُ في المنصّة — نهاراً وليلاً وبكلّ حالةٍ (سليم وانتبه وخطر وغيرُ معلوم): التباينُ خصوصاً."""
    from command_center import contract

    contract.store("production", {"status": "ok", "headline": "سليم", "detail": "تفصيلٌ قصير"})
    contract.store("ci", {"status": "warn", "headline": "انتبه", "detail": "تفصيلٌ قصير"})
    contract.store("guards", {"status": "bad", "headline": "خطر", "detail": "تفصيلٌ قصير"})
    _login(page, live_server, developer_user)  # «roadmap» و«pulls» تبقيان غيرَ معلومتين

    found = {}
    for theme in ("light", "dark"):
        page.goto(f"{live_server.url}/command-center/")
        page.evaluate(f"localStorage.setItem('theme', '{theme}')")
        page.reload()
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(300)  # الاستطلاعُ الأوّل يعيد رسمَ اللوحات من اللقطة
        counts = ratchet.measure_page(page)
        if counts:
            found[theme] = counts

    assert not found, f"مخالفاتُ axe في مركز قيادة الجودة (راجع .qc-* في 33-modules-4.css): {found}"


def test_the_command_center_does_not_overflow_on_a_phone_or_a_laptop(
    page, live_server, developer_user
):
    """QCC-01b: لا تجاوزَ أفقيّاً بعرض 375 (جوّال) ولا 1366 (لابتوب) — ولا هدفَ لمسٍ دون 44px على الجوّال (أيقونةُ التلميح `.ui-tip__btn` خارجةٌ: مكوّنٌ مركزيٌّ يُرفع بـ`pointer: coarse`)."""
    _login(page, live_server, developer_user)

    found, small = {}, []
    for width, height in ((375, 812), (1366, 768)):
        page.set_viewport_size({"width": width, "height": height})
        page.goto(f"{live_server.url}/command-center/")
        page.wait_for_load_state("networkidle")
        over = page.evaluate(
            "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
        )
        if over > 0:
            found[width] = over
        if width == 375:
            small = page.evaluate(
                "() => [...document.querySelectorAll('#main-content button:not(.ui-tip__btn), #main-content a')]"
                ".filter(e => e.offsetParent !== null && e.getBoundingClientRect().height < 44)"
                ".map(e => e.textContent.trim().slice(0, 20))"
            )

    assert not found, f"تجاوزٌ أفقيٌّ في مركز قيادة الجودة (بكسل): {found}"
    assert not small, f"أهدافُ لمسٍ دون 44px على الجوّال: {small}"


def test_the_admin_widgets_have_accessible_names(
    page, live_server, school, developer_user, teacher_user
):
    """لا سقّاطةَ هنا بل صفر: كلُّ مخالفات هذه الصفحات من أدوات جانغو، وقد سُمّيت كلُّها."""
    from core.models import Department

    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.save()
    Department.objects.create(school=school, name="الرياضيات", code="math")
    _login(page, live_server, developer_user)

    found = {}
    for path in _admin_pages(teacher_user):
        page.goto(f"{live_server.url}{path}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)  # select2 والاختيارُ بين قائمتين يُنشآن بعد التحميل ثمّ يُسمَّيان
        counts = ratchet.measure_page(page)
        if counts:
            found[path] = counts

    assert not found, f"مخالفاتُ axe في صفحات الإدارة (راجع static/js/admin_a11y.js): {found}"


def test_the_admin_image_alternatives_are_arabic(page, live_server, developer_user, teacher_user):
    """axe لا يحكم على لغة النصّ البديل: أيقونةُ القيمة المنطقيّة تقول «True» وحقلُ البحث «Search» بلا هذا الحارس."""
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.save()
    _login(page, live_server, developer_user)

    page.goto(f"{live_server.url}/admin/core/customuser/")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(200)
    assert page.locator('img[alt="True"], img[alt="False"], img[alt="None"]').count() == 0
    assert (
        page.locator('td.field-is_active img[alt="نعم"]').count() >= 1
    )  # عمود «حساب نشط» يعرض أيقونةً

    page.goto(f"{live_server.url}/admin/auth/group/")
    page.wait_for_load_state("networkidle")
    page.wait_for_timeout(200)
    assert page.locator('label[for="searchbar"] img').get_attribute("alt") == "بحث"


class TestTheRatchetItself:
    """الحارسُ يحرس ما يقول إنّه يحرسه — منطقُ المقارنة لا يحتاج متصفّحاً لاختباره."""

    def test_a_new_violation_on_a_known_page_is_worse(self):
        before = {"ui_components": {"scrollable-region-focusable": 1}}
        after = {"ui_components": {"scrollable-region-focusable": 2}}
        worse, stale = ratchet.compare(before, after)
        assert len(worse) == 1 and not stale

    def test_a_new_page_with_a_violation_is_worse(self):
        before: dict = {}
        after = {"new_page": {"image-alt": 1}}
        worse, _ = ratchet.compare(before, after)
        assert worse and "new_page" in worse[0]

    def test_a_fixed_violation_must_be_recorded(self):
        before = {"ui_components": {"scrollable-region-focusable": 1}}
        after = {"ui_components": {}}
        worse, stale = ratchet.compare(before, after)
        assert not worse and len(stale) == 1

    def test_totals_sum_across_pages(self):
        data = {"a": {"rule1": 2}, "b": {"rule1": 1, "rule2": 3}}
        assert ratchet.totals(data) == {"rule1": 3, "rule2": 3}


#: كلُّ هدفِ لمسٍ مرئيٍّ عرضُه أو ارتفاعُه دون الحدّ — كتعريف `mobile_audit.py` (`small44`). ما يُستثنى ليس هدفاً:
#: رابطُ «تخطَّ إلى المحتوى» يُرى بالتركيز وحدَه، والعنصرُ المخفيُّ بصريّاً، ومصدرُ select2 الأصليُّ (يُستبدل بصندوقه).
SMALL_TARGETS_JS = """(min) => [...document.querySelectorAll(
  'a[href], button, input:not([type=hidden]):not([type=checkbox]):not([type=radio]), select, textarea, [role=button], summary')]
  .filter(e => {
    const r = e.getBoundingClientRect();
    if (r.width <= 1 || r.height <= 1 || getComputedStyle(e).visibility === 'hidden') return false;
    if (e.closest('.visually-hidden') || e.classList.contains('skip-to-content-link')) return false;
    if (e.matches('select.select2-hidden-accessible, select.admin-autocomplete')) return false;
    return r.width < min || r.height < min;
  })
  .map(e => e.tagName.toLowerCase() + (e.id ? '#' + e.id : '') + '.' + String(e.className).split(' ')[0]
     + ' ' + Math.round(e.getBoundingClientRect().width) + 'x' + Math.round(e.getBoundingClientRect().height))"""


def test_the_admin_touch_targets_are_44px_on_phones(
    page, live_server, school, developer_user, teacher_user
):
    """OWN-21: قِيس 736 هدفاً دون 44px على ثماني صفحات إدارةٍ بعرض 375؛ القواعدُ في `admin_theme.css` تُصفّرها."""
    from core.models import Department

    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.save()
    Department.objects.create(school=school, name="الرياضيات", code="math")
    page.set_viewport_size({"width": 375, "height": 812})
    _login(page, live_server, developer_user)

    found = {}
    for path in [
        "/admin/",
        "/admin/core/department/",
        "/admin/core/membership/",
        f"/admin/core/customuser/{teacher_user.pk}/change/",
        "/admin/auth/group/add/",
        "/admin/assessments/assessmentpackage/add/",
        # فئاتُ أهدافٍ وجدها مسحُ الإدارة كلِّها (OWN-21): زرُّ صفحة الخطأ 403، وطيّةُ الحقول `summary`، وحقلُ الملفّ،
        # ورابطُ «أظهر الكل» داخل النصّ.
        "/admin/axes/accessattempt/add/",
        "/admin/behavior/behaviorinfraction/add/",
        "/admin/core/school/add/",
        "/admin/roadmap/roadmapitem/",
    ]:
        page.goto(f"{live_server.url}{path}")
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(200)  # select2 والاختيارُ بين قائمتين يُنشآن بعد التحميل
        small = page.evaluate(SMALL_TARGETS_JS, 44)
        if small:
            found[path] = small[:6]

    assert not found, f"أهدافُ لمسٍ دون 44px على الجوّال (راجع admin_theme.css): {found}"
