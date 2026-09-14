"""[COMPLIANCE 0.1] ترحيلُ باقات الثاني عشر القائمة — عرضٌ، فتطبيق، فتراجع.

المرجع: القرار 14/2018، المادّة 3 «ثالثاً: الصف الثاني عشر» (2018/06/06): الفصل
الأول 40 لاختبار نهاية الفصل، والثاني 60 لاختبار نهاية الفصل — `04_academic.md`
قسم 9. والباقاتُ المنشأةُ قبل التصحيح على بنية 4–11 (P1/P2/AW · P3/P4/AW)
تُطابَق بها، **إلّا** ما رُصد عليه تقييم: ذاك قرارُ مالكٍ لا يُحذف آليّاً.
"""

from decimal import Decimal
from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from assessments.models import (
    AnnualSubjectResult,
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    SubjectClassSetup,
)
from core.domain.grades import package_weights
from core.models import AuditLog
from operations.models import Subject
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory


def _old_structure_setup(school, teacher, grade="G12", code="M"):
    """إعدادٌ بباقات 4–11 — كما أنشأتها الشاشةُ قبل التصحيح."""
    cg = ClassGroupFactory(school=school, grade=grade)
    subject = Subject.objects.create(school=school, name_ar=f"مادة {code}", code=code)
    setup = SubjectClassSetup.objects.create(
        school=school, subject=subject, class_group=cg, teacher=teacher, academic_year="2025-2026"
    )
    for sem, max_grade in (("S1", Decimal("40")), ("S2", Decimal("60"))):
        for ptype, weight in package_weights(11, sem).items():
            AssessmentPackage.objects.create(
                setup=setup,
                school=school,
                package_type=ptype,
                semester=sem,
                weight=weight,
                semester_max_grade=max_grade,
            )
    return setup


def _grade_on(setup, ptype, sem, pct):
    pkg = AssessmentPackage.objects.get(setup=setup, package_type=ptype, semester=sem)
    exam = Assessment.objects.create(
        package=pkg,
        school=setup.school,
        title="اختبار",
        max_grade=Decimal("100"),
        status="published",
    )
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=setup.class_group)
    StudentAssessmentGrade.objects.create(
        assessment=exam, student=student, school=setup.school, grade=Decimal(pct)
    )
    return student


def _structure(setup):
    return sorted(
        AssessmentPackage.objects.filter(setup=setup).values_list(
            "semester", "package_type", "weight"
        )
    )


def _run(*args):
    out = StringIO()
    call_command("fix_grade12_packages", *args, stdout=out)
    return out.getvalue()


@pytest.mark.django_db
def test_dry_run_counts_and_changes_nothing(school, teacher_user):
    clean = _old_structure_setup(school, teacher_user, code="A")
    _old_structure_setup(school, teacher_user, grade="G11", code="B")  # ليس من الثاني عشر
    before = _structure(clean)

    out = _run("--dry-run")

    assert "إعداداتُ الثاني عشر: 1 · تحتاج تصحيحاً: 1" in out
    assert "باقاتٌ زائدة تُحذف: 4 · باقاتٌ يُعاد وزنُها: 2" in out
    assert _structure(clean) == before


@pytest.mark.django_db
def test_apply_leaves_two_packages_and_recalculates(school, teacher_user):
    setup = _old_structure_setup(school, teacher_user, code="A")
    student = _grade_on(setup, "P2", "S1", "75")  # 75٪ من 40 = 30 بعد التصحيح (لا 15)

    _run("--apply")

    assert _structure(setup) == [("S1", "P2", Decimal("100.00")), ("S2", "P4", Decimal("100.00"))]
    annual = AnnualSubjectResult.objects.get(student=student, setup=setup)
    assert annual.s1_total == Decimal("30.00")
    assert AuditLog.objects.filter(object_id=str(setup.id), action="update").count() == 1
    # متكرّرٌ بلا أثر
    assert "تحتاج تصحيحاً: 0" in _run("--apply")


@pytest.mark.django_db
def test_graded_p1_blocks_that_setup_only(school, teacher_user):
    clean = _old_structure_setup(school, teacher_user, code="A")
    blocked = _old_structure_setup(school, teacher_user, code="B")
    _grade_on(blocked, "P1", "S1", "60")
    blocked_before = _structure(blocked)

    with pytest.raises(CommandError, match="محجوب"):
        _run("--apply")

    assert _structure(blocked) == blocked_before  # لا يُمسّ
    assert len(_structure(clean)) == 2  # والنظيفُ طُبِّق


@pytest.mark.django_db
def test_revert_restores_general_structure(school, teacher_user):
    setup = _old_structure_setup(school, teacher_user, code="A")
    before = _structure(setup)
    _run("--apply")
    assert len(_structure(setup)) == 2

    assert "عرضٌ فقط" in _run("--revert")
    assert len(_structure(setup)) == 2
    _run("--revert", "--apply")

    assert _structure(setup) == before
