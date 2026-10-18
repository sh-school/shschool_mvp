"""نافذةُ إدخال المعلّم مركزيّةٌ (W-20261006-004، D-237م): `entry_window` = `grid_window` — إعدادان واحدان للحقيقيّة والمؤقّتة.

لا حسابَ من الجرس ولا من بدء الحصّة: 07:10 → 14:00 افتراضاً، وتغيير الإعداد يحرّك النافذتين معاً،
والمعاينةُ تبقى مفتوحةً اليومَ كلَّه (قرارُ المالك 2026-10-04)، وبعد 14:00 يبقى الرفضُ كما اليوم.
"""

import datetime as dt
from unittest.mock import patch

import pytest
from django.test import override_settings

from operations.attendance_entries import EntryRefusedError, submit_entry
from operations.attendance_policy import entry_window, grid_window
from operations.models import Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

pytestmark = pytest.mark.django_db


def _session(school, klass, teacher, *, provisional, start=dt.time(12, 45), end=dt.time(13, 30)):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=start,
        end_time=end,
        period_number=3,
        status="scheduled",
        provisional=provisional,
    )


@pytest.mark.parametrize("provisional", [False, True])
def test_entry_window_is_the_central_grid_window(school, klass, teacher, provisional):
    session = _session(school, klass, teacher, provisional=provisional)

    assert entry_window(session) == grid_window(SUNDAY) == (at(7, 10), at(14, 0))


def test_changing_the_setting_moves_both_windows(school, klass, teacher):
    real = _session(school, klass, teacher, provisional=False)
    provisional = _session(school, klass, teacher, provisional=True)

    with override_settings(ATTENDANCE_GRID_OPENS="07:30", ATTENDANCE_GRID_CLOSES="13:00"):
        assert entry_window(real) == entry_window(provisional) == (at(7, 30), at(13, 0))


def test_a_real_period_is_open_before_its_own_start(school, klass, teacher, kid):
    """حصّةٌ حقيقيّةٌ تبدأ 12:45 تُرصد 07:10 — لا قيدَ ببدئها."""
    real = _session(school, klass, teacher, provisional=False)

    assert submit_entry(teacher, real, kid, "absent", now=at(7, 10)).pk


def test_entry_is_refused_before_open_and_after_close(school, klass, teacher, kid):
    session = _session(school, klass, teacher, provisional=True)

    with pytest.raises(EntryRefusedError):
        submit_entry(teacher, session, kid, "absent", now=at(7, 9))
    with pytest.raises(EntryRefusedError):
        submit_entry(teacher, session, kid, "absent", now=at(14, 1))


def test_the_preview_keeps_its_all_day_window(school, klass, teacher):
    session = _session(school, klass, teacher, provisional=False)

    with patch("operations.attendance_policy.in_preview_environment", return_value=True):
        assert entry_window(session) == (at(0, 0), at(23, 59, 59))
