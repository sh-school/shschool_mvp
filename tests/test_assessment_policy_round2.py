"""[COMPLIANCE 2.2 · جولة إصلاح 2] ما أثبتته المراجعةُ العدائيّة على الفرع.

الأصلُ: `04- سياسة تقييم الطلاب من الرابع حتى الحادي عشر.pdf` (أغسطس 2015) و`04- سياسة
تقييم الطلبة للصف الثاني عشر.pdf` في `data/2026-2027/03- الأكاديمي/`، وأرقامُ الصفحات
المطبوعة:

  م8 ص9 (4–11)  «عند حساب درجات أية مادة … في منتصف الفصل أو نهايته أو الدور الثاني»
  م7 ص5 (12)    «عند حساب درجات أي مادة … في نهاية كل فصل دراسي أو الدور الثاني»
  م19–21 ص20    الملحقُ يسبق الدورَ الثاني لمن عُذر عن نهاية الفصل الأول
  م22–23 ص21   الغيابُ بلا عذر عن الفصل الأول بكامله؛ وأكثرُ من ثلاث → «راسباً وباقياً للإعادة»
  م24 «ثالثاً»  الغيابُ عن جزءٍ من اختبار نهاية الفصل الثاني (وليس كليهما) → يُحكم بالمجموع
  م27 ص22      الغيابُ بلا عذر عن نهاية الثاني → الدرجةُ النهائيّة «غائب» ومن موادّ الرسوب
  م29 ص22–23  الحرمانُ بأيّام الغياب «اعتباراً من بداية العام الدراسي» حتّى الاختبار
  م50–51 ص33  قواعدُ الترفيع — الأوليان في الدور الأول، والثالثةُ «في الدور الثاني فقط»
  12: م13 وم16 ص10 — المعذورُ يُختبر في «منهاج الفصلين … ولا تحسب له درجات الفصل الأول»
"""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from assessments.models import (
    AnnualSubjectResult,
    Assessment,
    StudentAssessmentGrade,
    StudentSubjectResult,
    SubjectClassSetup,
)
from assessments.services import GradeService, SecondRoundService
from core.domain.grades import (
    DEPRIVED,
    EXCUSED,
    FAILED_ELIGIBLE,
    FAILED_INELIGIBLE,
    PASSED,
    PROMOTED,
    SECOND_ROUND_LABELS,
    SubjectOutcome,
    classify_first_round,
    second_round_credit,
    semester_total,
)
from operations.models import Subject
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

SUBJECTS = ("عربي", "إنجليزي", "رياضيات", "علوم", "إسلامية", "اجتماعيات")


def _o(totals, **flags):
    return [
        SubjectOutcome(
            subject=name,
            annual_total=None if t is None else Decimal(str(t)),
            excused_final_absence=name in flags.get("excused", ()),
            unexcused_final_absence=name in flags.get("unexcused", ()),
            unexcused_first_semester_absence=name in flags.get("unexcused_s1", ()),
        )
        for name, t in zip(SUBJECTS, totals, strict=True)
    ]


def _year(school):
    from core.academic_calendar import academic_year_for_school

    return academic_year_for_school(school)


def _setup(school, teacher, grade="G10", code="X", year=None):
    year = year or _year(school)
    cg = ClassGroupFactory(school=school, grade=grade, academic_year=year)
    subject = Subject.objects.create(school=school, name_ar=f"مادة {code}", code=code)
    return SubjectClassSetup.objects.create(
        school=school, subject=subject, class_group=cg, teacher=teacher, academic_year=year
    )


def _exam(pkg, max_grade, title="اختبار", **kw):
    return Assessment.objects.create(
        package=pkg,
        school=pkg.school,
        title=title,
        max_grade=Decimal(max_grade),
        status="published",
        **kw,
    )


def _grade(exam, student, value=None, absent=False, excused=False):
    return StudentAssessmentGrade.objects.create(
        assessment=exam,
        student=student,
        school=exam.school,
        grade=None if value is None else Decimal(str(value)),
        is_absent=absent or excused,
        is_excused=excused,
    )


# ═══ 1. موضعُ الجبر (م8 / م7) ═══════════════════════════════════════


@pytest.mark.django_db
@pytest.mark.parametrize("path", ["single", "batch"])
def test_jabr_on_subject_grade_not_on_each_package(school, teacher_user, path):
    """P1=7.1 AW=2.1 P2=9.1 · P3=7.1 AW=2.1 P4=20.1 — الخامُ من درجة كلّ باقة القصوى.

    جبرُ كلّ باقة: 19.5 + 30.5 = 50 «ناجح». وبالنصّ: المنتصفُ 7.5 ثمّ مجموعُ الفصل
    18.7 ← 19، والثاني 29.7 ← 30 = 49 راسب.
    """
    setup = _setup(school, teacher_user)
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=setup.class_group)
    # الدرجةُ القصوى لكلّ تقييم = درجةُ الباقة من الفصل: 15 · 5 · 20 ثمّ 15 · 5 · 40
    points = {("S1", "P1"): 15, ("S1", "AW"): 5, ("S1", "P2"): 20}
    points |= {("S2", "P3"): 15, ("S2", "AW"): 5, ("S2", "P4"): 40}
    raw = {("S1", "P1"): "7.1", ("S1", "AW"): "2.1", ("S1", "P2"): "9.1"}
    raw |= {("S2", "P3"): "7.1", ("S2", "AW"): "2.1", ("S2", "P4"): "20.1"}
    for sem in ("S1", "S2"):
        for pkg in GradeService.ensure_packages(setup, sem):
            _grade(
                _exam(pkg, points[(sem, pkg.package_type)]), student, raw[(sem, pkg.package_type)]
            )

    if path == "batch":
        GradeService.recalculate_full_class(setup)
    else:
        for sem in ("S1", "S2"):
            GradeService.recalculate_semester_result(student, setup, sem)
        GradeService.recalculate_annual_result(student, setup)

    s1 = StudentSubjectResult.objects.get(student=student, setup=setup, semester="S1")
    s2 = StudentSubjectResult.objects.get(student=student, setup=setup, semester="S2")
    assert (s1.p1_score, s1.p_aw_score, s1.p2_score) == (
        Decimal("7.50"),
        Decimal("2.10"),
        Decimal("9.10"),
    )
    assert (s1.total, s2.total) == (Decimal("19"), Decimal("30"))
    annual = AnnualSubjectResult.objects.get(student=student, setup=setup)
    assert (annual.annual_total, annual.status) == (Decimal("49"), "fail")


def test_semester_total_jabrs_once():
    # المنتصفُ 7.01 ← 7.5، ثمّ 7.5 + 7.01 + 4.01 = 18.52 ← 19 (لا 7.5 + 7.5 + 4.5 = 19.5)
    assert semester_total({"P1": "7.01", "P2": "7.01", "AW": "4.01"}) == Decimal("19")
    # 10.5 + 20.01 + 0.01 = 30.52 ← 31 (لا 10.5 + 20.5 + 0.5 = 31.5)؛ فالمجموعُ 50 لا 51
    assert semester_total({"P3": "10.01", "P4": "20.01", "AW": "0.01"}) == Decimal("31")
    assert semester_total({"P3": "10", "P4": "20", "AW": "0"}) == Decimal("30")


@pytest.mark.django_db
def test_gradebook_total_is_computed_from_its_own_cells(
    client_as, school, principal_user, teacher_user
):
    """مجموعٌ مخزَّنٌ قديم (37.30) لا يُعرض بجانب خلايا تساوي 19."""
    setup = _setup(school, teacher_user)
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=setup.class_group)
    points = {"P1": 15, "AW": 5, "P2": 20}
    raw = {"P1": "7.1", "AW": "2.1", "P2": "9.1"}
    for pkg in GradeService.ensure_packages(setup, "S1"):
        _grade(_exam(pkg, points[pkg.package_type]), student, raw[pkg.package_type])
    StudentSubjectResult.objects.create(
        student=student, setup=setup, school=school, semester="S1", total=Decimal("37.30")
    )

    resp = client_as(principal_user).get(f"/assessments/setup/{setup.id}/gradebook/?semester=S1")
    assert resp.status_code == 200
    (row,) = resp.context["rows"]
    assert row["sem_total"] == Decimal("19")
    assert "37.30" not in resp.content.decode()


@pytest.mark.django_db
def test_recalculate_button_refuses_a_closed_year(client_as, school, principal_user, teacher_user):
    start, end = (int(x) for x in _year(school).split("-"))
    setup = _setup(school, teacher_user, year=f"{start - 1}-{end - 1}")
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=setup.class_group)
    AnnualSubjectResult.objects.create(
        student=student,
        setup=setup,
        school=school,
        academic_year=setup.academic_year,
        s1_total=Decimal("20.1"),
        s2_total=Decimal("29.5"),
        annual_total=Decimal("49.60"),
        status="fail",
    )
    client_as(principal_user).post(f"/assessments/setup/{setup.id}/recalculate/")
    assert AnnualSubjectResult.objects.get(setup=setup).annual_total == Decimal("49.60")


@pytest.mark.django_db
def test_recalculate_command_is_current_year_and_audited(school, teacher_user, principal_user):
    from io import StringIO

    from django.core.management import call_command

    from core.models import AuditLog

    setup = _setup(school, teacher_user)
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=setup.class_group)
    points = {"P1": 15, "AW": 5, "P2": 20}
    raw = {"P1": "7.1", "AW": "2.1", "P2": "9.1"}
    for pkg in GradeService.ensure_packages(setup, "S1"):
        _grade(_exam(pkg, points[pkg.package_type]), student, raw[pkg.package_type])
    StudentSubjectResult.objects.create(
        student=student, setup=setup, school=school, semester="S1", total=Decimal("19.5")
    )
    call_command(
        "recalculate_grade_results",
        "--apply",
        "--actor",
        principal_user.national_id,
        "--school",
        school.code,
        stdout=StringIO(),
    )
    assert StudentSubjectResult.objects.get(setup=setup, semester="S1").total == Decimal("19")
    log = AuditLog.objects.get(changes__op="recalculate_grade_results")
    assert log.user == principal_user and log.changes["students"] == 1


# ═══ 2. قاعدتا الترفيع الأولى والثانية (م50) ═══════════════════════════


@pytest.mark.parametrize(
    "grade,totals,category,article",
    [
        (10, (48.5, 80, 70, 60, 55, 50), PROMOTED, "م50 القاعدة الأولى"),
        (9, (48, 80, 70, 60, 55, 50), PROMOTED, "م50 القاعدة الأولى"),
        (11, (47.5, 80, 70, 60, 55, 50), FAILED_ELIGIBLE, "م12-أ"),
        (10, (47, 46, 70, 60, 55, 50), PROMOTED, "م50 القاعدة الثانية"),
        (10, (46, 45.5, 70, 60, 55, 50), FAILED_ELIGIBLE, "م12-أ"),
        (10, (49, 49, 49, 60, 55, 50), FAILED_ELIGIBLE, "م12-أ"),
        # لا قواعدَ ترفيعٍ في سياسة الثاني عشر
        (12, (48.5, 80, 70, 60, 55, 50), FAILED_ELIGIBLE, "م8-أ"),
    ],
)
def test_promotion_rules_one_and_two(grade, totals, category, article):
    decision = classify_first_round(_o(totals), grade)
    assert (decision.category, decision.article) == (category, article)
    if category == PROMOTED:
        assert not decision.sits_second_round and decision.retake == ()
        assert decision.promoted == tuple(SUBJECTS[: sum(1 for t in totals if t < 50)])


def test_promotion_needs_a_grade_not_an_absence():
    """م27: المادّةُ «غائب» لا درجةَ لها يُقاس منها النقص."""
    decision = classify_first_round(_o((48.5, 80, 70, 60, 55, 50), unexcused=("إنجليزي",)), 10)
    assert decision.category == FAILED_ELIGIBLE


# ═══ 3. م23 قبل الحرمان ═══════════════════════════════════════════════


def test_m23_bars_before_deprivation():
    decision = classify_first_round(_o((None,) * 6, unexcused_s1=SUBJECTS[:5]), 10, deprived=True)
    assert (decision.category, decision.article) == (FAILED_INELIGIBLE, "م23")
    assert not decision.sits_second_round


def test_grade12_deprived_before_first_final_is_not_m15():
    """م19-1: المحرومُ من نهاية الفصل الأول غيابُه عنها «محروم» لا «غائب» (م20)."""
    decision = classify_first_round(
        _o((None,) * 6, unexcused_s1=SUBJECTS[:5]),
        12,
        deprived=True,
        deprived_before_first_final=True,
    )
    assert (decision.category, decision.article) == (DEPRIVED, "م19")


def test_deprived_label_is_not_a_verdict():
    assert SECOND_ROUND_LABELS[DEPRIVED] != "محروم"
    assert "فريق" in SECOND_ROUND_LABELS[DEPRIVED]


# ═══ 4. م16 للثاني عشر، وسقفُ المئة ══════════════════════════════════


def test_grade12_excused_carries_nothing():
    with pytest.raises(ValueError):
        second_round_credit(EXCUSED, 70, carried=34, grade=12)
    assert second_round_credit(EXCUSED, 70, grade=12) == (True, Decimal("70"))


@pytest.mark.parametrize("score,carried", [(70, 34), (101, 0)])
def test_credit_never_exceeds_full_mark(score, carried):
    with pytest.raises(ValueError):
        second_round_credit(EXCUSED, score, carried=carried, grade=10)


def test_failed_score_over_hundred_is_rejected():
    with pytest.raises(ValueError):
        second_round_credit(FAILED_ELIGIBLE, 120, grade=10)


# ═══ 5. الغيابُ عن الاختبار كلِّه لا عن جزئه (م24)، والملحق (م19–21) ════════


def _roster_class(school, teacher, grade="G10", n=2):
    year = _year(school)
    cg = ClassGroupFactory(school=school, grade=grade, academic_year=year)
    setups = [
        SubjectClassSetup.objects.create(
            school=school,
            subject=Subject.objects.create(school=school, name_ar=SUBJECTS[i], code=f"RT{i}"),
            class_group=cg,
            teacher=teacher,
            academic_year=year,
        )
        for i in range(n)
    ]
    return cg, setups, year


def _annual(student, setup, total, status=None):
    AnnualSubjectResult.objects.create(
        student=student,
        setup=setup,
        school=setup.school,
        academic_year=setup.academic_year,
        s1_total=Decimal("0"),
        s2_total=Decimal(total),
        annual_total=Decimal(total),
        status=status or ("pass" if Decimal(total) >= 50 else "fail"),
    )


def _pkg(setup, ptype):
    sem = "S1" if ptype in ("P1", "P2") else "S2"
    return next(p for p in GradeService.ensure_packages(setup, sem) if p.package_type == ptype)


@pytest.mark.django_db
def test_absence_from_one_part_of_the_final_is_judged_by_total(school, teacher_user):
    cg, (sci, other), year = _roster_class(school, teacher_user)
    p4 = _pkg(sci, "P4")
    theory, practical = _exam(p4, 30, "نظري"), _exam(p4, 10, "عملي")
    part_unexcused, part_excused, whole = UserFactory(), UserFactory(), UserFactory()
    for s in (part_unexcused, part_excused, whole):
        StudentEnrollmentFactory(student=s, class_group=cg)
        _annual(s, sci, "62")
        _annual(s, other, "80")
    _grade(theory, part_unexcused, 25)
    _grade(practical, part_unexcused, absent=True)
    _grade(theory, part_excused, 25)
    _grade(practical, part_excused, excused=True)
    _grade(theory, whole, absent=True)
    _grade(practical, whole, absent=True)

    rows = {r.student.id: r.decision for r in SecondRoundService.roster(cg, year)}

    assert rows[part_unexcused.id].category == PASSED
    assert rows[part_excused.id].category == PASSED
    assert (rows[whole.id].category, rows[whole.id].retake) == (
        FAILED_ELIGIBLE,
        (sci.subject.name_ar,),
    )


@pytest.mark.django_db
def test_excused_first_final_goes_to_makeup_not_second_round(school, teacher_user):
    """4–11: العذرُ عن P2 وحدَه يُحيل إلى الملحق (م19)، فيُحكم بالمجموع (م20)."""
    cg, (arabic, other), year = _roster_class(school, teacher_user)
    p2 = _exam(_pkg(arabic, "P2"), 20)
    good, weak = UserFactory(), UserFactory()
    for s, total in ((good, "71"), (weak, "42")):
        StudentEnrollmentFactory(student=s, class_group=cg)
        _grade(p2, s, excused=True)
        _annual(s, arabic, total)
        _annual(s, other, "80")

    rows = {r.student.id: r.decision for r in SecondRoundService.roster(cg, year)}

    assert rows[good.id].category == PASSED
    assert rows[weak.id].category == FAILED_ELIGIBLE
    assert rows[weak.id].failed == (arabic.subject.name_ar,)


@pytest.mark.django_db
def test_excused_whole_first_semester_and_grade12_final_go_to_second_round(school, teacher_user):
    cg, (arabic, other), year = _roster_class(school, teacher_user)
    p1, p2 = _exam(_pkg(arabic, "P1"), 15), _exam(_pkg(arabic, "P2"), 20)
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=cg)
    _grade(p1, student, excused=True)
    _grade(p2, student, excused=True)
    _annual(student, arabic, "30")
    _annual(student, other, "80")
    (row,) = SecondRoundService.roster(cg, year)
    assert (row.decision.category, row.decision.article) == (EXCUSED, "م12-ب")  # م21

    cg12, (math12, other12), _ = _roster_class(school, teacher_user, grade="G12")
    s12 = UserFactory()
    StudentEnrollmentFactory(student=s12, class_group=cg12)
    _grade(_exam(_pkg(math12, "P2"), 40), s12, excused=True)
    _annual(s12, math12, "30")
    _annual(s12, other12, "80")
    (row12,) = SecondRoundService.roster(cg12, year)
    assert (row12.decision.category, row12.decision.article) == (EXCUSED, "م8-ب")  # م13


# ═══ 6. الحالةُ المخزَّنة تطابق الشاشة (م27، م12-ب) ════════════════════════


@pytest.mark.django_db
@pytest.mark.parametrize(
    "flags,expected",
    [
        ({"absent": True}, (None, "fail")),  # م27: «غائب» ومن موادّ الرسوب
        ({"excused": True}, (Decimal("57.00"), "second_round")),  # م25
    ],
)
def test_stored_annual_status_reads_final_exam_absence(school, teacher_user, flags, expected):
    setup = _setup(school, teacher_user, grade="G9")
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=setup.class_group)
    _grade(_exam(_pkg(setup, "P4"), 40), student, **flags)
    for sem, total in (("S1", "38"), ("S2", "19")):
        StudentSubjectResult.objects.create(
            student=student, setup=setup, school=school, semester=sem, total=Decimal(total)
        )
    annual = GradeService.recalculate_annual_result(student, setup)
    annual.refresh_from_db()
    assert (annual.annual_total, annual.status) == expected
    failing = GradeService.get_failing_students(school, setup.academic_year)
    assert failing.filter(student=student).exists() == (expected[1] == "fail")


# ═══ 7. أيّامُ الحرمان حتّى عشيّة الاختبار وفي العام المعروض (م29) ═══════════


@pytest.mark.django_db
def test_deprivation_days_counted_at_the_exam_of_the_shown_year(school, teacher_user, monkeypatch):
    from core.models import AcademicYear, CalendarEvent, Semester

    start, end = (int(x) for x in _year(school).split("-"))
    past = f"{start - 1}-{end - 1}"
    year_obj = AcademicYear.objects.create(
        school=school, name=past, start_date=date(start - 1, 9, 1), end_date=date(end - 1, 6, 30)
    )
    s2 = Semester.objects.create(
        academic_year=year_obj,
        code="S2",
        start_date=date(end - 1, 1, 4),
        end_date=date(end - 1, 6, 30),
        max_grade=Decimal("60"),
    )
    exam_day = date(end - 1, 5, 24)
    CalendarEvent.objects.create(
        academic_year=year_obj,
        semester=s2,
        event_type="final_exam",
        name="اختبارات نهاية الفصل الثاني",
        start_date=exam_day,
        end_date=exam_day + timedelta(days=9),
        grade_scope="g10_11",
    )
    cg = ClassGroupFactory(school=school, grade="G10", academic_year=past)
    setup = SubjectClassSetup.objects.create(
        school=school,
        subject=Subject.objects.create(school=school, name_ar="عربي", code="DP"),
        class_group=cg,
        teacher=teacher_user,
        academic_year=past,
    )
    student = UserFactory()
    StudentEnrollmentFactory(student=student, class_group=cg)
    _annual(student, setup, "80")

    seen = []

    def fake_days(class_group, school_, on=None):
        seen.append(on)
        # 14 يوماً حتّى الاختبار، و17 إن عُدّ ما بعده
        return {student.id: 14 if on and on < exam_day else 17}

    monkeypatch.setattr("operations.absence_standing.unexcused_days_for_class", fake_days)

    (row,) = SecondRoundService.roster(cg, past)

    assert seen == [exam_day - timedelta(days=1)]
    assert row.decision.category == PASSED


# ═══ 8. الصلاحيّة: الكشفُ لمن نطاقُه المدرسة ═══════════════════════════════


@pytest.mark.django_db
def test_second_round_screen_is_not_open_to_department_scoped_roles(
    client_as, principal_user, coordinator_user, activities_coordinator_user
):
    assert client_as(coordinator_user).get("/assessments/second-round/").status_code == 403
    assert (
        client_as(activities_coordinator_user).get("/assessments/second-round/").status_code == 403
    )
    assert client_as(principal_user).get("/assessments/second-round/").status_code == 200


# ═══ 9. لا مسارَ بذرٍ يُنشئ باقاتٍ خارج `ensure_packages` ═══════════════════


def test_no_package_creation_outside_the_service():
    """بذرُ `seed_assessments` و`full_seed` كانا يُنشئان P1/P3 للثاني عشر بجدولٍ ثانٍ."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    pattern = re.compile(
        r"AssessmentPackage\.objects\.(create|get_or_create|update_or_create|bulk_create)\("
    )
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        parts = set(path.relative_to(root).parts)
        if parts & {"tests", "migrations", "node_modules", ".venv", "venv", ".git", "staticfiles"}:
            continue
        if rel == "assessments/services.py":
            continue
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore")):
            offenders.append(rel)
    assert offenders == []
