"""الحكمُ الواحد `judge_student` والجبرُ (م8) — دوالُّ المجال الخالصة، بلا قاعدةِ بيانات.

المرجعُ: سياسةُ تقييم الطلبة 4–11 (أغسطس 2015) م6–م8 وم12–م16 وم50–م51 بأرقام الصفحات
المطبوعة، والقرار 14/2018 م3. وموضعُ الجبر (منتصفُ الفصل ثمّ مجموعُه، وجمعُ الفصلين بلا
جبرٍ ثالث) قراءةٌ مرجَّحةٌ من م8 وكشوفِ ص44 بند 6 لا نصٌّ صريح.
الأمثلةُ اصطناعيّةٌ بحتة: لا طالبَ حقيقيّاً ولا رقماً شخصيّاً.
"""

from __future__ import annotations

from fractions import Fraction

import pytest

from core.domain import grades as g

GRADE = 8


def _exam(score, out_of, excused=0, absent=0):
    return g.ExamFacts(
        score=None if score is None else Fraction(str(score)),
        out_of=Fraction(out_of),
        excused_share=Fraction(excused),
        absent_share=Fraction(absent),
    )


def _by_total(key: str, s1, s2) -> g.SubjectFacts:
    """مادّةٌ بمجموعَي فصلين خام موزَّعَين بنصيب الباقات (15·5·20 و15·5·40)."""
    s1, s2 = Fraction(str(s1)), Fraction(str(s2))
    return g.SubjectFacts(
        key=key,
        s1={
            "P1": _exam(s1 * Fraction(3, 8), 15),
            "AW": _exam(s1 / 8, 5),
            "P2": _exam(s1 / 2, 20),
        },
        s2={
            "P3": _exam(s2 / 4, 15),
            "AW": _exam(s2 / 12, 5),
            "P4": _exam(s2 * Fraction(2, 3), 40),
        },
    )


def _passing(n: int) -> list[g.SubjectFacts]:
    return [_by_total(f"ok{i}", 32, 48) for i in range(n)]


def _judge(extra: list[g.SubjectFacts], **kw) -> g.StudentVerdict:
    return g.judge_student(GRADE, _passing(8 - len(extra)) + extra, **kw)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("47", "47"),
        ("47.01", "47.5"),
        ("47.5", "47.5"),
        ("47.51", "48"),
        ("49.99", "50"),
        ("0.49", "0.5"),
    ],
)
def test_jabr_article_8_never_rounds_down(raw, expected):
    assert str(g.jabr_fraction(raw)) == expected


def test_jabr_none_stays_none():
    assert g.jabr_fraction(None) is None


@pytest.mark.parametrize(
    ("s1", "s2", "standing"),
    [
        (19.8, 29.8, g.STANDING_PASSED),  # 49.6 خام: يبلغ الخمسين بالجبر
        (19.0, 30.0, g.STANDING_PROMOTED),  # 49.0: ينقصه نصفٌ → م50 قاعدة 1
        (18.2, 30.0, g.STANDING_PROMOTED),  # 48.2: نقصٌ ≤ 2 بعد الجبر
        (17.0, 30.0, g.STANDING_SECOND_ROUND),  # 47.0: نقصٌ 2.5 بعد الجبر → دورٌ ثانٍ
    ],
)
def test_single_subject_short(s1, s2, standing):
    assert _judge([_by_total("x", s1, s2)]).standing == standing


def test_two_subjects_short_by_up_to_four_are_promoted_by_rule_two():
    v = _judge([_by_total("x", 17, 29.5), _by_total("y", 17, 29)])
    assert v.standing == g.STANDING_PROMOTED
    assert v.article.endswith("القاعدة الثانية")


def test_three_failed_subjects_go_to_second_round():
    v = _judge([_by_total(k, 15, 25) for k in "xyz"])
    assert v.standing == g.STANDING_SECOND_ROUND


def test_four_failed_subjects_fail_without_second_round():
    v = _judge([_by_total(k, 15, 25) for k in "wxyz"])
    assert v.standing == g.STANDING_FAILED
    assert all(s.status == g.STATUS_FAIL for s in v.subjects if not s.key.startswith("ok"))


def test_absent_without_excuse_from_s2_final_sits_second_round():
    absent = g.SubjectFacts(
        key="x",
        s1={"P1": _exam(12, 15), "AW": _exam(4, 5), "P2": _exam(16, 20)},
        s2={"P3": _exam(12, 15), "AW": _exam(4, 5), "P4": _exam(0, 40, absent=1)},
    )
    v = _judge([absent])
    assert v.standing == g.STANDING_SECOND_ROUND
    assert v.by_key()["x"].mark == g.ABSENT


def test_excused_from_s2_final_is_excused_not_failed():
    excused = g.SubjectFacts(
        key="x",
        s1={"P1": _exam(12, 15), "AW": _exam(4, 5), "P2": _exam(16, 20)},
        s2={"P3": _exam(12, 15), "AW": _exam(4, 5), "P4": _exam(0, 40, excused=1)},
    )
    v = _judge([excused])
    assert v.by_key()["x"].status == g.STATUS_EXCUSED
    assert v.standing == g.STANDING_SECOND_ROUND


def test_missing_s1_final_without_makeup_is_pending():
    pending = g.SubjectFacts(
        key="x",
        s1={"P1": _exam(12, 15), "AW": _exam(4, 5), "P2": _exam(0, 20, excused=1)},
        s2={"P3": _exam(12, 15), "AW": _exam(4, 5), "P4": _exam(32, 40)},
    )
    assert _judge([pending]).standing == g.STANDING_INCOMPLETE


def test_cancelled_writes_the_word_in_every_subject():
    v = g.judge_student(GRADE, _passing(3), cancelled=True)
    assert v.standing == g.STANDING_FAILED
    assert {s.status for s in v.subjects} == {g.STATUS_CANCELLED}
