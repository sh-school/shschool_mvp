"""[SCHEDULE] عمودُ «الجودة» في سجلّ التوليد: الصحّةُ أوّلاً ثمّ الجودة (W-20261003-010).

مسودّةٌ فيها ثلاثُ متعذّراتٍ وخمسُ مخالفاتٍ أُعلنت «100%» فوق جدولين كاملين «99%»: الدرجةُ المنسوبةُ متوسّطُ
اثنين وعشرين مؤشّراً كلٌّ منها حتى 120، فنقصُ الإكمال يُمحى بتحسّنٍ في غيره، ومخالفاتُ المدقّق ليست فيها.
"""

from operations.schedule_breaches import quality_display


def test_a_complete_clean_draft_keeps_its_score():
    shown = quality_display(99.0, unplaced=0, breaches=0)

    assert shown == {"invalid": False, "value": 99.0, "tone": "", "sort": 99.0}


def test_unplaced_lessons_mark_the_draft_incomplete():
    shown = quality_display(100.0, unplaced=3, breaches=0)

    assert shown["invalid"] is True and shown["tone"] == "danger"
    assert shown["value"] == 100.0, "درجةُ ما وُضع تبقى ظاهرةً ثانويّة"


def test_breaches_alone_mark_the_draft_incomplete():
    assert quality_display(100.0, unplaced=0, breaches=5)["invalid"] is True


def test_an_incomplete_draft_never_sorts_above_a_complete_one():
    """البلاغُ نفسُه: 868/871 بـ100% تحت 871/871 بـ99%."""
    broken = quality_display(100.0, unplaced=3, breaches=5)
    complete = quality_display(99.0, unplaced=0, breaches=0)
    worst_complete = quality_display(0.0, unplaced=0, breaches=0)

    assert broken["sort"] < complete["sort"]
    assert broken["sort"] < worst_complete["sort"]


def test_no_score_yet_is_still_marked_when_incomplete():
    assert quality_display(None, unplaced=1, breaches=0)["invalid"] is True
    assert quality_display(None, unplaced=0, breaches=0)["invalid"] is False
