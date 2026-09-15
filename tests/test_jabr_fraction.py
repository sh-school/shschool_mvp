"""[COMPLIANCE] جبرُ كسور الدرجات — المادّة 8.

المرجع: سياسة تقييم الطلبة للصفوف 4–11 (أغسطس 2015)، المادّة 8، صفحة 9
(الملفّ `04- سياسة تقييم الطلاب من الرابع حتى الحادي عشر.pdf`)، ونصُّها المصوَّر:

    «عند حساب درجات أية مادة من المواد الدراسية في منتصف الفصل أو نهايته أو
     الدور الثاني تطبق الأحكام الآتية لجبر الكسور:
     1- يجبر ما دون النصف إلى النصف.
     2- يثبت النصف.
     3- يجبر ما زاد على النصف إلى واحد صحيح.»

وسياسة الثاني عشر، المادّة 7، صفحة 5، بالنصّ نفسه.

تنبيه: لخّص `04_academic.md` هذه المادّةَ «أقل من نصف تُجبر لأسفل» — وليس في النصّ
تنزيلٌ أبداً. فالجولةُ الأولى بنت عليه `round_half_up` (2.5 ← 3، 2.4 ← 2) وهو
يُنقص الطالبَ في «ما دون النصف» ويزيده في «النصف» — خلافَ البندين 1 و2 كليهما.
والصحيح: 2.4 ← 2.5، و2.5 تثبت 2.5، و2.6 ← 3.
"""

from decimal import Decimal

import pytest

from assessments.models import (
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)
from assessments.services import GradeService
from core.domain.grades import jabr_fraction
from operations.models import Subject
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("2", "2"),  # لا كسر
        ("2.01", "2.5"),  # 1- ما دون النصف إلى النصف
        ("2.4", "2.5"),
        ("2.49", "2.5"),
        ("2.5", "2.5"),  # 2- يثبت النصف
        ("2.51", "3"),  # 3- ما زاد على النصف إلى واحد صحيح
        ("2.99", "3"),
        ("0.01", "0.5"),
        ("49.6", "50"),  # يبلغ النهايةَ الصغرى
        ("49.5", "49.5"),  # ولا يبلغها
    ],
)
def test_ten_values(raw, expected):
    assert jabr_fraction(Decimal(raw)) == Decimal(expected)


def test_none_stays_none():
    assert jabr_fraction(None) is None


def test_never_rounds_down_and_never_past_next_half():
    for hundredths in range(0, 10001):
        raw = Decimal(hundredths) / 100
        result = jabr_fraction(raw)
        assert raw <= result < raw + Decimal("0.5")
        assert (result * 2) % 1 == 0


# ── المواضعُ التي تغيّرت ─────────────────────────────────────────


def _package(school, teacher, grade, sem, ptype, weight):
    cg = ClassGroupFactory(school=school, grade=grade)
    subject = Subject.objects.create(school=school, name_ar="مادة", code=f"J{grade}{ptype}")
    setup = SubjectClassSetup.objects.create(
        school=school, subject=subject, class_group=cg, teacher=teacher, academic_year="2025-2026"
    )
    pkg = AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type=ptype,
        semester=sem,
        weight=Decimal(weight),
        semester_max_grade=Decimal("40") if sem == "S1" else Decimal("60"),
    )
    exam = Assessment.objects.create(
        package=pkg, school=school, title="اختبار", max_grade=Decimal("100"), status="published"
    )
    return setup, pkg, exam


@pytest.mark.django_db
@pytest.mark.parametrize(
    "pct,expected",
    [
        # P2 للثاني عشر = 40 كاملة: مجموعُ الفصل = النسبة × 0.4 — ويُجبر المجموع (م7)
        ("6.25", "2.5"),  # 2.5 تثبت
        ("6", "2.5"),  # 2.4 ← 2.5
        ("6.5", "3"),  # 2.6 ← 3
    ],
)
def test_semester_total_is_jabred_single_and_batch(school, teacher_user, pct, expected):
    """المساران المفرد والدُّفعي يكتبان مجموعَ الفصل مجبوراً — والباقةُ (نهايةُ الفصل) خامٌ."""
    setup, pkg, exam = _package(school, teacher_user, "G12", "S1", "P2", "100")
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=setup.class_group)
    StudentAssessmentGrade.objects.create(
        assessment=exam, student=student, school=school, grade=Decimal(pct)
    )
    raw = Decimal(pct) * Decimal("0.4")
    assert GradeService.calc_package_score(student, pkg) == raw.quantize(Decimal("0.01"))
    batch = GradeService.calc_package_scores_batch([student.id], [pkg])
    assert batch[(student.id, "P2")] == raw.quantize(Decimal("0.01"))

    single = GradeService.recalculate_semester_result(student, setup, "S1")
    assert single.total == Decimal(expected)
    GradeService.recalculate_full_class(setup)
    assert StudentSubjectResult.objects.get(pk=single.pk).total == Decimal(expected)


@pytest.mark.django_db
def test_annual_total_is_the_sum_of_jabred_semesters(school, teacher_user):
    """المجموعُ السنويّ = مجموعا الفصلين المجبوران (م8 «نهايته»): 20.1 ← 20.5، و29.5 تثبت.

    والحكمُ يُبنى من الدرجات لا من مجموعٍ مخزَّن — فلا تختلط في الشعبة قاعدتان."""
    setup, p2, e2 = _package(school, teacher_user, "G12", "S1", "P2", "100")
    (p4,) = GradeService.ensure_packages(setup, "S2")
    e4 = Assessment.objects.create(
        package=p4, school=school, title="نهاية ف2", max_grade=Decimal("60"), status="published"
    )
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=setup.class_group)
    StudentAssessmentGrade.objects.create(
        assessment=e2, student=student, school=school, grade=Decimal("50.25")
    )
    StudentAssessmentGrade.objects.create(
        assessment=e4, student=student, school=school, grade=Decimal("29.5")
    )
    annual = GradeService.recalculate_annual_result(student, setup)
    assert (annual.s1_total, annual.s2_total, annual.annual_total) == (
        Decimal("20.5"),
        Decimal("29.5"),
        Decimal("50"),
    )
    assert annual.status == "pass"


@pytest.mark.django_db
def test_two_and_a_half_stays(school, teacher_user):
    """الموجز طلب «2.5 ← 3»؛ والنصُّ «يثبت النصف» — فيُثبَت ويُوثَّق الخلاف."""
    setup, pkg, exam = _package(school, teacher_user, "G12", "S1", "P2", "100")
    student = UserFactory()
    StudentAssessmentGrade.objects.create(
        assessment=exam, student=student, school=school, grade=Decimal("6.25")
    )
    assert GradeService.recalculate_semester_result(student, setup, "S1").total == Decimal("2.5")
