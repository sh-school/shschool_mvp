"""أثرُ التدقيق على ما يوسّع صلاحيةَ منسّق شؤون الطلبة (W-20261001-020، ملاحظات 0104).

إيقافُ القيد وانتقالُ الطالب يعطّلان عضويّتَه بتحديثٍ جماعيّ (`queryset.update`) لا يُطلق إشاراتِ التدقيق،
فيُكتب الأثرُ صراحةً وبلا اسمٍ شخصيّ. ومنعُ الاعتماد للمنسّق لا يتجاوزه تعيينُه حاملَ جناح.
"""

import datetime as dt

import pytest
from django.urls import reverse

from core.models import AuditLog, Membership
from student_affairs.models import StudentTransfer
from tests.attendance_fixtures import *  # noqa: F401,F403

pytestmark = pytest.mark.django_db


def _events(event):
    return AuditLog.objects.filter(changes__event=event)


def test_deactivating_a_student_leaves_an_audit_trail(
    client, student_affairs_coordinator_user, student_user, school
):
    client.force_login(student_affairs_coordinator_user)

    response = client.post(reverse("student_affairs:student_deactivate", args=[student_user.pk]))

    assert response.status_code == 302
    assert not Membership.objects.filter(user=student_user, school=school, is_active=True).exists()
    entry = _events("student_deactivated").get()
    assert entry.user == student_affairs_coordinator_user
    assert entry.object_id == str(student_user.pk)
    assert student_user.full_name not in entry.object_repr


@pytest.mark.parametrize("decision", ["approved", "rejected", "completed"])
def test_every_transfer_decision_leaves_an_audit_trail(
    client, student_affairs_coordinator_user, student_user, school, decision
):
    transfer = StudentTransfer.objects.create(
        school=school,
        student=student_user,
        direction="out",
        other_school_name="مدرسة أخرى",
        transfer_date=dt.date(2026, 10, 8),
        academic_year="2026-2027",
        created_by=student_affairs_coordinator_user,
        updated_by=student_affairs_coordinator_user,
    )
    client.force_login(student_affairs_coordinator_user)

    client.post(
        reverse("student_affairs:transfer_review", args=[transfer.pk]),
        {"action": decision, "notes": "سبب القرار"},
    )

    entry = _events(f"transfer_{decision}").get()
    assert entry.user == student_affairs_coordinator_user
