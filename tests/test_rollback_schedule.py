"""غلاف الرجوع بالجدول: يستعيد اللقطة ويصالح الجلسات، ويرفض ما مُسّ، وثابتُ التكرار."""

import datetime as dt
import json

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import ClassGroup
from operations.models import ScheduleSlot, Session, StudentAttendance, Subject
from operations.services import ScheduleService
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

SUNDAY = dt.date(2026, 3, 22)
YEAR = "2026-2027"


def _teacher(school, name):
    t = UserFactory(full_name=name)
    MembershipFactory(user=t, school=school, role=RoleFactory(school=school, name="teacher"))
    return t


@pytest.fixture
def world(db, school, tmp_path):
    cg = ClassGroup.objects.create(school=school, grade="G8", section="1", academic_year=YEAR)
    subject = Subject.objects.create(school=school, name_ar="رياضيات")
    old, new = _teacher(school, "قديم"), _teacher(school, "جديد")
    # الجدولُ الذي نرجع إليه: يُلتقط في اللقطة ثمّ يُطفأ، ويحلّ محلَّه جدولٌ «جديد».
    snap = tmp_path / "snap.json"
    snap.write_text(
        json.dumps(
            {
                "school_id": str(school.id),
                "school_code": school.code,
                "academic_year": YEAR,
                "taken_at": "2026-10-08T10:00:00",
                "slots": [
                    {
                        "teacher_id": str(old.id),
                        "class_group_id": str(cg.id),
                        "subject_id": str(subject.id),
                        "day_of_week": 0,
                        "period_number": 1,
                        "start_time": "07:10:00",
                        "end_time": "07:55:00",
                        "academic_year": YEAR,
                        "elective_group": "",
                        "notes": "",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    ScheduleSlot.objects.create(
        school=school,
        teacher=new,
        class_group=cg,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year=YEAR,
        is_active=True,
    )
    ScheduleService.resync_sessions_for_date(school, SUNDAY, academic_year=YEAR)
    return {"school": school, "old": old, "new": new, "snap": str(snap)}


def _args(world, *extra):
    return ["--snapshot", world["snap"], "--from", "2026-03-22", "--to", "2026-03-22", *extra]


def test_dry_run_changes_nothing(world):
    call_command("rollback_schedule", *_args(world, "--dry-run"))
    assert ScheduleSlot.objects.get(is_active=True).teacher_id == world["new"].id
    assert Session.objects.get(date=SUNDAY).teacher_id == world["new"].id


def test_real_run_restores_and_resyncs_then_is_idempotent(world):
    call_command("rollback_schedule", *_args(world, "--yes"))
    assert ScheduleSlot.objects.get(is_active=True).teacher_id == world["old"].id
    assert [s.teacher_id for s in Session.objects.filter(date=SUNDAY)] == [world["old"].id]
    total = ScheduleSlot.objects.count()
    call_command("rollback_schedule", *_args(world, "--yes"))
    assert ScheduleSlot.objects.count() == total, "جدولٌ يطابق اللقطة لا يُستعاد ثانيةً"
    assert Session.objects.filter(date=SUNDAY).count() == 1


def test_refuses_when_a_session_in_range_was_touched(world):
    session = Session.objects.get(date=SUNDAY)
    Session.objects.filter(pk=session.pk).update(status="completed")
    with pytest.raises(CommandError, match="1 جلسةً ممسوسةً"):
        call_command("rollback_schedule", *_args(world, "--yes"))
    assert ScheduleSlot.objects.get(is_active=True).teacher_id == world["new"].id
    assert StudentAttendance.objects.count() == 0
