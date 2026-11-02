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
#: 15 في الإنتاج (≤15 بالبطاقة) + 4 عبارات SAVEPOINT/RELEASE تضيفها معاملةُ الاختبار؛ وكانت 542 لاثنين وعشرين طالباً.
SAVE_ALL_MAX_QUERIES = 19


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
    packages = [
        AssessmentPackage.objects.create(
            setup=setup,
            school=school,
            package_type=ptype,
            semester=sem,
            weight=Decimal("50"),
            semester_max_grade=Decimal("40") if sem == "S1" else Decimal("60"),
        )
        for ptype, sem in (("P1", "S1"), ("P4", "S1"), ("P1", "S2"))
    ]
    assessment = Assessment.objects.create(
        package=packages[0],
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


def _post(pupils):
    post = {f"grade_{pupil.id}": str(40 + i * 7 % 70) for i, pupil in enumerate(pupils)}
    post[f"absent_{pupils[1].id}"] = "1"
    post[f"grade_{pupils[2].id}"] = "250"  # يُقصّ إلى الأقصى
    post[f"notes_{pupils[3].id}"] = "ملاحظة"
    del post[f"grade_{pupils[3].id}"]  # المفتاحُ غائبٌ: تبقى الدرجةُ المحفوظة
    return post


def _legacy_recalculate_class(setup):
    """المسارُ القديم حرفيّاً: كتابةٌ مفردةٌ لكلّ طالبٍ وفصلٍ ثمّ السنويُّ لكلّ طالب — مرجعُ المقارنة."""
    from assessments.models import AssessmentPackage
    from assessments.services import GradeService
    from core.models import StudentEnrollment

    students = [
        enr.student
        for enr in StudentEnrollment.objects.filter(
            class_group=setup.class_group, is_active=True
        ).select_related("student")
    ]
    ids = [s.id for s in students]
    for sem in ("S1", "S2"):
        packages = list(AssessmentPackage.objects.filter(setup=setup, semester=sem, is_active=True))
        batch = GradeService.calc_package_scores_batch(ids, packages)
        for student in students:
            scores = {p.package_type: batch.get((student.id, p.package_type)) for p in packages}
            GradeService._write_semester_result(student, setup, sem, packages, scores)
    for student in students:
        GradeService.recalculate_annual_result(student, setup)


def _snapshot(assessment):
    from assessments.models import StudentAssessmentGrade
    from core.models import AuditLog

    setup = assessment.package.setup
    grades = [
        (g.student.full_name, g.grade, g.is_absent, g.notes, g.is_excused)
        for g in StudentAssessmentGrade.objects.filter(assessment=assessment)
        .select_related("student")
        .order_by("student__full_name")
    ]
    semesters = [
        (r.student.full_name, r.semester, r.total, r.p1_score, r.p4_score, r.semester_max)
        for r in StudentSubjectResult.objects.filter(setup=setup)
        .select_related("student")
        .order_by("student__full_name", "semester")
    ]
    annuals = [
        (a.student.full_name, a.s1_total, a.s2_total, a.annual_total, a.status)
        for a in AnnualSubjectResult.objects.filter(setup=setup)
        .select_related("student")
        .order_by("student__full_name")
    ]
    # معرّفُ الصفّ يختلف بين العالمين، فيُستبدل بمفتاحٍ ثابت (الطالب/الفصل) ويُقارَن كلُّ ما عداه حرفيّاً
    keys = {
        ("StudentAssessmentGrade", str(g.pk)): g.student.full_name
        for g in StudentAssessmentGrade.objects.filter(assessment=assessment).select_related(
            "student"
        )
    }
    keys.update(
        {
            ("StudentSubjectResult", str(r.pk)): f"{r.student.full_name}/{r.semester}"
            for r in StudentSubjectResult.objects.filter(setup=setup).select_related("student")
        }
    )
    audit = sorted(
        (
            a.action,
            a.model_name,
            keys.get((a.model_name, str(a.object_id)), "؟"),
            a.object_repr.replace(str(a.object_id)[:8], "‹pk›"),
            repr(sorted((a.changes or {}).items(), key=str)),
            a.school_id is not None,
            a.user_id is not None,
        )
        for a in AuditLog.objects.filter(
            model_name__in=("StudentAssessmentGrade", "StudentSubjectResult"),
            school=setup.school,
        )
    )
    return grades, semesters, annuals, audit


def test_batched_save_all_equals_the_rowwise_path_including_the_audit_trail(
    seeded_calendar, settings
):
    """الحفظُ الدفعيُّ يطابق المسارَ المفرد القديم: الدرجاتُ والنتائجُ الفصليّةُ والسنويّةُ، وصفوفُ التدقيق عدداً ومحتوى."""
    from assessments.models import StudentAssessmentGrade
    from assessments.services import GradeService
    from core.models import StudentEnrollment

    settings.VERDICT_ENGINE_ENABLED = False
    school_a, school_b = SchoolFactory(), SchoolFactory()
    assessment_a, pupils_a = _assessment_world(school_a, seeded_calendar, 6)
    assessment_b, pupils_b = _assessment_world(school_b, seeded_calendar, 6)
    for assessment, pupils in ((assessment_a, pupils_a), (assessment_b, pupils_b)):
        # صفٌّ قائمٌ يُحدَّث، وآخرُ معذورٌ يبقى مقفلاً
        for index in (0, 4):
            StudentAssessmentGrade.objects.create(
                assessment=assessment,
                student=pupils[index],
                school=assessment.school,
                grade=Decimal("10"),
                is_excused=index == 4,
            )

    saved_a = GradeService.save_all_from_post(assessment_a, _post(pupils_a), UserFactory())

    # المرجع: حلقةُ save_grade المفردة + إعادةُ الحساب القديمة لكلّ طالب
    post_b = _post(pupils_b)
    saved_b = 0
    for enr in StudentEnrollment.objects.filter(
        class_group=assessment_b.class_group, is_active=True
    ).select_related("student"):
        sid = str(enr.student.id)
        current = StudentAssessmentGrade.objects.filter(
            assessment=assessment_b, student=enr.student
        ).first()
        if not any(f"{prefix}{sid}" in post_b for prefix in ("grade_", "absent_", "notes_")):
            continue
        if current is not None and current.is_excused:
            continue
        is_absent = post_b.get(f"absent_{sid}") == "1"
        notes = post_b.get(f"notes_{sid}", "")
        grade, skip = GradeService._grade_from_post(post_b, sid, current, is_absent, notes)
        if skip:
            continue
        GradeService.save_grade(
            assessment=assessment_b,
            student=enr.student,
            grade=grade,
            is_absent=is_absent,
            notes=notes,
            entered_by=None,
            recalc=False,
        )
        saved_b += 1
    _legacy_recalculate_class(assessment_b.package.setup)

    assert saved_a == saved_b == 5
    snapshot = _snapshot(assessment_a)
    assert snapshot == _snapshot(assessment_b)
    audit = snapshot[3]
    assert ("update", "StudentAssessmentGrade") in {(row[0], row[1]) for row in audit}
    assert ("create", "StudentAssessmentGrade") in {(row[0], row[1]) for row in audit}
    assert "StudentSubjectResult" in {row[1] for row in audit}


def test_batched_recalculate_full_class_equals_the_legacy_loop_with_existing_rows(
    seeded_calendar, settings
):
    """إعادةُ الحساب وحدَها: صفوفٌ قائمةٌ وعتبةُ نجاحٍ مخصّصة؛ النتيجةُ وأثرُ التدقيق مطابقان للحلقة القديمة."""
    from assessments.models import Assessment, AssessmentPackage, StudentAssessmentGrade
    from assessments.services import GradeService

    settings.VERDICT_ENGINE_ENABLED = False
    worlds = []
    for _ in range(2):
        school = SchoolFactory()
        assessment, pupils = _assessment_world(school, seeded_calendar, 5)
        setup = assessment.package.setup
        # كلُّ باقةٍ بتقييمٍ مُدرجٍ فيه درجاتٌ للجميع ليكتمل الفصلان فيصدر حكمٌ سنويّ
        for package in AssessmentPackage.objects.filter(setup=setup):
            target = assessment
            if package.pk != assessment.package_id:
                target = Assessment.objects.create(
                    package=package,
                    school=school,
                    title=f"تقييم {package.package_type}{package.semester}",
                    assessment_type="exam",
                    max_grade=Decimal("100"),
                    weight_in_package=Decimal("100"),
                    status="published",
                )
            for i, pupil in enumerate(pupils):
                StudentAssessmentGrade.objects.create(
                    assessment=target, student=pupil, school=school, grade=Decimal(20 + i * 15)
                )
        # صفوفٌ قائمةٌ بقيمٍ قديمة وعتبةٍ مخصّصة (70) لبعضها
        for i, pupil in enumerate(pupils):
            for sem in ("S1", "S2"):
                StudentSubjectResult.objects.create(
                    student=pupil, setup=setup, school=school, semester=sem, total=Decimal("1")
                )
            AnnualSubjectResult.objects.create(
                student=pupil,
                setup=setup,
                school=school,
                academic_year=seeded_calendar,
                annual_total=Decimal("1"),
                status="fail",
                pass_grade=Decimal("70") if i % 2 == 0 else Decimal("50"),
            )
        worlds.append((assessment, setup))

    GradeService.recalculate_full_class(worlds[0][1])
    _legacy_recalculate_class(worlds[1][1])

    snap_a, snap_b = _snapshot(worlds[0][0]), _snapshot(worlds[1][0])
    assert snap_a == snap_b
    assert {row[4] for row in snap_a[2]} <= {"pass", "fail"}
    assert snap_a[3], "يجب أن يكتب أثرَ تدقيقٍ للنتائج المحدَّثة"


def test_recalculate_full_class_query_count_does_not_grow_with_pupils(seeded_calendar, settings):
    """عدُّ الاستعلامات (يشمل ما تلمسه `object_repr` من علاقاتٍ كسولة) ثابتٌ بين فصلٍ صغيرٍ وكبير."""
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from assessments.models import StudentAssessmentGrade
    from assessments.services import GradeService

    settings.VERDICT_ENGINE_ENABLED = False
    counts = {}
    for size in (2, 12):
        school = SchoolFactory()
        assessment, pupils = _assessment_world(school, seeded_calendar, size)
        setup = assessment.package.setup
        for i, pupil in enumerate(pupils):
            StudentAssessmentGrade.objects.create(
                assessment=assessment, student=pupil, school=school, grade=Decimal(30 + i)
            )
        GradeService.recalculate_full_class(setup)  # أوّلُ مرّةٍ تُنشئ الصفوف
        with CaptureQueriesContext(connection) as ctx:
            GradeService.recalculate_full_class(setup)  # الثانيةُ تحدّث صفوفاً قائمة
        counts[size] = len(ctx)
    assert counts[2] == counts[12], counts


def test_save_all_grades_uses_a_constant_number_of_queries(
    seeded_calendar, settings, django_assert_max_num_queries
):
    from assessments.services import GradeService

    settings.VERDICT_ENGINE_ENABLED = False
    school = SchoolFactory()
    assessment, pupils = _assessment_world(school, seeded_calendar, 22)
    post = {f"grade_{p.id}": str(50 + i) for i, p in enumerate(pupils)}

    teacher = UserFactory()
    with django_assert_max_num_queries(SAVE_ALL_MAX_QUERIES):
        saved = GradeService.save_all_from_post(assessment, post, teacher)

    assert saved == 22


# ── أخطاء الصحّة (بند 5-6) ────────────────────────────────────────────


def test_a_zero_annual_total_counts_in_the_average(seeded_calendar):
    school = SchoolFactory()
    group, pupils = _class_with_pupils(school, seeded_calendar, 1)
    AnnualSubjectResult.objects.filter(student=pupils[0]).update(annual_total=Decimal("0"))
    first = AnnualSubjectResult.objects.filter(student=pupils[0]).order_by(
        "setup__subject__name_ar"
    )[1]
    first.annual_total = Decimal("100")
    first.save()

    report = ReportDataService.get_student_report(pupils[0], school, seeded_calendar)

    assert report["avg"] == 50.0  # الصفرُ درجةٌ لا غيابُ درجة


def test_the_annual_verdict_reads_the_rows_pass_grade_not_a_constant():
    from assessments.services import GradeService

    total = (Decimal("30"), Decimal("25"))
    assert GradeService._annual_values(*total)[1] == "pass"  # 55 ≥ 50 الافتراضيّة
    assert GradeService._annual_values(*total, Decimal("60")) == (Decimal("55.00"), "fail")


@pytest.mark.parametrize("raw", ["nan", "NaN", "inf", "-Infinity"])
def test_a_non_finite_grade_is_skipped_not_a_crash(raw):
    from assessments.services import GradeService

    post = {"grade_x": raw}

    assert GradeService._grade_from_post(post, "x", None, False, "") == (None, True)


def test_the_monthly_report_lists_the_schools_classes(seeded_calendar):
    from core.academic_calendar import academic_year_for_school

    school = SchoolFactory()
    group, _ = _class_with_pupils(school, academic_year_for_school(school), 1)

    report = AcademicReportsService.get_monthly_behavior_academic_report(
        school, month=1, year=2026, scope="section", class_group_id=str(group.pk)
    )

    assert [cid for cid, _label in report["classes"]] == [group.pk]


def test_student_attendance_counts_only_the_requested_year(seeded_calendar):
    """كان الحضورُ يُجمَّع عبر كلّ الأعوام فتتراكم أرقامُ الغياب."""
    import datetime as dt

    from operations.models import Session, StudentAttendance

    school = SchoolFactory()
    old_group = ClassGroupFactory(school=school, grade="G7", section="ج", academic_year="2020-2021")
    group, pupils = _class_with_pupils(school, seeded_calendar, 1)
    subject = Subject.objects.create(school=school, name_ar="تاريخ", code="HX")
    for klass, day in ((old_group, dt.date(2020, 10, 4)), (group, dt.date(2026, 10, 4))):
        session = Session.objects.create(
            school=school,
            class_group=klass,
            teacher=UserFactory(),
            subject=subject,
            date=day,
            start_time=dt.time(8),
            end_time=dt.time(9),
        )
        StudentAttendance.objects.create(
            session=session, student=pupils[0], school=school, status="absent"
        )

    report = ReportDataService.get_student_report(pupils[0], school, seeded_calendar)

    assert report["absent_total"] == 1
