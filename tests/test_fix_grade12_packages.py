"""[COMPLIANCE 0.1] ترحيلُ باقات الثاني عشر القائمة — عرضٌ، فتطبيق، فتراجع.

المرجع: القرار 14/2018، المادّة 3 «ثالثاً: الصف الثاني عشر» (2018/06/06): الفصل
الأول 40 لاختبار نهاية الفصل، والثاني 60 لاختبار نهاية الفصل — `04_academic.md`
قسم 9. والباقاتُ المنشأةُ قبل التصحيح على بنية 4–11 (P1/P2/AW · P3/P4/AW)
تُطابَق بها، **إلّا** ما رُصد عليه تقييم: ذاك قرارُ مالكٍ لا يُحذف آليّاً.

والجولةُ الثانية: النطاقُ العامُ الجاري وحدَه، والفاعلُ إلزاميٌّ في السجلّ مع
الحالة السابقة، والتراجعُ يستعيد ما سجّله التطبيقُ لا بنيةً عامّة، والتطبيقُ
يعيد الفحصَ تحت القفل.
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


def _current(school):
    from core.academic_calendar import academic_year_for_school

    return academic_year_for_school(school)


def _past(school):
    start, end = (int(x) for x in _current(school).split("-"))
    return f"{start - 1}-{end - 1}"


def _old_structure_setup(school, teacher, grade="G12", code="M", year=None):
    """إعدادٌ بباقات 4–11 — كما أنشأتها الشاشةُ قبل التصحيح."""
    year = year or _current(school)
    cg = ClassGroupFactory(school=school, grade=grade, academic_year=year)
    subject = Subject.objects.create(school=school, name_ar=f"مادة {code}", code=code)
    setup = SubjectClassSetup.objects.create(
        school=school, subject=subject, class_group=cg, teacher=teacher, academic_year=year
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
            "semester", "package_type", "weight", "semester_max_grade"
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

    assert "إعداداتُ الثاني عشر (العامُ الجاري): 1 · تحتاج تصحيحاً: 1" in out
    assert "باقاتٌ زائدة تُحذف: 4 · باقاتٌ يُعاد وزنُها: 2" in out
    assert _structure(clean) == before


@pytest.mark.django_db
def test_apply_leaves_two_packages_and_recalculates(school, teacher_user, principal_user):
    setup = _old_structure_setup(school, teacher_user, code="A")
    student = _grade_on(setup, "P2", "S1", "75")  # 75٪ من 40 = 30 بعد التصحيح (لا 15)
    nid = principal_user.national_id

    _run("--apply", "--actor", nid)

    assert [(s, p, w) for s, p, w, _ in _structure(setup)] == [
        ("S1", "P2", Decimal("100.00")),
        ("S2", "P4", Decimal("100.00")),
    ]
    annual = AnnualSubjectResult.objects.get(student=student, setup=setup)
    assert annual.s1_total == Decimal("30.00")
    log = AuditLog.objects.get(object_id=str(setup.id), action="update")
    # الفاعلُ والحالةُ السابقة في السجلّ
    assert log.user == principal_user
    p2 = next(r for r in log.changes["reweighted"] if r["package_type"] == "P2")
    assert (p2["old_weight"], p2["weight"]) == ("50.00", "100")
    assert len(log.changes["deleted"]) == 4
    assert log.changes["recalculated_students"] == 1
    # متكرّرٌ بلا أثر
    assert "تحتاج تصحيحاً: 0" in _run("--apply", "--actor", nid)


@pytest.mark.django_db
def test_graded_p1_blocks_that_setup_only(school, teacher_user, principal_user):
    clean = _old_structure_setup(school, teacher_user, code="A")
    blocked = _old_structure_setup(school, teacher_user, code="B")
    _grade_on(blocked, "P1", "S1", "60")
    blocked_before = _structure(blocked)

    with pytest.raises(CommandError, match="محجوب"):
        _run("--apply", "--actor", principal_user.national_id)

    assert _structure(blocked) == blocked_before  # لا يُمسّ
    assert len(_structure(clean)) == 2  # والنظيفُ طُبِّق


@pytest.mark.django_db
def test_revert_restores_what_apply_recorded(school, teacher_user, principal_user):
    setup = _old_structure_setup(school, teacher_user, code="A")
    before = _structure(setup)
    nid = principal_user.national_id
    _run("--apply", "--actor", nid)
    assert len(_structure(setup)) == 2

    assert "عرضٌ فقط" in _run("--revert")
    assert len(_structure(setup)) == 2
    _run("--revert", "--apply", "--actor", nid)

    assert _structure(setup) == before
    # تراجعٌ واحدٌ لكلّ تطبيق
    assert "تراجع: 0 إعداداً" in _run("--revert")


# ── الجولة الثانية ────────────────────────────────────────────────


@pytest.mark.django_db
def test_apply_requires_an_actor(school, teacher_user):
    _old_structure_setup(school, teacher_user, code="A")
    with pytest.raises(CommandError, match="--actor"):
        _run("--apply")


@pytest.mark.django_db
def test_past_year_setups_are_not_touched(school, teacher_user, principal_user):
    """عامٌ مُغلق: لا يُعاد وزنُه ولا حسابُه، ولا تحجب الأمرَ درجةٌ مرصودةٌ فيه."""
    old = _old_structure_setup(school, teacher_user, code="OLD", year=_past(school))
    _grade_on(old, "P1", "S1", "60")
    before = _structure(old)

    out = _run("--apply", "--actor", principal_user.national_id)

    assert "(العامُ الجاري): 0" in out
    assert _structure(old) == before


@pytest.mark.django_db
def test_revert_leaves_correct_setups_alone(school, teacher_user, principal_user):
    """إعدادٌ أنشأه `ensure_packages` صحيحاً ورُصد عليه P2 لا يمسّه التراجع."""
    from assessments.services import GradeService

    nid = principal_user.national_id
    fixed = _old_structure_setup(school, teacher_user, code="A")
    _run("--apply", "--actor", nid)

    year = _current(school)
    cg = ClassGroupFactory(school=school, grade="G12", academic_year=year)
    subject = Subject.objects.create(school=school, name_ar="مادة سليمة", code="OK")
    good = SubjectClassSetup.objects.create(
        school=school, subject=subject, class_group=cg, teacher=teacher_user, academic_year=year
    )
    GradeService.ensure_packages(good, "S1")
    GradeService.ensure_packages(good, "S2")
    student = _grade_on(good, "P2", "S1", "95")
    GradeService.recalculate_full_class(good)
    good_before = _structure(good)

    _run("--revert", "--apply", "--actor", nid)

    assert _structure(good) == good_before
    assert AnnualSubjectResult.objects.get(student=student, setup=good).s1_total == Decimal("38")
    assert len(_structure(fixed)) == 6


@pytest.mark.django_db
def test_revert_restores_recorded_weights_not_defaults(school, teacher_user, principal_user):
    setup = _old_structure_setup(school, teacher_user, code="A")
    AssessmentPackage.objects.filter(setup=setup, package_type="P2").update(weight=Decimal("45"))
    before = _structure(setup)
    nid = principal_user.national_id
    _run("--apply", "--actor", nid)
    _run("--revert", "--apply", "--actor", nid)
    assert _structure(setup) == before


@pytest.mark.django_db
def test_revert_stops_when_grades_were_entered_after_apply(school, teacher_user, principal_user):
    setup = _old_structure_setup(school, teacher_user, code="A")
    nid = principal_user.national_id
    _run("--apply", "--actor", nid)
    _grade_on(setup, "P2", "S1", "80")
    after_apply = _structure(setup)

    with pytest.raises(CommandError, match="بعد التطبيق"):
        _run("--revert", "--apply", "--actor", nid)
    assert _structure(setup) == after_apply


@pytest.mark.django_db
def test_apply_rechecks_what_was_graded_after_the_plan(school, teacher_user, principal_user):
    """خطّةٌ عُرضت نظيفة، ثمّ رُصد تقييمٌ على P1 قبل التطبيق: لا يُحذف شيء."""
    from assessments.services import Grade12BlockedError, Grade12PackageFix

    setup = _old_structure_setup(school, teacher_user, code="A")
    (plan,) = Grade12PackageFix.plan()
    assert plan.changes and not plan.blocked
    _grade_on(setup, "P1", "S1", "70")
    before = _structure(setup)

    with pytest.raises(Grade12BlockedError):
        Grade12PackageFix.apply(setup, principal_user)
    assert _structure(setup) == before
    assert StudentAssessmentGrade.objects.filter(assessment__package__setup=setup).count() == 1
