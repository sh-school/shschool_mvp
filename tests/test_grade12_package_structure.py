"""[COMPLIANCE 0.1] بنيةُ باقات الثاني عشر — مكوّنان فقط.

المرجع: قرار وزير التعليم والتعليم العالي رقم (14) لسنة 2018، صادر 2018/06/06
(1439/09/21هـ)، المادّة 3، صفحة القرار 5 — `04_academic.md` قسم 9:

    «ثالثاً: الصف الثاني عشر: يقيم طلبة الصف الثاني عشر على النحو التالي:
     الفصل الدراسي الأول: (40 درجة) من الدرجة المخصصة للمادة في الفصل الدراسي
     الأول لاختبار نهاية الفصل … الفصل الدراسي الثاني: (60 درجة) من الدرجة
     المخصصة للمادة في الفصل الدراسي الثاني لاختبار نهاية الفصل …»

وسياسة تقييم الصف الثاني عشر (2015) — `04_academic.md` قسم 3، الفروق الجوهريّة
(2): «لا يوجد "أعمال فصل" أو تقييم مستمر منفصل». والنسبةُ 40/60 لا تتغيّر —
`remediation_plan.md` «تصحيحٌ جوهري».

والصفوفُ الأخرى (في مدرستنا 7–11) على «ثانياً» من المادّة نفسها (صفحتا 4–5):
15 منتصف · 5 أعمال · 20 نهاية = 40، ثمّ 15 · 5 · 40 = 60 — ولا يمسّها الفرع.
"""

from decimal import Decimal

import pytest

from assessments.models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    SubjectClassSetup,
)
from assessments.services import GradeService
from core.domain.grades import package_weight, package_weights
from operations.models import Subject
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

#: الأوزانُ كما كانت في `AssessmentPackage.DEFAULT_WEIGHTS_S1/S2` قبل هذا التغيير
#: (الإيداع f469cf7e) — «القبل» الذي يُقارَن به انحدارُ الصفوف 7–11.
WEIGHTS_BEFORE = {
    "S1": {"P1": Decimal("37.50"), "P2": Decimal("50.00"), "AW": Decimal("12.50")},
    "S2": {"P3": Decimal("25.00"), "P4": Decimal("66.67"), "AW": Decimal("8.33")},
}


# ── الجدولُ الصافي ─────────────────────────────────────────────


def test_grade12_table_has_no_p1_p3_aw():
    assert package_weights(12, "S1") == {"P2": Decimal("100")}
    assert package_weights(12, "S2") == {"P4": Decimal("100")}
    for sem in ("S1", "S2"):
        for ptype in ("P1", "P3", "AW"):
            # معطَّلةٌ بنيويّاً: None لا صفر.
            assert package_weight(12, sem, ptype) is None


@pytest.mark.parametrize("grade", [4, 5, 6, 7, 8, 9, 10, 11])
def test_other_grades_table_unchanged(grade):
    for sem in ("S1", "S2"):
        assert package_weights(grade, sem) == WEIGHTS_BEFORE[sem]


# ── الإعدادُ الفعليّ ────────────────────────────────────────────


def _setup(school, grade, teacher):
    cg = ClassGroupFactory(school=school, grade=grade)
    subject = Subject.objects.create(school=school, name_ar=f"مادة {grade}", code=f"S{grade}")
    return SubjectClassSetup.objects.create(
        school=school, subject=subject, class_group=cg, teacher=teacher, academic_year="2025-2026"
    )


def _exam(package, title="اختبار"):
    return Assessment.objects.create(
        package=package,
        school=package.school,
        title=title,
        max_grade=Decimal("100"),
        status="published",
    )


@pytest.mark.django_db
def test_grade12_package_structure(school, teacher_user):
    """طالبُ الثاني عشر: مكوّنان فقط — P2 من 40 وP4 من 60."""
    setup = _setup(school, "G12", teacher_user)
    s1 = GradeService.ensure_packages(setup, "S1")
    s2 = GradeService.ensure_packages(setup, "S2")
    GradeService.ensure_packages(setup, "S1")  # متكرّرٌ بلا أثر

    assert [(p.package_type, p.weight, p.effective_max_grade) for p in s1] == [
        ("P2", Decimal("100.00"), Decimal("40.00"))
    ]
    assert [(p.package_type, p.weight, p.effective_max_grade) for p in s2] == [
        ("P4", Decimal("100.00"), Decimal("60.00"))
    ]
    assert AssessmentPackage.objects.filter(setup=setup).count() == 2
    assert not AssessmentPackage.objects.filter(
        setup=setup, package_type__in=["P1", "P3", "AW"]
    ).exists()


@pytest.mark.django_db
def test_setup_screen_creates_two_packages_for_grade12(client_as, school, teacher_user):
    """شاشةُ إعداد المادّة — المدخلُ الفعليّ لإنشاء الباقات — تتبع البنيةَ نفسها."""
    setup = _setup(school, "G12", teacher_user)
    c = client_as(teacher_user)
    for sem in ("S1", "S2"):
        assert c.get(f"/assessments/setup/{setup.id}/?semester={sem}").status_code == 200
    assert sorted(
        AssessmentPackage.objects.filter(setup=setup).values_list("semester", "package_type")
    ) == [("S1", "P2"), ("S2", "P4")]


@pytest.mark.django_db
def test_grade12_annual_total_is_p2_plus_p4(school, teacher_user):
    """المجموعُ السنويّ = P2 (من 40) + P4 (من 60) — عيّنةُ 20 طالباً اصطناعيّاً."""
    setup = _setup(school, "G12", teacher_user)
    (p2,) = GradeService.ensure_packages(setup, "S1")
    (p4,) = GradeService.ensure_packages(setup, "S2")
    e2, e4 = _exam(p2), _exam(p4)

    expected = {}
    for i in range(20):
        student = UserFactory()
        StudentEnrollmentFactory(student=student, class_group=setup.class_group)
        g2, g4 = Decimal(5 * i), Decimal(100 - 5 * i)  # نسبٌ مئويّة
        StudentAssessmentGrade.objects.create(
            assessment=e2, student=student, school=school, grade=g2
        )
        StudentAssessmentGrade.objects.create(
            assessment=e4, student=student, school=school, grade=g4
        )
        expected[student.id] = g2 * Decimal("0.4") + g4 * Decimal("0.6")

    GradeService.recalculate_full_class(setup)
    results = AnnualSubjectResult.objects.filter(setup=setup)
    assert results.count() == 20
    for r in results:
        assert r.annual_total == expected[r.student_id], r.student_id
        assert r.status == ("pass" if r.annual_total >= 50 else "fail")


@pytest.mark.django_db
def test_grades_7_to_11_regression_20_students(school, teacher_user):
    """انحدار: 20 طالباً في 7–11 — البنيةُ والأوزانُ والمجاميعُ كما قبل الفرع."""
    expected = {}
    setups = []
    for grade in ("G7", "G8", "G9", "G10", "G11"):
        setup = _setup(school, grade, teacher_user)
        setups.append(setup)
        exams = {}
        for sem in ("S1", "S2"):
            pkgs = GradeService.ensure_packages(setup, sem)
            assert {p.package_type: p.weight for p in pkgs} == WEIGHTS_BEFORE[sem]
            for p in pkgs:
                exams[(sem, p.package_type)] = _exam(p)
        for k in range(4):  # 5 صفوف × 4 طلاب = 20
            student = UserFactory()
            StudentEnrollmentFactory(student=student, class_group=setup.class_group)
            pct = {key: Decimal(10 * ((n + k) % 11)) for n, key in enumerate(exams)}
            for key, exam in exams.items():
                StudentAssessmentGrade.objects.create(
                    assessment=exam, student=student, school=school, grade=pct[key]
                )
            # «ثانياً» من المادّة 3: 15·5·20 ثمّ 15·5·40 — بالنسب مباشرةً.
            points = {"P1": 15, "P2": 20, "P3": 15, "P4": 40}
            total = sum(pct[(sem, pt)] * (points.get(pt) or 5) / Decimal(100) for sem, pt in exams)
            expected[(setup.id, student.id)] = total

    for setup in setups:
        GradeService.recalculate_full_class(setup)
    results = AnnualSubjectResult.objects.filter(setup__in=setups)
    assert results.count() == 20
    for r in results:
        assert r.annual_total == expected[(r.setup_id, r.student_id)]
