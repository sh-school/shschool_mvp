"""[COMPLIANCE 2.2] الدورُ الثاني — الأهليّة، والموقف، وحسابُ درجة الناجح.

المرجع: سياسة تقييم الطلبة للصفوف 4–11 (أغسطس 2015)، الفصل الثاني، صفحة 18 —
`04_academic.md` قسم 1؛ والثاني عشر بالنصّ نفسه في سياسته صفحتا 7–8 (قسم 3):

    م12 (12: م8)  «يسمح بدخول اختبار الدور الثاني للفئات الآتية:
                   أ- الطلبة الراسبون في ثلاث مواد دراسية أو أقل.
                   ب- الطلبة المتغيبون … عن تأدية اختبارات نهاية الفصل الدراسي
                      الأول أو الثاني بعذر مقبول.
                   ج- الطلبة الذين يجمعون بين الرسوب والغياب بعذر مقبول …
                      يختبرون فيما رسبوا فيه وفيما تغيبوا عنه.»
    م13 (12: م9)  «لا يسمح بدخول اختبار الدور الثاني للطلبة المتغيبين (بدون عذر)
                   عن اختبارات نهاية الفصل الدراسي الثاني في أكثر من ثلاث مواد.»
    م16 (12: م12) «1. الراسب … النهاية الصغرى للمادة فقط. 2. (المعذور) … الدرجة
                   التي يحصل عليها في الدور الثاني. 3. (المحروم) … النهاية الصغرى
                   للمادة فقط.»
    م29-4 (12: م19-2): المحرومُ من الدور الأول «يسمح له بدخول اختبار الدور الثاني
                   بواقع 100% من النهاية العظمى» — بقرارٍ مسجَّلٍ لفريق السلوك.

والحكمُ كلُّه في `core.domain.grades.judge_student` (جولة 4): الاختباراتُ هنا تبني
وقائعَ الطالب وتقرأ موقفَه وموضعَه وموادَّ دوره الثاني.
"""

from __future__ import annotations

from decimal import Decimal
from fractions import Fraction

import pytest

from core.domain.grades import (
    SITTING_STATUSES,
    STATUS_DEPRIVED,
    STATUS_EXCUSED,
    STATUS_SECOND_ROUND,
    ExamFacts,
    SubjectFacts,
    judge_student,
    second_round_credit,
)

SUBJECTS = ("عربي", "إنجليزي", "رياضيات", "علوم", "إسلامية", "اجتماعيات")


def facts(name, total, grade, excused=False, unexcused=False, unexcused_s1=False):
    """وقائعُ مادّةٍ تبلغ مجموعاً معلوماً: الفصلُ الأول صفر، والثاني المجموعُ كلُّه."""
    s1 = {"P2": ExamFacts(Fraction(0), Fraction(20))}
    if unexcused_s1:
        s1 = {"P2": ExamFacts(Fraction(0), Fraction(20), absent_share=Fraction(1))}
        if grade != 12:
            s1["P1"] = ExamFacts(Fraction(0), Fraction(15), absent_share=Fraction(1))
    if excused:
        s2 = {"P4": ExamFacts(None, Fraction(40), excused_share=Fraction(1))}
    elif unexcused:
        s2 = {"P4": ExamFacts(Fraction(0), Fraction(40), absent_share=Fraction(1))}
    elif total is None:
        s2 = {}
    else:
        s2 = {"P4": ExamFacts(Fraction(Decimal(str(total))), Fraction(40))}
    if grade != 12:
        # بقيّةُ بنية القرار 14/2018 م3 مرصودةٌ صفراً — باقةٌ غيرُ مرصودة «غير مكتمل» (جولة 7).
        s1 = {"P1": ExamFacts(Fraction(0), Fraction(15)), "AW": ZERO_AW, **s1}
        if s2:
            s2 = {"P3": ExamFacts(Fraction(0), Fraction(15)), "AW": ZERO_AW, **s2}
    return SubjectFacts(name, s1, s2)


ZERO_AW = ExamFacts(Fraction(0), Fraction(5))


def student(totals, grade, excused=(), unexcused=(), unexcused_s1=()):
    return [
        facts(n, t, grade, n in excused, n in unexcused, n in unexcused_s1)
        for n, t in zip(SUBJECTS, totals, strict=True)
    ]


def retake(verdict):
    return tuple(v.key for v in verdict.subjects if v.status in SITTING_STATUSES)


P, SR, F, INC = "passed", "second_round", "failed", "incomplete"

# (الوصف، الصفّ، الموادّ، معذورٌ فيها، غائبٌ بلا عذر، محروم؟) → (الموقف، الموضع، موادُّ الدور الثاني)
SAMPLE = [
    ("كلّها فوق الخمسين", 10, (90, 80, 70, 60, 55, 50), (), (), False, P, "م10–11", ()),
    ("خمسون تماماً ناجحة", 12, (50, 50, 50, 50, 50, 50), (), (), False, P, "م6", ()),
    ("درجاتٌ عالية", 7, (99, 98, 97, 96, 95, 94), (), (), False, P, "م10–11", ()),
    (
        "مادّةٌ 47.5 — نقصُها فوق درجتين",
        8,
        (47.5, 80, 70, 60, 55, 50),
        (),
        (),
        False,
        SR,
        "م12-أ",
        ("عربي",),
    ),
    (
        "مادّتان إحداهما صفر",
        9,
        (0, 30, 70, 60, 55, 50),
        (),
        (),
        False,
        SR,
        "م12-أ",
        ("عربي", "إنجليزي"),
    ),
    ("ثلاثُ موادّ — الحدّ", 11, (10, 20, 30, 60, 55, 50), (), (), False, SR, "م12-أ", SUBJECTS[:3]),
    ("ثلاثٌ في الثاني عشر", 12, (49, 49, 49, 60, 55, 50), (), (), False, SR, "م8-أ", SUBJECTS[:3]),
    (
        "غيابٌ بلا عذر في مادّة",
        10,
        (70, 80, 70, 60, 55, 50),
        (),
        ("علوم",),
        False,
        SR,
        "م12-أ",
        ("علوم",),
    ),
    ("أربعُ موادّ", 10, (40, 45, 48, 49, 55, 50), (), (), False, F, "م12-أ", ()),
    ("ستُّ موادّ", 7, (1, 2, 3, 4, 5, 6), (), (), False, F, "م12-أ", ()),
    ("أربعٌ في الثاني عشر", 12, (10, 10, 10, 10, 90, 90), (), (), False, F, "م8-أ", ()),
    ("غيابٌ بلا عذر في أربع — م13", 11, (60,) * 6, (), SUBJECTS[:4], False, F, "م13", ()),
    ("غيابٌ بلا عذر في أربع — م9", 12, (60,) * 6, (), SUBJECTS[:4], False, F, "م9", ()),
    ("معذورٌ في مادّة", 9, (None, 80, 70, 60, 55, 50), ("عربي",), (), False, SR, "م12-ب", ("عربي",)),
    ("معذورٌ في كلّ الموادّ", 10, (None,) * 6, SUBJECTS, (), False, SR, "م12-ب", SUBJECTS),
    (
        "راسبٌ ومعذور — م12-ج",
        8,
        (30, None, 70, 60, 55, 50),
        ("إنجليزي",),
        (),
        False,
        SR,
        "م12-ج",
        ("عربي", "إنجليزي"),
    ),
    (
        "معذورٌ في الثاني عشر",
        12,
        (None, 80, 70, 60, 55, 50),
        ("عربي",),
        (),
        False,
        SR,
        "م8-ب",
        ("عربي",),
    ),
    ("محرومٌ بقرار", 10, (80,) * 6, (), (), True, SR, "م29-4", SUBJECTS),
    ("محرومٌ في الثاني عشر", 12, (80,) * 6, (), (), True, SR, "م19-2", SUBJECTS),
    ("مادّةٌ لم تُرصد", 10, (None, 80, 70, 60, 55, 50), (), (), False, INC, "", ()),
]


def test_sample_is_twenty_and_covers_every_standing():
    assert len(SAMPLE) == 20
    assert {row[6] for row in SAMPLE} == {P, SR, F, INC}


@pytest.mark.parametrize(
    "desc,grade,totals,excused,unexcused,deprived,standing,article,retake_",
    SAMPLE,
    ids=[row[0] for row in SAMPLE],
)
def test_first_round(desc, grade, totals, excused, unexcused, deprived, standing, article, retake_):
    gates = frozenset({"s2_final"}) if deprived else frozenset()
    verdict = judge_student(grade, student(totals, grade, excused, unexcused), gates)
    assert verdict.standing == standing, desc
    assert verdict.article == article, desc
    assert retake(verdict) == tuple(retake_), desc
    if deprived:
        assert {v.status for v in verdict.subjects} == {STATUS_DEPRIVED}
        assert {v.mark for v in verdict.subjects} == {"deprived"}


@pytest.mark.parametrize(
    "desc,grade,kwargs,standing,article",
    [
        # م23 (4–11 ص21) / م15 (12 ص10)
        ("غيابٌ بلا عذر عن الفصل الأول في أربع", 9, {"unexcused_s1": SUBJECTS[:4]}, F, "م23"),
        ("وفي الثاني عشر", 12, {"unexcused_s1": SUBJECTS[:4]}, F, "م15"),
        # م22: ثلاثٌ فأقلّ «تحسب ضمن مواد الرسوب» فيبقى مؤهَّلاً بم12-أ
        ("غيابٌ بلا عذر عن الفصل الأول في ثلاث", 9, {"unexcused_s1": SUBJECTS[:3]}, SR, "م12-أ"),
    ],
)
def test_bars_beyond_the_twenty(desc, grade, kwargs, standing, article):
    verdict = judge_student(grade, student((60,) * 6, grade, **kwargs))
    assert (verdict.standing, verdict.article) == (standing, article), desc


@pytest.mark.parametrize("grade,article", [(10, "م45 مكرر"), (12, "م33 مكرر")])
def test_cancelled_bars_the_second_round(grade, article):
    verdict = judge_student(grade, student((60,) * 6, grade), cancelled=True)
    assert (verdict.standing, verdict.article) == (F, article)


def test_no_invented_minimum_grade_for_eligibility():
    """م12-أ لا تشترط درجةً دنيا: الصفرُ في مادّةٍ واحدة يؤهّل كالسبعة والأربعين."""
    zero = judge_student(10, student((0, 90, 90, 90, 90, 90), 10))
    near = judge_student(10, student((47, 90, 90, 90, 90, 90), 10))
    assert zero.standing == near.standing == SR


# ── م16 (12: م12): درجةُ الناجح في الدور الثاني ─────────────────


@pytest.mark.parametrize(
    "kind,score,expected",
    [
        (STATUS_SECOND_ROUND, 83, (True, Decimal("50"))),  # م16-1: الصغرى فقط
        (STATUS_SECOND_ROUND, 50, (True, Decimal("50"))),
        (STATUS_SECOND_ROUND, 49, (False, Decimal("49"))),
        (STATUS_EXCUSED, 83, (True, Decimal("83"))),  # م16-2: الدرجةُ التي حصل عليها
        (STATUS_EXCUSED, 49.2, (False, Decimal("49.5"))),  # م8: الجبرُ قبل الحكم
        (STATUS_EXCUSED, 49.6, (True, Decimal("50"))),
        (STATUS_DEPRIVED, 100, (True, Decimal("50"))),  # م16-3: الصغرى فقط
        (STATUS_DEPRIVED, 12, (False, Decimal("12"))),
    ],
)
def test_second_round_credit(kind, score, expected):
    assert second_round_credit(kind, score, grade=10) == expected


@pytest.mark.parametrize(
    "score,carried,expected",
    [
        # م25 (ص22): معذورٌ عن نهاية ف2 وحدَها — حصّل 40 واختبارُ دوره من 40.
        (Decimal("12"), Decimal("40"), (True, Decimal("52"))),
        (Decimal("9.2"), Decimal("40"), (False, Decimal("49.5"))),
        # م21: معذورٌ عن الفصل الأول كلِّه والملحق — من مئة ولا محمول
        (Decimal("64"), Decimal("0"), (True, Decimal("64"))),
    ],
)
def test_excused_credit_adds_what_was_earned(score, carried, expected):
    assert second_round_credit(STATUS_EXCUSED, score, carried, grade=10) == expected


def test_carried_is_ignored_for_failed_and_deprived():
    assert second_round_credit(STATUS_SECOND_ROUND, 50, carried=45, grade=10) == (
        True,
        Decimal("50"),
    )
    assert second_round_credit(STATUS_DEPRIVED, 49, carried=45, grade=10) == (False, Decimal("49"))


def test_combined_student_statuses_per_subject():
    """م12-ج + م16: الجامعُ يُعيد ما رسب فيه راسباً، وما عُذر عنه معذوراً."""
    verdict = judge_student(8, student((30, None, 70, 60, 55, 50), 8, excused=("إنجليزي",)))
    by = verdict.by_key()
    assert (by["عربي"].status, by["إنجليزي"].status) == (STATUS_SECOND_ROUND, STATUS_EXCUSED)


def test_passed_subject_has_no_second_round_credit():
    with pytest.raises(ValueError):
        second_round_credit("pass", 70, grade=10)


# ── الخدمةُ والشاشة ────────────────────────────────────────────


def _setup_class(school, teacher, n_subjects=4):
    from assessments.models import SubjectClassSetup
    from core.academic_calendar import academic_year_for_school
    from operations.models import Subject
    from tests.conftest import ClassGroupFactory

    year = academic_year_for_school(school)
    cg = ClassGroupFactory(school=school, grade="G10", academic_year=year)
    setups = [
        SubjectClassSetup.objects.create(
            school=school,
            subject=Subject.objects.create(school=school, name_ar=SUBJECTS[i], code=f"SR{i}"),
            class_group=cg,
            teacher=teacher,
            academic_year=year,
        )
        for i in range(n_subjects)
    ]
    return cg, setups, year


def _grades(setup, student, p4=None, p4_absent=False, p4_excused=False, s1=Decimal("0")):
    """الفصلُ الأول P2 (من 20) والثاني P4 (من 40) — وبقيّةُ البنية مرصودةٌ صفراً (جولة 7)."""
    from assessments.models import Assessment, StudentAssessmentGrade
    from assessments.services import GradeService

    for sem, ptype, value, absent, excused in (
        ("S1", "P1", 0, False, False),
        ("S1", "AW", 0, False, False),
        ("S1", "P2", s1, False, False),
        ("S2", "P3", 0, False, False),
        ("S2", "AW", 0, False, False),
        ("S2", "P4", p4, p4_absent, p4_excused),
    ):
        pkg = next(p for p in GradeService.ensure_packages(setup, sem) if p.package_type == ptype)
        exam, _ = Assessment.objects.get_or_create(
            package=pkg,
            title=ptype,
            defaults={
                "school": setup.school,
                "max_grade": pkg.effective_max_grade,
                "status": "published",
            },
        )
        StudentAssessmentGrade.objects.create(
            assessment=exam,
            student=student,
            school=setup.school,
            grade=None if value is None else Decimal(str(value)),
            is_absent=absent or excused,
            is_excused=excused,
        )


@pytest.mark.django_db
def test_roster_reads_the_stored_verdict(school, teacher_user):
    from assessments.services import GradeService, SecondRoundService
    from tests.conftest import StudentEnrollmentFactory, UserFactory

    cg, setups, year = _setup_class(school, teacher_user)
    passer, failer, excused, absentee = UserFactory(), UserFactory(), UserFactory(), UserFactory()
    for s in (passer, failer, excused, absentee):
        StudentEnrollmentFactory(student=s, class_group=cg)
    for i, setup in enumerate(setups):
        _grades(setup, passer, 35, s1=20)
        _grades(setup, failer, "29.2", s1=20)  # 49.2 ← 49.5: ما زال دون الخمسين
        if i == 0:
            _grades(setup, excused, p4_excused=True, s1=20)
            _grades(setup, absentee, p4_absent=True, s1=20)
        else:
            _grades(setup, excused, 35, s1=20)
            _grades(setup, absentee, 35, s1=20)
    GradeService.recalculate_full_class(setups[0])

    rows, _ = SecondRoundService.roster(cg, year)
    by = {r.student.id: r for r in rows}
    assert by[passer.id].standing == "passed"
    assert by[failer.id].standing == "failed"  # أربعُ موادّ راسبة
    assert (by[excused.id].standing, by[excused.id].retake) == ("second_round", [SUBJECTS[0]])
    # م27: الغيابُ بلا عذر عن نهاية الثاني — «غائب» ومن موادّ الرسوب، ويُعيدها.
    assert (by[absentee.id].standing, by[absentee.id].retake) == ("second_round", [SUBJECTS[0]])


@pytest.mark.django_db
def test_second_round_screen(client_as, school, teacher_user, principal_user):
    from assessments.services import GradeService
    from tests.conftest import StudentEnrollmentFactory, UserFactory

    cg, setups, year = _setup_class(school, teacher_user, n_subjects=2)
    student = UserFactory(full_name="طالبُ الدور الثاني")
    StudentEnrollmentFactory(student=student, class_group=cg)
    _grades(setups[0], student, 10, s1=20)
    _grades(setups[1], student, 35, s1=20)
    GradeService.recalculate_full_class(setups[0])

    resp = client_as(principal_user).get(f"/assessments/second-round/?class_group={cg.id}")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "طالبُ الدور الثاني" in body and "م12-أ" in body

    assert client_as(teacher_user).get("/assessments/second-round/").status_code == 403
