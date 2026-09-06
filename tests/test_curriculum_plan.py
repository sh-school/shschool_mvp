"""[CURRICULUM] الخطّةُ الدراسيّةُ مصدرَ الطلب — وقياسُ الإسناد عليها.

الثوابتُ التي تحرسها هذه الاختبارات:

    CurriculumDemand ≠ ObservedAssignment
    InstructionalPeriods ≠ StudentPeriods
    ExpectedTotal(scope) = ∑ Mandatory + ∑ max(ElectiveGroup)

وأخطرُها الثاني: بديلا الاختياريّ المتوازيان في الشعبة الواحدة يُجدولان أربعَ
حصص ويأخذ الطالبُ اثنتين. فمن جمعهما ظنّ الشعبةَ فائضةً وهي مضبوطة، وطالبَ
المدرسةَ بحذفِ ما لا يجوز حذفُه.
"""

import pytest
from django.core.exceptions import ValidationError
from django.db.utils import IntegrityError

from academic_management import curriculum_service as cs
from academic_management.models import (
    FROM_MINISTRY_GUIDE,
    FROM_PILOT,
    CurriculumPlan,
)

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
GUIDE = "دليل الخطط الدراسية 2025-2026 ص14"


# ── تجهيز ────────────────────────────────────────────────────────────


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة الشحانية", code="SHH-C")


@pytest.fixture
def subjects(db, school):
    from operations.models import Subject

    return {
        code: Subject.objects.create(school=school, name_ar=name, code=code)
        for code, name in (
            ("MAT", "الرياضيات"),
            ("SCI", "العلوم"),
            ("ART", "الفنون البصرية"),
            ("CHM", "الكيمياء"),
        )
    }


def section(school, grade="G7", name="1", *, track="", own_timetable=False):
    from core.models import ClassGroup

    return ClassGroup.objects.create(
        school=school,
        grade=grade,
        section=name,
        level_type="prep" if grade in ("G7", "G8", "G9") else "sec",
        track=track,
        academic_year=YEAR,
        has_own_timetable=own_timetable,
    )


def row(
    school, subject, *, grade="G7", track="", periods=5, group="", pilot=False, department=None
):
    return CurriculumPlan.objects.create(
        school=school,
        academic_year=YEAR,
        grade=grade,
        track=track,
        subject=subject,
        weekly_periods=periods,
        source_kind=FROM_PILOT if pilot else FROM_MINISTRY_GUIDE,
        source_reference="" if pilot else GUIDE,
        is_pilot=pilot,
        elective_group=group,
        department=department,
    )


def assign(school, class_group, subject, *, periods=5, teacher=None):
    from operations.models import SubjectClassAssignment

    return SubjectClassAssignment.objects.create(
        school=school,
        class_group=class_group,
        subject=subject,
        teacher=teacher,
        weekly_periods=periods,
        academic_year=YEAR,
    )


# ── النموذج: كلُّ رقمٍ يعرف من أين جاء ───────────────────────────────


def test_a_ministry_number_without_its_page_is_refused(school, subjects):
    """رقمٌ يُنسب إلى دليلٍ منشورٍ بلا صفحته ادّعاءُ مصدرٍ لا مصدر."""
    entry = CurriculumPlan(
        school=school,
        academic_year=YEAR,
        grade="G7",
        subject=subjects["MAT"],
        weekly_periods=5,
        source_kind=FROM_MINISTRY_GUIDE,
        source_reference="",
    )
    with pytest.raises(ValidationError) as err:
        entry.full_clean()
    assert "source_reference" in err.value.error_dict


def test_a_pilot_row_may_wait_for_its_circular(school, subjects):
    """تجربةٌ تطبّقها المدرسةُ وتعميمُها لم يصل — تُوسم ولا تُمنع.

    فمنعُها يعني أن تبقى خطّةُ العاشر فارغةً حتى تصل ورقة، وفراغُ الخطّة
    يُسكت كلَّ فحصٍ يقيس عليها.
    """
    entry = CurriculumPlan(
        school=school,
        academic_year=YEAR,
        grade="G10",
        subject=subjects["SCI"],
        weekly_periods=6,
        source_kind=FROM_PILOT,
        source_reference="",
        is_pilot=True,
    )
    entry.full_clean()
    entry.save()
    assert entry.pk


def test_a_track_on_an_untracked_grade_is_refused(school, subjects):
    entry = CurriculumPlan(
        school=school,
        academic_year=YEAR,
        grade="G7",
        track="science",
        subject=subjects["MAT"],
        weekly_periods=5,
        source_reference=GUIDE,
    )
    with pytest.raises(ValidationError) as err:
        entry.full_clean()
    assert "track" in err.value.error_dict


def test_a_subject_cannot_hold_two_rows_in_one_scope(school, subjects):
    row(school, subjects["MAT"])
    with pytest.raises(IntegrityError):
        row(school, subjects["MAT"], periods=6)


def test_the_same_subject_may_differ_between_tracks(school, subjects):
    """رياضياتُ العلميّ ستٌّ ورياضياتُ الآداب ثلاث — والمفتاحُ يحمل المسار."""
    row(school, subjects["MAT"], grade="G11", track="science", periods=6)
    row(school, subjects["MAT"], grade="G11", track="humanities", periods=3)
    assert CurriculumPlan.objects.count() == 2


def test_a_row_with_no_periods_is_refused_by_the_database(school, subjects):
    with pytest.raises(IntegrityError):
        row(school, subjects["MAT"], periods=0)


# ── مجموعُ الطالب: الاختياريّةُ تُعدّ مرّةً ───────────────────────────


def test_an_elective_group_counts_once_towards_the_student_total(school, subjects):
    """بديلان بحصّتين لا يصيران أربعاً في مجموع الطالب."""
    row(school, subjects["MAT"], grade="G11", track="science", periods=6)
    row(school, subjects["ART"], grade="G11", track="science", periods=2, group="elective")
    row(school, subjects["CHM"], grade="G11", track="science", periods=2, group="elective")

    scope = cs.plan_rows(school, YEAR)
    assert cs.expected_total(scope) == 8


def test_alternatives_that_disagree_on_periods_are_reported(school, subjects):
    row(school, subjects["ART"], grade="G11", track="science", periods=2, group="elective")
    row(school, subjects["CHM"], grade="G11", track="science", periods=3, group="elective")

    issues = cs.scope_issues(cs.plan_rows(school, YEAR))
    assert issues and "تختلف حصصُها" in issues[0]


# ── التغطية: الخطّةُ مقابل الإسناد ───────────────────────────────────


def test_an_assignment_that_matches_the_plan_is_clean(school, subjects):
    seven = section(school)
    row(school, subjects["MAT"], periods=5)
    assign(school, seven, subjects["MAT"], periods=5)

    cells = cs.coverage(school, YEAR)
    assert [c["status"] for c in cells] == [cs.MATCH]
    assert cs.coverage_summary(cells)["problems"] == 0


@pytest.mark.parametrize(
    ("assigned", "expected"),
    [(4, cs.UNDER), (6, cs.OVER)],
)
def test_a_count_that_differs_from_the_plan_is_named(school, subjects, assigned, expected):
    seven = section(school)
    row(school, subjects["MAT"], periods=5)
    assign(school, seven, subjects["MAT"], periods=assigned)

    cell = cs.coverage(school, YEAR)[0]
    assert cell["status"] == expected
    assert cell["delta"] == assigned - 5


def test_a_planned_subject_with_no_assignment_is_missing(school, subjects):
    section(school)
    row(school, subjects["MAT"], periods=5)

    cell = cs.coverage(school, YEAR)[0]
    assert cell["status"] == cs.MISSING
    assert cell["assigned"] == 0


def test_an_assignment_outside_the_plan_is_reported_not_hidden(school, subjects):
    """مادّةٌ تُدرَّس ولا صفَّ لها في الخطّة — تُقال، ولا تُحذف من الفحص."""
    seven = section(school)
    row(school, subjects["MAT"], periods=5)
    assign(school, seven, subjects["MAT"], periods=5)
    assign(school, seven, subjects["ART"], periods=2)

    statuses = {c["subject"]: c["status"] for c in cs.coverage(school, YEAR)}
    assert statuses["الرياضيات"] == cs.MATCH
    assert statuses["الفنون البصرية"] == cs.EXTRA


def test_two_parallel_electives_are_both_clean_and_not_summed(school, subjects):
    """11/4 تأخذ الفنونَ والكيمياءَ في التوقيت نفسه — والطالبُ حصّتان.

    InstructionalPeriods ≠ StudentPeriods
    """
    eleven = section(school, "G11", "4", track="technology")
    row(school, subjects["MAT"], grade="G11", track="technology", periods=6)
    row(school, subjects["ART"], grade="G11", track="technology", periods=2, group="elective")
    row(school, subjects["CHM"], grade="G11", track="technology", periods=2, group="elective")
    assign(school, eleven, subjects["MAT"], periods=6)
    assign(school, eleven, subjects["ART"], periods=2)
    assign(school, eleven, subjects["CHM"], periods=2)

    cells = cs.coverage(school, YEAR)
    assert {c["status"] for c in cells} == {cs.MATCH}

    totals = cs.section_totals(school, YEAR)[0]
    assert totals["planned"] == 8
    assert totals["assigned"] == 10
    assert totals["parallel"] == 2
    assert totals["balanced"], "الحصّتان المتوازيتان لا تجعلان الشعبةَ فائضة"


def test_an_elective_group_with_no_choice_at_all_is_uncovered(school, subjects):
    eleven = section(school, "G11", "1", track="science")
    row(school, subjects["MAT"], grade="G11", track="science", periods=6)
    row(school, subjects["ART"], grade="G11", track="science", periods=2, group="elective")
    row(school, subjects["CHM"], grade="G11", track="science", periods=2, group="elective")
    assign(school, eleven, subjects["MAT"], periods=6)

    statuses = {c["status"] for c in cs.coverage(school, YEAR)}
    assert cs.UNCOVERED_ELECTIVE in statuses


def test_a_section_with_its_own_timetable_is_left_out_entirely(school, subjects):
    """التربيةُ الخاصّةُ جدولُها مستقلّ — فلا تُقاس ولا تظهر فجوةً دائمة."""
    section(school, "G8", "ESE", own_timetable=True)
    row(school, subjects["MAT"], grade="G8", periods=5)

    assert cs.coverage(school, YEAR) == []


def test_a_section_with_no_plan_for_its_scope_is_named_not_ignored(school, subjects):
    eleven = section(school, "G11", "2", track="humanities")
    assign(school, eleven, subjects["MAT"], periods=3)

    cell = cs.coverage(school, YEAR)[0]
    assert cell["status"] == cs.NO_TRACK


def test_the_summary_counts_clean_sections_not_only_cells(school, subjects):
    good = section(school, "G7", "1")
    bad = section(school, "G7", "2")
    row(school, subjects["MAT"], periods=5)
    assign(school, good, subjects["MAT"], periods=5)
    assign(school, bad, subjects["MAT"], periods=3)

    summary = cs.coverage_summary(cs.coverage(school, YEAR))
    assert summary["sections"] == 2
    assert summary["clean_sections"] == 1
    assert summary["problems"] == 1


# ── ميزانُ القسم ─────────────────────────────────────────────────────


def test_the_demand_is_the_plan_times_the_sections(school, subjects):
    from core.models import Department

    math = Department.objects.create(school=school, name="الرياضيات", code="math")
    section(school, "G7", "1")
    section(school, "G7", "2")
    row(school, subjects["MAT"], periods=5, department=math)

    balance = {d["name"]: d for d in cs.department_balance(school, YEAR)}
    assert balance["الرياضيات"]["demand"] == 10


def test_a_department_without_targets_reports_no_delta_not_a_deficit(school, subjects):
    """قسمٌ بلا معلّمٍ مسجَّلٍ مجهولُ العرض — ولا يُقال إنّه عاجزٌ بكامل الطلب."""
    from core.models import Department

    math = Department.objects.create(school=school, name="الرياضيات", code="math")
    section(school, "G7", "1")
    row(school, subjects["MAT"], periods=5, department=math)

    entry = next(d for d in cs.department_balance(school, YEAR) if d["name"] == "الرياضيات")
    assert entry["demand"] == 5
    assert entry["supply"] is None
    assert entry["delta"] is None


def test_a_section_with_its_own_timetable_adds_no_demand(school, subjects):
    from core.models import Department

    math = Department.objects.create(school=school, name="الرياضيات", code="math")
    section(school, "G7", "1")
    section(school, "G7", "ESE", own_timetable=True)
    row(school, subjects["MAT"], periods=5, department=math)

    entry = next(d for d in cs.department_balance(school, YEAR) if d["name"] == "الرياضيات")
    assert entry["demand"] == 5, "شعبةُ الجدول المستقلّ لا تُضاعف الطلب"


# ── الطلبُ لشعبةٍ بعينها ─────────────────────────────────────────────


def test_the_demand_of_a_section_follows_its_grade_and_track(school, subjects):
    eleven = section(school, "G11", "1", track="science")
    row(school, subjects["MAT"], grade="G11", track="science", periods=6)
    row(school, subjects["MAT"], grade="G11", track="humanities", periods=3)

    demand = cs.demand_for(eleven)
    assert [r.weekly_periods for r in demand] == [6]


def test_a_section_with_its_own_timetable_demands_nothing(school, subjects):
    ese = section(school, "G8", "ESE", own_timetable=True)
    row(school, subjects["MAT"], grade="G8", periods=5)

    assert cs.demand_for(ese) == []
