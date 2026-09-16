"""[COMPLIANCE 2.2 · جولة إصلاح 5] القاعدةُ الأولى «في أية مادة» — تُعرض ولا تُحسم.

الأصل: `data/2026-2027/03- الأكاديمي/04- سياسة تقييم الطلاب من الرابع حتى الحادي عشر.pdf`،
م50 ص33 (صفحة PDF 34):

    «القاعدة الأولى: يُرفّع الطالب الراسب في أية مادة من المواد الدراسية التي لها نهاية
     صغرى إذا كانت الدرجات التي يحتاجها للنجاح لا تزيد عن درجتين.»
    «القاعدة الثانية: يرفع الطالب الراسب في مادتين …»
    «القاعدة الثالثة: يُرفّع الطالب الراسب في مادة وحيدة …»
    م51: «في جميع الأحوال لا يجوز أن تطبق إلا قاعدة واحدة فقط من القواعد الثلاثة.»

فالأولى تقول «أية مادة» لا «مادة وحيدة» (كالثالثة)، ولا تشترط ألّا يرسب الطالبُ في غيرها؛
و«يُرفَّع الطالب» ترفيعٌ للطالب لا للمادّة، فلا يُرفَّع وفي غيرها رسوبٌ لم يُحسم. قراءتان لا
يحسم النصُّ بينهما — فالحكمُ المخزَّن يبقى على الأضيق، ويُحمل معه تنبيهٌ للمراجعة على
المادّة التي تنالها القاعدةُ بالقراءة الأخرى، فلا تُطوى حجّةُ الطالب.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from tests import test_assessment_verdict as tv

RULE_ONE = "م50 القاعدة الأولى"


def _subject(key, s1, s2, second=None, excused_final=False):
    from core.domain.grades import ExamFacts, SecondRoundFacts, SubjectFacts

    p4 = (
        ExamFacts(Fraction(0), Fraction(40), excused_share=Fraction(1))
        if excused_final
        else ExamFacts(Fraction(s2), Fraction(40))
    )
    zero_mid, zero_aw = ExamFacts(Fraction(0), Fraction(15)), ExamFacts(Fraction(0), Fraction(5))
    return SubjectFacts(
        key,
        {"P1": zero_mid, "AW": zero_aw, "P2": ExamFacts(Fraction(s1), Fraction(20))},
        {"P3": zero_mid, "AW": zero_aw, "P4": p4},
        second_round=None if second is None else SecondRoundFacts(Fraction(second)),
    )


def _passing(n=2):
    return [_subject(f"ن{i}", 20, 40) for i in range(n)]


def test_rule_one_with_another_failure_is_flagged_for_review_on_that_subject():
    """49 في العربيّة و30 في الرياضيات: دورٌ ثانٍ فيهما، وتنبيهٌ على العربيّة وحدَها."""
    from core.domain.grades import judge_student

    verdict = judge_student(11, [_subject("ع", 19, 30), _subject("ر", 10, 20), *_passing()])
    subs = verdict.by_key()
    assert verdict.standing == "second_round"
    assert subs["ع"].status == subs["ر"].status == "second_round"
    assert RULE_ONE in subs["ع"].review and "1" in subs["ع"].review
    assert subs["ر"].review == ""
    assert all(subs[k].review == "" for k in ("ن0", "ن1"))


def test_rule_one_with_an_excused_subject_is_flagged_too():
    from core.domain.grades import judge_student

    verdict = judge_student(
        11, [_subject("ع", 19, 30), _subject("ر", 20, 0, excused_final=True), *_passing()]
    )
    subs = verdict.by_key()
    assert verdict.standing == "second_round"
    assert RULE_ONE in subs["ع"].review
    assert subs["ر"].review == ""


def test_sole_failure_is_promoted_without_a_review_note():
    from core.domain.grades import judge_student

    verdict = judge_student(11, [_subject("ع", 19, 30), *_passing()])
    assert verdict.standing == "promoted"
    assert all(s.review == "" for s in verdict.subjects)


def test_a_gap_above_two_is_not_flagged():
    from core.domain.grades import judge_student

    verdict = judge_student(11, [_subject("ع", 19, "27.5"), _subject("ر", 10, 20), *_passing()])
    assert all(s.review == "" for s in verdict.subjects)


def test_after_the_second_round_the_first_round_gap_stays_on_record():
    """رسب في العربيّة في الدور الثاني (30) ونجح في الرياضيات: راسب — والتنبيهُ باقٍ."""
    from core.domain.grades import judge_student

    verdict = judge_student(
        11, [_subject("ع", 19, 30, second=30), _subject("ر", 10, 20, second=60), *_passing()]
    )
    subs = verdict.by_key()
    assert verdict.standing == "failed"
    assert subs["ع"].status == "fail"
    assert RULE_ONE in subs["ع"].review and "الدور الأول" in subs["ع"].review


def test_second_round_failures_with_one_small_gap_are_flagged():
    from core.domain.grades import judge_student

    verdict = judge_student(
        11, [_subject("ع", 10, 20, second=49), _subject("ر", 10, 20, second=30), *_passing()]
    )
    subs = verdict.by_key()
    assert verdict.standing == "failed"
    assert RULE_ONE in subs["ع"].review and "الدور الثاني" in subs["ع"].review
    assert subs["ر"].review == ""


def test_grade_twelve_has_no_promotion_review():
    """سياسة الثاني عشر لا قواعدَ ترفيعٍ فيها — فلا تنبيه."""
    from core.domain.grades import ExamFacts, SubjectFacts, judge_student

    def s12(key, a, b):
        return SubjectFacts(
            key,
            {"P2": ExamFacts(Fraction(a), Fraction(40))},
            {"P4": ExamFacts(Fraction(b), Fraction(60))},
        )

    verdict = judge_student(12, [s12("ع", 19, 30), s12("ر", 10, 20), s12("ن", 40, 60)])
    assert all(s.review == "" for s in verdict.subjects)


@pytest.mark.django_db
def test_review_note_is_stored_and_shown_on_the_second_round_screen(
    client_as, school, principal_user, teacher_user
):
    from assessments.models import AnnualSubjectResult
    from assessments.services import GradeService

    cg, setups = tv._class(school, teacher_user, grade="G11", n=3, code="R")
    student = tv._student(cg, "صاحب الدرجة الناقصة")
    t49 = (7.5, 10, 2, 7, 20, 2.5)  # 19.5 + 29.5
    for setup, values in zip(setups, (t49, tv.T30, tv.T80), strict=True):
        tv._fill(tv._exams(setup), student, values)
    GradeService.recalculate_full_class(setups[0])

    arabic = AnnualSubjectResult.objects.get(student=student, setup=setups[0])
    assert (arabic.status, arabic.annual_total) == ("second_round", 49)
    assert RULE_ONE in arabic.review
    assert AnnualSubjectResult.objects.get(student=student, setup=setups[1]).review == ""

    body = client_as(principal_user).get(f"/assessments/second-round/?class_group={cg.id}")
    assert body.status_code == 200
    assert arabic.review in body.content.decode()
