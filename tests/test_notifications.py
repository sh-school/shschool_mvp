"""
tests/test_notifications.py
اختبارات وحدات نظام الإشعارات (NotificationHub)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يختبر:
  - InAppNotification (النموذج والـ Manager)
  - UserNotificationPreference
  - NotificationHub.dispatch / dispatch_to_parents / dispatch_to_role
  - تكامل behavior → Hub (notify_parents)
  - تكامل operations → Hub (check_absence_threshold)
  - DEFAULT_CHANNELS / DEFAULT_PRIORITY
"""

from datetime import time as dt_time
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _use_in_memory_channel_layer(settings):
    """تجنب الحاجة لـ Redis في اختبارات الإشعارات."""
    settings.CHANNEL_LAYERS = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


from notifications.hub import (
    DEFAULT_CHANNELS,
    DEFAULT_PRIORITY,
    NotificationHub,
    _map_event_type,
    _resolve_channels,
)
from notifications.models import InAppNotification, UserNotificationPreference

from .conftest import (
    BehaviorInfractionFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)

# ══════════════════════════════════════════════════════════
#  1. InAppNotification — النموذج والـ Manager
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestInAppNotification:
    def test_create_notification(self, school, student_user):
        notif = InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="اختبار إشعار",
            body="نص الإشعار",
            event_type="general",
            priority="medium",
        )
        assert notif.title == "اختبار إشعار"
        assert notif.is_read is False
        assert notif.read_at is None

    def test_mark_read(self, school, student_user):
        notif = InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="إشعار",
            event_type="general",
        )
        notif.mark_read()
        notif.refresh_from_db()
        assert notif.is_read is True
        assert notif.read_at is not None

    def test_mark_read_idempotent(self, school, student_user):
        """استدعاء mark_read مرتين لا يسبب خطأ"""
        notif = InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="إشعار",
            event_type="general",
        )
        notif.mark_read()
        notif.mark_read()
        assert notif.is_read is True

    def test_unread_count(self, school, student_user):
        InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="إشعار 1",
            event_type="general",
        )
        InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="إشعار 2",
            event_type="absence",
        )
        assert InAppNotification.objects.unread_count(student_user) == 2

    def test_unread_count_after_read(self, school, student_user):
        n1 = InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="إشعار 1",
            event_type="general",
        )
        InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="إشعار 2",
            event_type="general",
        )
        n1.mark_read()
        assert InAppNotification.objects.unread_count(student_user) == 1

    def test_unread_for_user_returns_unread_only(self, school, student_user):
        n1 = InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="مقروء",
            event_type="general",
        )
        n2 = InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="غير مقروء",
            event_type="general",
        )
        n1.mark_read()
        unread = list(InAppNotification.objects.unread_for_user(student_user))
        assert n2 in unread
        assert n1 not in unread

    def test_mark_all_read(self, school, student_user):
        for i in range(3):
            InAppNotification.objects.create(
                user=student_user,
                school=school,
                title=f"إشعار {i}",
                event_type="general",
            )
        InAppNotification.objects.mark_all_read(student_user)
        assert InAppNotification.objects.unread_count(student_user) == 0

    def test_str_representation(self, school, student_user):
        notif = InAppNotification.objects.create(
            user=student_user,
            school=school,
            title="اختبار",
            event_type="general",
        )
        s = str(notif)
        assert "اختبار" in s
        assert student_user.full_name in s

    def test_unread_count_isolated_between_users(self, db, school):
        """عدد الإشعارات معزول بين المستخدمين"""
        u1 = UserFactory()
        u2 = UserFactory()
        InAppNotification.objects.create(
            user=u1,
            school=school,
            title="إشعار",
            event_type="general",
        )
        assert InAppNotification.objects.unread_count(u2) == 0


# ══════════════════════════════════════════════════════════
#  2. UserNotificationPreference
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestUserNotificationPreference:
    def _make_prefs(self, user, **kwargs):
        return UserNotificationPreference.objects.create(user=user, **kwargs)

    def test_default_channels_include_in_app_email(self, db):
        user = UserFactory()
        prefs = self._make_prefs(user)
        channels = prefs.get_channels_for_event("general")
        assert "in_app" in channels
        assert "email" in channels

    def test_disabled_channel_excluded(self, db):
        user = UserFactory()
        prefs = self._make_prefs(user, email_enabled=False)
        channels = prefs.get_channels_for_event("general")
        assert "email" not in channels

    def test_custom_event_channels(self, db):
        """تفضيل مخصص لحدث محدد"""
        user = UserFactory()
        prefs = self._make_prefs(user, event_channels={"behavior": ["in_app", "whatsapp"]})
        channels = prefs.get_channels_for_event("behavior")
        assert channels == ["in_app", "whatsapp"]

    def test_non_custom_event_uses_general(self, db):
        user = UserFactory()
        prefs = self._make_prefs(
            user,
            event_channels={"behavior": ["in_app"]},
            push_enabled=False,
        )
        channels = prefs.get_channels_for_event("absence")
        assert "push" not in channels
        assert "in_app" in channels

    def test_quiet_hours_no_start_end(self, db):
        user = UserFactory()
        prefs = self._make_prefs(user)
        assert prefs.is_quiet_hours() is False

    def test_quiet_hours_within_range(self, db):
        from django.utils import timezone

        user = UserFactory()
        now_time = timezone.localtime().time()
        h = now_time.hour
        start = dt_time((h - 1) % 24, 0)
        end = dt_time((h + 1) % 24, 0)
        prefs = self._make_prefs(user, quiet_hours_start=start, quiet_hours_end=end)
        assert prefs.is_quiet_hours() is True

    def test_is_quiet_hours_returns_bool(self, db):
        from django.utils import timezone

        user = UserFactory()
        now_time = timezone.localtime().time()
        h = now_time.hour
        start = dt_time((h + 3) % 24, 0)
        end = dt_time((h + 4) % 24, 0)
        prefs = self._make_prefs(user, quiet_hours_start=start, quiet_hours_end=end)
        assert isinstance(prefs.is_quiet_hours(), bool)


# ══════════════════════════════════════════════════════════
#  3. NotificationHub — dispatch / dispatch_to_parents
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestNotificationHub:
    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_creates_inapp(self, mock_queue, school, student_user):
        """dispatch يُنشئ InAppNotification فوراً (synchronous)"""
        result = NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[student_user],
            title="إشعار تجريبي",
            body="نص",
        )
        assert InAppNotification.objects.filter(user=student_user, title="إشعار تجريبي").exists()
        assert result["in_app"] == 1

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_queues_external(self, mock_queue, school, student_user):
        """dispatch يستدعي _queue_external_after_commit للقنوات الخارجية"""
        NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[student_user],
            title="إشعار",
            body="نص",
        )
        assert mock_queue.called

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_multiple_recipients(self, mock_queue, db, school):
        u1 = UserFactory()
        u2 = UserFactory()
        result = NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[u1, u2],
            title="إشعار جماعي",
        )
        assert result["in_app"] == 2
        assert InAppNotification.objects.filter(title="إشعار جماعي").count() == 2

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_empty_recipients(self, mock_queue, school):
        result = NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[],
            title="إشعار",
        )
        assert result["in_app"] == 0
        assert not mock_queue.called

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_priority_from_event(self, mock_queue, school, student_user):
        NotificationHub.dispatch(
            event_type="behavior_l4",
            school=school,
            recipients=[student_user],
            title="مخالفة خطيرة",
        )
        notif = InAppNotification.objects.get(user=student_user)
        assert notif.priority == "urgent"

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_event_type_mapped(self, mock_queue, school, student_user):
        """behavior_l2 → event_type='behavior' في InAppNotification"""
        NotificationHub.dispatch(
            event_type="behavior_l2",
            school=school,
            recipients=[student_user],
            title="مخالفة",
        )
        notif = InAppNotification.objects.get(user=student_user)
        assert notif.event_type == "behavior"

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_with_custom_priority(self, mock_queue, school, student_user):
        NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[student_user],
            title="إشعار",
            priority="urgent",
        )
        notif = InAppNotification.objects.get(user=student_user)
        assert notif.priority == "urgent"

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_to_parents(self, mock_queue, school, student_user, parent_user):
        """dispatch_to_parents يُرسل لأولياء الطالب"""
        result = NotificationHub.dispatch_to_parents(
            event_type="absence",
            school=school,
            student=student_user,
            title="تنبيه غياب",
            body="تجاوز الحد المسموح",
        )
        assert InAppNotification.objects.filter(user=parent_user, event_type="absence").exists()
        assert result["in_app"] == 1

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_to_parents_no_parent(self, mock_queue, school, student_user):
        """طالب بدون ولي أمر — لا إشعار ولا خطأ"""
        result = NotificationHub.dispatch_to_parents(
            event_type="absence",
            school=school,
            student=student_user,
            title="تنبيه",
        )
        assert result["in_app"] == 0

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_to_role(self, mock_queue, db, school):
        role = RoleFactory(school=school, name="teacher")
        t1 = UserFactory()
        t2 = UserFactory()
        MembershipFactory(user=t1, school=school, role=role)
        MembershipFactory(user=t2, school=school, role=role)

        result = NotificationHub.dispatch_to_role(
            event_type="general",
            school=school,
            role_name="teacher",
            title="إشعار للمعلمين",
        )
        assert result["in_app"] == 2

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_related_url_stored(self, mock_queue, school, student_user):
        url = "/behavior/student/123/"
        NotificationHub.dispatch(
            event_type="behavior_l1",
            school=school,
            recipients=[student_user],
            title="مخالفة",
            related_url=url,
        )
        notif = InAppNotification.objects.get(user=student_user)
        assert notif.related_url == url

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_user_prefs_disable_inapp(self, mock_queue, db, school):
        """إذا أوقف المستخدم in_app → لا يُنشأ InAppNotification"""
        user = UserFactory()
        UserNotificationPreference.objects.create(user=user, in_app_enabled=False)
        result = NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[user],
            title="إشعار",
        )
        assert result["in_app"] == 0
        assert not InAppNotification.objects.filter(user=user).exists()

    @patch("notifications.hub._queue_external_after_commit")
    def test_dispatch_quiet_hours_skips_external(self, mock_queue, db, school):
        """ساعات الهدوء تمنع القنوات الخارجية — in_app يُرسَل دائماً"""
        user = UserFactory()
        UserNotificationPreference.objects.create(
            user=user,
            quiet_hours_start=dt_time(0, 0),
            quiet_hours_end=dt_time(23, 59),
        )
        result = NotificationHub.dispatch(
            event_type="general",
            school=school,
            recipients=[user],
            title="إشعار",
        )
        assert result["in_app"] == 1
        assert not mock_queue.called


# ══════════════════════════════════════════════════════════
#  4. DEFAULT_CHANNELS / DEFAULT_PRIORITY (بدون DB)
# ══════════════════════════════════════════════════════════


class TestDefaultChannelsAndPriority:
    def test_behavior_l1_channels(self):
        assert "in_app" in DEFAULT_CHANNELS["behavior_l1"]
        assert "email" in DEFAULT_CHANNELS["behavior_l1"]

    def test_behavior_l4_all_channels(self):
        ch = DEFAULT_CHANNELS["behavior_l4"]
        for channel in ["in_app", "push", "whatsapp", "email", "sms"]:
            assert channel in ch, f"القناة {channel} مفقودة من behavior_l4"

    def test_sent_home_priority_urgent(self):
        assert DEFAULT_PRIORITY["sent_home"] == "urgent"

    def test_behavior_l1_priority_low(self):
        assert DEFAULT_PRIORITY["behavior_l1"] == "low"

    def test_behavior_l4_priority_urgent(self):
        assert DEFAULT_PRIORITY["behavior_l4"] == "urgent"

    def test_absence_has_whatsapp(self):
        assert "whatsapp" in DEFAULT_CHANNELS["absence"]

    def test_plan_update_no_sms(self):
        assert "sms" not in DEFAULT_CHANNELS["plan_update"]

    def test_map_event_type_behavior(self):
        assert _map_event_type("behavior_l1") == "behavior"
        assert _map_event_type("behavior_l4") == "behavior"

    def test_map_event_type_absence(self):
        assert _map_event_type("absence") == "absence"

    def test_map_event_type_sent_home(self):
        assert _map_event_type("sent_home") == "sent_home"

    def test_map_event_type_unknown(self):
        assert _map_event_type("unknown_event") == "general"

    def test_resolve_channels_no_prefs(self):
        defaults = ["in_app", "email"]
        result = _resolve_channels(None, "general", defaults)
        assert result == defaults

    @pytest.mark.django_db
    def test_resolve_channels_with_prefs(self):
        user = UserFactory()
        prefs = UserNotificationPreference.objects.create(user=user, email_enabled=False)
        defaults = ["in_app", "email"]
        result = _resolve_channels(prefs, "general", defaults)
        assert "email" not in result
        assert "in_app" in result


# ══════════════════════════════════════════════════════════
#  5. تكامل Behavior → Hub
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestBehaviorHubIntegration:
    @patch("notifications.hub._queue_external_after_commit")
    def test_notify_parents_creates_inapp(
        self, mock_queue, school, student_user, teacher_user, parent_user
    ):
        """BehaviorService.notify_parents() → InAppNotification لولي الأمر"""
        from behavior.services import BehaviorService

        inf = BehaviorInfractionFactory(
            school=school,
            student=student_user,
            reported_by=teacher_user,
            level=2,
            points_deducted=15,
        )
        BehaviorService.notify_parents(inf, school, teacher_user)

        assert InAppNotification.objects.filter(
            user=parent_user,
            event_type="behavior",
        ).exists()

    @patch("notifications.hub._queue_external_after_commit")
    def test_notify_parents_l4_urgent(
        self, mock_queue, school, student_user, teacher_user, parent_user
    ):
        """مخالفة L4 → إشعار بأولوية urgent"""
        from behavior.services import BehaviorService

        inf = BehaviorInfractionFactory(
            school=school,
            student=student_user,
            reported_by=teacher_user,
            level=4,
            points_deducted=40,
        )
        BehaviorService.notify_parents(inf, school, teacher_user)

        notif = InAppNotification.objects.filter(user=parent_user, event_type="behavior").first()
        assert notif is not None
        assert notif.priority == "urgent"

    @patch("notifications.hub._queue_external_after_commit")
    def test_notify_parents_l1_low(
        self, mock_queue, school, student_user, teacher_user, parent_user
    ):
        """مخالفة L1 → إشعار بأولوية low"""
        from behavior.services import BehaviorService

        inf = BehaviorInfractionFactory(
            school=school,
            student=student_user,
            reported_by=teacher_user,
            level=1,
            points_deducted=5,
        )
        BehaviorService.notify_parents(inf, school, teacher_user)

        notif = InAppNotification.objects.filter(user=parent_user, event_type="behavior").first()
        assert notif is not None
        assert notif.priority == "low"

    @patch("notifications.hub._queue_external_after_commit")
    def test_notify_parents_no_parent_no_error(
        self, mock_queue, school, student_user, teacher_user
    ):
        """بدون ولي أمر — لا خطأ، لا إشعار"""
        from behavior.services import BehaviorService

        inf = BehaviorInfractionFactory(
            school=school,
            student=student_user,
            reported_by=teacher_user,
            level=1,
        )
        BehaviorService.notify_parents(inf, school, teacher_user)
        # لا استثناء = نجاح، لا إشعار لأنه لا يوجد ولي أمر
        assert InAppNotification.objects.filter(event_type="behavior").count() == 0

    @patch("notifications.hub._queue_external_after_commit")
    def test_notify_parents_title_contains_student_name(
        self, mock_queue, school, student_user, teacher_user, parent_user
    ):
        """العنوان يحتوي على اسم الطالب"""
        from behavior.services import BehaviorService

        inf = BehaviorInfractionFactory(
            school=school,
            student=student_user,
            reported_by=teacher_user,
            level=2,
        )
        BehaviorService.notify_parents(inf, school, teacher_user)

        notif = InAppNotification.objects.get(user=parent_user)
        assert student_user.full_name in notif.title


# ══════════════════════════════════════════════════════════
#  6. تكامل Operations (غياب) → Hub
# ══════════════════════════════════════════════════════════


@pytest.mark.django_db
class TestAbsenceHubIntegration:
    """[LEGAL] إشعار الغياب يصل لوليّ الأمر مرّةً واحدة لكل عتبة.

    كانت هذه الاختبارات تُحاكي `StudentAttendance.objects.filter` وتُغذّي
    `.count()` بقيمتين — أي أنها تفحص **آليّة** الشيفرة لا سلوكها. فلمّا صار
    العدّ بالأيام عبر `absence_standing` لم يعد المُحاكي يعترض شيئاً، وصارت
    تُراقب مساراً لا يُنفَّذ. فأُعيدت على بياناتٍ حقيقية.
    """

    @staticmethod
    def _enrol(school, student, grade="G7"):
        from core.academic_calendar import academic_year_for_school
        from core.models import ClassGroup, StudentEnrollment

        cg = ClassGroup.objects.create(
            school=school,
            grade=grade,
            section="1",
            academic_year=academic_year_for_school(school),
        )
        StudentEnrollment.objects.create(student=student, class_group=cg, is_active=True)
        return cg

    @staticmethod
    def _absent_days(school, cg, teacher, student, start, days):
        from datetime import time, timedelta

        from operations.models import Session, StudentAttendance, Subject

        subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
        for offset in range(days):
            session = Session.objects.create(
                school=school,
                class_group=cg,
                teacher=teacher,
                subject=subject,
                date=start + timedelta(days=offset),
                start_time=time(8, 0),
                end_time=time(8, 45),
                status="scheduled",
            )
            StudentAttendance.objects.create(
                session=session,
                student=student,
                school=school,
                status="absent",
                excuse_type="",
            )

    def _reach_a_gate(self, school, student, teacher_user):
        """ستّةُ أيامٍ غياب: يفصله يومٌ عن العتبة الأولى — فيُنذَر."""
        from datetime import timedelta

        from django.core.management import call_command

        from core.academic_calendar import academic_year_window

        call_command("seed_academic_calendar", school=school.code, verbosity=0)
        start, _ = academic_year_window(school)
        cg = self._enrol(school, student)
        self._absent_days(school, cg, teacher_user, student, start, 6)
        return start + timedelta(days=30)

    @patch("notifications.hub._queue_external_after_commit")
    def test_absence_alert_creates_inapp_for_parent(
        self, mock_queue, school, student_user, parent_user, teacher_user
    ):
        from operations.services import AttendanceService

        on = self._reach_a_gate(school, student_user, teacher_user)
        AttendanceService.check_absence_threshold(student_user, school, on=on)

        assert InAppNotification.objects.filter(
            user=parent_user,
            event_type="absence",
        ).exists()

    @patch("notifications.hub._queue_external_after_commit")
    def test_absence_alert_sent_once_only(
        self, mock_queue, school, student_user, parent_user, teacher_user
    ):
        """الدالّة تُنادى عند كل تسجيل حضور — فالتكرار يُغرق وليّ الأمر."""
        from operations.services import AttendanceService

        on = self._reach_a_gate(school, student_user, teacher_user)
        AttendanceService.check_absence_threshold(student_user, school, on=on)
        AttendanceService.check_absence_threshold(student_user, school, on=on)

        count = InAppNotification.objects.filter(user=parent_user, event_type="absence").count()
        assert count == 1, "إشعار الغياب يجب أن يُرسَل مرة واحدة فقط"

    @patch("notifications.hub._queue_external_after_commit")
    def test_absence_alert_no_parent_no_error(self, mock_queue, school, student_user, teacher_user):
        """طالب بدون ولي أمر → لا خطأ عند بلوغ العتبة."""
        from operations.services import AttendanceService

        on = self._reach_a_gate(school, student_user, teacher_user)
        AttendanceService.check_absence_threshold(student_user, school, on=on)
