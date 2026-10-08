"""حذفُ خروجٍ من ملف الطالب يُعيد حسابَ ملخّص اليوم (W-20261008-001 · البند 3).

كان `delete_exit_event` يحذف السطر ويترك `DailyExitTally` يعدّ ما حُذف.
"""

import pytest
from django.urls import reverse

from operations.class_exit import close_unreturned, come_back, leave
from operations.models import ClassExit, DailyExitTally
from tests.test_period_register import (  # noqa: F401 — التجهيزاتُ نفسُها
    SUNDAY,
    _periods,
    at,
    kids,
    klass,
    other_teacher,
    subjects,
    supervisor,
    teacher,
    year,
)

pytestmark = pytest.mark.django_db


def _tally(student):
    return DailyExitTally.objects.filter(student=student, date=SUNDAY).first()


def _delete(client_as, supervisor, exit_):
    return client_as(supervisor).post(
        reverse("wings:exit_event_delete", args=[exit_.pk]), {"reason": "رُصد على طالبٍ آخر"}
    )


def test_deleting_an_exit_recomputes_the_days_tally(
    client_as, school, seeded_calendar, klass, kids, teacher, supervisor
):
    (period,) = _periods(school, klass, teacher, 1)
    kept = leave(period, kids[0], "restroom", by=teacher, now=at(7, 10))
    come_back(period, kids[0], now=at(7, 15))
    gone = leave(period, kids[0], "clinic", by=teacher, now=at(7, 20))
    come_back(period, kids[0], now=at(7, 30))
    assert (_tally(kids[0]).exit_count, _tally(kids[0]).total_seconds) == (2, 15 * 60)

    assert _delete(client_as, supervisor, gone).status_code == 302

    tally = _tally(kids[0])
    assert (tally.exit_count, tally.total_seconds) == (1, 5 * 60)
    assert ClassExit.objects.filter(pk=kept.pk).exists()


def test_deleting_the_last_exit_zeroes_the_tally(
    client_as, school, seeded_calendar, klass, kids, teacher, supervisor
):
    (period,) = _periods(school, klass, teacher, 1)
    only = leave(period, kids[0], "restroom", by=teacher, now=at(7, 10))
    come_back(period, kids[0], now=at(7, 15))
    _delete(client_as, supervisor, only)
    tally = _tally(kids[0])
    assert (tally.exit_count, tally.total_seconds) == (0, 0)


def test_deleting_the_origin_of_a_carried_exit_counts_the_remaining_part_once(
    client_as, school, seeded_calendar, klass, kids, teacher, supervisor
):
    first, second = _periods(school, klass, teacher, 2)
    origin = leave(first, kids[0], "restroom", by=teacher, now=at(7, 10))
    close_unreturned(first, now=at(7, 56))
    carried = ClassExit.objects.get(session=second, student=kids[0])
    assert carried.continued_from_id == origin.id
    assert _tally(kids[0]).exit_count == 1

    _delete(client_as, supervisor, origin)

    carried.refresh_from_db()
    assert carried.continued_from_id is None  # SET_NULL: صار خروجاً قائماً بذاته
    assert _tally(kids[0]).exit_count == 1  # يُعدّ مرّةً واحدةً لا صفراً ولا مرّتين
