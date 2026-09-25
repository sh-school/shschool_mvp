"""[BREACH] إنذارُ مهلة الـ72 ساعة يصل داخل المنصّة — لا بالبريد وحدَه.

كان `_send_breach_alert` يرسل بالبريد وحدَه إلى `DPO_EMAIL` والمكلَّف والمُبلِّغ، و`DPO_EMAIL`
ومزوّدُ البريد غيرُ مضبوطَين في الإنتاج (DPIA R8): المؤقّتُ يعمل ولا يصل أحداً. فصار التنبيهُ
يُكتب في جرس المنصّة أيضاً، بلا بياناتٍ شخصيّة في نصّه.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.models import BreachReport, School
from notifications.models import InAppNotification
from notifications.tasks import BREACH_INAPP_REPEAT_HOURS, _notify_breach_in_app
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

SECRET_TITLE = "خرقٌ يذكر الطالب فلان بن فلان"


@pytest.fixture
def school(db):
    return School.objects.create(name="مدرسة الخرق", code="SHH-BRC")


def _member(school, role_name, **fields):
    user = UserFactory(**fields)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


@pytest.fixture
def breach(school):
    reporter = _member(school, "teacher")
    return BreachReport.objects.create(
        school=school,
        title=SECRET_TITLE,
        description="وصف",
        discovered_at=timezone.now() - timedelta(hours=62),
        reported_by=reporter,
    )


def _got(user, breach):
    return InAppNotification.objects.filter(user=user, related_object_id=str(breach.pk))


def test_the_principal_the_developer_and_the_reporter_are_notified(school, breach):
    principal = _member(school, "principal")
    developer = _member(school, "platform_developer")
    bystander = _member(school, "teacher")

    _notify_breach_in_app(breach, 10)

    assert _got(principal, breach).count() == 1
    assert _got(developer, breach).count() == 1
    assert _got(breach.reported_by, breach).count() == 1
    assert not _got(bystander, breach).exists()


def test_the_assignee_is_notified(school, breach):
    assignee = _member(school, "teacher")
    breach.assigned_to = assignee
    breach.save()

    _notify_breach_in_app(breach, 10)

    assert _got(assignee, breach).count() == 1


def test_the_dpo_by_email_is_notified(school, breach, settings):
    settings.DPO_EMAIL = "dpo@example.com"
    dpo = UserFactory(email="DPO@example.com")
    MembershipFactory(user=dpo, school=school, role=RoleFactory(school=school, name="teacher"))

    _notify_breach_in_app(breach, 10)

    assert _got(dpo, breach).count() == 1


def test_the_text_carries_no_personal_data_nor_the_breach_title(school, breach):
    principal = _member(school, "principal")

    _notify_breach_in_app(breach, 10)

    note = _got(principal, breach).get()
    assert "فلان" not in note.title + note.body
    assert note.related_url == f"/breach/{breach.pk}/"
    assert note.priority == "urgent"


def test_the_hourly_task_does_not_repeat_within_the_window(school, breach):
    principal = _member(school, "principal")

    first = _notify_breach_in_app(breach, 10)
    again = _notify_breach_in_app(breach, 9)

    assert first >= 1 and again == 0
    assert _got(principal, breach).count() == 1


def test_it_repeats_after_the_window(school, breach):
    principal = _member(school, "principal")
    _notify_breach_in_app(breach, 10)
    InAppNotification.objects.filter(related_object_id=str(breach.pk)).update(
        created_at=timezone.now() - timedelta(hours=BREACH_INAPP_REPEAT_HOURS + 1)
    )

    _notify_breach_in_app(breach, 2)

    assert _got(principal, breach).count() == 2


def test_overdue_says_so(school, breach):
    principal = _member(school, "principal")

    _notify_breach_in_app(breach, 0, overdue=True)

    assert "تجاوزتَ" in _got(principal, breach).get().title


def test_another_school_hears_nothing(school, breach):
    other = School.objects.create(name="مدرسةٌ أخرى", code="SHH-OTH")
    stranger = _member(other, "principal")

    _notify_breach_in_app(breach, 10)

    assert not _got(stranger, breach).exists()


def test_the_alert_reaches_the_bell_even_when_email_is_not_configured(school, breach, settings):
    """جوهرُ الإصلاح: لا `DPO_EMAIL` ولا مزوّد — والتنبيهُ يصل."""
    from notifications.tasks import _send_breach_alert

    settings.DPO_EMAIL = ""
    settings.EMAIL_BACKEND = "core.mail_backends.UndeliveredEmailBackend"
    principal = _member(school, "principal")

    _send_breach_alert(breach, 6)

    assert _got(principal, breach).count() == 1
