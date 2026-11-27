"""U-09 (PDPPL): قنواتُ وليّ الأمر الخارجية بنصٍّ محايد — والتفاصيلُ داخل المنصّة وحدَها.

الحارس: لا اسمَ طالبٍ ولا سببَ ولا مخالفةَ ولا درجةَ ولا مواد في SMS وواتساب وإشعار الجوال وعنوان البريد.
"""

import datetime as dt
from unittest.mock import patch

import pytest
from django.urls import reverse
from django.utils import timezone

from behavior.services import BehaviorService
from clinic.models import ClinicVisit
from clinic.services import ClinicService
from notifications.models import InAppNotification, NotificationSettings
from notifications.parent_neutral import PARENT_NEUTRAL_BODY, PARENT_NEUTRAL_TITLE
from notifications.services import DeliveryOutcome, NotificationService
from notifications.tasks import notify_absence_task
from operations.models import AbsenceAlert
from wings import absence_notice_services

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

NAME = "طالبٌ-مميَّزُ-الاسم"
REASON = "سببٌ-سرّيٌّ-91"
SUBJECT_NAME = "مادةٌ-سرّيّةٌ-92"
HUB_TASK = "notifications.tasks.hub_send_notification_task.delay"


@pytest.fixture
def family(school, student_user, parent_user):
    student_user.full_name = NAME
    student_user.save(update_fields=["full_name"])
    parent_user.email = "parent@example.com"
    parent_user.phone = "+97455000001"
    parent_user.save()
    return student_user, parent_user


def _alert(school, student, status="pending"):
    return AbsenceAlert.objects.create(
        school=school,
        student=student,
        absence_count=7,
        gate="s1_midterm",
        period_start=dt.date(2025, 9, 1),
        period_end=dt.date(2026, 1, 31),
        status=status,
    )


def _assert_neutral(*texts):
    for text in texts:
        for secret in (NAME, REASON, SUBJECT_NAME):
            assert secret not in text


def _inapp(parent):
    note = InAppNotification.objects.get(user=parent)
    return f"{note.title}\n{note.body}"


# ── الغياب والرسوب: SMS وعنوان البريد ──


@pytest.mark.parametrize("kind", ["absence", "fail"])
def test_absence_and_fail_sms_and_subject_are_neutral(school, family, kind):
    student, _parent = family
    NotificationSettings.objects.update_or_create(
        school=school,
        defaults={
            "sms_enabled": True,
            "absence_email_enabled": True,
            "fail_email_enabled": True,
            "absence_email_subject": "غياب {student_name}",
            "fail_email_subject": "نتيجة {student_name}",
        },
    )
    ok = DeliveryOutcome(True, None)
    with (
        patch.object(NotificationService, "deliver_email", return_value=ok) as email,
        patch.object(NotificationService, "deliver_sms", return_value=ok) as sms,
    ):
        if kind == "absence":
            NotificationService.notify_absence(_alert(school, student))
        else:
            NotificationService.notify_fail(student, school, [SUBJECT_NAME], year="2025-2026")

    assert email.call_args.kwargs["subject"] == PARENT_NEUTRAL_TITLE
    assert sms.call_args.kwargs["message"] == PARENT_NEUTRAL_BODY
    # متنُ البريد كما كان بتفاصيله
    assert NAME in email.call_args.kwargs["body_text"]


def test_absence_task_push_is_neutral(school, family):
    student, _parent = family
    alert = _alert(school, student)
    with (
        patch.object(NotificationService, "notify_absence", return_value=[]),
        patch("notifications.push_publisher.enqueue_push") as push,
    ):
        notify_absence_task.run(str(alert.pk), school_id=str(school.pk))

    assert push.call_args.kwargs["title"] == PARENT_NEUTRAL_TITLE
    assert push.call_args.kwargs["body"] == PARENT_NEUTRAL_BODY


# ── الاستدعاء الآلي واليدوي ──


def test_auto_summon_channels_neutral_and_in_app_detailed(
    school, family, behavior_infraction, principal_user, django_capture_on_commit_callbacks
):
    _student, parent = family
    with patch(HUB_TASK) as task, django_capture_on_commit_callbacks(execute=True):
        BehaviorService._auto_summon_parent(behavior_infraction, principal_user, REASON)

    sent = task.call_args.kwargs
    assert {"sms", "whatsapp", "push", "email"} <= set(sent["channels"])
    assert sent["title"] == PARENT_NEUTRAL_TITLE
    assert sent["body"] == PARENT_NEUTRAL_BODY
    assert "email_text" not in sent  # متنُ البريد هو المتنُ المحايد
    assert NAME in _inapp(parent)
    assert REASON in _inapp(parent)


def test_manual_summon_keeps_only_appointment_and_place(
    school, family, principal_user, client_as, django_capture_on_commit_callbacks
):
    student, parent = family
    client = client_as(principal_user)
    with patch(HUB_TASK) as task, django_capture_on_commit_callbacks(execute=True):
        client.post(
            reverse("behavior:summon_parent"),
            {
                "student_id": str(student.pk),
                "reason": REASON,
                "summon_date": "2026-03-01",
                "summon_time": "09:30",
                "meeting_place": "other",
                "meeting_place_other": "قاعة الاجتماعات",
            },
        )

    sent = task.call_args.kwargs
    assert sent["title"] == PARENT_NEUTRAL_TITLE
    assert sent["body"] == (
        f"{PARENT_NEUTRAL_BODY}\n"
        "الموعد المطلوب: 2026-03-01 الساعة 09:30\n"
        "مكان الاجتماع: قاعة الاجتماعات"
    )
    assert "email_text" not in sent
    _assert_neutral(sent["title"], sent["body"])
    assert NAME in _inapp(parent)
    assert REASON in _inapp(parent)


# ── إخطار الغياب بزرّ حاصر الغياب ──


def test_absence_notice_channels_neutral_with_date_and_email_body_detailed(
    school, family, principal_user, django_capture_on_commit_callbacks
):
    from operations.absence_policy import gates_for

    student, parent = family
    alert = _alert(school, student, status="held")
    gate = next(g for g in gates_for("G7") if g.key == "s1_midterm")
    now = timezone.now()

    with (
        patch("wings.services.holds_school_wide", return_value=True),
        patch.object(absence_notice_services, "period_four_over", return_value=True),
        patch.object(absence_notice_services, "_still_due", return_value=(True, gate, 5)),
        patch(HUB_TASK) as task,
        django_capture_on_commit_callbacks(execute=True),
    ):
        absence_notice_services.issue(principal_user, school, alert.pk, now=now)

    sent = task.call_args.kwargs
    notice_date = f"{timezone.localtime(now):%Y/%m/%d}"
    assert sent["title"] == PARENT_NEUTRAL_TITLE
    assert sent["body"] == f"{PARENT_NEUTRAL_BODY}\nتاريخ الإخطار: {notice_date}"
    note = InAppNotification.objects.get(user=parent)
    assert NAME in note.title
    assert sent["email_text"] == note.body


# ── العيادة: عنوان البريد ──


def test_clinic_email_subject_has_no_name(school, family, nurse_user):
    student, _parent = family
    visit = ClinicVisit.objects.create(
        school=school, student=student, nurse=nurse_user, reason=REASON, is_sent_home=True
    )
    with patch.object(NotificationService, "deliver_email") as email:
        assert ClinicService.confirm_referral_notice(visit, school, nurse_user) is True

    assert email.call_args.kwargs["subject"] == PARENT_NEUTRAL_TITLE
