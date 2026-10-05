"""[W-20261004-014] «اعتمادُ الكلّ» للمشرف — أمرُ المالك 2026-10-04: لا يعتمد حصّةً حصّةً لخمس شعب.

كلُّ إدخالٍ في طابوره (كلُّ الشعب والحصص) يمرّ بـ`decide_entry` نفسِه فيُسجَّل قرارُه باسمه؛ والرفضُ يبقى بنداً بنداً؛ ومن لا يملك الاعتمادَ لا يستطيع.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.attendance_entries import submit_entry
from operations.models import AttendanceDecision, Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

pytestmark = pytest.mark.django_db


@pytest.fixture
def now_0830(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(8, 30))


@pytest.fixture
def second(school, klass, teacher, session):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )


def test_approve_all_decides_every_pending_entry_across_periods_with_the_holders_name(
    client_as, now_0830, session, second, teacher, holder, kid
):
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    submit_entry(teacher, second, kid, "late", tardiness_minutes=5, now=at(8, 5))
    response = client_as(holder).post(reverse("attendance_approve_all"))
    assert response.status_code == 302
    assert AttendanceDecision.objects.filter(decided_by=holder, decision="approved").count() == 2
    assert StudentAttendance.objects.filter(student=kid).count() == 2  # الرصدُ الفعليّ كُتب لكلّ حصّة


def test_approve_all_is_idempotent_and_a_second_press_adds_nothing(
    client_as, now_0830, session, teacher, holder, kid
):
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    client_as(holder).post(reverse("attendance_approve_all"))
    client_as(holder).post(reverse("attendance_approve_all"))
    assert AttendanceDecision.objects.count() == 1


def test_a_teacher_cannot_approve_all(client_as, now_0830, session, teacher, holder, kid):
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    assert client_as(teacher).post(reverse("attendance_approve_all")).status_code == 403
    assert not AttendanceDecision.objects.exists()


def test_the_queue_page_shows_the_approve_all_button_with_the_count(
    client_as, now_0830, session, teacher, holder, kid
):
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    body = client_as(holder).get(reverse("attendance_approvals")).content.decode()
    assert reverse("attendance_approve_all") in body and "اعتمادُ الكلّ (1)" in body
