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
15 منتصف · 5 أعمال · 20 نهاية = 40، ثمّ 15 · 5 · 40 = 60 — والبنيةُ والأوزانُ لا يمسّها
الفرع، **لكنّ مجاميعَها تتغيّر** بجبر الكسور (م8، البند 2.4): 18.30 صارت 19
(`test_grades_7_to_11_fractional_totals_change_by_article_8`). (تصحيح 2026-09-16.)
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
        # مادّةٌ واحدة دون الخمسين: دورٌ ثانٍ (م8-أ)، ولا قواعدَ ترفيعٍ للثاني عشر.
        assert r.status == ("pass" if r.annual_total >= 50 else "second_round")


@pytest.mark.django_db
def test_grades_7_to_11_regression_20_students(school, teacher_user):
    """انحدار: 20 طالباً في 7–11 — البنيةُ والأوزان كما قبل الفرع.

    نسبُه مضاعفاتُ عشرة، فمجاميعُه مضاعفاتُ نصفٍ لا يغيّرها الجبر — فهو لا يرى الجبر؛
    وأثرُ الجبر في الاختبار الكسريّ أدناه.
    """
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


# ── انحدارُ 7–11 بدرجاتٍ كسريّة: الفرعُ **يغيّر** مجاميعَهم بجبر المادّة 8 ─────────
#
# الاختبارُ أعلاه نسبُه مضاعفاتُ عشرة، فكلُّ مجموعٍ فيه مضاعفُ نصف ولا يرى الجبر. وهنا
# «القبلُ» هو معادلةُ الإيداع 7aaa42da بعينها (درجةُ الباقة = النسبة × الوزن × قصوى
# الفصل ÷ 10000 مقرّبةً إلى 0.01 نصفاً لأعلى، والفصلُ جمعُها، ولا جبر)، و«البعدُ» نصُّ
# م8 ص9: «يجبر ما دون النصف إلى النصف، يثبت النصف، يجبر ما زاد على النصف إلى واحد
# صحيح» — على المنتصف (P1/P3) ثمّ على مجموع الفصل، بالأوزان كسوراً دقيقة (P4 = 2/3).


def _jabr(x):
    import math
    from fractions import Fraction

    return Fraction(math.ceil(Fraction(x) * 2), 2)


def _dec(x):
    return Decimal(x.numerator) / Decimal(x.denominator)


def _before(pct):
    """معادلةُ 7aaa42da — `calc_package_score` ثمّ الجمع."""
    from decimal import ROUND_HALF_UP

    total = Decimal(0)
    for (sem, pt), p in pct.items():
        semester_max = Decimal(40) if sem == "S1" else Decimal(60)
        score = p * WEIGHTS_BEFORE[sem][pt] * semester_max / Decimal(10000)
        total += score.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return total


def _after(pct):
    """(الأول، الثاني) بنصّ م8 — مستقلٌّ عن شيفرة الفرع."""
    from fractions import Fraction

    f = {k: Fraction(v) / 100 for k, v in pct.items()}
    s1 = _jabr(_jabr(f[("S1", "P1")] * 15) + f[("S1", "AW")] * 5 + f[("S1", "P2")] * 20)
    s2 = _jabr(_jabr(f[("S2", "P3")] * 15) + f[("S2", "AW")] * 5 + f[("S2", "P4")] * 40)
    return _dec(s1), _dec(s2)


#: المثالُ المثبَّت: 81% و42% و20.25% في الأول ← 12.15 + 2.10 + 4.05 = 18.30 قبلُ،
#: و12.5 (منتصفٌ مجبور) + 2.1 + 4.05 = 18.65 ← 19 بعدُ؛ والثاني 34 في الحالين.
PINNED = {
    ("S1", "P1"): Decimal("81"),
    ("S1", "AW"): Decimal("42"),
    ("S1", "P2"): Decimal("20.25"),
    ("S2", "P3"): Decimal("80"),
    ("S2", "AW"): Decimal("40"),
    ("S2", "P4"): Decimal("50"),
}


def test_pinned_example_formulas():
    assert _before(PINNED) == Decimal("52.30")
    assert _after(PINNED) == (Decimal("19"), Decimal("34"))


@pytest.mark.django_db
def test_grades_7_to_11_fractional_totals_change_by_article_8(school, teacher_user):
    """20 طالباً في 7–11 بنسبٍ كسريّة: المخزَّنُ = م8، ويختلف عن «القبل» حيث يلزم."""
    cases = {}
    for gi, grade in enumerate(("G7", "G8", "G9", "G10", "G11")):
        setup = _setup(school, grade, teacher_user)
        exams = {}
        for sem in ("S1", "S2"):
            for p in GradeService.ensure_packages(setup, sem):
                exams[(sem, p.package_type)] = _exam(p)
        for k in range(4):
            student = UserFactory()
            StudentEnrollmentFactory(student=student, class_group=setup.class_group)
            if gi == 0 and k == 0:
                pct = PINNED
            else:
                pct = {
                    key: Decimal((n * 373 + gi * 97 + k * 211) % 1000) / 10
                    for n, key in enumerate(exams)
                }
            for key, exam in exams.items():
                StudentAssessmentGrade.objects.create(
                    assessment=exam, student=student, school=school, grade=pct[key]
                )
            cases[(setup.id, student.id)] = (setup, pct)

    for setup in {s for s, _ in cases.values()}:
        GradeService.recalculate_full_class(setup)

    changed = 0
    results = AnnualSubjectResult.objects.filter(setup__in={s for s, _ in cases.values()})
    assert results.count() == 20
    for r in results:
        _, pct = cases[(r.setup_id, r.student_id)]
        s1, s2 = _after(pct)
        assert (r.s1_total, r.s2_total, r.annual_total) == (s1, s2, s1 + s2), pct
        # الجبرُ لا يُنزل أبداً؛ و«القبل» يزيد على الدقيق بتقريب ستّ باقاتٍ لا غير.
        assert r.annual_total >= _before(pct) - Decimal("0.05")
        changed += r.annual_total != _before(pct)
        if pct is PINNED:
            assert (_before(pct), r.annual_total) == (Decimal("52.30"), Decimal("53"))
    # الفرعُ يغيّر مجاميعَ 4–11 ذواتِ الكسور — لا «لا تغيير».
    assert changed >= 15, changed
