"""[COMPLIANCE 2.2] الدورُ الثاني — الأهليّة، والصنف، وحسابُ درجة الناجح.

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
    م29، الصفّ الأخير (12: م19): المحرومُ من الدور الأول بالغياب «مع السماح بدخول
                   الدور الثاني بواقع 100% من النهاية العظمى».

ومواضعُ الاستخراج: `04_academic.md:48-52` و`:65` و`:175-179`؛
`04b_academic_deep_part1.md:1884-1898` (الدليل التعريفي 4–11 ص23) و`:2028-2042`
(الثاني عشر ص35) و`:1908-1910` و`:1925-1929` و`:2052-2053` (أحكام الغياب).
وقُرئت الصفحاتُ المصوَّرة للمادّتين 23 (4–11 ص21) و15 (الثاني عشر ص10): «أكثر من
ثلاث مواد» بدون عذر — وكان `04b:1910` قد نقلها «بعذر … ثلاث مواد أو أكثر» فصُحِّح.

وما كان في الجولة الأولى ولا أصلَ له في النصّ فأُزيل: «راسبٌ مؤهَّل = 40–49»
و«غيرُ مؤهَّل = أقلّ من 40» — الأهليّةُ بعدد الموادّ لا بدرجةٍ دنيا.
"""

from decimal import Decimal

import pytest

from core.domain.grades import (
    DEPRIVED,
    EXCUSED,
    FAILED_ELIGIBLE,
    FAILED_INELIGIBLE,
    INCOMPLETE,
    PASSED,
    SubjectOutcome,
    classify_first_round,
    second_round_credit,
)

SUBJECTS = ("عربي", "إنجليزي", "رياضيات", "علوم", "إسلامية", "اجتماعيات")


def _student(totals, excused=(), unexcused=(), unexcused_s1=()):
    return [
        SubjectOutcome(
            subject=name,
            annual_total=None if t is None else Decimal(str(t)),
            excused_final_absence=name in excused,
            unexcused_final_absence=name in unexcused,
            unexcused_first_semester_absence=name in unexcused_s1,
        )
        for name, t in zip(SUBJECTS, totals, strict=True)
    ]


# (الوصف، الصفّ، الموادّ، معذورٌ فيها، غائبٌ بلا عذر، محروم؟) → (الصنف، الموضع، موادُّ الدور الثاني)
SAMPLE = [
    # ── ناجح: م10–11 (م6 للثاني عشر) — لا مادّةَ دون الخمسين
    ("كلّها فوق الخمسين", 10, (90, 80, 70, 60, 55, 50), (), (), False, PASSED, "م10–11", ()),
    ("خمسون تماماً ناجحة", 12, (50, 50, 50, 50, 50, 50), (), (), False, PASSED, "م6", ()),
    ("درجاتٌ عالية", 7, (99, 98, 97, 96, 95, 94), (), (), False, PASSED, "م10–11", ()),
    # ── راسبٌ مؤهَّل: م12-أ «ثلاث مواد دراسية أو أقل»
    (
        "مادّةٌ واحدة 47.5 — نقصُها فوق درجتين فلا ترفّعه م50",
        8,
        (47.5, 80, 70, 60, 55, 50),
        (),
        (),
        False,
        FAILED_ELIGIBLE,
        "م12-أ",
        ("عربي",),
    ),
    (
        "مادّتان، إحداهما صفر",
        9,
        (0, 30, 70, 60, 55, 50),
        (),
        (),
        False,
        FAILED_ELIGIBLE,
        "م12-أ",
        ("عربي", "إنجليزي"),
    ),
    (
        "ثلاثُ موادّ — الحدّ",
        11,
        (10, 20, 30, 60, 55, 50),
        (),
        (),
        False,
        FAILED_ELIGIBLE,
        "م12-أ",
        ("عربي", "إنجليزي", "رياضيات"),
    ),
    (
        "ثلاثٌ في الثاني عشر",
        12,
        (49, 49, 49, 60, 55, 50),
        (),
        (),
        False,
        FAILED_ELIGIBLE,
        "م8-أ",
        ("عربي", "إنجليزي", "رياضيات"),
    ),
    (
        "غيابٌ بلا عذر في مادّةٍ واحدة",
        10,
        (70, 80, 70, 60, 55, 50),
        (),
        ("علوم",),
        False,
        FAILED_ELIGIBLE,
        "م12-أ",
        ("علوم",),
    ),
    # ── راسبٌ غيرُ مؤهَّل: أكثرُ من ثلاث (م12-أ بمفهومها) أو م13
    ("أربعُ موادّ", 10, (40, 45, 48, 49, 55, 50), (), (), False, FAILED_INELIGIBLE, "م12-أ", ()),
    ("ستُّ موادّ", 7, (1, 2, 3, 4, 5, 6), (), (), False, FAILED_INELIGIBLE, "م12-أ", ()),
    (
        "أربعٌ في الثاني عشر",
        12,
        (10, 10, 10, 10, 90, 90),
        (),
        (),
        False,
        FAILED_INELIGIBLE,
        "م8-أ",
        (),
    ),
    (
        "غيابٌ بلا عذر في أربع — م13",
        11,
        (60, 60, 60, 60, 60, 60),
        (),
        SUBJECTS[:4],
        False,
        FAILED_INELIGIBLE,
        "م13",
        (),
    ),
    (
        "غيابٌ بلا عذر في أربع — م9",
        12,
        (60, 60, 60, 60, 60, 60),
        (),
        SUBJECTS[:4],
        False,
        FAILED_INELIGIBLE,
        "م9",
        (),
    ),
    # ── معذور: م12-ب، والجامعُ م12-ج يختبر فيما رسب وفيما تغيّب
    (
        "معذورٌ في مادّة",
        9,
        (None, 80, 70, 60, 55, 50),
        ("عربي",),
        (),
        False,
        EXCUSED,
        "م12-ب",
        ("عربي",),
    ),
    ("معذورٌ في كلّ الموادّ", 10, (None,) * 6, SUBJECTS, (), False, EXCUSED, "م12-ب", SUBJECTS),
    (
        "راسبٌ ومعذور — م12-ج",
        8,
        (30, None, 70, 60, 55, 50),
        ("إنجليزي",),
        (),
        False,
        EXCUSED,
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
        EXCUSED,
        "م8-ب",
        ("عربي",),
    ),
    # ── محروم: م29 / م19 — يدخل الدورَ الثاني في كلّ الموادّ
    ("محرومٌ بالغياب", 10, (None,) * 6, (), (), True, DEPRIVED, "م29", SUBJECTS),
    ("محرومٌ في الثاني عشر", 12, (None,) * 6, (), (), True, DEPRIVED, "م19", SUBJECTS),
    # ── ما لم يكتمل لا يُحكم عليه
    ("مادّةٌ لم تُرصد", 10, (None, 80, 70, 60, 55, 50), (), (), False, INCOMPLETE, "", ()),
]


def test_sample_is_twenty_and_covers_all_five_categories():
    assert len(SAMPLE) == 20
    assert {row[6] for row in SAMPLE} >= {
        PASSED,
        FAILED_ELIGIBLE,
        FAILED_INELIGIBLE,
        EXCUSED,
        DEPRIVED,
    }


@pytest.mark.parametrize(
    "desc,grade,totals,excused,unexcused,deprived,category,article,retake",
    SAMPLE,
    ids=[row[0] for row in SAMPLE],
)
def test_first_round_classification(
    desc, grade, totals, excused, unexcused, deprived, category, article, retake
):
    decision = classify_first_round(_student(totals, excused, unexcused), grade, deprived)
    assert decision.category == category, desc
    assert decision.article == article, desc
    assert decision.retake == tuple(retake), desc
    assert decision.sits_second_round == (category in (FAILED_ELIGIBLE, EXCUSED, DEPRIVED))


@pytest.mark.parametrize(
    "desc,grade,kwargs,category,article",
    [
        # م23 (4–11 ص21) / م15 (12 ص10) — `04b_academic_deep_part1.md:1910`, `:2053`
        (
            "غيابٌ بلا عذر عن الفصل الأول في أربع",
            9,
            {"unexcused_s1": SUBJECTS[:4]},
            FAILED_INELIGIBLE,
            "م23",
        ),
        ("وفي الثاني عشر", 12, {"unexcused_s1": SUBJECTS[:4]}, FAILED_INELIGIBLE, "م15"),
        # م22: ثلاثٌ فأقلّ «تحسب ضمن مواد الرسوب» فيبقى مؤهَّلاً بم12-أ
        (
            "غيابٌ بلا عذر عن الفصل الأول في ثلاث",
            9,
            {"unexcused_s1": SUBJECTS[:3]},
            FAILED_ELIGIBLE,
            "م12-أ",
        ),
        # م45 مكرر — `04_academic.md:143`، و«لا يحق له دخول اختبارات الدور الثاني» `04b:1975`
        ("ملغي", 10, {"cancelled": True}, FAILED_INELIGIBLE, "م45 مكرر"),
        # م33 مكرر للثاني عشر — `04_academic.md:145`
        ("ملغي في الثاني عشر", 12, {"cancelled": True}, FAILED_INELIGIBLE, "م33 مكرر"),
    ],
)
def test_bars_beyond_the_twenty(desc, grade, kwargs, category, article):
    cancelled = kwargs.pop("cancelled", False)
    outcomes = _student((60, 60, 60, 60, 60, 60), **kwargs)
    decision = classify_first_round(outcomes, grade, cancelled=cancelled)
    assert (decision.category, decision.article) == (category, article), desc


def test_no_invented_minimum_grade_for_eligibility():
    """م12-أ لا تشترط درجةً دنيا: الصفرُ في مادّةٍ واحدة يؤهّل كالتسعة والأربعين."""
    zero = classify_first_round(_student((0, 90, 90, 90, 90, 90)), 10)
    near = classify_first_round(_student((47, 90, 90, 90, 90, 90)), 10)
    assert zero.category == near.category == FAILED_ELIGIBLE


# ── م16 (12: م12): درجةُ الناجح في الدور الثاني ─────────────────


@pytest.mark.parametrize(
    "kind,score,expected",
    [
        (FAILED_ELIGIBLE, 83, (True, Decimal("50"))),  # م16-1: الصغرى فقط
        (FAILED_ELIGIBLE, 50, (True, Decimal("50"))),
        (FAILED_ELIGIBLE, 49, (False, Decimal("49"))),  # لم ينجح: درجتُه كما هي
        (EXCUSED, 83, (True, Decimal("83"))),  # م16-2: الدرجةُ التي حصل عليها
        (EXCUSED, 49.2, (False, Decimal("49.5"))),  # م8: الجبرُ قبل الحكم
        (EXCUSED, 49.6, (True, Decimal("50"))),
        (DEPRIVED, 100, (True, Decimal("50"))),  # م16-3: الصغرى فقط
        (DEPRIVED, 12, (False, Decimal("12"))),
    ],
)
def test_second_round_credit(kind, score, expected):
    assert second_round_credit(kind, score, grade=10) == expected


@pytest.mark.parametrize(
    "score,carried,expected",
    [
        # م25 (ص22، `04b_academic_deep_part1.md:1925`): معذورٌ عن نهاية ف2 وحدَها —
        # حصّل 40 (ف1 30 + منتصفُ ف2 وأعمالُه 10) واختبارُ الدور الثاني من 40.
        (Decimal("12"), Decimal("40"), (True, Decimal("52"))),
        (Decimal("9.2"), Decimal("40"), (False, Decimal("49.5"))),  # م8 قبل الحكم
        # م21: معذورٌ عن الفصل الأول كلِّه والملحق — من مئة ولا محمول
        (Decimal("64"), Decimal("0"), (True, Decimal("64"))),
    ],
)
def test_excused_credit_adds_what_was_earned(score, carried, expected):
    assert second_round_credit(EXCUSED, score, carried, grade=10) == expected


def test_carried_is_ignored_for_failed_and_deprived():
    """م16-1 و3: الصغرى فقط — ما حُصّل في الدور الأول لا يُضاف."""
    assert second_round_credit(FAILED_ELIGIBLE, 50, carried=45, grade=10) == (True, Decimal("50"))
    assert second_round_credit(DEPRIVED, 49, carried=45, grade=10) == (False, Decimal("49"))


def test_combined_student_credit_per_subject():
    """م12-ج + م16: الجامعُ ينال الصغرى فيما رسب فيه ودرجتَه فيما عُذر عنه."""
    decision = classify_first_round(_student((30, None, 70, 60, 55, 50), excused=("إنجليزي",)), 8)
    assert second_round_credit(decision.kind_of("عربي"), 90, grade=8) == (True, Decimal("50"))
    assert second_round_credit(decision.kind_of("إنجليزي"), 90, grade=8) == (True, Decimal("90"))


def test_passed_student_has_no_second_round_credit():
    with pytest.raises(ValueError):
        second_round_credit(PASSED, 70, grade=10)


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


def _annual(student, setup, total):
    from assessments.models import AnnualSubjectResult

    AnnualSubjectResult.objects.create(
        student=student,
        setup=setup,
        school=setup.school,
        academic_year=setup.academic_year,
        s1_total=Decimal("0"),
        s2_total=Decimal(total),
        annual_total=Decimal(total),
        status="pass" if Decimal(total) >= 50 else "fail",
    )


@pytest.mark.django_db
def test_roster_reads_totals_and_final_exam_absences(school, teacher_user):
    from assessments.models import Assessment, AssessmentPackage, StudentAssessmentGrade
    from assessments.services import GradeService, SecondRoundService
    from tests.conftest import StudentEnrollmentFactory, UserFactory

    cg, setups, year = _setup_class(school, teacher_user)
    passer, failer, excused, absentee = UserFactory(), UserFactory(), UserFactory(), UserFactory()
    for s in (passer, failer, excused, absentee):
        StudentEnrollmentFactory(student=s, class_group=cg)
    for setup in setups:
        _annual(passer, setup, "70")
        _annual(failer, setup, "49.2")  # م8: 49.5 — ما زال دون الخمسين
        _annual(excused, setup, "80")
        _annual(absentee, setup, "70")
    (p4,) = (p for p in GradeService.ensure_packages(setups[0], "S2") if p.package_type == "P4")
    exam = Assessment.objects.create(
        package=p4, school=school, title="نهاية ف2", status="published"
    )
    StudentAssessmentGrade.objects.create(
        assessment=exam, student=excused, school=school, is_absent=True, is_excused=True
    )
    # م27: الغيابُ بلا عذر عن نهاية الفصل الثاني يجعل المادّةَ من موادّ الرسوب ولو بلغ مجموعُها 70.
    StudentAssessmentGrade.objects.create(
        assessment=exam, student=absentee, school=school, is_absent=True, is_excused=False
    )
    assert AssessmentPackage.objects.filter(setup=setups[0]).count() == 3

    rows = {r.student.id: r.decision for r in SecondRoundService.roster(cg, year)}

    assert rows[passer.id].category == PASSED
    assert rows[failer.id].category == FAILED_INELIGIBLE  # أربعُ موادّ راسبة
    assert rows[excused.id].category == EXCUSED
    assert rows[excused.id].retake == (SUBJECTS[0],)
    assert rows[absentee.id].category == FAILED_ELIGIBLE
    assert rows[absentee.id].retake == (SUBJECTS[0],)


@pytest.mark.django_db
def test_second_round_screen(client_as, school, teacher_user, principal_user, student_user):
    from tests.conftest import StudentEnrollmentFactory, UserFactory

    cg, setups, year = _setup_class(school, teacher_user, n_subjects=2)
    student = UserFactory(full_name="طالبُ الدور الثاني")
    StudentEnrollmentFactory(student=student, class_group=cg)
    _annual(student, setups[0], "30")
    _annual(student, setups[1], "90")

    resp = client_as(principal_user).get(f"/assessments/second-round/?class_group={cg.id}")
    assert resp.status_code == 200
    body = resp.content.decode()
    assert "طالبُ الدور الثاني" in body and "م12-أ" in body

    assert client_as(teacher_user).get("/assessments/second-round/").status_code == 403
