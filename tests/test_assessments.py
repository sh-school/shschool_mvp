"""
tests/test_assessments.py
اختبارات شاملة لنظام التقييمات — الوحدة الأكثر حساسية

يغطي:
  - نماذج التقييمات (SubjectClassSetup, AssessmentPackage, Assessment, Grades)
  - GradeService: حساب الدرجات حسب معادلة وزارة التعليم القطرية
  - Views: لوحة التحكم، إدخال الدرجات، التقارير
"""

from decimal import Decimal

import pytest

from assessments.models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)
from assessments.services import GradeService
from operations.models import Subject
from tests.conftest import (
    MembershipFactory,
    RoleFactory,
    UserFactory,
)

# ══════════════════════════════════════════════════
#  FACTORIES خاصة بالتقييمات
# ══════════════════════════════════════════════════


@pytest.fixture
def subject(db, school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


@pytest.fixture
def setup(db, school, subject, class_group, teacher_user):
    return SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=class_group,
        teacher=teacher_user,
        academic_year="2025-2026",
    )


@pytest.fixture
def s1_package(db, school, setup):
    """منتصف الفصل الأول (P1) — 15 من 40 بالقرار 14/2018 م3 (ص4)."""
    return AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P1",
        semester="S1",
        weight=Decimal("37.50"),
        semester_max_grade=Decimal("40"),
    )


@pytest.fixture
def s1_exam_package(db, school, setup):
    """نهاية الفصل الأول (P2) — 20 من 40. (كانت «P4» في الفصل الأول بوزنٍ 50: بنيةٌ ليست في
    القرار، ولا تُجمع منذ 2026-09-16 — م5 تجعل توزيعَ الدرجات للقطاع لا للمدرسة.)"""
    return AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P2",
        semester="S1",
        weight=Decimal("50"),
        semester_max_grade=Decimal("40"),
    )


@pytest.fixture
def s2_package_p1(db, school, setup):
    """منتصف الفصل الثاني (P3) — 15 من 60."""
    return AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P3",
        semester="S2",
        weight=Decimal("25"),
        semester_max_grade=Decimal("60"),
    )


@pytest.fixture
def s2_package_p4(db, school, setup):
    """نهاية الفصل الثاني (P4) — 40 من 60."""
    return AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P4",
        semester="S2",
        weight=Decimal("66.67"),
        semester_max_grade=Decimal("60"),
    )


@pytest.fixture
def aw_packages(db, school, setup, student_user):
    """أعمالُ الفصلين (AW) — جزءٌ من بنية القرار 14/2018 م3؛ مادّةٌ بلا باقةٍ منها «غير مكتمل»
    منذ جولة 6، وباقةٌ منها بلا رصدٍ «غير مكتمل» منذ جولة 7 (2026-09-17) — فتُرصد صفراً،
    فلا تتغيّر مجاميعُ الاختبارات."""
    packages = []
    for sem, weight, semester_max in (
        ("S1", Decimal("12.50"), Decimal("40")),
        ("S2", Decimal("8.33"), Decimal("60")),
    ):
        pkg = AssessmentPackage.objects.create(
            setup=setup,
            school=school,
            package_type="AW",
            semester=sem,
            weight=weight,
            semester_max_grade=semester_max,
        )
        exam = Assessment.objects.create(
            package=pkg,
            school=school,
            title=f"أعمال {sem}",
            max_grade=Decimal("5"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        StudentAssessmentGrade.objects.create(
            assessment=exam, student=student_user, school=school, grade=Decimal("0")
        )
        packages.append(pkg)
    return packages


@pytest.fixture
def assessment_in_p1(db, school, s1_package):
    """تقييم داخل الباقة الأولى"""
    return Assessment.objects.create(
        package=s1_package,
        school=school,
        title="اختبار قصير 1",
        max_grade=Decimal("20"),
        weight_in_package=Decimal("100"),
        status="published",
    )


@pytest.fixture
def assessment_in_p4(db, school, s1_exam_package):
    """تقييم اختبار نهاية الفصل الأول"""
    return Assessment.objects.create(
        package=s1_exam_package,
        school=school,
        title="اختبار نهاية الفصل الأول",
        max_grade=Decimal("40"),
        weight_in_package=Decimal("100"),
        status="published",
    )


# ══════════════════════════════════════════════════
#  اختبارات النماذج
# ══════════════════════════════════════════════════


class TestAssessmentModels:
    def test_subject_class_setup_creation(self, setup):
        assert setup.academic_year == "2025-2026"
        assert setup.is_active is True
        assert "الرياضيات" in str(setup)

    def test_package_semester_max(self, s1_package, s2_package_p4):
        assert s1_package.semester_max_grade == Decimal("40")
        assert s2_package_p4.semester_max_grade == Decimal("60")

    def test_package_weight_s1(self, s1_package, s1_exam_package):
        """الفصل الأول بالقرار 14/2018 م3: P1=15 وP2=20 وAW=5 من 40 — مجموعُ الأوزان 100%."""
        from core.domain.grades import package_weights

        table = package_weights(7, "S1")
        assert (s1_package.weight, s1_exam_package.weight) == (table["P1"], table["P2"])
        assert sum(table.values()) == Decimal("100")

    def test_assessment_max_grade_constraint(self, assessment_in_p1):
        assert assessment_in_p1.max_grade == Decimal("20")
        assert assessment_in_p1.status == "published"

    def test_unique_setup_constraint(self, setup, school, subject, class_group):
        """لا يمكن تكرار نفس المادة+الفصل+السنة"""
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            SubjectClassSetup.objects.create(
                school=school,
                subject=subject,
                class_group=class_group,
                teacher=setup.teacher,
                academic_year="2025-2026",
            )


# ══════════════════════════════════════════════════
#  اختبارات GradeService — المحرك الأساسي
# ══════════════════════════════════════════════════


class TestGradeService:
    def test_save_grade_basic(self, assessment_in_p1, student_user, teacher_user):
        """حفظ درجة أساسية"""
        obj, created = GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("15"),
            entered_by=teacher_user,
        )
        assert created is True
        assert obj.grade == Decimal("15")

    def test_batch_matches_single_package_score(self, s1_package, assessment_in_p1, student_user):
        """[PERF-01] calc_package_scores_batch يطابق calc_package_score تماماً — ضمان
        عدم انحراف النتائج بعد اعتماد المسار الدُّفعي في recalculate_full_class."""
        GradeService.save_grade(
            assessment=assessment_in_p1, student=student_user, grade=Decimal("15"), recalc=False
        )
        single = GradeService.calc_package_score(student_user, s1_package)
        batch = GradeService.calc_package_scores_batch([student_user.id], [s1_package])
        assert batch[(student_user.id, "P1")] == single

    def test_save_grade_clamps_to_max(self, assessment_in_p1, student_user):
        """الدرجة لا تتجاوز الحد الأقصى"""
        obj, _ = GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("999"),
        )
        assert obj.grade == assessment_in_p1.max_grade

    def test_save_grade_clamps_to_zero(self, assessment_in_p1, student_user):
        """الدرجة لا تقل عن صفر"""
        obj, _ = GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("-5"),
        )
        assert obj.grade == Decimal("0")

    def test_save_grade_absent(self, assessment_in_p1, student_user):
        """تسجيل غياب"""
        obj, _ = GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            is_absent=True,
        )
        assert obj.is_absent is True

    def test_save_grade_updates_existing(self, assessment_in_p1, student_user):
        """تحديث درجة موجودة — ليس إنشاء جديد"""
        GradeService.save_grade(
            assessment=assessment_in_p1, student=student_user, grade=Decimal("10")
        )
        obj, created = GradeService.save_grade(
            assessment=assessment_in_p1, student=student_user, grade=Decimal("18")
        )
        assert created is False
        assert obj.grade == Decimal("18")

    def test_calc_package_score_full_marks(self, s1_package, assessment_in_p1, student_user):
        """طالب أخذ الدرجة الكاملة في الباقة"""
        GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=assessment_in_p1.max_grade,
        )
        score = GradeService.calc_package_score(student_user, s1_package)
        # 100% × 15 (درجةُ P1 من القرار)
        assert score == Decimal("15.00")

    def test_calc_package_score_half_marks(self, s1_package, assessment_in_p1, student_user):
        """طالب أخذ نصف الدرجة"""
        GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("10"),  # 10 من 20 = 50%
        )
        score = GradeService.calc_package_score(student_user, s1_package)
        # 50% × 15 = 7.5 (يثبت النصف — م8)
        assert score == Decimal("7.50")

    def test_calc_package_score_zero(self, s1_package, assessment_in_p1, student_user):
        """طالب أخذ صفر"""
        GradeService.save_grade(
            assessment=assessment_in_p1,
            student=student_user,
            grade=Decimal("0"),
        )
        score = GradeService.calc_package_score(student_user, s1_package)
        assert score == Decimal("0.00")

    def test_calc_package_no_grades(self, s1_package, student_user):
        """لا توجد درجات — يرجع None"""
        score = GradeService.calc_package_score(student_user, s1_package)
        assert score is None

    def test_semester_result_s1(
        self,
        setup,
        s1_package,
        s1_exam_package,
        assessment_in_p1,
        assessment_in_p4,
        student_user,
        enrolled_student,
        aw_packages,
    ):
        """حساب نتيجة الفصل الأول الكاملة"""
        # الفصلُ الثاني بلا باقاتٍ بعد: لا تنبيهَ بنيةٍ فيه (أعمالُه وحدَها بنيةٌ ناقصة).
        aw_packages[1].delete()
        # P1: 15/20 = 75% → 75% × 15 = 11.25
        GradeService.save_grade(
            assessment=assessment_in_p1, student=student_user, grade=Decimal("15")
        )
        # P2: 30/40 = 75% → 75% × 20 = 15
        GradeService.save_grade(
            assessment=assessment_in_p4, student=student_user, grade=Decimal("30")
        )

        result = StudentSubjectResult.objects.get(student=student_user, setup=setup, semester="S1")
        # المجموع = 26.25 → يُجبر إلى 26.5 من 40 (م8: ما دون النصف إلى النصف)
        assert result.total == Decimal("26.50")

    def test_annual_result_pass(
        self,
        setup,
        s1_package,
        s1_exam_package,
        s2_package_p1,
        s2_package_p4,
        student_user,
        school,
        enrolled_student,
        aw_packages,
    ):
        """النتيجة السنوية — طالب ناجح"""
        # الفصل الأول
        a1 = Assessment.objects.create(
            package=s1_package,
            school=school,
            title="عمل 1",
            max_grade=Decimal("20"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        a4_s1 = Assessment.objects.create(
            package=s1_exam_package,
            school=school,
            title="اختبار ف1",
            max_grade=Decimal("40"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        GradeService.save_grade(assessment=a1, student=student_user, grade=Decimal("16"))  # 80%
        GradeService.save_grade(assessment=a4_s1, student=student_user, grade=Decimal("32"))  # 80%

        # الفصل الثاني
        a1_s2 = Assessment.objects.create(
            package=s2_package_p1,
            school=school,
            title="عمل 2",
            max_grade=Decimal("20"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        a4_s2 = Assessment.objects.create(
            package=s2_package_p4,
            school=school,
            title="اختبار نهائي",
            max_grade=Decimal("60"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        GradeService.save_grade(assessment=a1_s2, student=student_user, grade=Decimal("16"))  # 80%
        GradeService.save_grade(assessment=a4_s2, student=student_user, grade=Decimal("48"))  # 80%

        annual = AnnualSubjectResult.objects.get(student=student_user, setup=setup)
        # S1: 80%×15 + 80%×20 = 12 + 16 = 28
        # S2: 80%×15 + 80%×40 = 12 + 32 = 44
        # Total = 72 → pass
        assert annual.annual_total == Decimal("72")
        assert annual.status == "pass"

    def test_annual_result_fail(
        self,
        setup,
        s1_package,
        s1_exam_package,
        s2_package_p1,
        s2_package_p4,
        student_user,
        school,
        enrolled_student,
        aw_packages,
    ):
        """النتيجة السنوية — طالب راسب"""
        a1 = Assessment.objects.create(
            package=s1_package,
            school=school,
            title="عمل 1",
            max_grade=Decimal("20"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        a4_s1 = Assessment.objects.create(
            package=s1_exam_package,
            school=school,
            title="اختبار ف1",
            max_grade=Decimal("40"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        # 20% فقط
        GradeService.save_grade(assessment=a1, student=student_user, grade=Decimal("4"))
        GradeService.save_grade(assessment=a4_s1, student=student_user, grade=Decimal("8"))

        a1_s2 = Assessment.objects.create(
            package=s2_package_p1,
            school=school,
            title="عمل 2",
            max_grade=Decimal("20"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        a4_s2 = Assessment.objects.create(
            package=s2_package_p4,
            school=school,
            title="اختبار نهائي",
            max_grade=Decimal("60"),
            weight_in_package=Decimal("100"),
            status="published",
        )
        GradeService.save_grade(assessment=a1_s2, student=student_user, grade=Decimal("4"))
        GradeService.save_grade(assessment=a4_s2, student=student_user, grade=Decimal("12"))

        annual = AnnualSubjectResult.objects.get(student=student_user, setup=setup)
        assert annual.annual_total < Decimal("50")
        # مادّةٌ واحدة راسبة: تُعاد في الدور الثاني (م12-أ) — ومن موادّ الرسوب.
        assert annual.status == "second_round" and annual.is_failed

    def test_annual_result_incomplete(
        self, setup, s1_package, assessment_in_p1, student_user, enrolled_student
    ):
        """نتيجة غير مكتملة — فصل واحد فقط"""
        GradeService.save_grade(
            assessment=assessment_in_p1, student=student_user, grade=Decimal("15")
        )
        annual = AnnualSubjectResult.objects.get(student=student_user, setup=setup)
        assert annual.status == "incomplete"

    def test_get_assessment_stats(self, assessment_in_p1, school):
        """إحصائيات التقييم"""
        students = [UserFactory() for _ in range(5)]
        grades = [Decimal("20"), Decimal("15"), Decimal("10"), Decimal("8"), Decimal("5")]
        for s, g in zip(students, grades):
            StudentAssessmentGrade.objects.create(
                assessment=assessment_in_p1,
                student=s,
                school=school,
                grade=g,
            )

        stats = GradeService.get_assessment_stats(assessment_in_p1)
        assert stats["entered"] == 5
        assert stats["max"] == 20.0
        assert stats["min"] == 5.0
        assert stats["avg"] == 11.6  # (20+15+10+8+5)/5


# ══════════════════════════════════════════════════
#  اختبارات Views
# ══════════════════════════════════════════════════


class TestAssessmentViews:
    def test_dashboard_as_principal(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/assessments/")
        assert resp.status_code == 200

    def test_dashboard_as_teacher(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/assessments/")
        assert resp.status_code == 200

    def test_dashboard_forbidden_for_student(self, client_as, student_user):
        c = client_as(student_user)
        resp = c.get("/assessments/")
        assert resp.status_code == 403

    def test_setup_detail_as_teacher(self, client_as, teacher_user, setup):
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/setup/{setup.id}/")
        assert resp.status_code == 200

    def test_setup_detail_forbidden_other_teacher(self, client_as, setup, school):
        """معلم آخر لا يمكنه رؤية إعداد ليس له"""
        role = RoleFactory(school=school, name="teacher")
        other = UserFactory(full_name="معلم آخر")
        MembershipFactory(user=other, school=school, role=role)
        c = client_as(other)
        resp = c.get(f"/assessments/setup/{setup.id}/")
        assert resp.status_code == 403

    def test_grade_entry_page(self, client_as, teacher_user, assessment_in_p1):
        c = client_as(teacher_user)
        resp = c.get(f"/assessments/assessment/{assessment_in_p1.id}/")
        assert resp.status_code == 200

    def test_failing_students_page(self, client_as, principal_user):
        c = client_as(principal_user)
        resp = c.get("/assessments/failing/")
        assert resp.status_code == 200
