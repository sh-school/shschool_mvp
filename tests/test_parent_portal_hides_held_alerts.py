"""[LEGAL] بوّابةُ وليّ الأمر لا تعرض تنبيهَ غيابٍ «محجوزاً» أو «قيد الإصدار» (W-20261008-011، D-246م).

التنبيهُ يُنشأ `held` ولا يصير للأهل شيءٌ إلا بزرّ حاصر الغياب بعد ح4 (`issuing` وسيطةٌ أثناء الإرسال). فعرضُه في البوّابة قبل ذلك يُخبر وليَّ الأمر
بغيابٍ لم تُصدر المدرسةُ إخطارَه — خرقٌ لقرار المالك. والحالاتُ `pending` و`notified` و`resolved` تبقى ظاهرةً كما كانت.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import ParentStudentLink
from operations.models import AbsenceAlert
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff

pytestmark = pytest.mark.django_db

#: عددُ أيّام الغياب مفتاحُ التمييز بين الحالات في الصفحة (لكلّ حالةٍ رقمٌ فريد).
COUNTS = {"held": 11, "issuing": 12, "pending": 13, "notified": 14, "resolved": 15}


@pytest.fixture
def parent(school, kid):
    user = _staff(school, "parent", "وليّ أمرٍ مرتبط", "29000007001")
    user.consent_given_at = timezone.now()  # بلا موافقةٍ تُحوَّل الصفحةُ إلى /parents/consent/
    user.save(update_fields=["consent_given_at"])
    ParentStudentLink.objects.create(
        parent=user, student=kid, school=school, can_view_attendance=True
    )
    return user


@pytest.fixture
def alerts(school, kid):
    for status, count in COUNTS.items():
        AbsenceAlert.objects.create(
            school=school,
            student=kid,
            absence_count=count,
            gate=f"s1_{status}"[:20],
            period_start=dt.date(2025, 9, 1),
            period_end=dt.date(2026, 6, 30),
            status=status,
        )


def _shown(page: str) -> set[str]:
    return {status for status, count in COUNTS.items() if f"{count} غياب" in page}


def test_the_childs_attendance_page_hides_held_and_issuing_only(client_as, parent, kid, alerts):
    response = client_as(parent).get(reverse("parent_student_attendance", args=[kid.id]))
    page = response.content.decode()

    assert response.status_code == 200
    assert _shown(page) == {"pending", "notified", "resolved"}


def test_the_all_children_summary_hides_held_and_issuing_only(client_as, parent, kid, alerts):
    response = client_as(parent).get(reverse("parent_all_attendance"))
    page = response.content.decode()

    assert response.status_code == 200
    assert _shown(page) == {"pending", "notified", "resolved"}


def test_the_notify_task_refuses_a_held_alert(school, kid, alerts):
    """مسارٌ آخرُ يُخرج لوليّ الأمر: مهمّةُ الإشعار بالمعرّف لا تُرسل محجوزاً."""
    from unittest.mock import patch

    from notifications.tasks import notify_absence_task

    held = AbsenceAlert.objects.get(status="held")
    with patch("notifications.services.NotificationService.notify_absence") as notify:
        result = notify_absence_task.apply(
            args=[str(held.pk)], kwargs={"school_id": school.pk}
        ).result

    assert result["skipped"] == "held"
    notify.assert_not_called()


def test_the_constant_names_exactly_the_two_hidden_states():
    assert AbsenceAlert.HIDDEN_FROM_PARENTS == ("held", "issuing")
