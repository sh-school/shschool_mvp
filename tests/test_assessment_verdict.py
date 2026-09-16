"""[COMPLIANCE 0.1 · 2.2 · جولة إصلاح 4] الحكمُ الواحد — يُحسب في `judge_student` ويُخزَّن.

الأصل: `data/2026-2027/03- الأكاديمي/04- سياسة تقييم الطلاب من الرابع حتى الحادي عشر.pdf`
(أغسطس 2015) و`04- سياسة تقييم الطلبة للصف الثاني عشر.pdf`، بأرقام الصفحات المطبوعة:

  4–11  م17 ص20  المعذورُ عن المنتصف «يختبر في نهاية الفصل بواقع 100% من الدرجة المخصصة للفصل»
        م18 ص20  المعذورُ عن الفصل الأول بكامله «يجرى له اختبار ملحق … بواقع 100%»
        م21 ص20  «بكامله والملحق» ← الدورُ الثاني
        م29–30 ص22–23  المحرومُ «يرصد له كلمة "محروم"» لا «غائب»
        م50 ص33  القاعدةُ الثالثة «في الدور الثاني فقط»، والأوليان بلا قيدِ دور
  12    م13 ص10  «ب- لا يسمح له بدخول اختبار الفصل الدراسي الثاني … ويعتبر معذوراً فيها»
  م8 ص9 (12: م7 ص5) — «يجبر ما دون النصف إلى النصف» على القيمة الدقيقة.

كلُّ اختبارٍ هنا يستورد الجديدَ داخلَه، فيُجمع على الشيفرة القديمة ويسقط فيها بعينه.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from io import BytesIO, StringIO

import pytest

from assessments.models import (
    AnnualSubjectResult,
    Assessment,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)
from assessments.services import GradeService
from operations.models import Subject
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

NAMES = ("عربي", "إنجليزي", "رياضيات", "علوم", "إسلامية", "اجتماعيات")

#: قصوى كلّ تقييمٍ = درجةُ باقته من الفصل، فالدرجةُ الخامُ هي درجةُ الباقة.
MARKS = {
    ("S1", "P1"): 15,
    ("S1", "P2"): 20,
    ("S1", "AW"): 5,
    ("S2", "P3"): 15,
    ("S2", "P4"): 40,
    ("S2", "AW"): 5,
}
MARKS_12 = {("S1", "P2"): 40, ("S2", "P4"): 60}

#: درجاتٌ تبلغ مجاميعَ معلومة — (P1, P2, AW1, P3, P4, AW2).
T80 = (12, 16, 4, 12, 32, 4)
T90 = (13.5, 18, 4.5, 13.5, 36, 4.5)
T30 = (5, 5, 2, 5, 10, 3)
T48_5 = (7.5, 10, 2, 7, 20, 2)  # 19.5 + 29


def _year(school):
    from core.academic_calendar import academic_year_for_school

    return academic_year_for_school(school)


def _class(school, teacher, grade="G10", n=6, year=None, code="V"):
    year = year or _year(school)
    cg = ClassGroupFactory(school=school, grade=grade, academic_year=year)
    setups = [
        SubjectClassSetup.objects.create(
            school=school,
            subject=Subject.objects.create(school=school, name_ar=NAMES[i], code=f"{code}{i}"),
            class_group=cg,
            teacher=teacher,
            academic_year=year,
        )
        for i in range(n)
    ]
    return cg, setups


def _exams(setup):
    grade12 = setup.class_group.grade == "G12"
    table = MARKS_12 if grade12 else MARKS
    out = {}
    for sem in ("S1", "S2"):
        for pkg in GradeService.ensure_packages(setup, sem):
            out[(sem, pkg.package_type)] = Assessment.objects.create(
                package=pkg,
                school=pkg.school,
                title=f"{sem}-{pkg.package_type}",
                max_grade=Decimal(table[(sem, pkg.package_type)]),
                status="published",
            )
    return out


def _mark(exam, student, value=None, absent=False, excused=False):
    return StudentAssessmentGrade.objects.update_or_create(
        assessment=exam,
        student=student,
        defaults={
            "school": exam.school,
            "grade": None if value is None else Decimal(str(value)),
            "is_absent": absent or excused,
            "is_excused": excused,
        },
    )[0]


def _fill(exams, student, values):
    keys = (("S1", "P1"), ("S1", "P2"), ("S1", "AW"), ("S2", "P3"), ("S2", "P4"), ("S2", "AW"))
    for key, value in zip(keys, values, strict=True):
        if value == "excused":
            _mark(exams[key], student, excused=True)
        elif value == "absent":
            _mark(exams[key], student, absent=True)
        elif value is not None:
            _mark(exams[key], student, value)


def _student(cg, name=None):
    student = UserFactory(full_name=name) if name else UserFactory()
    StudentEnrollmentFactory(student=student, class_group=cg)
    return student


def _annual(student, setup):
    return AnnualSubjectResult.objects.get(student=student, setup=setup)


# ═══ م17 — المعذورُ عن منتصف الفصل: النهايةُ بواقع 100% من الفصل ═════════════


def test_m17_excused_midterm_takes_the_semester_from_the_final(school, teacher_user):
    """معذورٌ عن P1، و16 من 20 في P2، و5 في الأعمال: 80% من الأربعين = 32 لا 21."""
    cg, (setup,) = _class(school, teacher_user, n=1)
    exams, student = _exams(setup), _student(cg)
    _fill(exams, student, ("excused", 16, 5, 12, 32, 4))
    GradeService.recalculate_full_class(setup)
    s1 = StudentSubjectResult.objects.get(student=student, setup=setup, semester="S1")
    assert s1.total == Decimal("32")
    annual = _annual(student, setup)
    assert (annual.annual_total, annual.status) == (Decimal("80"), "pass")


# ═══ م18/م21 — العذرُ عن الفصل الأول كلِّه: الملحقُ قبل الدور الثاني ═══════════


def test_m18_whole_first_semester_excused_waits_for_the_makeup_then_counts_it(school, teacher_user):
    cg, (setup, other) = _class(school, teacher_user, n=2)
    exams, student = _exams(setup), _student(cg)
    _fill(exams, student, ("excused", "excused", 4, 12, 32, 4))
    _fill(_exams(other), student, T80)
    GradeService.recalculate_full_class(setup)
    annual = _annual(student, setup)
    assert annual.status == "makeup"
    assert annual.standing == "incomplete"

    p2 = exams[("S1", "P2")].package
    makeup = Assessment.objects.create(
        package=p2,
        school=school,
        title="الملحق",
        assessment_type="makeup",
        max_grade=Decimal("40"),
        status="published",
    )
    _mark(makeup, student, 30)
    GradeService.recalculate_full_class(setup)
    annual = _annual(student, setup)
    # «بواقع 100% من الدرجة المخصصة للفصل الدراسي الأول»: 30 من 40، والأعمالُ لا تُضاف.
    assert (annual.s1_total, annual.annual_total, annual.status) == (
        Decimal("30"),
        Decimal("78"),
        "pass",
    )


def test_m21_excused_from_the_makeup_too_goes_to_second_round(school, teacher_user):
    cg, (setup, other) = _class(school, teacher_user, n=2)
    exams, student = _exams(setup), _student(cg)
    # مُنع من الفصل الثاني في المادّة (م21)، فرُصد «غائب» في P4 — لا يُقرأ.
    _fill(exams, student, ("excused", "excused", 4, None, "absent", None))
    _fill(_exams(other), student, T80)
    makeup = Assessment.objects.create(
        package=exams[("S1", "P2")].package,
        school=school,
        title="الملحق",
        assessment_type="makeup",
        max_grade=Decimal("40"),
        status="published",
    )
    _mark(makeup, student, excused=True)
    GradeService.recalculate_full_class(setup)
    annual = _annual(student, setup)
    assert (annual.status, annual.mark, annual.article) == ("excused", "excused", "م21")
    assert annual.standing == "second_round"


# ═══ م29–م30 — المحرومُ بقرارٍ ليس «غائباً» ═══════════════════════════════════


def test_deprived_from_first_semester_exams_is_not_m23(school, teacher_user):
    from assessments.models import ExamDeprivation

    cg, setups = _class(school, teacher_user, grade="G9", n=5)
    student = _student(cg)
    for setup in setups:
        _fill(_exams(setup), student, ("absent", "absent", 4, 13, 34, 5))
    for gate in ("s1_midterm", "s1_final"):
        ExamDeprivation.objects.create(
            school=school,
            student=student,
            academic_year=setups[0].academic_year,
            gate=gate,
            decided_on=date.today(),
        )
    GradeService.recalculate_full_class(setups[0])
    rows = list(AnnualSubjectResult.objects.filter(student=student))
    assert {r.article for r in rows} != {"م22"}
    assert all(r.standing != "failed" for r in rows)


def test_threshold_without_a_team_decision_is_a_warning_not_a_verdict(
    client_as, school, principal_user, teacher_user, monkeypatch
):
    from assessments.services import SecondRoundService

    cg, setups = _class(school, teacher_user, n=2)
    student = _student(cg)
    for setup in setups:
        exams = _exams(setup)
        _fill(exams, student, T80)
        exams[("S2", "P4")].date = date(2027, 5, 20)
        exams[("S2", "P4")].save(update_fields=["date"])
        exams[("S1", "P2")].date = date(2027, 1, 5)
        exams[("S1", "P2")].save(update_fields=["date"])
    GradeService.recalculate_full_class(setups[0])
    monkeypatch.setattr(
        "operations.absence_standing.unexcused_days_for_class",
        lambda class_group, school_, on=None: {student.id: 16},
    )
    rows, _ = SecondRoundService.roster(cg)
    (row,) = rows
    assert row.standing == "passed" and not row.sits_second_round
    assert any("لم يُسجَّل قرارُ فريق السلوك" in w for w in row.warnings)
    assert {r.status for r in _annual_rows(student)} == {"pass"}


def _annual_rows(student):
    return AnnualSubjectResult.objects.filter(student=student)


def test_exam_eve_is_unknown_without_a_date_not_today(school, teacher_user):
    from assessments.services import SecondRoundService

    cg, setups = _class(school, teacher_user, grade="G12", n=1)
    assert SecondRoundService.exam_eve(cg, setups[0].academic_year, "s1_final", setups) is None
    _, warnings = SecondRoundService.roster(cg)
    assert any("غير محدَّد — يحتاج تاريخ الاختبار" in w for w in warnings)


# ═══ م13-ب (12) وم21 (4–11) — الممنوعُ من الفصل الثاني ليس غائباً بلا عذر ════════


def test_grade12_excused_first_final_is_not_counted_absent_in_second_semester(school, teacher_user):
    cg, setups = _class(school, teacher_user, grade="G12", n=5)
    student = _student(cg)
    for i, setup in enumerate(setups):
        exams = _exams(setup)
        if i < 4:
            _mark(exams[("S1", "P2")], student, excused=True)
            _mark(exams[("S2", "P4")], student, absent=True)  # مُنع من دخوله
        else:
            _mark(exams[("S1", "P2")], student, 32)
            _mark(exams[("S2", "P4")], student, 48)
    GradeService.recalculate_full_class(setups[0])
    rows = {r.setup_id: r for r in _annual_rows(student)}
    assert [rows[s.id].status for s in setups[:4]] == ["excused"] * 4
    assert rows[setups[4].id].status == "pass"
    assert {r.standing for r in rows.values()} == {"second_round"}
    assert not GradeService.get_failing_students(school).filter(student=student).exists()


# ═══ م50 — القاعدةُ الثالثة في الدور الثاني، والأولى بلا قيدِ دور ══════════════


def test_rule_three_promotes_after_second_round_and_keeps_the_obtained_grade(school, teacher_user):
    cg, setups = _class(school, teacher_user, n=4)
    student = _student(cg)
    _fill(_exams(setups[0]), student, T30)
    for setup in setups[1:]:
        _fill(_exams(setup), student, T90)
    GradeService.recalculate_full_class(setups[0])
    physics = _annual(student, setups[0])
    assert (physics.status, physics.standing) == ("second_round", "second_round")

    physics.second_round_score = Decimal("44")
    physics.save(update_fields=["second_round_score"])
    GradeService.recalculate_full_class(setups[0])
    physics = _annual(student, setups[0])
    assert (physics.status, physics.annual_total, physics.article) == (
        "promoted",
        Decimal("44"),
        "م50 القاعدة الثالثة",
    )
    assert physics.standing == "promoted"


def test_rule_one_applies_to_the_second_round_too():
    from fractions import Fraction

    from core.domain.grades import ExamFacts, SecondRoundFacts, SubjectFacts, judge_student

    def subject(key, s1, s2, second=None):
        mid, aw = ExamFacts(Fraction(0), Fraction(15)), ExamFacts(Fraction(0), Fraction(5))
        return SubjectFacts(
            key,
            {"P1": mid, "AW": aw, "P2": ExamFacts(Fraction(s1), Fraction(20))},
            {"P3": mid, "AW": aw, "P4": ExamFacts(Fraction(s2), Fraction(40))},
            second_round=None if second is None else SecondRoundFacts(Fraction(second)),
        )

    subjects = [subject("ف", 10, 10, "48.5")] + [subject(str(i), 20, 40) for i in range(3)]
    verdict = judge_student(10, subjects)
    assert verdict.standing == "promoted"
    assert verdict.by_key()["ف"].article == "م50 القاعدة الأولى"


# ═══ الجبرُ على الكسر الدقيق — لا قصَّ قبله ════════════════════════════════════


def test_jabr_is_on_the_exact_semester_total_not_a_cent_truncation(school, teacher_user):
    """P1=7.5 وP2=7.5 وأعمالٌ من تقييمين متساويين 9.01 و9.00 من 10: الخامُ 19.5025 ← 20."""
    cg, (setup,) = _class(school, teacher_user, n=1)
    student = _student(cg)
    for pkg in GradeService.ensure_packages(setup, "S1"):
        if pkg.package_type == "AW":
            for title, value in (("أ", "9.01"), ("ب", "9.00")):
                exam = Assessment.objects.create(
                    package=pkg,
                    school=school,
                    title=title,
                    max_grade=Decimal("10"),
                    weight_in_package=Decimal("50"),
                    status="published",
                )
                _mark(exam, student, value)
        else:
            exam = Assessment.objects.create(
                package=pkg,
                school=school,
                title=pkg.package_type,
                max_grade=Decimal(MARKS[("S1", pkg.package_type)]),
                status="published",
            )
            _mark(exam, student, "7.5")
    GradeService.recalculate_full_class(setup)
    s1 = StudentSubjectResult.objects.get(student=student, setup=setup, semester="S1")
    assert s1.total == Decimal("20")


# ═══ البذر — لا أوزانَ فوق المئة ═══════════════════════════════════════════════


def test_reseeding_an_old_structure_aligns_or_stops(school, teacher_user):
    from assessments.models import AssessmentPackage
    from assessments.services import PackageStructureError

    cg, (clean, graded) = _class(school, teacher_user, n=2)
    for setup in (clean, graded):
        for ptype in ("P1", "P4"):
            AssessmentPackage.objects.create(
                setup=setup,
                school=school,
                package_type=ptype,
                semester="S1",
                weight=Decimal("50"),
                semester_max_grade=Decimal("40"),
            )
    GradeService.align_packages(clean, "S1")
    weights = dict(
        AssessmentPackage.objects.filter(setup=clean, semester="S1").values_list(
            "package_type", "weight"
        )
    )
    assert weights == {"P1": Decimal("37.50"), "P2": Decimal("50.00"), "AW": Decimal("12.50")}

    p1 = AssessmentPackage.objects.get(setup=graded, package_type="P1")
    exam = Assessment.objects.create(package=p1, school=school, title="x", status="published")
    _mark(exam, _student(cg), 5)
    with pytest.raises(PackageStructureError):
        GradeService.align_packages(graded, "S1")
    assert AssessmentPackage.objects.filter(setup=graded, semester="S1").count() == 2


# ═══ المخزَّنُ وحدَه يُعرض — سجلُّ الدرجات وExcel كالكشف والشهادة ═══════════════


def test_gradebook_and_excel_show_the_stored_total(client_as, school, principal_user, teacher_user):
    cg, (setup,) = _class(school, teacher_user, n=1)
    student = _student(cg)
    exams = _exams(setup)
    _fill(exams, student, (7.9, 9.9, 2, None, None, None))
    StudentSubjectResult.objects.create(
        student=student, setup=setup, school=school, semester="S1", total=Decimal("19.80")
    )
    resp = client_as(principal_user).get(f"/assessments/setup/{setup.id}/gradebook/?semester=S1")
    (row,) = resp.context["rows"]
    assert row["sem_total"] == Decimal("19.80")

    from openpyxl import load_workbook

    resp = client_as(principal_user).get(f"/assessments/setup/{setup.id}/export/?semester=S1")
    ws = load_workbook(BytesIO(resp.content)).active
    totals = [c.value for c in ws[3]]
    assert 19.8 in totals


# ═══ الأعوامُ المغلقة مجمَّدة ══════════════════════════════════════════════════


def test_closed_year_refuses_writes_from_every_path(
    client_as, school, principal_user, teacher_user
):
    from assessments.services import ClosedYearError

    start, end = (int(x) for x in _year(school).split("-"))
    cg, (setup,) = _class(school, teacher_user, n=1, year=f"{start - 1}-{end - 1}", code="C")
    student = _student(cg)
    exams = _exams(setup)
    _mark(exams[("S1", "P2")], student, 10)
    AnnualSubjectResult.objects.create(
        student=student,
        setup=setup,
        school=school,
        academic_year=setup.academic_year,
        annual_total=Decimal("49.60"),
        status="fail",
    )
    with pytest.raises(ClosedYearError):
        GradeService.save_grade(exams[("S1", "P2")], student, Decimal("20"))
    with pytest.raises(ClosedYearError):
        GradeService.recalculate_full_class(setup)

    exam = exams[("S1", "P2")]
    client_as(principal_user).post(
        f"/assessments/assessment/{exam.id}/save-all/", {f"grade_{student.id}": "20"}
    )
    assert StudentAssessmentGrade.objects.get(assessment=exam, student=student).grade == 10
    assert _annual(student, setup).annual_total == Decimal("49.60")


# ═══ الأمر — عرضٌ بمن يتغيّر، وسجلٌّ قبل الكتابة، ومعاملةٌ للمدرسة ════════════════


def _stale(school, teacher_user):
    cg, (setup,) = _class(school, teacher_user, n=1, code="R")
    student = _student(cg)
    _fill(_exams(setup), student, T80)
    GradeService.recalculate_full_class(setup)
    AnnualSubjectResult.objects.filter(student=student).update(
        annual_total=Decimal("79.40"), status="pass"
    )
    return cg, setup, student


def test_command_shows_who_changes_and_writes_nothing_by_default(school, teacher_user):
    from django.core.management import call_command

    from core.models import AuditLog

    _, setup, student = _stale(school, teacher_user)
    out = StringIO()
    call_command("recalculate_grade_results", "--school", school.code, stdout=out)
    text = out.getvalue()
    assert "annual_total: 79.40 → 80" in text and str(student.id) in text
    assert _annual(student, setup).annual_total == Decimal("79.40")
    assert not AuditLog.objects.filter(changes__op="recalculate_grade_results").exists()


def test_command_audits_before_and_after_of_every_changed_total(
    school, teacher_user, principal_user
):
    from django.core.management import call_command

    from core.models import AuditLog

    _, setup, student = _stale(school, teacher_user)
    call_command(
        "recalculate_grade_results",
        "--apply",
        "--actor",
        principal_user.national_id,
        "--school",
        school.code,
        stdout=StringIO(),
    )
    assert _annual(student, setup).annual_total == Decimal("80")
    log = AuditLog.objects.get(changes__op="recalculate_grade_results")
    (row,) = log.changes["rows"]
    assert row["before"]["annual_total"] == "79.40" and row["after"]["annual_total"] == "80.00"
    assert row["before"]["status"] == row["after"]["status"] == "pass"


def test_command_is_one_transaction_per_school(school, teacher_user, principal_user, monkeypatch):
    from django.core.management import call_command

    from assessments.services import VerdictPlan
    from core.models import AuditLog

    _, setup_a, student_a = _stale(school, teacher_user)
    _, setup_b, student_b = _stale(school, teacher_user)
    real = VerdictPlan.write
    calls = {"n": 0}

    def flaky(self, actor=None, audit=True):
        calls["n"] += 1
        if calls["n"] == 2:  # الشعبةُ الثانية — بعد السجلّ والأولى
            raise RuntimeError("انقطاع")
        return real(self, actor=actor, audit=audit)

    monkeypatch.setattr(VerdictPlan, "write", flaky)
    with pytest.raises(RuntimeError):
        call_command(
            "recalculate_grade_results",
            "--apply",
            "--actor",
            principal_user.national_id,
            "--school",
            school.code,
            stdout=StringIO(),
        )
    assert _annual(student_a, setup_a).annual_total == Decimal("79.40")
    assert _annual(student_b, setup_b).annual_total == Decimal("79.40")
    assert not AuditLog.objects.filter(changes__op="recalculate_grade_results").exists()


# ═══ الحكمُ الواحد — الشاشةُ وقائمةُ الراسبين والكشفُ والشهادةُ ولوحةُ المدير وبوّابةُ وليّ الأمر ═══


def test_every_consumer_agrees_on_promoted_second_round_deprived_and_excused(
    client_as, school, principal_user, teacher_user
):
    from assessments.models import ExamDeprivation
    from assessments.services import SecondRoundService
    from core.views_dashboard import _get_director_ctx
    from parents.services import ParentService
    from reports.services import ReportDataService
    from reports.views import _set_final_status

    cg, setups = _class(school, teacher_user, n=3, code="A")
    promoted, retaker, deprived, excused = (
        _student(cg, name) for name in ("المُرفَّع", "المُعيد", "المحروم", "المعذور")
    )
    exams = [_exams(setup) for setup in setups]
    for student, first in (
        (promoted, T48_5),
        (retaker, T30),
        (deprived, T80),
        (excused, (12, 16, 4, 12, "excused", 4)),
    ):
        for i, subject_exams in enumerate(exams):
            _fill(subject_exams, student, first if i == 0 else T80)
    ExamDeprivation.objects.create(
        school=school,
        student=deprived,
        academic_year=setups[0].academic_year,
        gate="s2_final",
        decided_on=date.today(),
    )
    GradeService.recalculate_full_class(setups[0])

    expected = {
        promoted.id: ("promoted", "ناجح بالترفيع", False, False),
        retaker.id: ("second_round", "دور ثانٍ", True, True),
        deprived.id: ("second_round", "دور ثانٍ", False, True),
        excused.id: ("second_round", "دور ثانٍ", False, True),
    }

    # الشاشة
    rows, _ = SecondRoundService.roster(cg)
    screen = {r.student.id: (r.standing, r.sits_second_round) for r in rows}
    # قائمةُ الراسبين
    failing = set(GradeService.get_failing_students(school).values_list("student_id", flat=True))
    # كشفُ الفصل
    sheet = {
        r["student"].id: r["status"]
        for r in ReportDataService.get_class_results(cg, school)["student_rows"]
    }
    for student in (promoted, retaker, deprived, excused):
        standing, label, is_failing, sits = expected[student.id]
        assert screen[student.id] == (standing, sits)
        assert (student.id in failing) is is_failing
        assert sheet[student.id] == label
        # الشهادة
        ctx = ReportDataService.get_student_report(student, school)
        _set_final_status(ctx)
        assert ctx["final_status"] == label
        # بوّابةُ وليّ الأمر
        grades = ParentService.get_student_grades(student, school)
        assert grades["standing"] == standing
        assert grades["failed"] == (1 if is_failing else 0)

    # لوحةُ المدير: من له مادّةٌ راسبة
    assert _get_director_ctx(school, date.today())["failing_count"] == 1
    # وصفحةُ قائمة الراسبين
    body = client_as(principal_user).get("/assessments/failing/").content.decode()
    assert retaker.full_name in body and promoted.full_name not in body


# ═══ سقّاطةُ mypy — لا زيادةَ في assessments/services.py ═══════════════════════


def test_services_signatures_are_typed():
    import inspect

    from assessments.services import Grade12PackageFix, SecondRoundService

    for fn in (Grade12PackageFix._plan_for, Grade12PackageFix.plan, SecondRoundService.exam_eve):
        params = inspect.signature(fn).parameters.values()
        assert all(p.annotation is not inspect.Parameter.empty for p in params), fn
