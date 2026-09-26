"""
E2E: شاشةُ تسجيل المخالفة — الصفُّ والشعبةُ يحصران قائمةَ الطالب وبحثَها (بلاغ المالك 2026-09-26).

يحرس سلوكَ السكربت في المتصفّح: اختيارُ الصفّ يحصر الطلبةَ ويحصر الشعبَ في شعبه، واختيارُ الشعبة يحصر أكثر،
والبحثُ بالاسم يجري داخل ما حُصر، وتغييرُ الصفّ بعد اختيار طالبٍ من غيره يمسح اختيارَه، ولا نتيجةَ تُظهر
«لا طالب مطابق». والاشتقاقُ في الخادم: `tests/test_behavior_report_class_filter.py`.
"""

import pytest

pytest.importorskip("pytest_playwright")
from playwright.sync_api import expect  # noqa: E402

from core.academic_calendar import academic_year_for_school  # noqa: E402
from core.models import ClassGroup, CustomUser, Membership, Role, StudentEnrollment  # noqa: E402

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(transaction=True)]

OPTIONS = ".js-student-option"


@pytest.fixture
def roster(e2e_school, e2e_roles):
    """G7/1: أحمد سالم وبدر ناصر · G7/2: أحمد خالد · G8/1: أحمد عمر (الأسماءُ اصطناعيّة)."""
    year = academic_year_for_school(e2e_school)
    role = e2e_roles.get("student") or Role.objects.get(school=e2e_school, name="student")
    plan = [
        ("G7", "1", "أحمد سالم"),
        ("G7", "1", "بدر ناصر"),
        ("G7", "2", "أحمد خالد"),
        ("G8", "1", "أحمد عمر"),
    ]
    for index, (grade, section, name) in enumerate(plan):
        group, _ = ClassGroup.objects.get_or_create(
            school=e2e_school,
            grade=grade,
            section=section,
            academic_year=year,
            defaults={"level_type": "prep"},
        )
        user = CustomUser.objects.create_user(
            national_id=f"9990001{index:04d}", full_name=name, password="TestPass123!"
        )
        Membership.objects.create(user=user, school=e2e_school, role=role)
        StudentEnrollment.objects.create(student=user, class_group=group, is_active=True)


def _visible_names(page):
    return [node.inner_text().strip() for node in page.locator(f"{OPTIONS}:not([hidden])").all()]


def _open_picker(page, live_server):
    page.goto(f"{live_server.url}/behavior/report/")
    page.wait_for_load_state("networkidle")
    page.click("#studentSearchInput")


def _section_values(page):
    return page.eval_on_selector_all(
        "#classSectionSelect option", "options => options.map(o => o.value)"
    )


def test_the_grade_narrows_the_students_and_the_sections(principal_page, live_server, roster):
    page = principal_page
    _open_picker(page, live_server)

    assert len(_visible_names(page)) == 4
    assert _section_values(page) == ["", "1", "2"], "بلا صفٍّ: كلُّ الشعب"

    page.select_option("#classGradeSelect", "G8")

    assert _visible_names(page) == ["أحمد عمر"]
    assert _section_values(page) == ["", "1"], "شُعبُ الثامن وحدَها"


def test_the_section_narrows_further_and_the_name_search_works_inside(
    principal_page, live_server, roster
):
    page = principal_page
    _open_picker(page, live_server)
    page.select_option("#classGradeSelect", "G7")

    assert sorted(_visible_names(page)) == ["أحمد خالد", "أحمد سالم", "بدر ناصر"]

    page.select_option("#classSectionSelect", "1")
    assert sorted(_visible_names(page)) == ["أحمد سالم", "بدر ناصر"]

    page.fill("#studentSearchInput", "أحمد")
    assert _visible_names(page) == ["أحمد سالم"], "البحثُ داخل الصفّ والشعبة — لا «أحمد» من غيرهما"


def test_a_section_without_a_grade_narrows_across_grades(principal_page, live_server, roster):
    page = principal_page
    _open_picker(page, live_server)

    page.select_option("#classSectionSelect", "1")

    assert sorted(_visible_names(page)) == ["أحمد سالم", "أحمد عمر", "بدر ناصر"]


def test_changing_the_grade_clears_a_student_who_no_longer_matches(
    principal_page, live_server, roster
):
    page = principal_page
    _open_picker(page, live_server)
    page.locator(f"{OPTIONS}", has_text="أحمد سالم").click()

    assert page.input_value("#studentSelect") != ""

    page.select_option("#classGradeSelect", "G8")

    assert page.input_value("#studentSelect") == "", "لا يُسجَّل على طالبٍ لا تراه القائمة"
    assert page.input_value("#studentSearchInput") == ""


def test_a_student_who_still_matches_keeps_the_choice(principal_page, live_server, roster):
    page = principal_page
    _open_picker(page, live_server)
    page.locator(f"{OPTIONS}", has_text="أحمد سالم").click()
    chosen = page.input_value("#studentSelect")

    page.select_option("#classGradeSelect", "G7")

    assert page.input_value("#studentSelect") == chosen


def test_no_match_says_so_and_clearing_the_filters_restores_the_list(
    principal_page, live_server, roster
):
    page = principal_page
    _open_picker(page, live_server)
    page.select_option("#classGradeSelect", "G8")

    page.fill("#studentSearchInput", "بدر")
    expect(page.locator("#studentEmpty")).to_be_visible()

    page.fill("#studentSearchInput", "")
    page.select_option("#classGradeSelect", "")
    page.select_option("#classSectionSelect", "")

    assert len(_visible_names(page)) == 4
    expect(page.locator("#studentEmpty")).to_be_hidden()


def test_the_selected_student_is_what_the_form_posts(principal_page, live_server, roster):
    page = principal_page
    _open_picker(page, live_server)
    page.select_option("#classGradeSelect", "G7")
    page.select_option("#classSectionSelect", "2")
    page.locator(f"{OPTIONS}", has_text="أحمد خالد").click()

    selected = page.eval_on_selector(
        "#studentSelect", "select => select.selectedOptions[0].textContent.trim()"
    )
    assert selected == "أحمد خالد"
    # الصفُّ والشعبةُ واجهةٌ فقط: لا حقلَ لهما في النموذج المُرسَل
    posted = page.eval_on_selector_all(
        "form[method=post] [name]", "nodes => nodes.map(n => n.getAttribute('name'))"
    )
    assert "student_id" in posted
    assert "classGradeSelect" not in posted and "classSectionSelect" not in posted
