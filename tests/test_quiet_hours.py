"""
tests/test_quiet_hours.py
ساعات الهدوء — تُؤجَّل القنواتُ الخارجيّة إلى انتهائها ولا تُتخطّى، على كلّ مسارات الإرسال.

القاعدة: إشعارُ المنصّة يصل فوراً دائماً؛ وما يخرج (بريد، SMS، WhatsApp، Push) في ساعات
هدوء المستلم تحفظه مهمّةٌ مؤجَّلة (`release_after_quiet_hours_task`) حتى تنتهي، فلا يضيع
تنبيهُ غيابٍ أو رسوب. والحكمُ من مرجعٍ واحد: `notifications.quiet_hours.plan`.

الوقتُ يُجمَّد بتوقيت قطر (UTC+3)، والنافذةُ الأساسيّة 22:00–06:00 لأنّها التي تعبر
منتصفَ الليل. والاختباراتُ تفترض عاملاً حقيقيّاً (`CELERY_TASK_ALWAYS_EAGER=False`)
إلّا حيث يُقاس السلوكُ بدونه صراحةً.
"""

from contextlib import contextmanager
from datetime import date, datetime, time, timedelta
from unittest.mock import patch
from zoneinfo import ZoneInfo

import pytest
from django.contrib.messages import get_messages
from django.urls import reverse

from notifications import quiet_hours
from notifications.hub import NotificationHub
from notifications.models import InAppNotification, UserNotificationPreference
from notifications.quiet_hours import HOLD, MAX_HOLD_HOP, SEND_NOW, SKIP, in_quiet_window
from notifications.services import NotificationService
from tests.conftest import UserFactory

QATAR = ZoneInfo("Asia/Qatar")
NIGHT_START, NIGHT_END = time(22, 0), time(6, 0)


def at(hour, minute=0, day=21):
    """لحظةٌ بتوقيت قطر — 2026-09-{day}."""
    return datetime(2026, 9, day, hour, minute, tzinfo=QATAR)


@contextmanager
def clock(moment):
    """يجمّد `timezone.now()` — وبه `localtime()` الذي يقرؤه النموذجُ والمرجع معاً."""
    with patch("django.utils.timezone.now", return_value=moment):
        yield


@pytest.fixture(autouse=True)
def _real_worker(settings):
    """عاملٌ حقيقيّ (فلا تنفيذَ فوريّ) وطبقةُ قنوات في الذاكرة."""
    settings.CELERY_TASK_ALWAYS_EAGER = False
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}
    settings.NOTIFICATION_HUB_DELIVERY_PIPELINE_ENABLED = False


@pytest.fixture
def hold_spy():
    """يعترض جدولةَ المؤجَّل — لا وسيطَ ولا تنفيذ."""
    with patch("notifications.tasks.release_after_quiet_hours_task.apply_async") as spy:
        yield spy


@pytest.fixture
def hub_send_spy():
    with patch("notifications.tasks.hub_send_notification_task.delay") as spy:
        yield spy


def _quiet_user(start=NIGHT_START, end=NIGHT_END, **user_kwargs):
    user = UserFactory(**user_kwargs)
    UserNotificationPreference.objects.create(
        user=user, quiet_hours_start=start, quiet_hours_end=end
    )
    return user


# ══════════════════════════════════════════════════════════════════
#  النافذة — الحكمُ الخالص
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (22, 0, True),  # البدايةُ داخلة
        (23, 59, True),
        (0, 0, True),  # بعد منتصف الليل
        (3, 30, True),
        (5, 59, True),
        (6, 0, False),  # النهايةُ خارجة: يُرسَل عند انتهائها بالضبط
        (12, 0, False),
        (21, 59, False),
    ],
)
def test_a_window_that_wraps_midnight(hour, minute, expected):
    assert in_quiet_window(NIGHT_START, NIGHT_END, time(hour, minute)) is expected


@pytest.mark.parametrize(
    ("hour", "expected"),
    [(13, False), (14, True), (15, True), (16, False)],
)
def test_a_same_day_window(hour, expected):
    assert in_quiet_window(time(14, 0), time(16, 0), time(hour, 0)) is expected


@pytest.mark.parametrize(
    ("start", "end"),
    [(None, None), (time(22, 0), None), (None, time(6, 0)), (time(8, 0), time(8, 0))],
)
def test_an_incomplete_or_empty_window_is_disabled(start, end):
    assert in_quiet_window(start, end, time(8, 0)) is False


@pytest.mark.django_db
def test_the_model_and_the_reference_agree():
    """`is_quiet_hours` يفوّض إلى المرجع نفسه — لا نسخةَ ثانية تنحرف."""
    user = _quiet_user()

    with clock(at(23, 30)):
        assert user.notification_preferences.is_quiet_hours() is True
    with clock(at(12, 0)):
        assert user.notification_preferences.is_quiet_hours() is False


# ══════════════════════════════════════════════════════════════════
#  موعد الرفع — بتوقيت قطر
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReleaseTime:
    def test_before_midnight_releases_tomorrow_morning(self):
        user = _quiet_user()
        assert quiet_hours.quiet_release_at(user, at(23, 30)) == at(6, 0, day=22)

    def test_after_midnight_releases_this_morning(self):
        user = _quiet_user()
        assert quiet_hours.quiet_release_at(user, at(3, 0)) == at(6, 0)

    def test_outside_the_window_there_is_nothing_to_wait_for(self):
        user = _quiet_user()
        assert quiet_hours.quiet_release_at(user, at(12, 0)) is None

    def test_the_end_minute_itself_is_outside(self):
        user = _quiet_user()
        assert quiet_hours.quiet_release_at(user, at(6, 0)) is None

    def test_the_clock_is_qatar_not_utc(self):
        """20:30 UTC = 23:30 بتوقيت قطر ⇒ داخل 22:00–06:00؛ و12:00 UTC = 15:00 قطر ⇒ خارجها."""
        from datetime import UTC

        user = _quiet_user()
        assert quiet_hours.quiet_release_at(user, datetime(2026, 9, 21, 20, 30, tzinfo=UTC)) == at(
            6, 0, day=22
        )
        assert quiet_hours.quiet_release_at(user, datetime(2026, 9, 21, 12, 0, tzinfo=UTC)) is None

    def test_a_user_without_preferences_is_never_quiet(self):
        assert quiet_hours.quiet_release_at(UserFactory(), at(23, 30)) is None


@pytest.mark.django_db
class TestPlan:
    def test_outside_quiet_hours_send_now(self):
        assert quiet_hours.plan(_quiet_user(), at(12, 0)).action == SEND_NOW

    def test_inside_quiet_hours_hold_in_short_hops(self):
        """قفزةٌ ≤ 45 دقيقة لا موعدٌ واحد إلى الصباح — وإلّا أعاد Redis تسليمَ الرسالة كلَّ ساعة."""
        plan = quiet_hours.plan(_quiet_user(), at(23, 30))
        assert plan.action == HOLD
        assert plan.eta == at(23, 30) + MAX_HOLD_HOP

    def test_the_last_hop_lands_exactly_on_the_end(self):
        plan = quiet_hours.plan(_quiet_user(), at(5, 50))
        assert (plan.action, plan.eta) == (HOLD, at(6, 0))

    def test_without_a_worker_nothing_is_sent_in_quiet_hours(self, settings):
        """تنفيذٌ فوريّ يجعل `eta` بلا معنى — فلا يخرج شيءٌ في الهدوء."""
        settings.CELERY_TASK_ALWAYS_EAGER = True
        assert quiet_hours.plan(_quiet_user(), at(23, 30)).action == SKIP

    def test_without_a_worker_outside_quiet_hours_still_sends(self, settings):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        assert quiet_hours.plan(_quiet_user(), at(12, 0)).action == SEND_NOW


# ══════════════════════════════════════════════════════════════════
#  الـHub — المنصّة فوراً والخارجيّ مؤجَّل
# ══════════════════════════════════════════════════════════════════


def _dispatch(school, user, capture, title="إشعار الهدوء"):
    with capture(execute=True):
        return NotificationHub.dispatch(
            event_type="general", school=school, recipients=[user], title=title, body="نصّ"
        )


@pytest.mark.django_db
class TestHub:
    def test_in_quiet_hours_in_app_arrives_and_external_is_held(
        self, school, hold_spy, hub_send_spy, django_capture_on_commit_callbacks
    ):
        user = _quiet_user()

        with clock(at(23, 30)):
            result = _dispatch(school, user, django_capture_on_commit_callbacks)

        # المنصّة فوراً
        assert InAppNotification.objects.filter(user=user, title="إشعار الهدوء").count() == 1
        assert result["in_app"] == 1
        # والخارجيّ لا يخرج الآن...
        hub_send_spy.assert_not_called()
        # ...بل يُحفظ إلى انتهاء الهدوء
        hold_spy.assert_called_once()
        call = hold_spy.call_args.kwargs
        assert call["eta"] == at(23, 30) + MAX_HOLD_HOP
        assert call["kwargs"]["target"] == "hub"
        assert call["kwargs"]["user_id"] == str(user.id)
        payload = call["kwargs"]["payload"]
        assert "email" in payload["channels"] and "in_app" not in payload["channels"]
        assert payload["title"] == "إشعار الهدوء"

    def test_outside_quiet_hours_it_is_sent_immediately(
        self, school, hold_spy, hub_send_spy, django_capture_on_commit_callbacks
    ):
        user = _quiet_user()

        with clock(at(12, 0)):
            _dispatch(school, user, django_capture_on_commit_callbacks)

        assert InAppNotification.objects.filter(user=user).count() == 1
        hub_send_spy.assert_called_once()
        hold_spy.assert_not_called()

    def test_after_midnight_inside_a_wrapping_window_it_is_held(
        self, school, hold_spy, hub_send_spy, django_capture_on_commit_callbacks
    ):
        user = _quiet_user()

        with clock(at(3, 0)):
            _dispatch(school, user, django_capture_on_commit_callbacks)

        hub_send_spy.assert_not_called()
        assert hold_spy.call_args.kwargs["eta"] == at(3, 45)

    def test_without_a_worker_in_app_still_arrives_and_nothing_leaks_out(
        self, school, settings, hold_spy, hub_send_spy, django_capture_on_commit_callbacks
    ):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        user = _quiet_user()

        with clock(at(23, 30)):
            _dispatch(school, user, django_capture_on_commit_callbacks)

        assert InAppNotification.objects.filter(user=user).count() == 1
        hub_send_spy.assert_not_called()
        hold_spy.assert_not_called()

    def test_a_user_with_no_quiet_hours_is_unaffected(
        self, school, hold_spy, hub_send_spy, django_capture_on_commit_callbacks
    ):
        user = UserFactory()

        with clock(at(23, 30)):
            _dispatch(school, user, django_capture_on_commit_callbacks)

        hub_send_spy.assert_called_once()
        hold_spy.assert_not_called()


# ══════════════════════════════════════════════════════════════════
#  المهمّة المؤجَّلة — تقفز ثمّ تُطلق
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestReleaseTask:
    def _run(self, school, user, target="email", payload=None):
        from notifications.tasks import release_after_quiet_hours_task

        return release_after_quiet_hours_task.run(
            school_id=str(school.id),
            user_id=str(user.id),
            target=target,
            payload=payload or {"recipient_email": "p@example.com", "subject": "س"},
        )

    def test_still_quiet_it_hops_again_without_sending(self, school, hold_spy):
        user = _quiet_user()

        with patch("notifications.tasks.send_email_task.delay") as send:
            with clock(at(5, 50)):
                outcome = self._run(school, user)

        assert outcome["status"] == "held"
        send.assert_not_called()
        assert hold_spy.call_args.kwargs["eta"] == at(6, 0)

    def test_when_quiet_hours_end_it_releases_the_payload_once(self, school, hold_spy):
        user = _quiet_user()

        with patch("notifications.tasks.send_email_task.delay") as send:
            with clock(at(6, 0)):
                outcome = self._run(school, user)

        assert outcome["status"] == "released"
        send.assert_called_once_with(recipient_email="p@example.com", subject="س")
        hold_spy.assert_not_called()

    def test_the_target_is_a_closed_list(self, school, hold_spy):
        """المهمّةُ لا تُنفّذ ما يُملى عليها — مفتاحٌ من قائمةٍ مغلقة لا اسمُ مهمّةٍ حرّ."""
        user = _quiet_user()

        with clock(at(6, 0)):
            outcome = self._run(school, user, target="core.enforce_data_retention")

        assert outcome == {"status": "unknown_target"}

    def test_it_is_a_tenant_task(self):
        """كلُّ مهام الإشعارات مستأجَرة: `school_id` وقاعدةُ `TenantRLSTask`."""
        from core.celery_tasks import TenantRLSTask
        from notifications.tasks import release_after_quiet_hours_task

        assert isinstance(release_after_quiet_hours_task, TenantRLSTask)


# ══════════════════════════════════════════════════════════════════
#  زرّا لوحة الإشعارات — كانا يتجاوزان الهدوء كلّيّاً
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def pending_alert(school, student_user, parent_user):
    from operations.models import AbsenceAlert

    return AbsenceAlert.objects.create(
        school=school,
        student=student_user,
        absence_count=4,
        period_start=date(2026, 9, 14),
        period_end=date(2026, 9, 21),
        status="pending",
    )


def _make_parent_quiet(parent_user):
    parent_user.email = "parent@example.com"
    parent_user.save(update_fields=["email"])
    UserNotificationPreference.objects.create(
        user=parent_user, quiet_hours_start=NIGHT_START, quiet_hours_end=NIGHT_END
    )


@pytest.mark.django_db
class TestAlertButtons:
    def test_absence_alerts_in_quiet_hours_are_held_not_sent_and_not_lost(
        self, school, parent_user, pending_alert, hold_spy
    ):
        _make_parent_quiet(parent_user)

        with patch.object(NotificationService, "send_email") as send_email:
            with clock(at(23, 30)):
                counts = NotificationService.send_pending_absence_alerts(school)

        send_email.assert_not_called()
        sent, failed = counts  # التفكيكُ الثنائيّ القديم يعمل كما كان
        assert (sent, failed, counts.deferred) == (1, 0, 1)

        call = hold_spy.call_args.kwargs
        assert call["kwargs"]["target"] == "email"
        assert call["eta"] == at(23, 30) + MAX_HOLD_HOP
        payload = call["kwargs"]["payload"]
        assert payload["recipient_email"] == "parent@example.com"
        assert payload["notif_type"] == "absence_alert"
        assert payload["student_id"] == str(pending_alert.student_id)

        # قُبل للجدولة فلا يُكرَّر بضغطةٍ ثانية على الزرّ (idempotent)
        pending_alert.refresh_from_db()
        assert pending_alert.status == "notified"

    def test_a_second_press_does_not_schedule_a_duplicate(
        self, school, parent_user, pending_alert, hold_spy
    ):
        _make_parent_quiet(parent_user)

        with clock(at(23, 30)):
            NotificationService.send_pending_absence_alerts(school)
            again = NotificationService.send_pending_absence_alerts(school)

        assert tuple(again) == (0, 0)
        assert hold_spy.call_count == 1

    def test_absence_alerts_outside_quiet_hours_are_sent_now(
        self, school, parent_user, pending_alert, hold_spy
    ):
        _make_parent_quiet(parent_user)

        with patch.object(NotificationService, "send_email", return_value=(True, None)) as send:
            with clock(at(12, 0)):
                counts = NotificationService.send_pending_absence_alerts(school)

        send.assert_called_once()
        assert (tuple(counts), counts.deferred) == ((1, 0), 0)
        hold_spy.assert_not_called()

    def test_without_a_worker_the_alert_stays_pending_instead_of_breaking_quiet_hours(
        self, school, settings, parent_user, pending_alert, hold_spy
    ):
        settings.CELERY_TASK_ALWAYS_EAGER = True
        _make_parent_quiet(parent_user)

        with patch.object(NotificationService, "send_email") as send:
            with clock(at(23, 30)):
                counts = NotificationService.send_pending_absence_alerts(school)

        send.assert_not_called()
        hold_spy.assert_not_called()
        assert (tuple(counts), counts.deferred) == ((0, 1), 0)
        pending_alert.refresh_from_db()
        assert pending_alert.status == "pending"  # يستردّه الزرّ أو المهمّةُ اليوميّة لاحقاً

    def test_the_button_says_how_many_were_deferred(
        self, client, principal_user, school, parent_user, pending_alert, hold_spy
    ):
        _make_parent_quiet(parent_user)
        client.force_login(principal_user)

        with clock(at(23, 30)):
            response = client.post(reverse("send_absence_alerts"))

        assert response.status_code == 302
        text = " ".join(str(m) for m in get_messages(response.wsgi_request))
        assert "مؤجَّلٌ" in text and "ساعات هدوء" in text

    def test_the_dashboard_warns_truthfully_and_counts_recipients(
        self, client, principal_user, school, parent_user, pending_alert
    ):
        client.force_login(principal_user)

        response = client.get(reverse("notifications_dashboard"))

        html = response.content.decode()
        assert "ساعات هدوئه" in html and "يُؤجَّل" in html
        assert response.context["recipients"] == {"absence": 1, "fail": 0}

    def test_the_count_is_parents_not_alerts(
        self, school, student_user, parent_user, pending_alert
    ):
        """وليٌّ واحدٌ لتنبيهين ⇒ شخصٌ واحد."""
        from operations.models import AbsenceAlert

        AbsenceAlert.objects.create(
            school=school,
            student=student_user,
            absence_count=6,
            gate="second",
            period_start=date(2026, 9, 14),
            period_end=date(2026, 9, 21),
            status="pending",
        )

        counts = NotificationService.count_alert_recipients(school, "2026-2027")

        assert counts["absence"] == 1


@pytest.mark.django_db
def test_the_preferences_page_states_the_true_behaviour(client, teacher_user):
    client.force_login(teacher_user)

    html = client.get(reverse("notification_preferences")).content.decode()

    assert "تُتخطّى" not in html
    assert "تُؤجَّل" in html
    assert "منتصفَ الليل" in html


def test_the_window_end_is_never_in_the_past():
    """أيُّ لحظةٍ داخل النافذة تُرجع موعداً بعدها، ولا يبعد أكثر من 24 ساعة."""
    user = type("U", (), {})()
    prefs = UserNotificationPreference(quiet_hours_start=NIGHT_START, quiet_hours_end=NIGHT_END)
    user.notification_preferences = prefs

    for minutes in range(0, 24 * 60, 7):
        moment = at(0, 0) + timedelta(minutes=minutes)
        release = quiet_hours.quiet_release_at(user, moment)
        if in_quiet_window(NIGHT_START, NIGHT_END, moment.time()):
            assert moment < release <= moment + timedelta(hours=24)
        else:
            assert release is None
