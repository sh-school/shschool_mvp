"""[SCHEDULE] مصالحةُ الأسابيع المولَّدة سلفاً بعد اعتماد جدول (SCH-08).

الاعتمادُ يصالح الأسبوعَ الجاريَ وحدَه، فتبقى أيّامُ الأسابيع القادمة المولَّدة على الجدول
القديم — والأحدُ 2026-09-27 أوّلُ يومٍ يعمل بالجدول الجديد. فمهمّةٌ خلفيّةٌ تُكمل ما بعده،
من حدود الأسبوع نفسها لا من تاريخ اليوم: فلا فجوةَ بين المصالحتين ولا تكرار.
"""

from datetime import date, time

import pytest

from operations.services import ScheduleService
from tests.conftest import ClassGroupFactory, UserFactory

YEAR = "2026-2027"


@pytest.mark.parametrize(
    ("today", "expected"),
    [
        (date(2026, 9, 25), date(2026, 10, 4)),  # الجمعة: الاعتمادُ يصالح 27/9–1/10
        (date(2026, 9, 26), date(2026, 10, 4)),  # السبت
        (date(2026, 9, 27), date(2026, 10, 4)),  # الأحد: الأسبوعُ الجاري 27/9–1/10
        (date(2026, 9, 30), date(2026, 10, 4)),  # الأربعاء
        (date(2026, 10, 1), date(2026, 10, 4)),  # الخميس
    ],
)
def test_the_future_weeks_start_the_sunday_after_the_week_the_approval_covers(today, expected):
    assert ScheduleService.future_weeks_start(today) == expected


def _session(school, day):
    from operations.models import Session

    return Session.objects.create(
        school=school,
        class_group=ClassGroupFactory(school=school, academic_year=YEAR),
        teacher=UserFactory(),
        date=day,
        start_time=time(7, 10),
        end_time=time(7, 55),
    )


@pytest.mark.django_db
def test_the_range_ends_at_the_last_generated_day(school, monkeypatch):
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 25))
    _session(school, date(2026, 10, 11))
    _session(school, date(2026, 10, 18))
    _session(school, date(2026, 9, 28))  # في أسبوع الاعتماد: لا يدخل المدى
    seen = {}

    def spy(cls, school_, start, end, academic_year=None, generated_only=True):
        seen.update(start=start, end=end, year=academic_year)
        return {"deleted": 0, "created": 0, "kept": 0}

    monkeypatch.setattr(ScheduleService, "resync_sessions_for_range", classmethod(spy))

    ScheduleService.resync_future_weeks(school, YEAR)

    assert seen == {"start": date(2026, 10, 4), "end": date(2026, 10, 18), "year": YEAR}


@pytest.mark.django_db
def test_nothing_generated_beyond_the_covered_week_means_nothing_to_do(school, monkeypatch):
    from django.utils import timezone

    monkeypatch.setattr(timezone, "localdate", lambda: date(2026, 9, 25))
    _session(school, date(2026, 9, 28))
    called = []
    monkeypatch.setattr(
        ScheduleService, "resync_sessions_for_range", classmethod(lambda *a, **k: called.append(1))
    )

    assert ScheduleService.resync_future_weeks(school, YEAR) == {
        "deleted": 0,
        "created": 0,
        "kept": 0,
    }
    assert not called


@pytest.mark.django_db
def test_approving_queues_the_future_weeks_after_commit(
    school, monkeypatch, django_capture_on_commit_callbacks
):
    from core import academic_calendar
    from operations import tasks
    from operations.models import ScheduleGeneration

    monkeypatch.setattr(academic_calendar, "academic_year_for_school", lambda _school: YEAR)
    sent = []
    monkeypatch.setattr(
        tasks.resync_generated_sessions_task, "delay", lambda *args: sent.append(args)
    )
    monkeypatch.setattr(ScheduleService, "resync_current_week", classmethod(lambda *a, **k: {}))
    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="draft")

    with django_capture_on_commit_callbacks(execute=True):
        result = ScheduleService.approve_generation(gen, notify=False)

    assert result["future_weeks_queued"] is True
    assert sent == [(str(school.pk), YEAR)]


@pytest.mark.django_db
def test_a_dead_broker_does_not_fail_the_approval(
    school, monkeypatch, django_capture_on_commit_callbacks
):
    from core import academic_calendar
    from operations import tasks
    from operations.models import ScheduleGeneration

    monkeypatch.setattr(academic_calendar, "academic_year_for_school", lambda _school: YEAR)

    def dead(*_args):
        raise ConnectionError("broker down")

    monkeypatch.setattr(tasks.resync_generated_sessions_task, "delay", dead)
    monkeypatch.setattr(ScheduleService, "resync_current_week", classmethod(lambda *a, **k: {}))
    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status="draft")

    with django_capture_on_commit_callbacks(execute=True):
        ScheduleService.approve_generation(gen, notify=False)

    gen.refresh_from_db()
    assert gen.status == "approved", "الاعتمادُ تمّ ولو سقط الإرسال"
