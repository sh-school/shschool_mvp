"""تمييزُ عددِ الحصص في جملة النصاب (W-20261012-009، بلاغ 0423).

كانت صفحةُ تفضيلات المعلّم تطبع «نصابُك N حصة» لكلّ عدد، وتمييزُ العدد العربيّ يتغيّر:
واحدةٌ، حصّتان، ثلاثٌ إلى عشرٍ «حصص»، وما فوقها «حصّة».
"""

from pathlib import Path

import pytest
from django.template import Context, Template

from core.templatetags.schedule_filters import periods_phrase

TEMPLATE = Path(__file__).resolve().parent.parent / "templates/schedule/teacher_preferences.html"


@pytest.mark.parametrize(
    ("n", "expected"),
    [
        (0, "لا حصص"),
        (1, "حصّة واحدة"),
        (2, "حصّتان"),
        (3, "3 حصص"),
        (10, "10 حصص"),
        (11, "11 حصّة"),
        (24, "24 حصّة"),
        ("5", "5 حصص"),
        (6.0, "6 حصص"),
    ],
)
def test_the_noun_follows_the_number(n, expected):
    assert periods_phrase(n) == expected


@pytest.mark.parametrize("bad", [None, "", "abc"])
def test_an_unreadable_count_prints_nothing(bad):
    assert periods_phrase(bad) == ""


def test_the_filter_is_available_to_templates():
    out = Template("{% load schedule_filters %}{{ n|periods_phrase }}").render(Context({"n": 2}))
    assert out == "حصّتان"


def test_the_preferences_page_uses_the_filter_not_a_fixed_noun():
    """الصفحةُ تمرّ بالمرشّح: لا «حصة» ثابتةً بعد العدد (حصّةٌ ملصوقةٌ بـ`{{ load }}` هي العيب نفسُه)."""
    source = TEMPLATE.read_text(encoding="utf-8")
    assert "load|periods_phrase" in source
    assert "{{ load }}</b> حصة" not in source
