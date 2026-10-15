"""[SCHEDULE-V2] HC10 في الحلّال يعدّ الفراغَ داخل نطاق جرسٍ واحد (W-20261012-022).

الخطأ: فواصلُ المعلّم الزمنيّةُ تُجمع من كلّ نطاقٍ يدرّس فيه ثم تُرتَّب معاً، فتدخل فواصلُ النطاق الآخر في
`l - f + 1` فيُحسب فراغٌ وهميّ (25 من 72 معلّماً في قياس 0424). الصحيح: فجوةٌ بين حصّةٍ في نطاقٍ وحصّةٍ في
نطاقٍ آخر ليست فراغاً. والبياناتُ مصنّعةٌ بلا أسماءٍ ولا هويّات (PDPPL، D-381م).
"""

from operations.cpsat_adapter import TeacherPref
from tests.test_scheduler_v2_hard import feasible, make

#: مادّتان في الشعبة C1 (نطاق B) كي لا يمنع HC6 حصّتين من مادّةٍ واحدةٍ في اليوم، ومادّتان في C2 (نطاق B2).
TWO_BANDS = [
    ("C1", "S1", "T1", "", 1),
    ("C1", "S3", "T1", "", 1),
    ("C2", "S2", "T1", "", 1),
    ("C2", "S4", "T1", "", 1),
]
ONE_BAND = TWO_BANDS[:2]


def _inputs(rows, cap=1):
    """C1 في نطاق B وC2 في B2 (جرسان مُزاحان 25 دقيقة)، والمعلّمُ T1 يدرّس فيهما بسقف فراغ."""
    return make(rows, bands={"C2": "B2"}, prefs={"T1": TeacherPref("T1", None, None, cap, None)})


def test_a_teacher_in_two_bell_bands_gets_no_phantom_gap_from_the_other_band():
    # ح1 وح3 في نطاق B: فراغٌ واحدٌ حقيقيّ (ح2) ≤ 1؛ وفواصلُ B2 بينهما لا تُعدّ.
    assert feasible(_inputs(TWO_BANDS), [(0, 0, 1), (1, 0, 3)])


def test_a_real_gap_inside_one_band_is_still_refused():
    # ح1 وح4 في نطاق B: فراغان (ح2 وح3) > 1 — القيدُ قائمٌ داخل النطاق.
    assert not feasible(_inputs(TWO_BANDS), [(0, 0, 1), (1, 0, 4)])


def test_each_band_is_measured_on_its_own():
    inp = _inputs(TWO_BANDS)
    # فراغٌ واحدٌ داخل كلّ نطاقٍ في يومَين مختلفَين: مقبول.
    assert feasible(inp, [(0, 0, 1), (1, 0, 3), (2, 1, 1), (3, 1, 3)])
    # وفراغان داخل B2 مرفوضان ولو كانت حصتا B بفراغٍ واحدٍ فقط في اليوم نفسه.
    assert not feasible(inp, [(0, 0, 1), (1, 0, 3), (2, 0, 4), (3, 0, 7)])


def test_a_single_band_teacher_is_unchanged():
    one = _inputs(ONE_BAND)
    assert feasible(one, [(0, 0, 1), (1, 0, 3)])
    assert not feasible(one, [(0, 0, 1), (1, 0, 4)])
