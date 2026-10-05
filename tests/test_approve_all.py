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


def test_the_approve_all_button_is_in_the_absence_dashboards_themselves(
    client_as, now_0830, klass, session, teacher, holder, kid
):
    """ملاحظةُ المالك: الزرُّ في لوحة الغياب (شبكةُ الشعبة وتقريرُ غياب اليوم) لا في صفحةٍ جانبيّةٍ وحدَها."""
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    url = reverse("attendance_approve_all")
    grid = (
        client_as(holder)
        .get(reverse("wings:record_section", args=[klass.id]), {"date": SUNDAY.isoformat()})
        .content.decode()
    )
    assert url in grid and "اعتمادُ الكلّ (1)" in grid
    report = (
        client_as(holder)
        .get(reverse("daily_report"), {"date": SUNDAY.isoformat()})
        .content.decode()
    )
    assert url in report and "اعتمادُ الكلّ (1)" in report


def test_the_button_returns_to_the_page_it_was_pressed_from_and_ignores_foreign_hosts(
    client_as, now_0830, session, teacher, holder, kid
):
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    back = client_as(holder).post(
        reverse("attendance_approve_all"), {"next": "/teacher/reports/daily/?date=2026-09-13"}
    )
    assert back.url == "/teacher/reports/daily/?date=2026-09-13"
    foreign = client_as(holder).post(
        reverse("attendance_approve_all"), {"next": "https://evil.example/x"}
    )
    assert foreign.url == reverse("attendance_approvals")


def test_the_button_is_absent_when_nothing_waits(client_as, now_0830, klass, session, holder, kid):
    body = (
        client_as(holder)
        .get(reverse("wings:record_section", args=[klass.id]), {"date": SUNDAY.isoformat()})
        .content.decode()
    )
    assert "اعتمادُ الكلّ" not in body


def test_the_supervisor_sheet_opens_with_the_teachers_pending_absence_checked(
    client_as, now_0830, klass, session, teacher, holder, kid
):
    """واقعة «الكلُّ سُجّل حاضراً» 2026-10-05: كان الكشفُ يفتح الجميعَ حاضراً فيكتب تثبيتُه حاضراً فوق غياب المعلّم."""
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    body = (
        client_as(holder)
        .get(
            reverse("wings:record_section", args=[klass.id]),
            {"date": SUNDAY.isoformat(), "p": "07:10"},
        )
        .content.decode()
    )
    assert f'name="s-{kid.id}" value="absent" checked' in body
    assert f'name="s-{kid.id}" value="present" checked' not in body


def test_confirming_the_prefilled_sheet_records_the_teachers_absence_not_present(
    client_as, now_0830, klass, session, teacher, holder, kid
):
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    client_as(holder).post(
        reverse("wings:record_period", args=[klass.id]),
        {"date": SUNDAY.isoformat(), "start": "07:10", f"s-{kid.id}": "absent"},
    )
    assert StudentAttendance.objects.get(session=session, student=kid).status == "absent"


def test_a_special_education_teacher_sees_the_same_shared_sheet_and_the_absence_is_final(
    client_as, now_0830, school, special_klass, teacher, bells
):
    """أمرُ المالك 2026-10-04: تصميمٌ واحد — شعبةُ ESE (بلا جناح) تُرسم بالكشف المشترك نفسِه، وإدخالُها نهائيٌّ مباشر (D-126م)."""
    from tests.attendance_fixtures import ENROLLED
    from tests.conftest import MembershipFactory, RoleFactory, StudentEnrollmentFactory, UserFactory

    pupil = UserFactory(full_name="طالب خاصّ", national_id="29000001077")
    StudentEnrollmentFactory(student=pupil, class_group=special_klass, enrolled_at=ENROLLED)
    MembershipFactory(user=pupil, school=school, role=RoleFactory(school=school, name="student"))
    ese = Session.objects.create(
        school=school,
        class_group=special_klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )
    page = client_as(teacher).get(reverse("attendance", args=[ese.id]))
    body = page.content.decode()
    assert 'class="per-head"' in body and f'name="s-{pupil.id}"' in body
    assert "student_row" not in body and "mark_all_present" not in body  # لا قائمةَ قديمة
    client_as(teacher).post(
        reverse("attendance_period_entries", args=[ese.id]), {f"s-{pupil.id}": "absent"}
    )
    assert StudentAttendance.objects.get(session=ese, student=pupil).status == "absent"
