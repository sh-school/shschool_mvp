"""[FILE-SIZE] لا ملفَّ شيفرةٍ جديدٌ فوق 900 سطر، ولا قائمٌ تجاوزه يكبر — راجع `tests/file_size_ratchet.py`."""

import json

from tests import file_size_ratchet as ratchet

UPDATE = "python -m tests.file_size_ratchet --update"


def _compare():
    baseline = json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))
    return ratchet.compare(baseline, ratchet.measure())


def test_no_module_grows_past_the_size_limit():
    worse, _stale = _compare()
    assert not worse, (
        f"ملفٌّ فوق {ratchet.HARD_LIMIT} سطراً أو كبُر ملفٌّ مسجَّل — قسِّمه إلى حزمةٍ حسب "
        "المسؤوليّة (النموذج: `staff_affairs/attendance/`) بدل الزيادة:\n  " + "\n  ".join(worse)
    )


def test_shrinkage_is_recorded_so_it_cannot_be_spent_again():
    _worse, stale = _compare()
    assert not stale, (
        f"صغُر ملفٌّ ولم يُثبَّت نقصُه — أحسنت؛ ثبّته بـ `{UPDATE}` وأودع السجلّ:\n  " + "\n  ".join(stale)
    )
