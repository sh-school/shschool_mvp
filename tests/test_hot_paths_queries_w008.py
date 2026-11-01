"""[PERF] المسارات الساخنة (W-20261101-008): عددُ الاستعلامات ثابتٌ لا يتبع عددَ الطلاب.

«شهاداتُ الفصل» كانت تستدعي تقريرَ الطالب لكلّ طالبٍ (≈11 استعلاماً × 22 طالباً ≈ 240)؛ فصار الجلبُ دفعةً
واحدةً. ويُقاس هنا بمقارنة فصلٍ صغيرٍ بفصلٍ أكبرَ منه: العددُ نفسُه، والمضمونُ يطابق تقريرَ الطالب المفرد.
"""

from decimal import Decimal

import pytest

from assessments.models import AnnualSubjectResult, StudentSubjectResult, Subject, SubjectClassSetup
from reports.selectors import class_certificates_context
from reports.services import AcademicReportsService, ReportDataService
from tests.conftest import (
    ClassGroupFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

CERTIFICATES_MAX_QUERIES = 12


def _class_with_pupils(school, year, count):
    group = ClassGroupFactory(school=school, grade="G7", section="أ", academic_year=year)
    teacher = UserFactory()
    setups = [
        SubjectClassSetup.objects.create(
            school=school,
            subject=Subject.objects.create(school=school, name_ar=name, code=code),
            class_group=group,
            teacher=teacher,
            academic_year=year,
        )
        for name, code in (("الرياضيات", "M1"), ("العلوم", "S1X"))
    ]
    pupils = []
    for i in range(count):
        pupil = UserFactory(full_name=f"طالب {i:02d}")
        StudentEnrollmentFactory(student=pupil, class_group=group)
        for setup in setups:
            AnnualSubjectResult.objects.create(
                student=pupil,
                setup=setup,
                school=school,
                academic_year=year,
                annual_total=Decimal("40") + i,
                status="pass" if i % 2 == 0 else "fail",
            )
            for semester in ("S1", "S2"):
                StudentSubjectResult.objects.create(
                    student=pupil, setup=setup, school=school, semester=semester
                )
        pupils.append(pupil)
    return group, pupils


def test_class_certificates_use_a_constant_number_of_queries(
    seeded_calendar, django_assert_max_num_queries
):
    small_school, big_school = SchoolFactory(), SchoolFactory()
    small, _ = _class_with_pupils(small_school, seeded_calendar, 2)
    big, _ = _class_with_pupils(big_school, seeded_calendar, 12)

    with django_assert_max_num_queries(CERTIFICATES_MAX_QUERIES):
        small_ctx = class_certificates_context(small_school, small, seeded_calendar, "A4")
    with django_assert_max_num_queries(CERTIFICATES_MAX_QUERIES):
        big_ctx = class_certificates_context(big_school, big, seeded_calendar, "A4")

    assert len(small_ctx["students_ctx"]) == 2
    assert len(big_ctx["students_ctx"]) == 12


def test_the_bulk_report_matches_the_single_student_report(seeded_calendar):
    school = SchoolFactory()
    group, pupils = _class_with_pupils(school, seeded_calendar, 4)

    bulk = ReportDataService.get_students_reports(pupils, school, seeded_calendar)

    assert [r["student"] for r in bulk] == pupils
    for report, pupil in zip(bulk, pupils, strict=True):
        single = ReportDataService.get_student_report(pupil, school, seeded_calendar)
        for key in ("total", "passed", "failed", "avg", "absent_total", "late_total", "year"):
            assert report[key] == single[key], key
        assert report["enrollment"].class_group_id == group.pk
        assert (
            [row["subject"] for row in report["rows"]]
            == [row["subject"] for row in single["rows"]]
            == ["الرياضيات", "العلوم"]
        )
    assert bulk[0]["passed"] == 2 and bulk[1]["failed"] == 2


def _assessment_world(school, year, pupils_count):
    from assessments.models import Assessment, AssessmentPackage

    group = ClassGroupFactory(school=school, grade="G8", section="ب", academic_year=year)
    setup = SubjectClassSetup.objects.create(
        school=school,
        subject=Subject.objects.create(school=school, name_ar="الفيزياء", code="PH1"),
        class_group=group,
        teacher=UserFactory(),
        academic_year=year,
    )
    package = AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P1",
        semester="S1",
        weight=Decimal("50"),
        semester_max_grade=Decimal("40"),
    )
    assessment = Assessment.objects.create(
        package=package,
        school=school,
        title="اختبار قصير",
        assessment_type="exam",
        max_grade=Decimal("100"),
        weight_in_package=Decimal("100"),
        status="published",
    )
    pupils = []
    for i in range(pupils_count):
        pupil = UserFactory(full_name=f"طالب {i:02d}")
        StudentEnrollmentFactory(student=pupil, class_group=group)
        pupils.append(pupil)
    return assessment, pupils


def test_academic_progress_report_does_not_query_the_assessment_per_grade(
    seeded_calendar,
):
    """`grade_pct` يقرأ `assessment.max_grade` — بلا `select_related` كان استعلاماً لكلّ درجة (≈600 لفصلٍ كامل)."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from assessments.models import StudentAssessmentGrade

    counts = {}
    for size in (2, 10):
        school = SchoolFactory()
        assessment, pupils = _assessment_world(school, seeded_calendar, size)
        for i, pupil in enumerate(pupils):
            StudentAssessmentGrade.objects.create(
                assessment=assessment, student=pupil, school=school, grade=Decimal(50 + i)
            )
        with CaptureQueriesContext(connection) as ctx:
            report = AcademicReportsService.get_academic_progress_reports(
                school, class_group_id=str(assessment.package.setup.class_group_id)
            )
        counts[size] = len(ctx)
        assert report["rows"] if "rows" in report else True
    assert counts[2] == counts[10], counts
