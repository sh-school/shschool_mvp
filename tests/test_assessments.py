"""
tests/test_assessments.py
اختبارات شاملة لنظام التقييمات — الوحدة الأكثر حساسية

يغطي:
  - نماذج التقييمات (SubjectClassSetup, AssessmentPackage, Assessment, Grades)
  - GradeService: حساب الدرجات حسب معادلة وزارة التعليم القطرية
  - Views: لوحة التحكم، إدخال الدرجات، التقارير
"""
import pytest
from decimal import Decimal
from django.urls import reverse

from assessments.models import (
    SubjectClassSetup, AssessmentPackage, Assessment,
    StudentAssessmentGrade, StudentSubjectResult, AnnualSubjectResult,
)
from assessments.services import GradeService
from operations.models import Subject
from tests.conftest import (
    SchoolFactory, UserFactory, RoleFactory, MembershipFactory,
    ClassGroupFactory, StudentEnrollmentFactory,
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
    """باقة الأعمال المستمرة — الفصل الأول (وزن 50% من 40)"""
    return AssessmentPackage.objects.create(
        setup=setup, school=school,
        package_type="P1", semester="S1",
        weight=Decimal("50"), semester_max_grade=Decimal("40"),
    )


@pytest.fixture
def s1_exam_package(db, school, setup):
    """باقة اختبار نهاية الفصل الأول (وزن 50% من 40)"""
    return AssessmentPackage.objects.create(
        setup=setup, school=school,
        package_type="P4", semester="S1",
        weight=Decimal("50"), semester_max_grade=Decimal("40"),
    )


@pytest.fixture
def s2_package_p1(db, school, setup):
    """أعمال مستمرة — الفصل الثاني (وزن 17% من 60)"""
    return AssessmentPackage.objects.create(
        setup=setup, school=school,
        package_type="P1", semester="S2",
        weight=Decimal("17"), semester_max_grade=Decimal("60"),
    )


@pytest.fixture
def s2_package_p4(db, school, setup):
    """اختبار نهائي — الفصل الثاني (وزن 50% من 60)"""
    return AssessmentPackage.objects.create(
        setup=setup, school=school,
        package_type="P4", semester="S2",
        weight=Decimal("50"), semester_max_grade=Decimal("60"),
    )


@pytest.fixture
def assessment_in_p1(db, school, s1_package):
    """تقييم داخل الباقة الأولى"""
    return Assessment.objects.create(
        package=s1_package, school=school,
        title="اختبار قصير 1",
        max_grade=Decimal("20"),
        weight_in_package=Decimal("100"),
        status="published",
    )


@pytest.fixture
def assessment_in_p4(db, school, s1_exam_package):
    """تقييم اختبار نهاية الفصل الأول"""
    return Assessment.objects.create(
        package=s1_exam_package, school=school,
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
        """الفصل الأول: P1=50% + P4=50% = 100%"""
        assert s1_package.weight + s1_exam_package.weight == Decimal("100")

    def test_assessment_max_grade_constraint(self, assessment_in_p1):
        assert assessment_in_p1.max_grade == Decimal("20")
        assert assessment_in_p1.status == "published"

    def test_unique_setup_constraint(self, setup, school, subject, class_group):
        """لا يمكن تكرار نفس المادة+الفصل+السنة"""
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            SubjectClassSetup.objects.create(
                school=school, subject=subject,
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
        GradeService.save_grade(assessment=assessment_in_p1, student=student_user, grade=Decimal("10"))
        obj, created = GradeService.save_grade(assessment=assessment_in_p1, student=student_user, grade=Decimal("18"))
        assert created is False
        assert obj.grade == Decimal("18")

    def test_calc_package_score_full_marks(self, s1_package, assessment_in_p1, student_user):
        """طالب أخذ الدرجة الكاملة في الباقة"""
        GradeService.save_grade(
            assessment=assessment_in_p1, student=student_user,
            grade=assessment_in_p1.max_grade,
        )
        score = GradeService.calc_package_score(student_user, s1_package)
        # 100% × 50% × 40 / 100 = 20
        assert score == Decimal("20.00")

    def test_calc_package_score_half_marks(self, s1_package, assessment_in_p1, student_user):
        """طالب أخذ نصف الدرجة"""
        GradeService.save_grade(
            assessment=assessment_in_p1, student=student_user,
            grade=Decimal("10"),  # 10 من 20 = 50%
        )
        score = GradeService.calc_package_score(student_user, s1_package)
        # 50% × 50% × 40 / 100 = 10
        assert score == Decimal("10.00")

    def test_calc_package_score_zero(self, s1_package, assessment_in_p1, student_user):
        """طالب أخذ صفر"""
        GradeService.save_grade(
            assessment=assessment_in_p1, student=student_user,
            grade=Decimal("0"),
        )
        score = GradeService.calc_package_score(student_user, s1_package)
        assert score == Decimal("0.00")

    def test_calc_package_no_grades(self, s1_package, student_user):
        """لا توجد درجات — يرجع None"""
        score = GradeService.calc_package_score(student_user, s1_package)
        assert score is None

    def test_semester_result_s1(
        self, setup, s1_package, s1_exam_package,
        assessment_in_p1, assessment_in_p4, student_user,
        enrolled_student,
    ):
        """حساب نتيجة الفصل الأول الكاملة"""
        # P1: 15/20 = 75% → 75% × 50% × 40 / 100 = 15
        GradeService.save_grade(assessment=assessment_in_p1, student=student_user, grade=Decimal("15"))
        # P4: 30/40 = 75% → 75% × 50% × 40 / 100 = 15
        GradeService.save_grade(assessment=assessment_in_p4, student=student_user, grade=Decimal("30"))

        result = StudentSubjectResult.objects.get(student=student_user, setup=setup, semester="S1")
        # المجموع = 15 + 15 = 30 من 40
        assert result.total == Decimal("30.00")

    def test_annual_result_pass(
        self, setup, s1_package, s1_exam_package,
        s2_package_p1, s2_package_p4,
        student_user, school, enrolled_student,
    ):
        """النتيجة السنوية — طالب ناجح"""
        # الفصل الأول
        a1 = Assessment.objects.create(
            package=s1_package, school=school, title="عمل 1",
            max_grade=Decimal("20"), weight_in_package=Decimal("100"), status="published",
        )
        a4_s1 = Assessment.objects.create(
            package=s1_exam_package, school=school, title="اختبار ف1",
            max_grade=Decimal("40"), weight_in_package=Decimal("100"), status="published",
        )
        GradeService.save_grade(assessment=a1, student=student_user, grade=Decimal("16"))      # 80%
        GradeService.save_grade(assessment=a4_s1, student=student_user, grade=Decimal("32"))    # 80%

        # الفصل الثاني
        a1_s2 = Assessment.objects.create(
            package=s2_package_p1, school=school, title="عمل 2",
            max_grade=Decimal("20"), weight_in_package=Decimal("100"), status="published",
        )
        a4_s2 = Assessment.objects.create(
            package=s2_package_p4, school=school, title="اختبار نهائي",
            max_grade=Decimal("60"), weight_in_package=Decimal("100"), status="published",
        )
        GradeService.save_grade(assessment=a1_s2, student=student_user, grade=Decimal("16"))   # 80%
        GradeService.save_grade(assessment=a4_s2, student=student_user, grade=Decimal("48"))   # 80%

        annual = AnnualSubjectResult.objects.get(student=student_user, setup=setup)
        # S1: 80%×50%×40/100 + 80%×50%×40/100 = 16 + 16 = 32
        # S2: 80%×17%×60/100 + 80%×50%×60/100 = 8.16 + 24 = 32.16
        # Total ≈ 64.16 → pass
        assert annual.annual_total > Decimal("50")
        assert annual.status == "pass"

    def test_annual_result_fail(
        self, setup, s1_package, s1_exam_package,
        s2_package_p1, s2_package_p4,
        student_user, school, enrolled_student,
    ):
        """النتيجة السنوية — طالب راسب"""
        a1 = Assessment.objects.create(
            package=s1_package, school=school, title="عمل 1",
            max_grade=Decimal("20"), weight_in_package=Decimal("100"), status="published",
        )
        a4_s1 = Assessment.objects.create(
            package=s1_exam_package, school=school, title="اختبار ف1",
            max_grade=Decimal("40"), weight_in_package=Decimal("100"), status="published",
        )
        # 20% فقط
        GradeService.save_grade(assessment=a1, student=student_user, grade=Decimal("4"))
        GradeService.save_grade(assessment=a4_s1, student=student_user, grade=Decimal("8"))

        a1_s2 = Assessment.objects.create(
            package=s2_package_p1, school=school, title="عمل 2",
            max_grade=Decimal("20"), weight_in_package=Decimal("100"), status="published",
        )
        a4_s2 = Assessment.objects.create(
            package=s2_package_p4, school=school, title="اختبار نهائي",
            max_grade=Decimal("60"), weight_in_package=Decimal("100"), status="published",
        )
        GradeService.save_grade(assessment=a1_s2, student=student_user, grade=Decimal("4"))
        GradeService.save_grade(assessment=a4_s2, student=student_user, grade=Decimal("12"))

        annual = AnnualSubjectResult.objects.get(student=student_user, setup=setup)
        assert annual.annual_total < Decimal("50")
        assert annual.status == "fail"

    def test_annual_result_incomplete(self, setup, s1_package, assessment_in_p1, student_user, enrolled_student):
        """نتيجة غير مكتملة — فصل واحد فقط"""
        GradeService.save_grade(assessment=assessment_in_p1, student=student_user, grade=Decimal("15"))
        annual = AnnualSubjectResult.objects.get(student=student_user, setup=setup)
        assert annual.status == "incomplete"

    def test_get_assessment_stats(self, assessment_in_p1, school):
        """إحصائيات التقييم"""
        students = [UserFactory() for _ in range(5)]
        grades = [Decimal("20"), Decimal("15"), Decimal("10"), Decimal("8"), Decimal("5")]
        for s, g in zip(students, grades):
            StudentAssessmentGrade.objects.create(
                assessment=assessment_in_p1, student=s, school=school, grade=g,
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
