"""[BREACH] تنبيهُ المكلَّف عند إسناد بلاغ خرق (DBT-24) — مرّةً لكلّ تغيير، بلا بياناتٍ شخصيّة، ولا إشعارَ للإسناد الذاتيّ.

PDPPL م.11: مهلةُ إشعار الجهة 72 ساعة. كان تسجيلُ الخرق بمكلَّفٍ (أو تغييرُ المكلَّف) يمرّ صامتاً — فلا يعلم من
كُلِّف إلّا بتذكير المهلة. والثوابت:

    إسنادٌ جديد          يصل المكلَّفَ إشعارٌ واحدٌ عبر `NotificationHub` برابط البلاغ
    تغييرُ المكلَّف        يصل الجديدَ وحدَه
    بلا تغيير             لا إشعار — ولا عند إعادة إرسال النموذج نفسه (مقارنةٌ بما تحت القفل)
    إسنادٌ ذاتيّ           لا إشعارَ لمن أسند نفسَه
    النصّ                 لا عنوانَ بلاغٍ ولا اسمَ ولا رقماً — خطورةٌ ومهلةٌ ورابطٌ فقط
    العطل                 إن تعطّل الإشعارُ سُجِّل الخطأ وبقي التسجيلُ/التعديل
    التذكيرات القائمة       لا تتغيّر (`test_breach_alert_in_app`)
"""

import logging
from datetime import timedelta

import pytest
from django.utils import timezone

from breach import services
from breach.forms import BreachEditForm, BreachReportForm
from core.models import BreachReport
from notifications.models import InAppNotification
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

#: عنوانٌ فيه ما لا يجوز أن يظهر في الإشعار — يُبنى بالاسم لا برقمٍ حقيقيّ.
SENSITIVE_TITLE = "تسريبُ كشفٍ فيه بياناتُ الطالب فلان"


def staff(school, role, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def reporter(school):
    return staff(school, "principal", "المُبلِّغ")


@pytest.fixture
def assignee(school):
    return staff(school, "vice_admin", "المكلَّف الأوّل")


@pytest.fixture
def other_assignee(school):
    return staff(school, "vice_academic", "المكلَّف الثاني")


def data(**extra):
    when = (timezone.now() - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M")
    base = {
        "title": SENSITIVE_TITLE,
        "description": "وصفٌ",
        "severity": "high",
        "data_type_affected": "personal",
        "affected_count": "3",
        "discovered_at": when,
    }
    base.update({k: (v.pk if hasattr(v, "pk") else v) for k, v in extra.items()})
    return base


def register(school, user, **extra):
    form = BreachReportForm(data(**extra), school=school)
    assert form.is_valid(), form.errors
    return services.register_breach(form=form, user=user, school=school)


def edit(school, breach, user, **extra):
    fields = {"title": breach.title, "description": breach.description, "severity": "high",
              "data_type_affected": "personal", "assigned_to": breach.assigned_to_id or ""}  # fmt: skip
    fields.update({k: (v.pk if hasattr(v, "pk") else v) for k, v in extra.items()})
    form = BreachEditForm(fields, instance=breach, school=school)
    assert form.is_valid(), form.errors
    return services.update_breach(breach, form, user=user)


def notes_for(user):
    return InAppNotification.objects.filter(user=user, title=services.ASSIGNED_TITLE)


# ── التسجيل ─────────────────────────────────────────────────────────────────────


def test_registering_with_an_assignee_notifies_them_once(school, reporter, assignee):
    breach = register(school, reporter, assigned_to=assignee)

    note = notes_for(assignee).get()
    assert note.related_url == f"/breach/{breach.pk}/"
    assert note.related_object_id == str(breach.pk)
    assert note.priority == "urgent" and note.school == school
    assert not notes_for(reporter).exists()  # المُبلِّغُ ليس المكلَّف


def test_registering_without_an_assignee_notifies_nobody(school, reporter):
    register(school, reporter)

    assert not InAppNotification.objects.filter(title=services.ASSIGNED_TITLE).exists()


def test_assigning_yourself_notifies_nobody(school, assignee):
    register(school, assignee, assigned_to=assignee)

    assert not notes_for(assignee).exists()


# ── التعديل ─────────────────────────────────────────────────────────────────────


def test_changing_the_assignee_notifies_the_new_one_only(
    school, reporter, assignee, other_assignee
):
    breach = register(school, reporter, assigned_to=assignee)

    edit(school, breach, reporter, assigned_to=other_assignee)

    assert notes_for(other_assignee).count() == 1
    assert notes_for(assignee).count() == 1  # تنبيهُ التسجيل الأوّل وحدَه — لا سحبَ ولا تكرار
    assert notes_for(other_assignee).get().related_url == f"/breach/{breach.pk}/"


def test_assigning_later_to_an_unassigned_breach_notifies(school, reporter, assignee):
    breach = register(school, reporter)

    edit(school, breach, reporter, assigned_to=assignee)

    assert notes_for(assignee).count() == 1


def test_an_unchanged_assignee_is_not_notified_again(school, reporter, assignee):
    breach = register(school, reporter, assigned_to=assignee)

    edit(school, breach, reporter, description="تحديثُ الوصف فقط")
    edit(school, breach, reporter, immediate_action="عُزل النظام")

    assert notes_for(assignee).count() == 1


def test_resubmitting_the_same_change_does_not_notify_twice(
    school, reporter, assignee, other_assignee
):
    """نقرتان على «حفظ» بالنموذج نفسِه: الثانيةُ تقرأ الحالةَ تحت القفل فلا تجد تغييراً."""
    breach = register(school, reporter, assigned_to=assignee)

    first = BreachReport.objects.get(pk=breach.pk)  # ما قرأه العرضُ قبل الحفظين — نسختان قديمتان
    second = BreachReport.objects.get(pk=breach.pk)
    edit(school, first, reporter, assigned_to=other_assignee)
    edit(school, second, reporter, assigned_to=other_assignee)

    assert notes_for(other_assignee).count() == 1


def test_clearing_the_assignee_notifies_nobody(school, reporter, assignee):
    breach = register(school, reporter, assigned_to=assignee)
    before = InAppNotification.objects.count()

    edit(school, breach, reporter, assigned_to="")

    assert InAppNotification.objects.count() == before


def test_an_editor_who_assigns_themselves_is_not_notified(school, reporter, assignee):
    breach = register(school, reporter)

    edit(school, breach, assignee, assigned_to=assignee)

    assert not notes_for(assignee).exists()


# ── النصّ والقنوات ──────────────────────────────────────────────────────────────


def test_the_notification_carries_no_title_no_name_no_number(school, reporter, assignee):
    register(school, reporter, assigned_to=assignee)

    note = notes_for(assignee).get()
    text = f"{note.title} {note.body}"
    for leaked in (SENSITIVE_TITLE, "فلان", reporter.full_name, assignee.full_name, "وصفٌ"):
        assert leaked not in text, leaked
    assert "الخطورة: عالية" in note.body and "افتح البلاغ" in note.body


def test_the_event_is_in_app_and_push_only_and_urgent():
    from notifications.hub import DEFAULT_CHANNELS, DEFAULT_PRIORITY, _map_event_type

    assert DEFAULT_CHANNELS["breach_assigned"] == ["in_app", "push"]
    assert DEFAULT_PRIORITY["breach_assigned"] == "urgent"
    assert _map_event_type("breach_assigned") == "general"


def test_an_inactive_assignee_is_not_notified(school, reporter, assignee):
    breach = register(school, reporter)
    assignee.is_active = False
    assignee.save(update_fields=["is_active"])

    assert not services.notify_assignee(breach, assignee=assignee, by=reporter)
    assert not notes_for(assignee).exists()


# ── العطل ───────────────────────────────────────────────────────────────────────


def test_a_broken_notification_never_drops_the_breach(
    school, reporter, assignee, monkeypatch, caplog
):
    from notifications.hub import NotificationHub

    def boom(*args, **kwargs):
        raise RuntimeError("الإشعارات معطّلة")

    monkeypatch.setattr(NotificationHub, "dispatch", boom)

    with caplog.at_level(logging.ERROR, logger="breach.services"):
        breach = register(school, reporter, assigned_to=assignee)

    assert BreachReport.objects.filter(pk=breach.pk, assigned_to=assignee).exists()
    assert "breach assignee notification failed" in caplog.text
    assert SENSITIVE_TITLE not in caplog.text  # الخطأُ يُسجَّل بمعرّف البلاغ لا بعنوانه


def test_a_broken_notification_never_drops_the_edit(school, reporter, assignee, monkeypatch):
    from notifications.hub import NotificationHub

    breach = register(school, reporter)
    monkeypatch.setattr(NotificationHub, "dispatch", lambda *a, **k: 1 / 0)

    edit(school, breach, reporter, assigned_to=assignee)

    breach.refresh_from_db()
    assert breach.assigned_to_id == assignee.pk
