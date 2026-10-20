"""طبقةُ إحصاء الغياب بالطلبة فوق ملخّص الوزارة (W-20261020-005 الخطوة 4): نسبٌ بمقام كلّ المقيَّدين وتجميعٌ بلا ضياع."""

import datetime as dt
from types import SimpleNamespace as NS

from wings.absence_stats import OUTSIDE_LABEL, absence_stats, rate
from wings.ministry_selectors import ClassRow, Counts, MinistrySummary


def _row(code, level, wing, enrolled, absent):
    counts = Counts(enrolled=enrolled, absent_both_unexcused=absent)
    return ClassRow(NS(short_code=code, level_type=level, wing=wing), counts, True)


W3 = NS(pk=3, code="w3", name="الجناح 3", order=3)
W1 = NS(pk=1, code="w1", name="الجناح 1", order=1)


def _summary(rows):
    total = Counts()
    for row in rows:
        total.add(row.counts)
    grade = NS(rows=rows)
    return MinistrySummary(dt.date(2026, 10, 20), [grade], total, [])


def test_rate_uses_all_enrolled_as_denominator_and_is_safe_at_zero():
    assert rate(1, 8) == 12.5
    assert rate(0, 0) == 0.0


def test_wing_three_is_one_wing_with_two_level_sublines():
    rows = [
        _row("9/3", "prep", W3, 20, 2),
        _row("9/4", "prep", W3, 20, 2),
        _row("10/1", "sec", W3, 20, 6),
        _row("7/1", "prep", W1, 10, 1),
    ]
    stats = absence_stats(_summary(rows))
    wing3 = next(w for w in stats.wings if w.key == "wing-w3")
    assert (wing3.enrolled, wing3.absent_both) == (60, 10)
    assert [c.label for c in wing3.children] == ["إعدادي", "ثانوي"]
    assert [c.absent_both for c in wing3.children] == [4, 6]
    wing1 = next(w for w in stats.wings if w.key == "wing-w1")
    assert [c.label for c in wing1.children] == ["7/1"]
    assert [w.key for w in stats.wings] == ["wing-w1", "wing-w3"]


def test_outside_wings_is_its_own_line_and_the_total_matches_the_school():
    rows = [_row("7/1", "prep", W1, 10, 1), _row("7/ESE", "prep", None, 5, 0)]
    stats = absence_stats(_summary(rows))
    assert stats.outside and stats.outside.label == OUTSIDE_LABEL and stats.outside.enrolled == 5
    parts = sum(w.enrolled for w in stats.wings) + stats.outside.enrolled
    assert parts == stats.school.enrolled == 15
    assert sum(s.enrolled for s in stats.stages) == 15


def test_no_outside_line_when_every_class_has_a_wing():
    stats = absence_stats(_summary([_row("7/1", "prep", W1, 10, 1)]))
    assert stats.outside is None and len(stats.bars) == 2
