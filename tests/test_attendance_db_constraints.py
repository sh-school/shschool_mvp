"""قيودُ القاعدة على الغياب (W-20261004-021، المرحلة أ١): ما لا يجوز أن يُكتب لا يُكتب مهما كان الطريق."""

import datetime as dt

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from operations.models import AbsenceAlert, AbsenceExcuse, ClassExit
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

pytestmark = pytest.mark.django_db


def _exit(school, session, kid, **kw):
    return ClassExit.objects.create(
        school=school, session=session, student=kid, left_at=at(8, 0), **kw
    )


def test_a_return_before_the_exit_is_refused(school, session, kid):
    with pytest.raises(IntegrityError), transaction.atomic():
        _exit(school, session, kid, returned_at=at(7, 59))


def test_a_return_at_the_same_moment_and_a_later_one_are_accepted(school, session, kid):
    _exit(school, session, kid, returned_at=at(8, 0))
    _exit(school, session, kid, returned_at=at(8, 20))


def test_two_open_exits_for_one_student_in_one_session_are_refused(school, session, kid):
    _exit(school, session, kid)
    with pytest.raises(IntegrityError), transaction.atomic():
        _exit(school, session, kid)


def test_a_closed_exit_does_not_block_a_new_open_one(school, session, kid):
    _exit(school, session, kid, returned_at=at(8, 5))
    _exit(school, session, kid)


def _alert(school, kid, **kw):
    return AbsenceAlert.objects.create(
        school=school,
        student=kid,
        absence_count=5,
        gate=kw.pop("gate", "g5"),
        period_start=SUNDAY,
        period_end=SUNDAY + dt.timedelta(days=200),
        **kw,
    )


def test_a_duplicate_alert_with_the_same_key_is_refused(school, kid):
    _alert(school, kid)
    with pytest.raises(IntegrityError), transaction.atomic():
        _alert(school, kid)


def test_another_gate_for_the_same_student_is_accepted(school, kid):
    _alert(school, kid, gate="g5")
    _alert(school, kid, gate="g8")


def _excuse(school, kid, start, end):
    return AbsenceExcuse.objects.create(
        school=school, student=kid, date_from=start, date_to=end, kind="illness"
    )


def test_an_excuse_range_that_ends_before_it_starts_is_refused(school, kid):
    with pytest.raises(IntegrityError), transaction.atomic():
        _excuse(school, kid, SUNDAY + dt.timedelta(days=2), SUNDAY)


def test_a_one_day_excuse_is_accepted(school, kid):
    _excuse(school, kid, SUNDAY, SUNDAY)


def test_the_data_cleanup_fixes_every_violator_and_is_idempotent(school, session, kid):
    """الهجرةُ الموثَّقة تعالج المخالفَ بلا حذف خروجٍ ولا إنقاصِ عدّ، ثمّ لا شيءَ في الإعادة."""
    import importlib

    from django.apps import apps as django_apps

    migration = importlib.import_module(
        "operations.migrations.0088_clean_attendance_constraint_violators"
    )
    now = timezone.now()
    # المخالفُ لا يُنشأ عبر الـORM (القيدُ يمنعه) فنُسقط القيدَين مؤقتاً داخل معاملة الاختبار (تُتراجع معها)
    from django.db import connection

    with connection.cursor() as cur:
        cur.execute(
            "ALTER TABLE operations_classexit DROP CONSTRAINT class_exit_returned_after_left"
        )
        cur.execute("DROP INDEX unique_open_class_exit_per_session_student")
    ClassExit.objects.create(
        school=school,
        session=session,
        student=kid,
        left_at=now,
        returned_at=now - dt.timedelta(minutes=3),
    )
    ClassExit.objects.create(school=school, session=session, student=kid, left_at=now)
    ClassExit.objects.create(
        school=school, session=session, student=kid, left_at=now + dt.timedelta(minutes=1)
    )

    migration.clean(django_apps, None)
    migration.clean(django_apps, None)

    rows = list(ClassExit.objects.filter(student=kid).order_by("left_at"))
    assert len(rows) == 3
    assert all(r.returned_at is None or r.returned_at >= r.left_at for r in rows)
    assert sum(1 for r in rows if r.returned_at is None) == 1
