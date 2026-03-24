"""
notifications/hub.py
━━━━━━━━━━━━━━━━━━━
NotificationHub — الموجّه المركزي لكل الإشعارات

الاستخدام:
    from notifications.hub import NotificationHub

    NotificationHub.dispatch(
        event_type="behavior_infraction",
        school=school,
        recipients=[parent1, parent2],
        title="مخالفة سلوكية — أحمد محمد",
        body="تم تسجيل مخالفة من الدرجة الثانية",
        context={"student": student, "level": 2, ...},
        priority="high",
        related_url="/behavior/student/xxx/",
    )

يتحقق من تفضيلات كل مستلم → يوزّع على القنوات → Celery async → retry
"""

import logging

from .models import (
    InAppNotification,
    UserNotificationPreference,
)

logger = logging.getLogger(__name__)


# ── مصفوفة القنوات الافتراضية حسب الحدث والأولوية ────────────
DEFAULT_CHANNELS = {
    # event_type: [channels]
    "behavior_l1": ["in_app", "push", "email"],
    "behavior_l2": ["in_app", "push", "whatsapp", "email"],
    "behavior_l3": ["in_app", "push", "whatsapp", "email", "sms"],
    "behavior_l4": ["in_app", "push", "whatsapp", "email", "sms"],
    "absence": ["in_app", "push", "whatsapp", "email"],
    "grade": ["in_app", "push", "email"],
    "fail": ["in_app", "push", "whatsapp", "email", "sms"],
    "clinic": ["in_app", "push", "whatsapp"],
    "sent_home": ["in_app", "push", "whatsapp", "email", "sms"],
    "meeting": ["in_app", "push", "whatsapp", "email"],
    "plan_update": ["in_app", "email"],
    "plan_deadline": ["in_app", "email"],
    "plan_overdue": ["in_app", "email"],
    "review_cycle": ["in_app", "email"],
    "general": ["in_app", "push", "email"],
}

# ── أولوية افتراضية حسب الحدث ────────────────────────────────
DEFAULT_PRIORITY = {
    "behavior_l1": "low",
    "behavior_l2": "medium",
    "behavior_l3": "high",
    "behavior_l4": "urgent",
    "absence": "medium",
    "grade": "low",
    "fail": "high",
    "clinic": "medium",
    "sent_home": "urgent",
    "meeting": "low",
    "plan_update": "low",
    "plan_deadline": "medium",
    "plan_overdue": "high",
    "review_cycle": "low",
    "general": "low",
}


class NotificationHub:
    """
    الموجّه المركزي — نقطة واحدة لإرسال كل الإشعارات.

    1. يُنشئ InAppNotification فوراً (synchronous)
    2. يوزّع القنوات الخارجية عبر Celery (async)
    3. يحترم تفضيلات المستخدم وساعات الهدوء
    """

    @staticmethod
    def dispatch(
        event_type,
        school,
        recipients,
        title,
        body="",
        context=None,
        priority=None,
        related_url="",
        related_object_id="",
        sent_by=None,
    ):
        """
        إرسال إشعار لقائمة مستلمين عبر كل القنوات المناسبة.

        Args:
            event_type: نوع الحدث (behavior_l2, absence, grade, ...)
            school: المدرسة
            recipients: قائمة CustomUser
            title: عنوان الإشعار
            body: نص الإشعار
            context: dict إضافي للقوالب (student, level, ...)
            priority: low/medium/high/urgent (تلقائي حسب الحدث)
            related_url: رابط مباشر للصفحة المعنية
            related_object_id: UUID الكائن المرتبط
            sent_by: المستخدم المُرسل (اختياري)

        Returns:
            dict: {"in_app": count, "queued": {"email": n, "sms": n, ...}}
        """
        if context is None:
            context = {}

        if priority is None:
            priority = DEFAULT_PRIORITY.get(event_type, "medium")

        # تحويل event_type للنوع المخزّن في InAppNotification
        inapp_event = _map_event_type(event_type)
        default_channels = DEFAULT_CHANNELS.get(event_type, ["in_app", "email"])

        results = {"in_app": 0, "queued": {}}

        for user in recipients:
            try:
                # ── 1. إشعار المنصة (دائماً — synchronous) ──────────
                prefs = _get_prefs(user)
                user_channels = _resolve_channels(prefs, event_type, default_channels)

                if "in_app" in user_channels:
                    notif = InAppNotification.objects.create(
                        user=user,
                        school=school,
                        title=title,
                        body=body,
                        event_type=inapp_event,
                        priority=priority,
                        related_object_id=str(related_object_id),
                        related_url=related_url,
                    )
                    results["in_app"] += 1

                    # ── WebSocket push (fail-safe — لا يكسر الإشعار) ──
                    _push_websocket(user, notif)

                # ── 2. القنوات الخارجية (async عبر Celery) ──────────
                external_channels = [ch for ch in user_channels if ch != "in_app"]

                if not external_channels:
                    continue

                # التحقق من ساعات الهدوء
                if prefs and prefs.is_quiet_hours():
                    # في ساعات الهدوء: in_app فقط (أُرسل أعلاه)
                    logger.info(f"Quiet hours for {user.full_name} — skipping external channels")
                    continue

                # إرسال عبر Celery
                _queue_external(
                    user=user,
                    school=school,
                    channels=external_channels,
                    title=title,
                    body=body,
                    event_type=event_type,
                    context=context,
                    sent_by=sent_by,
                )

                for ch in external_channels:
                    results["queued"][ch] = results["queued"].get(ch, 0) + 1

            except (OSError, RuntimeError, ValueError, KeyError) as e:
                logger.error(f"NotificationHub error for {user}: {e}", exc_info=True)

        logger.info(
            f"NotificationHub.dispatch({event_type}): "
            f"in_app={results['in_app']}, queued={results['queued']}"
        )
        return results

    @staticmethod
    def dispatch_to_role(event_type, school, role_name, title, body="", **kwargs):
        """إرسال لكل مستخدمي دور معين في المدرسة"""
        from core.models import Membership

        members = Membership.objects.filter(
            school=school, role__name=role_name, is_active=True
        ).select_related("user")
        recipients = [m.user for m in members]
        return NotificationHub.dispatch(
            event_type=event_type,
            school=school,
            recipients=recipients,
            title=title,
            body=body,
            **kwargs,
        )

    @staticmethod
    def dispatch_to_parents(event_type, school, student, title, body="", **kwargs):
        """إرسال لأولياء أمور طالب محدد"""
        from core.models import ParentStudentLink

        links = ParentStudentLink.objects.filter(student=student, school=school).select_related(
            "parent"
        )
        recipients = [link.parent for link in links]
        return NotificationHub.dispatch(
            event_type=event_type,
            school=school,
            recipients=recipients,
            title=title,
            body=body,
            **kwargs,
        )


# ── دوال مساعدة داخلية ──────────────────────────────────────


def _get_prefs(user):
    """يجلب تفضيلات المستخدم أو يُنشئ افتراضية"""
    try:
        return user.notification_preferences
    except UserNotificationPreference.DoesNotExist:
        return None


def _resolve_channels(prefs, event_type, defaults):
    """يحدد القنوات النهائية بناءً على التفضيلات"""
    if prefs is None:
        return defaults

    user_channels = prefs.get_channels_for_event(event_type)
    # تقاطع: القنوات المطلوبة ∩ القنوات المفعّلة عند المستخدم
    return [ch for ch in defaults if ch in user_channels]


def _map_event_type(hub_event):
    """يحوّل event_type من الـ Hub للنوع المخزّن في InAppNotification"""
    mapping = {
        "behavior_l1": "behavior",
        "behavior_l2": "behavior",
        "behavior_l3": "behavior",
        "behavior_l4": "behavior",
        "absence": "absence",
        "grade": "grade",
        "fail": "fail",
        "clinic": "clinic",
        "sent_home": "sent_home",
        "meeting": "meeting",
        "plan_update": "plan_update",
        "plan_deadline": "plan_deadline",
        "plan_overdue": "plan_overdue",
        "review_cycle": "review_cycle",
        "general": "general",
    }
    return mapping.get(hub_event, "general")


def _queue_external(user, school, channels, title, body, event_type, context, sent_by):
    """يُرسل المهام للقنوات الخارجية عبر Celery"""
    try:
        from .tasks import hub_send_notification_task

        hub_send_notification_task.delay(
            user_id=str(user.id),
            school_id=str(school.id),
            channels=channels,
            title=title,
            body=body,
            event_type=event_type,
            context=_serialize_context(context),
            sent_by_id=str(sent_by.id) if sent_by else None,
        )
    except (ImportError, OSError, RuntimeError) as e:
        # Fallback: إرسال مباشر لو Celery غير متاح
        logger.warning(f"Celery unavailable, sending sync: {e}")
        _send_sync(user, school, channels, title, body, event_type, context, sent_by)


def _serialize_context(context):
    """يحوّل الكائنات لـ JSON-serializable"""
    if not context:
        return {}
    safe = {}
    for key, val in context.items():
        if hasattr(val, "id"):
            safe[key] = str(val.id)
        elif hasattr(val, "pk"):
            safe[key] = str(val.pk)
        else:
            safe[key] = str(val)
    return safe


def _send_sync(user, school, channels, title, body, event_type, context, sent_by):
    """Fallback: إرسال مباشر بدون Celery"""
    from .services import NotificationService

    if "email" in channels and user.email:
        try:
            NotificationService.send_email(
                school=school,
                recipient_email=user.email,
                subject=title,
                body_text=body,
                notif_type=_map_event_type(event_type),
                sent_by=sent_by,
            )
        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"Sync email failed: {e}")

    if "sms" in channels and user.phone:
        try:
            NotificationService.send_sms(
                school=school,
                phone_number=user.phone,
                message=f"{title}\n{body}",
                notif_type=_map_event_type(event_type),
                sent_by=sent_by,
            )
        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"Sync SMS failed: {e}")


def _push_websocket(user, notif):
    """
    إرسال الإشعار فوراً عبر WebSocket بعد حفظه في DB.
    fail-safe: أي خطأ يُسجَّل ولا يكسر سير hub.dispatch()
    """
    try:
        from asgiref.sync import async_to_sync
        from channels.layers import get_channel_layer

        layer = get_channel_layer()
        if not layer:
            return  # Channels غير مُعدَّل (بيئة تطوير بلا Redis)

        unread = InAppNotification.objects.filter(user=user, is_read=False).count()

        async_to_sync(layer.group_send)(
            f"user_{user.pk}",
            {
                "type": "notification.new",
                "title": notif.title,
                "body": notif.body,
                "priority": notif.priority,
                "count": unread,
                "id": str(notif.pk),
                "url": notif.related_url or "",
            },
        )
    except (ImportError, OSError, RuntimeError, AttributeError) as exc:
        # لا نُوقف hub.dispatch() أبداً بسبب WebSocket
        logger.warning(f"WS push failed (non-critical): {exc}")
