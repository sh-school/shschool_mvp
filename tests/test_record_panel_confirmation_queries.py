"""فهرسُ الرصد لا يستعلم تثبيتات الحصص لكلّ شعبة (W-20261121-003، شكوى Sentry SCHOOLOS-PRODUCTION-37).

كان `sections_to_record` يستدعي `periods_of` لكلّ شعبةٍ في الجناح، فيُنفَّذ استعلامُ
`operations_periodconfirmation` بعدد الشُّعب. الإصلاحُ يجلب تثبيتات الجناح كلّها دفعةً
واحدة، والاختبارُ يعدّ الاستعلامات لا النتائج وحدها، ويتأكّد أنّ ما تعرضه الشُّعب لم يتغيّر.
"""

import datetime as dt

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from operations.models import PeriodConfirmation, Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _staff, at
from tests.conftest import ClassGroupFactory
from tests.test_class_grid import assigned, kids, subject  # noqa: F401
from wings.services import sections_to_record

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

STARTS = (dt.time(7, 10), dt.time(8, 0), dt.time(12, 45))
AFTER_SCHOOL = at(14, 0)


def _sessions_of(school, klass, teacher, subject) -> None:
    """حصصُ اليوم الثلاث للشعبة."""
    for start in STARTS:
        Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            subject=subject,
            date=SUNDAY,
            start_time=start,
            end_time=(dt.datetime.combine(SUNDAY, start) + dt.timedelta(minutes=45)).time(),
            status="scheduled",
        )


def _add_class_with_day(school, year, wing, teacher, subject, section: str):
    """شعبةٌ إضافيةٌ في الجناح نفسه بحصصٍ ثلاثٍ في اليوم، وتثبيتٌ قديمٌ لأوّل حصّة.

    لكلّ شعبةٍ معلّمُها: قيدُ DB يمنع المعلّمَ الواحد في الساعة نفسها لشعبتين (no_teacher_time_overlap_real).
    """
    klass = ClassGroupFactory(
        school=school,
        grade="G7",
        section=section,
        level_type="prep",
        academic_year=year,
        wing=wing,
    )
    _sessions_of(school, klass, teacher, subject)
    PeriodConfirmation.objects.create(
        school=school,
        class_group=klass,
        date=SUNDAY,
        start_time=STARTS[0],
        end_time=(dt.datetime.combine(SUNDAY, STARTS[0]) + dt.timedelta(minutes=45)).time(),
        confirmed_by=teacher,
        first_confirmed_at=timezone.now(),
        present_count=2,
        absent_count=1,
        late_count=0,
    )
    return klass


def test_confirmations_are_fetched_once_for_the_whole_wing(school, year, assigned, subject, kids):
    for i, section in enumerate(("2", "3", "4", "5"), start=1):
        own_teacher = _staff(school, "teacher", f"معلّم الشعبة {section}", f"2900000000{i}")
        _add_class_with_day(school, year, assigned.wing, own_teacher, subject, section)

    with CaptureQueriesContext(connection) as ctx:
        rows = sections_to_record(assigned.wing, SUNDAY, now=AFTER_SCHOOL)

    confirmation_queries = [
        q for q in ctx.captured_queries if "operations_periodconfirmation" in q["sql"]
    ]
    assert len(rows) == 5
    assert len(confirmation_queries) == 1, "استعلامٌ واحدٌ للجناح كلّه لا لكلّ شعبة"


def test_each_section_keeps_its_own_confirmation(
    school, year, assigned, teacher, other_teacher, subject, kids
):
    _sessions_of(school, assigned, teacher, subject)
    other = _add_class_with_day(school, year, assigned.wing, other_teacher, subject, "2")

    rows = {
        r.class_group.pk: r for r in sections_to_record(assigned.wing, SUNDAY, now=AFTER_SCHOOL)
    }

    assert rows[other.pk].statuses == ["confirmed", "missed", "missed"]
    assert rows[other.pk].shown_counts.absent_count == 1
    assert rows[assigned.pk].statuses == ["missed"] * 3, "شعبةٌ بلا تثبيتٍ تبقى فائتةً"
    assert rows[assigned.pk].shown_counts is None
