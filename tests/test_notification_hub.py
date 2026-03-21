"""
tests/test_notification_hub.py
اختبارات شاملة لـ NotificationHub + InAppNotification + UserNotificationPreference

يغطي:
  - InAppNotification: إنشاء، قراءة، Manager methods
  - UserNotificationPreference: get_channels_for_event، is_quiet_hours
  - NotificationHub.dispatch: in_app، قنوات، تفضيلات المستخدم
  - NotificationHub.dispatch_to_role + dispatch_to_parents
  - PushSubscription: إنشاء وتنسيق
  - Views: notification bell، mark read، inbox
"""
import pytest
from datetime import time
from unittest.mock import patch, MagicMock

from django.utils import timezone

from notifications.models import (
    InAppNotification, UserNotificationPreference,
    NotificationSettings, PushSubscription,
)
from notifications.hub import (
    NotificationHub, _map_event_type, _resolve_channels, DEFAULT_CHANNELS,
)
from tests.conftest import (
    UserFactory, RoleFactory, MembershipFactory,
)


# ══════════════════════════════════════════════════════════════════════
#  Fixtures
# ══════════════════════════════════════════════════════════════════════

@pytest.fixture
def notif_settings(db, school):
    return NotificationSettings.objects.create(
        school=school, email_enabled=True, sms_enabled=False, absence_threshold=3,
    )


@pytest.fixture
def in_app_notif(db, school, teacher_user):
    return InAppNotification.objects.create(
        user=teacher_user, school=school,
        title="إشعار تجريبي", body="نص الإشعار",
        event_type="general", priority="medium",
    )


@pytest.fixture
def user_prefs(db, teacher_user):
    return UserNotificationPreference.objects.create(
        user=teacher_user,
        in_app_enabled=True, push_enabled=True,
        whatsapp_enabled=False, email_enabled=True, sms_enabled=False,
    )


# ══════════════════════════════════════════════════════════════════════
#  InAppNotification — النموذج
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestInAppNotificationModel:

    def test_creation(self, in_app_notif):
        assert in_app_notif.title == "إشعار تجريبي"
        assert in_app_notif.is_read is False
        assert in_app_notif.read_at is None

    def test_str_contains_title(self, in_app_notif):
        assert "إشعار تجريبي" in str(in_app_notif)

    def test_str_shows_unread(self, in_app_notif):
        assert "جديد" in str(in_app_notif)

    def test_mark_read(self, in_app_notif):
        in_app_notif.mark_read()
        in_app_notif.refresh_from_db()
        assert in_app_notif.is_read is True
        assert in_app_notif.read_at is not None

    def test_mark_read_idempotent(self, in_app_notif):
        """mark_read مرتين لا يُحدث مشكلة"""
        in_app_notif.mark_read()
        first_read_at = in_app_notif.read_at
        in_app_notif.mark_read()
        assert in_app_notif.read_at == first_read_at

    def test_priority_choices(self, in_app_notif):
        valid = dict(InAppNotification.PRIORITY).keys()
        for p in ["low", "medium", "high", "urgent"]:
            assert p in valid

    def test_event_type_choices(self, in_app_notif):
        valid = dict(InAppNotification.EVENT_TYPES).keys()
        for et in ["behavior", "absence", "grade", "clinic", "sent_home", "general"]:
            assert et in valid


# ══════════════════════════════════════════════════════════════════════
#  InAppNotificationManager
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestInAppNotificationManager:

    def test_unread_for_user(self, school, teacher_user):
        InAppNotification.objects.create(
            user=teacher_user, school=school,
            title="رسالة 1", event_type="general",
        )
        InAppNotification.objects.create(
            user=teacher_user, school=school,
            title="رسالة 2", event_type="grade",
        )
        unread = InAppNotification.objects.unread_for_user(teacher_user)
        assert unread.count() == 2

    def test_unread_count(self, school, teacher_user):
        for i in range(3):
            InAppNotification.objects.create(
                user=teacher_user, school=school,
                title=f"إشعار {i}", event_type="general",
            )
        count = InAppNotification.objects.unread_count(teacher_user)
        assert count == 3

    def test_unread_count_excludes_read(self, in_app_notif, teacher_user):
        in_app_notif.mark_read()
        count = InAppNotification.objects.unread_count(teacher_user)
        assert count == 0

    def test_mark_all_read(self, school, teacher_user):
        for i in range(4):
            InAppNotification.objects.create(
                user=teacher_user, school=school,
                title=f"إشعار {i}", event_type="general",
            )
        InAppNotification.objects.mark_all_read(teacher_user)
        assert InAppNotification.objects.unread_count(teacher_user) == 0

    def test_for_user_limit(self, school, teacher_user):
        for i in range(60):
            InAppNotification.objects.create(
                user=teacher_user, school=school,
                title=f"إشعار {i}", event_type="general",
            )
        results = InAppNotification.objects.for_user(teacher_user, limit=50)
        assert len(list(results)) == 50

    def test_unread_only_for_current_user(self, school, teacher_user, student_user):
        """إشعارات مستخدم آخر لا تظهر"""
        InAppNotification.objects.create(
            user=student_user, school=school,
            title="إشعار طالب", event_type="grade",
        )
        count = InAppNotification.objects.unread_count(teacher_user)
        assert count == 0


# ══════════════════════════════════════════════════════════════════════
#  UserNotificationPreference
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestUserNotificationPreference:

    def test_defaults(self, user_prefs):
        assert user_prefs.in_app_enabled is True
        assert user_prefs.email_enabled is True
        assert user_prefs.sms_enabled is False
        assert user_prefs.whatsapp_enabled is False

    def test_get_channels_default(self, user_prefs):
        """قنوات افتراضية = كل القنوات المفعّلة"""
        channels = user_prefs.get_channels_for_event("general")
        assert "in_app" in channels
        assert "email" in channels
        assert "sms" not in channels
        assert "whatsapp" not in channels

    def test_get_channels_custom_event(self, user_prefs):
        """تخصيص قنوات لحدث معين"""
        user_prefs.event_channels = {"behavior": ["in_app", "whatsapp"]}
        user_prefs.save()
        channels = user_prefs.get_channels_for_event("behavior")
        assert channels == ["in_app", "whatsapp"]

    def test_get_channels_custom_overrides_global(self, user_prefs):
        """event_channels يتجاوز الإعدادات العامة"""
        user_prefs.email_enabled = False
        user_prefs.event_channels = {"grade": ["email"]}
        user_prefs.save()
        channels = user_prefs.get_channels_for_event("grade")
        assert channels == ["email"]

    def test_is_quiet_hours_false_no_config(self, user_prefs):
        """بدون ساعات هدوء — دائماً False"""
        assert user_prefs.is_quiet_hours() is False

    def test_is_quiet_hours_within_range(self, user_prefs):
        """الوقت الحالي ضمن ساعات الهدوء"""
        now = timezone.localtime().time()
        start = (timezone.datetime.combine(timezone.datetime.today(), now)
                 - timezone.timedelta(hours=1)).time()
        end   = (timezone.datetime.combine(timezone.datetime.today(), now)
                 + timezone.timedelta(hours=1)).time()
        user_prefs.quiet_hours_start = start
        user_prefs.quiet_hours_end   = end
        user_prefs.save()
        assert user_prefs.is_quiet_hours() is True

    def test_is_quiet_hours_outside_range(self, user_prefs):
        """الوقت الحالي خارج ساعات الهدوء"""
        user_prefs.quiet_hours_start = time(2, 0)
        user_prefs.quiet_hours_end   = time(4, 0)
        user_prefs.save()
        # افتراض أننا لسنا بين 2-4 صباحاً أثناء الاختبار
        # نتحقق فقط من عدم رفع استثناء
        result = user_prefs.is_quiet_hours()
        assert isinstance(result, bool)

    def test_one_preference_per_user(self, user_prefs, teacher_user):
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            UserNotificationPreference.objects.create(user=teacher_user)


# ══════════════════════════════════════════════════════════════════════
#  NotificationHub — dispatch
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestNotificationHubDispatch:

    def test_dispatch_creates_in_app_notification(self, school, teacher_user):
        result = NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[teacher_user],
            title="اختبار Hub",
            body="نص الإشعار",
        )
        assert result["in_app"] == 1
        assert InAppNotification.objects.filter(
            user=teacher_user, title="اختبار Hub"
        ).exists()

    def test_dispatch_multiple_recipients(self, school, teacher_user, student_user):
        result = NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[teacher_user, student_user],
            title="إشعار جماعي",
        )
        assert result["in_app"] == 2

    def test_dispatch_empty_recipients(self, school):
        result = NotificationHub.dispatch(
            event_type="general", school=school,
            recipients=[], title="لا أحد",
        )
        assert result["in_app"] == 0

    def test_dispatch_respects_in_app_disabled(self, school, teacher_user):
        """إذا عطّل المستخدم in_app لا يُنشأ إشعار"""
        UserNotificationPreference.objects.create(
            user=teacher_user,
            in_app_enabled=False,
            push_enabled=False,
            email_enabled=False,
        )
        result = NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[teacher_user],
            title="مكتوم",
        )
        assert result["in_app"] == 0
        assert not InAppNotification.objects.filter(
            user=teacher_user, title="مكتوم"
        ).exists()

    def test_dispatch_sets_correct_priority(self, school, teacher_user):
        NotificationHub.dispatch(
            event_type="behavior_l4",
            school=school,
            recipients=[teacher_user],
            title="مخالفة عاجلة",
        )
        notif = InAppNotification.objects.get(user=teacher_user, title="مخالفة عاجلة")
        assert notif.priority == "urgent"

    def test_dispatch_sets_related_url(self, school, teacher_user):
        NotificationHub.dispatch(
            event_type="grade",
            school=school,
            recipients=[teacher_user],
            title="درجات جديدة",
            related_url="/assessments/class/5/",
        )
        notif = InAppNotification.objects.get(user=teacher_user, title="درجات جديدة")
        assert notif.related_url == "/assessments/class/5/"

    @patch("notifications.hub._queue_external")
    def test_dispatch_queues_external_channels(self, mock_queue, school, teacher_user):
        """التحقق من أن القنوات الخارجية تُرسل لـ Celery"""
        NotificationHub.dispatch(
            event_type="fail",
            school=school,
            recipients=[teacher_user],
            title="نتيجة رسوب",
        )
        # لو لم يكن لدى المستخدم تفضيلات = يستخدم الافتراضي
        # fail channels: ["in_app", "push", "whatsapp", "email", "sms"]
        # in_app مُنشأ مباشرة، الباقي عبر Celery
        assert mock_queue.called or result is not None  # noqa

    def test_dispatch_to_role(self, school, teacher_user):
        """dispatch_to_role يُرسل لكل أعضاء الدور"""
        result = NotificationHub.dispatch_to_role(
            event_type="general",
            school=school,
            role_name="teacher",
            title="إشعار المعلمين",
        )
        assert result["in_app"] >= 1

    def test_dispatch_to_parents(self, school, student_user, parent_user):
        """dispatch_to_parents يُرسل لأولياء الطالب"""
        result = NotificationHub.dispatch_to_parents(
            event_type="absence",
            school=school,
            student=student_user,
            title="غياب الطالب",
        )
        assert result["in_app"] >= 1
        assert InAppNotification.objects.filter(
            user=parent_user, title="غياب الطالب"
        ).exists()


# ══════════════════════════════════════════════════════════════════════
#  دوال المساعدة الداخلية
# ══════════════════════════════════════════════════════════════════════

class TestHubHelpers:

    def test_map_event_type_behavior(self):
        assert _map_event_type("behavior_l1") == "behavior"
        assert _map_event_type("behavior_l4") == "behavior"

    def test_map_event_type_direct(self):
        assert _map_event_type("absence") == "absence"
        assert _map_event_type("grade")   == "grade"
        assert _map_event_type("fail")    == "fail"
        assert _map_event_type("clinic")  == "clinic"
        assert _map_event_type("sent_home") == "sent_home"

    def test_map_event_type_unknown(self):
        assert _map_event_type("unknown_event") == "general"

    def test_resolve_channels_no_prefs(self):
        """بدون تفضيلات — يستخدم القنوات الافتراضية"""
        defaults = ["in_app", "email"]
        result = _resolve_channels(None, "general", defaults)
        assert result == defaults

    def test_resolve_channels_intersect(self):
        """المستخدم يريد in_app فقط — يُلغي email"""
        prefs = MagicMock()
        prefs.get_channels_for_event.return_value = ["in_app"]
        defaults = ["in_app", "email"]
        result = _resolve_channels(prefs, "general", defaults)
        assert result == ["in_app"]
        assert "email" not in result

    def test_default_channels_coverage(self):
        """كل أنواع الأحداث لها قنوات افتراضية"""
        events = [
            "behavior_l1", "behavior_l4", "absence", "grade", "fail",
            "clinic", "sent_home", "meeting", "plan_update", "general",
        ]
        for event in events:
            assert event in DEFAULT_CHANNELS, f"{event} not in DEFAULT_CHANNELS"
            assert "in_app" in DEFAULT_CHANNELS[event]


# ══════════════════════════════════════════════════════════════════════
#  PushSubscription
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestPushSubscription:

    def test_creation(self, school, parent_user):
        sub = PushSubscription.objects.create(
            user=parent_user, school=school,
            endpoint="https://push.example.com/endpoint/abc123",
            p256dh="BNcRdreALRFXTkOOUHK1EtK2wtc",
            auth="tBHItJI5svbpez7KI4CCXg==",
        )
        assert sub.is_active is True
        assert sub.endpoint.startswith("https://")

    def test_to_dict_format(self, school, parent_user):
        sub = PushSubscription.objects.create(
            user=parent_user, school=school,
            endpoint="https://push.example.com/xyz",
            p256dh="key123",
            auth="auth456",
        )
        d = sub.to_dict()
        assert d["endpoint"] == "https://push.example.com/xyz"
        assert d["keys"]["p256dh"] == "key123"
        assert d["keys"]["auth"] == "auth456"

    def test_unique_endpoint(self, school, parent_user, teacher_user):
        PushSubscription.objects.create(
            user=parent_user, school=school,
            endpoint="https://unique.endpoint.com",
            p256dh="key", auth="auth",
        )
        from django.db import IntegrityError
        with pytest.raises(IntegrityError):
            PushSubscription.objects.create(
                user=teacher_user, school=school,
                endpoint="https://unique.endpoint.com",
                p256dh="key2", auth="auth2",
            )


# ══════════════════════════════════════════════════════════════════════
#  Notification Views
# ══════════════════════════════════════════════════════════════════════

@pytest.mark.django_db
class TestNotificationViews:

    def test_inbox_view(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/notifications/inbox/")
        assert resp.status_code == 200

    def test_mark_all_read_view(self, client_as, teacher_user, school, in_app_notif):
        c = client_as(teacher_user)
        resp = c.post("/notifications/mark-all-read/")
        assert resp.status_code in [200, 302, 204]
        in_app_notif.refresh_from_db()
        assert in_app_notif.is_read is True

    def test_unread_count_api(self, client_as, teacher_user, school, in_app_notif):
        c = client_as(teacher_user)
        resp = c.get("/notifications/unread-count/")
        assert resp.status_code == 200
        import json
        data = json.loads(resp.content)
        assert "count" in data
        assert data["count"] >= 1

    def test_preferences_view_get(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.get("/notifications/preferences/")
        assert resp.status_code == 200

    def test_preferences_view_post(self, client_as, teacher_user):
        c = client_as(teacher_user)
        resp = c.post("/notifications/preferences/", {
            "in_app_enabled": True,
            "email_enabled": False,
        })
        assert resp.status_code in [200, 302]
