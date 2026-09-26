"""[BEHAVIOR] شاشةُ تسجيل المخالفة: قائمتا الصفّ والشعبة تحصران قائمةَ الطالب وبحثَها (بلاغ المالك 2026-09-26).

كانت الشاشةُ تعرض كلَّ طلبة المدرسة (أو الجناح) في قائمةٍ يُبحث فيها بالاسم وحده. فأُضيفت قائمتان منسدلتان — الصفُّ
والشعبة — في بطاقة «بيانات المخالفة»، وتصفيتُهما في المتصفّح على `data-grade` و`data-section` (القائمةُ مرسومةٌ أصلاً).
وهذا الملفُّ يحرس ما يُشتقّ في الخادم: أيُّ صفٍّ وشعبةٍ لكلّ طالب، ومن أيّ قيد، وما يراه كلُّ دور. وسلوكُ السكربت في
`tests/e2e/test_behavior_report_filter.py`.
"""

import pytest
from django.urls import reverse

from behavior.selectors import _section_key, student_picker
from core.academic_calendar import academic_year_for_school
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)
from tests.test_period_register import klass, supervisor, year  # noqa: F401
from tests.test_supervisor_behavior_scope import (  # noqa: F401 — أجهزةُ الجناح والمشرف نفسُها
    far_klass,
    mine,
    principal,
    theirs,
)

pytestmark = pytest.mark.django_db

REPORT = "behavior:report_infraction"


@pytest.fixture
def now_year(school):
    return academic_year_for_school(school)


def _student(school, name, *, group=None, year=None, grade="G7", section="1", active=True):
    """طالبٌ بقيدٍ في شعبةٍ من العام المذكور (أو بلا قيدٍ إن لم يُعطَ `group` ولا `year`)."""
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    if group is None and year is not None:
        group = ClassGroupFactory(
            school=school, grade=grade, section=section, level_type="prep", academic_year=year
        )
    if group is not None:
        StudentEnrollmentFactory(student=user, class_group=group, is_active=active)
    return user


def _picker(client_as, user):
    response = client_as(user).get(reverse(REPORT))
    assert response.status_code == 200
    return response, response.context


def _by_name(ctx):
    return {s.full_name: s for s in ctx["students"]}


# ── الخياراتُ من طلبة النطاق ────────────────────────────────────────────


def test_the_grades_and_sections_come_from_the_students_of_the_school(
    client_as, school, principal, now_year
):
    _student(school, "س1", year=now_year, grade="G7", section="1")
    _student(school, "س2", year=now_year, grade="G7", section="2")
    _student(school, "س3", year=now_year, grade="G9", section="1")

    _response, ctx = _picker(client_as, principal)

    assert ctx["grade_options"] == [("G7", "الصف السابع"), ("G9", "الصف التاسع")]
    assert ctx["sections_by_grade"] == {"G7": ["1", "2"], "G9": ["1"]}
    assert ctx["all_sections"] == ["1", "2"]


def test_a_grade_nobody_is_enrolled_in_is_not_offered(client_as, school, principal, now_year):
    _student(school, "س1", year=now_year, grade="G8", section="3")

    _response, ctx = _picker(client_as, principal)

    assert [code for code, _label in ctx["grade_options"]] == ["G8"]


def test_the_grades_keep_the_official_order_not_the_alphabetical_one(
    client_as, school, principal, now_year
):
    for grade in ("G12", "G7", "G10", "G9"):
        _student(school, f"طالب {grade}", year=now_year, grade=grade, section="1")

    _response, ctx = _picker(client_as, principal)

    assert [code for code, _label in ctx["grade_options"]] == ["G7", "G9", "G10", "G12"]


def test_sections_sort_by_number_then_letters():
    assert sorted(["10", "2", "ESE", "1", "أ"], key=_section_key) == ["1", "2", "10", "ESE", "أ"]


# ── صفُّ الطالب وشعبتُه الحاليّان ─────────────────────────────────────────


def test_each_student_carries_his_current_grade_and_section(client_as, school, principal, now_year):
    _student(school, "طالبُ السابع", year=now_year, grade="G7", section="2")

    response, ctx = _picker(client_as, principal)

    student = _by_name(ctx)["طالبُ السابع"]
    assert (student.pick_grade, student.pick_section) == ("G7", "2")
    html = response.content.decode()
    assert f'data-id="{student.pk}"' in html
    assert 'data-grade="G7" data-section="2"' in html


def test_a_stale_active_enrollment_does_not_put_a_student_in_a_class_he_left(
    client_as, school, principal, now_year
):
    """قيدُ العام الماضي لا يُغلق دائماً (قِيس على بيانات المدرسة): الحاليُّ من العام الجاري وحدَه."""
    student = _student(school, "منتقل", year="2024-2025", grade="G7", section="1")
    current = ClassGroupFactory(
        school=school, grade="G8", section="4", level_type="prep", academic_year=now_year
    )
    StudentEnrollmentFactory(student=student, class_group=current, is_active=True)

    _response, ctx = _picker(client_as, principal)

    assert (_by_name(ctx)["منتقل"].pick_grade, _by_name(ctx)["منتقل"].pick_section) == ("G8", "4")
    assert ctx["sections_by_grade"] == {"G8": ["4"]}, "شعبةُ العام الماضي لا تُعرض"


def test_an_inactive_enrollment_is_not_a_class(client_as, school, principal, now_year):
    _student(school, "قيدٌ مُغلَق", year=now_year, grade="G7", section="1", active=False)

    _response, ctx = _picker(client_as, principal)

    assert _by_name(ctx)["قيدٌ مُغلَق"].pick_grade == ""


def test_a_student_without_a_current_class_stays_in_the_list_but_under_no_filter(
    client_as, school, principal, now_year
):
    _student(school, "بلا شعبة")  # لا قيدَ أصلاً

    response, ctx = _picker(client_as, principal)

    assert _by_name(ctx)["بلا شعبة"].pick_grade == ""
    assert 'data-grade="" data-section=""' in response.content.decode()
    assert ctx["grade_options"] == [], "لا يُعرض صفٌّ ليس فيه طالبٌ بقيدٍ حاليّ"


def test_an_enrollment_in_another_schools_class_is_not_a_class_here(
    client_as, school, principal, now_year
):
    """قيدٌ (شاذّ) في شعبةٍ من مدرسةٍ أخرى لا يضع طالبَ هذه المدرسة في صفٍّ ولا يُظهر شعبتَه في الخيارات."""
    other = ClassGroupFactory(grade="G9", section="7", level_type="prep", academic_year=now_year)
    _student(school, "س1", year=now_year, grade="G7", section="1")
    stray = _student(school, "قيدُه في مدرسةٍ أخرى")
    StudentEnrollmentFactory(student=stray, class_group=other)

    _response, ctx = _picker(client_as, principal)

    assert _by_name(ctx)["قيدُه في مدرسةٍ أخرى"].pick_grade == ""
    assert ctx["sections_by_grade"] == {"G7": ["1"]}


def test_the_enrollment_query_does_not_grow_with_the_students(school, now_year):
    """قراءةٌ واحدةٌ للقيود مهما كثر الطلبة (لا استعلامَ لكلّ طالب)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    people = [_student(school, f"طالب {i}", year=now_year, section=str(i)) for i in range(6)]

    def queries(batch):
        with CaptureQueriesContext(connection) as captured:
            student_picker(batch, school)
        return len(captured)

    assert queries(people[:1]) == queries(people)


# ── النطاقُ يحكم الخيارات ────────────────────────────────────────────────


def test_a_wing_supervisor_is_offered_only_his_wings_grade_and_section(
    client_as,
    school,
    seeded_calendar,
    mine,
    theirs,
    supervisor,
    far_klass,  # noqa: F811
):
    """جناحُه G7/1 وجناحُ الآخر G8/2: لا يرى المشرفُ صفّاً ولا شعبةً ولا طالباً ليست من جناحه."""
    _response, ctx = _picker(client_as, supervisor)

    assert [s.full_name for s in ctx["students"]] == ["طالبُ جناحي"]
    assert ctx["grade_options"] == [("G7", "الصف السابع")]
    assert ctx["sections_by_grade"] == {"G7": ["1"]}


def test_the_principal_is_offered_both_wings(
    client_as,
    school,
    seeded_calendar,
    mine,
    theirs,
    principal,
    far_klass,  # noqa: F811
):
    _response, ctx = _picker(client_as, principal)

    assert {code for code, _label in ctx["grade_options"]} == {"G7", "G8"}


# ── الشاشةُ ──────────────────────────────────────────────────────────────


def test_the_card_offers_the_two_selects_above_the_student_and_posts_neither(
    client_as, school, principal, now_year
):
    _student(school, "س1", year=now_year, grade="G7", section="1")

    html = client_as(principal).get(reverse(REPORT)).content.decode()

    grade_at = html.index('id="classGradeSelect"')
    section_at = html.index('id="classSectionSelect"')
    student_at = html.index('id="studentSearchInput"')
    assert grade_at < section_at < student_at, "الصفُّ فالشعبةُ فالطالب"
    for select_id in ("classGradeSelect", "classSectionSelect"):
        tag = html[html.rindex("<select", 0, html.index(f'id="{select_id}"')) :]
        assert "name=" not in tag.split(">", 1)[0], "واجهةٌ فقط — لا تُرسَل مع النموذج"
    assert 'id="sectionsByGrade"' in html
    assert 'id="studentEmpty"' in html, "سطرُ «لا طالب مطابق»"
    assert "كل الصفوف" in html and "كل الشُّعب" in html


def test_registering_still_takes_the_student_id_alone(client_as, school, principal, now_year):
    """التصفيةُ عرضٌ: النموذجُ يبقى `student_id` وحدَه كما كان."""
    from behavior.models import BehaviorInfraction

    student = _student(school, "س1", year=now_year, grade="G7", section="1")

    response = client_as(principal).post(
        reverse(REPORT),
        {
            "student_id": str(student.pk),
            "level": 1,
            "description": "إزعاجٌ في الممرّ",
            "disciplinary_action_type": "verbal_warning",
        },
    )

    assert response.status_code == 302
    assert BehaviorInfraction.objects.filter(student=student).count() == 1
