"""الانتقال الداخلي بين شعب المدرسة (W-20261005-008، المرحلة 2؛ D-201م: النقلُ يرحّل معه كلّ شيء).

الإتمامُ ذرّيّ: يُغلق التسجيلَ القديم وينشئ الجديد بتاريخ الانتقال بلا حذف. ويُرفض هدفٌ من صفٍّ آخر أو شعبةُ الطالب نفسُها،
وتاريخٌ في المستقبل. والوارد والصادر الخارجيّ كما كانا.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.models import StudentEnrollment
from student_affairs.internal_transfer import internal_target_error
from student_affairs.models import StudentTransfer
from tests.attendance_fixtures import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db

PAST = dt.date(2026, 10, 1)


@pytest.fixture
def klass2(school, year, wing):
    return ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def other_grade(school, year, wing):
    return ClassGroupFactory(
        school=school, grade="G8", section="1", level_type="prep", academic_year=year, wing=wing
    )


def _request(school, student, target, user, date=PAST):
    return StudentTransfer.objects.create(
        school=school,
        student=student,
        direction="internal",
        other_school_name=school.name,
        to_class_group=target,
        transfer_date=date,
        academic_year="2026-2027",
        created_by=user,
        updated_by=user,
    )


def _complete(client, user, transfer):
    client.force_login(user)
    return client.post(
        reverse("student_affairs:transfer_review", args=[transfer.pk]),
        {"action": "completed", "notes": ""},
    )


def test_completing_moves_the_enrollment_without_deleting_anything(
    client, student_affairs_coordinator_user, school, kid, klass, klass2
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)

    _complete(client, student_affairs_coordinator_user, transfer)

    transfer.refresh_from_db()
    assert transfer.status == "completed"
    old = StudentEnrollment.objects.get(student=kid, class_group=klass)
    new = StudentEnrollment.objects.get(student=kid, class_group=klass2)
    assert (old.is_active, new.is_active, new.enrolled_at) == (False, True, PAST)
    assert StudentEnrollment.objects.filter(student=kid).count() == 2


def test_the_move_does_not_touch_the_membership(
    client, student_affairs_coordinator_user, school, kid, klass2
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)

    _complete(client, student_affairs_coordinator_user, transfer)

    assert kid.memberships.filter(school=school, is_active=True).exists()


@pytest.mark.parametrize("target_fixture", ["other_grade", "klass"])
def test_a_target_of_another_grade_or_the_same_class_is_refused_and_nothing_is_written(
    client, student_affairs_coordinator_user, school, kid, klass, request, target_fixture
):
    target = request.getfixturevalue(target_fixture)
    transfer = _request(school, kid, target, student_affairs_coordinator_user)

    _complete(client, student_affairs_coordinator_user, transfer)

    transfer.refresh_from_db()
    assert transfer.status == "pending"
    assert list(StudentEnrollment.objects.filter(student=kid)) == [
        StudentEnrollment.objects.get(student=kid, class_group=klass)
    ]
    assert StudentEnrollment.objects.get(student=kid).is_active


def test_a_future_date_is_refused(client, student_affairs_coordinator_user, school, kid, klass2):
    transfer = _request(
        school, kid, klass2, student_affairs_coordinator_user, date=dt.date(2099, 1, 1)
    )

    _complete(client, student_affairs_coordinator_user, transfer)

    transfer.refresh_from_db()
    assert transfer.status == "pending"
    assert StudentEnrollment.objects.filter(student=kid).count() == 1


def test_a_student_without_an_active_enrollment_cannot_move(
    school, student_user, klass2, student_affairs_coordinator_user
):
    transfer = _request(school, student_user, klass2, student_affairs_coordinator_user)

    assert "بلا تسجيل" in internal_target_error(transfer)


def test_the_create_form_requires_a_target_for_an_internal_move(
    client, student_affairs_coordinator_user, kid
):
    client.force_login(student_affairs_coordinator_user)

    response = client.post(
        reverse("student_affairs:transfer_create"),
        {"student_id": str(kid.pk), "direction": "internal", "transfer_date": "2026-10-01"},
    )

    assert response.status_code == 200
    assert not StudentTransfer.objects.exists()


def test_the_create_form_saves_an_internal_request_and_shows_the_class_beside_the_student(
    client, student_affairs_coordinator_user, school, kid, klass, klass2
):
    client.force_login(student_affairs_coordinator_user)

    page = client.get(reverse("student_affairs:transfer_create"))
    assert f'data-class-id="{klass.pk}"' in page.content.decode()
    assert klass.short_label in page.content.decode()

    response = client.post(
        reverse("student_affairs:transfer_create"),
        {
            "student_id": str(kid.pk),
            "direction": "internal",
            "to_class_group_id": str(klass2.pk),
            "transfer_date": "2026-10-01",
        },
    )

    assert response.status_code == 302
    saved = StudentTransfer.objects.get()
    assert (saved.direction, saved.to_class_group_id) == ("internal", klass2.pk)


def test_the_create_form_refuses_a_target_of_another_grade(
    client, student_affairs_coordinator_user, kid, other_grade
):
    client.force_login(student_affairs_coordinator_user)

    response = client.post(
        reverse("student_affairs:transfer_create"),
        {
            "student_id": str(kid.pk),
            "direction": "internal",
            "to_class_group_id": str(other_grade.pk),
            "transfer_date": "2026-10-01",
        },
    )

    assert response.status_code == 200
    assert not StudentTransfer.objects.exists()


def test_an_external_outgoing_transfer_still_deactivates_as_before(
    client, student_affairs_coordinator_user, school, kid, klass
):
    transfer = StudentTransfer.objects.create(
        school=school,
        student=kid,
        direction="out",
        other_school_name="مدرسة أخرى",
        transfer_date=PAST,
        academic_year="2026-2027",
        created_by=student_affairs_coordinator_user,
        updated_by=student_affairs_coordinator_user,
    )

    _complete(client, student_affairs_coordinator_user, transfer)

    assert not StudentEnrollment.objects.get(student=kid, class_group=klass).is_active
