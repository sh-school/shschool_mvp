"""بحثُ الطالب بالاسم عند إنشاء الانتقال، وتعديلُ الانتقال المعلَّق (W-20261114-010)."""

import datetime as dt

import pytest
from django.urls import reverse

from core.models.audit import AuditLog
from student_affairs.models import StudentTransfer
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory
from tests.visual_snapshots import FIXED_NOW

# الساعةُ مثبَّتةٌ: نافذةُ رجوع التاريخ في الانتقال الداخليّ تقرأ «اليوم».
pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

PAST = FIXED_NOW.date() - dt.timedelta(days=1)
LATER = FIXED_NOW.date() - dt.timedelta(days=2)
SEARCH = "student_affairs:transfer_student_search"


@pytest.fixture
def klass2(school, year, wing):
    return ClassGroupFactory(  # noqa: F405
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def foreign_student():
    """طالبٌ في مدرسةٍ أخرى باسمٍ يطابق البحث نفسه."""
    other = SchoolFactory()
    student = UserFactory(full_name="طالب مدرسة أخرى", national_id="29000001090")
    MembershipFactory(user=student, school=other, role=RoleFactory(school=other, name="student"))
    return student


def _transfer(school, student, user, status="pending", direction="out", target=None):
    return StudentTransfer.objects.create(
        school=school,
        student=student,
        direction=direction,
        other_school_name=school.name if direction == "internal" else "مدرسة أولى",
        to_class_group=target,
        transfer_date=PAST,
        status=status,
        academic_year="2026-2027",
        created_by=user,
        updated_by=user,
    )


def _edit_url(transfer):
    return reverse("student_affairs:transfer_edit", args=[transfer.pk])


# ── البحث ──


def test_search_suggests_only_my_schools_students(
    client, student_affairs_coordinator_user, kid, klass, foreign_student
):
    client.force_login(student_affairs_coordinator_user)

    body = client.get(reverse(SEARCH), {"q": "طالب"}).content.decode()

    assert str(kid.pk) in body and klass.short_label in body
    assert str(foreign_student.pk) not in body and foreign_student.full_name not in body


def test_one_character_does_not_search(client, student_affairs_coordinator_user, kid):
    client.force_login(student_affairs_coordinator_user)

    body = client.get(reverse(SEARCH), {"q": "ط"}).content.decode()

    assert "data-student-pick" not in body


def test_search_returns_at_most_ten(client, student_affairs_coordinator_user, school):
    role = RoleFactory(school=school, name="student")
    for index in range(12):
        student = UserFactory(full_name=f"طالب تجريبي {index}", national_id=f"2900000{index:04d}")
        MembershipFactory(user=student, school=school, role=role)
    client.force_login(student_affairs_coordinator_user)

    body = client.get(reverse(SEARCH), {"q": "تجريبي"}).content.decode()

    assert body.count("data-student-pick") == 10


def test_search_is_refused_without_the_transfers_capability(client, teacher, kid):
    client.force_login(teacher)

    response = client.get(reverse(SEARCH), {"q": "طالب"})

    assert response.status_code in (302, 403)
    assert "data-student-pick" not in response.content.decode()


# ── التعديل ──


def test_editing_a_pending_transfer_saves_and_audits_field_names_only(
    client, student_affairs_coordinator_user, school, kid
):
    transfer = _transfer(school, kid, student_affairs_coordinator_user)
    client.force_login(student_affairs_coordinator_user)

    response = client.post(
        _edit_url(transfer),
        {
            "other_school_name": "مدرسة ثانية",
            "transfer_date": LATER.isoformat(),
            "reason": "سبب جديد",
        },
    )

    assert response.status_code == 302
    transfer.refresh_from_db()
    assert (transfer.other_school_name, transfer.transfer_date) == ("مدرسة ثانية", LATER)
    entry = AuditLog.objects.get(school=school, object_repr="تعديل انتقال معلَّق")
    assert set(entry.changes["changed_fields"]) == {"other_school_name", "transfer_date", "reason"}
    assert "مدرسة ثانية" not in str(entry.changes) and kid.full_name not in str(entry.changes)


def test_editing_an_internal_pending_transfer_changes_the_target(
    client, student_affairs_coordinator_user, school, kid, klass, klass2
):
    transfer = _transfer(school, kid, student_affairs_coordinator_user, direction="internal")
    client.force_login(student_affairs_coordinator_user)

    response = client.post(
        _edit_url(transfer),
        {"to_class_group_id": str(klass2.pk), "transfer_date": PAST.isoformat()},
    )

    assert response.status_code == 302
    transfer.refresh_from_db()
    assert transfer.to_class_group_id == klass2.pk


@pytest.mark.parametrize("status", ["approved", "completed"])
def test_editing_a_non_pending_transfer_is_refused(
    client, student_affairs_coordinator_user, school, kid, status
):
    transfer = _transfer(school, kid, student_affairs_coordinator_user, status=status)
    client.force_login(student_affairs_coordinator_user)

    page = client.get(_edit_url(transfer), follow=True)
    response = client.post(
        _edit_url(transfer),
        {"other_school_name": "مدرسة ثانية", "transfer_date": LATER.isoformat()},
    )

    assert "لا يُعدَّل إلا الانتقالُ المعلَّق" in page.content.decode()
    assert response.status_code == 302
    transfer.refresh_from_db()
    assert transfer.other_school_name == "مدرسة أولى"
    assert not AuditLog.objects.filter(object_repr="تعديل انتقال معلَّق").exists()


def test_editing_is_refused_without_the_transfers_capability(
    client, teacher, student_affairs_coordinator_user, school, kid
):
    transfer = _transfer(school, kid, student_affairs_coordinator_user)
    client.force_login(teacher)

    response = client.post(
        _edit_url(transfer),
        {"other_school_name": "مدرسة ثانية", "transfer_date": LATER.isoformat()},
    )

    assert response.status_code in (302, 403)
    transfer.refresh_from_db()
    assert transfer.other_school_name == "مدرسة أولى"


def test_the_edit_link_shows_for_pending_only(
    client, student_affairs_coordinator_user, school, kid
):
    pending = _transfer(school, kid, student_affairs_coordinator_user)
    approved = _transfer(school, kid, student_affairs_coordinator_user, status="approved")
    client.force_login(student_affairs_coordinator_user)

    listing = client.get(reverse("student_affairs:transfer_list")).content.decode()
    detail = client.get(reverse("student_affairs:transfer_detail", args=[approved.pk]))

    assert _edit_url(pending) in listing and _edit_url(approved) not in listing
    assert _edit_url(approved) not in detail.content.decode()
