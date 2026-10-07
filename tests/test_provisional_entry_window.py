"""نافذةُ إدخال الحصّة المؤقّتة (W-20261005-006، قرارُ المالك D-232م): من بدء **أوّل حصّةٍ في جرس الشعبة** إلى نهاية الدوام — لا من بدء حصّتها هي.

للمؤقّتة وحدَها: ح5 تُرصد 07:10 صباحاً، وقبل 07:10 مرفوضة، وبعد نهاية الجرس مرفوضة؛ وكلُّ شعبةٍ بجرسها لا جرسِ جناحها (جناحٌ يعبر جرسين)؛
والحقيقيّةُ (D-128م) تبقى من بدء حصّتها كما هي؛ والمعاينةُ تبقى مفتوحةً اليومَ كلَّه.
"""

import datetime as dt
from unittest.mock import patch

import pytest

from core.models import TimeBand
from operations.attendance_entries import EntryRefusedError, submit_entry
from operations.attendance_policy import entry_window
from operations.models import Session, TimeSlotConfig
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at
from tests.conftest import ClassGroupFactory

pytestmark = pytest.mark.django_db


def _provisional(school, klass, teacher, start=dt.time(12, 45), end=dt.time(13, 30), period=3):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=start,
        end_time=end,
        period_number=period,
        status="scheduled",
        provisional=True,
    )


@pytest.fixture
def banded(school, klass, band, bells):
    """الشعبةُ على جرس `ground` (حصّتان صباحاً 07:10 و08:00 وثالثةٌ 12:45–13:30 — آخرُ الدوام 13:30)."""
    type(klass).objects.filter(pk=klass.pk).update(time_band=band)
    klass.refresh_from_db()
    return klass


def test_a_provisional_period_is_open_from_the_first_slot_of_the_class_bell(
    school, banded, teacher
):
    session = _provisional(school, banded, teacher)  # ح3: تبدأ 12:45

    start, end = entry_window(session)

    assert start == at(7, 10), "من بدء أوّل خانةٍ في الجرس لا من بدء ح3"
    assert end == at(13, 30)


def test_a_real_period_keeps_its_own_start_d128(school, banded, teacher):
    real = Session.objects.create(
        school=school,
        class_group=banded,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(12, 45),
        end_time=dt.time(13, 30),
        status="scheduled",
    )

    start, _end = entry_window(real)

    assert start == at(12, 45), "الحقيقيّةُ من بدء حصّتها كما هي"


def test_a_provisional_entry_is_accepted_at_0710_and_refused_before_and_after_the_bell(
    school, banded, teacher, kid
):
    session = _provisional(school, banded, teacher)

    accepted = submit_entry(teacher, session, kid, "absent", now=at(7, 10))
    assert accepted.pk

    with pytest.raises(EntryRefusedError):
        submit_entry(teacher, session, kid, "absent", now=at(7, 9))
    with pytest.raises(EntryRefusedError):
        submit_entry(teacher, session, kid, "absent", now=at(13, 31))


def test_each_class_takes_its_own_bell_not_the_whole_wing(
    school, year, wing, band, banded, teacher
):
    """جناحٌ يعبر جرسين (جناح 3): شعبةٌ على جرسٍ آخرَ يبدأ 09:00 وينتهي 14:00 تأخذ جرسَها لا جرسَ الشعبة الأخرى في الجناح نفسِه."""
    other_band = TimeBand.objects.create(
        school=school, code="ninth", name="التاسع 3·4", floor="first"
    )
    for number, (start, end) in enumerate(
        ((dt.time(9, 0), dt.time(9, 45)), (dt.time(13, 15), dt.time(14, 0))), start=1
    ):
        TimeSlotConfig.objects.create(
            school=school,
            band=other_band,
            day_type="regular",
            period_number=number,
            start_time=start,
            end_time=end,
        )
    ninth = ClassGroupFactory(
        school=school, grade="G9", section="3", academic_year=year, wing=wing, time_band=other_band
    )
    here = _provisional(school, banded, teacher)
    there = _provisional(
        school, ninth, teacher, start=dt.time(13, 15), end=dt.time(14, 0), period=2
    )

    assert entry_window(here) == (at(7, 10), at(13, 30))
    assert entry_window(there) == (at(9, 0), at(14, 0)), "جرسُ شعبتها لا جرسُ الجناح كلِّه"


def test_the_preview_keeps_its_all_day_window(school, banded, teacher):
    session = _provisional(school, banded, teacher)

    with patch("operations.attendance_policy.in_preview_environment", return_value=True):
        start, end = entry_window(session)

    assert start == at(0, 0) and end == at(23, 59, 59)


def test_a_provisional_class_without_a_bell_falls_back_to_its_own_period(school, klass, teacher):
    """شعبةٌ بلا جرسٍ مضبوط: تضيق النافذةُ إلى حصّتها نفسِها — الأضيقُ لا ثابتٌ مخترَع."""
    session = _provisional(school, klass, teacher, start=dt.time(10, 0), end=dt.time(10, 45))

    start, end = entry_window(session)

    assert (start, end) == (at(10, 0), at(10, 45))
