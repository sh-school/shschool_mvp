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
