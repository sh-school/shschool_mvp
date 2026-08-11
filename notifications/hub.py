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

from django.conf import settings
from django.db import transaction

from .channels import deliverable_external_channels
from .models import (
    InAppNotification,
    NotificationDelivery,
    NotificationDispatch,
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
    "behavior_risk": ["in_app"],
    "absence": ["in_app", "push", "whatsapp", "email"],
    "grade": ["in_app", "push", "email"],
    "fail": ["in_app", "push", "whatsapp", "email", "sms"],
    "clinic": ["in_app", "push", "whatsapp"],
    "sent_home": ["in_app", "push", "whatsapp", "email", "sms"],
    "meeting": ["in_app", "push", "whatsapp", "email"],
    "parent_summon": ["in_app", "push", "whatsapp", "email", "sms"],
    "plan_update": ["in_app", "email"],
    "plan_deadline": ["in_app", "email"],
    "plan_overdue": ["in_app", "email"],
    "review_cycle": ["in_app", "email"],
    "observation": ["in_app", "email"],
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
    "parent_summon": "high",
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

        if not recipients:
            # لا مستلم ⇒ لا واقعة. إشعارٌ لا يخصّ أحداً ليس حدثاً يُسجَّل.
            return results

        prepared = {
            "school": school,
            "title": title,
            "body": body,
            "event_type": event_type,
            "inapp_event": inapp_event,
            "priority": priority,
            "related_object_id": related_object_id,
            "related_url": related_url,
            "default_channels": default_channels,
        }

        def _register(user, external_channels, dispatch_id):
            # [B4-PRE2] يُسجَّل الآن ويُنفَّذ بعد الالتزام.
            #
            # `InAppNotification` أعلاه كتابةُ قاعدة داخل معاملة المستدعي،
            # فتتراجع معها إن تراجعت — وهذا صحيح. أمّا ما يخرج إلى مزوّد
            # خارجي فلا يتراجع، فلا يجوز أن يقع قبل أن يُصبح الحدث نهائياً.
            _queue_external_after_commit(
                user=user,
                school=school,
                channels=external_channels,
                title=title,
                body=body,
                event_type=event_type,
                context=context,
                sent_by=sent_by,
                dispatch_id=dispatch_id,
            )

        if not _tracked_pipeline_enabled():
            # ── المسار القديم — حرفياً كما كان ───────────────────────
            #
            # [B4-2B] لا معاملة تُضاف هنا. لفُّ الحلقة كلّها بواحدة يُغيّر
            # سلوكاً قائماً في اتجاهين: التسجيل يصير مؤجَّلاً إلى نهاية النداء
            # بدل أن يُنفَّذ فور معالجة كل مستلم خارج أي معاملة، وإشعارات
            # المنصّة لعدّة مستلمين تصير وحدةً يُسقطها فشلٌ لاحق. والراية
            # المُطفأة يجب ألّا يُلاحَظ لها أثر.
            for user in recipients:
                try:
                    external_channels = _prepare_recipient(user, prepared, results)
                    if external_channels:
                        _register(user, external_channels, None)
                except (OSError, RuntimeError, ValueError, KeyError) as e:
                    logger.error(f"NotificationHub error for {user}: {e}", exc_info=True)

        else:
            # ── المسار المتتبَّع — مرحلتان داخل حدٍّ واحد ──────────────
            #
            # المرحلة الأولى قاعدةُ بيانات بحتة: التفضيلات، وإشعارات المنصّة،
            # والواقعة، وكل التسليمات. والثانية تسجيلُ ما سيخرج بعد الالتزام.
            # فصلُهما ليس ترتيباً تجميلياً: العامل يفشل مغلقاً إن نقص تسليم
            # لقناة طُلبت، فتسجيلُ نداء قبل اكتمال صفوفه عقدٌ يتّكئ على أن
            # الـcallback لن يُنفَّذ قبل الالتزام — صحيحٌ اليوم وهشٌّ غداً.
            #
            # والمعاملة داخلية: مالك طفرة الأعمال (B4-PRE3) يبقى صاحب الالتزام
            # وتصير هذه نقطةَ حفظ ضمنه، والمسارات المجدولة تجد الوحدة مضمونة.
            with transaction.atomic():
                intents = []

                for user in recipients:
                    try:
                        external_channels = _prepare_recipient(user, prepared, results)
                        if external_channels:
                            intents.append((user, external_channels))
                    except (OSError, RuntimeError, ValueError, KeyError) as e:
                        logger.error(f"NotificationHub error for {user}: {e}", exc_info=True)

                dispatch = _create_dispatch(
                    school=school,
                    event_type=event_type,
                    related_object_id=related_object_id,
                    related_url=related_url,
                    sent_by=sent_by,
                    intents=intents,
                )

                # ── التسجيل — بعد اكتمال كل صفوف التسليم ────────────
                for user, external_channels in intents:
                    _register(user, external_channels, str(dispatch.id) if dispatch else None)

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

        # ── PDPPL: استبعاد ولي أمر سحب موافقته على نوع بيانات هذا الحدث ──
        recipients = _filter_consent(recipients, event_type, school, student)

        return NotificationHub.dispatch(
            event_type=event_type,
            school=school,
            recipients=recipients,
            title=title,
            body=body,
            **kwargs,
        )


# ── دوال مساعدة داخلية ──────────────────────────────────────

# PDPPL: ربط حدث الإشعار بنوع الموافقة المطلوب (None ⇒ بلا فحص موافقة)
_CONSENT_DATA_TYPE = {
    "behavior_l1": "behavior",
    "behavior_l2": "behavior",
    "behavior_l3": "behavior",
    "behavior_l4": "behavior",
    "behavior_risk": "behavior",
    "parent_summon": "behavior",
    "sent_home": "behavior",
    "absence": "attendance",
    "grade": "grades",
    "fail": "grades",
    "clinic": "health",
}


def _prepare_recipient(user, prepared, results):
    """إشعار المنصّة، ثم القنوات الخارجية المطلوبة لهذا المستلم — أو `None`.

    مشترك بين المسارين كي لا تُكتب دلالةُ التفضيلات وساعات الهدوء مرّتين: نسخة
    للمسار القديم وأخرى للمتتبَّع كانتا ستنحرفان، فيصير ما يُنشئ له الكاتب
    تسليماً غير ما كان المسار القديم ليُرسله.
    """
    prefs = _get_prefs(user)
    user_channels = _resolve_channels(prefs, prepared["event_type"], prepared["default_channels"])

    # ── 1. إشعار المنصة (دائماً — synchronous) ──────────
    if "in_app" in user_channels:
        notif = InAppNotification.objects.create(
            user=user,
            school=prepared["school"],
            title=prepared["title"],
            body=prepared["body"],
            event_type=prepared["inapp_event"],
            priority=prepared["priority"],
            related_object_id=str(prepared["related_object_id"]),
            related_url=prepared["related_url"],
        )
        results["in_app"] += 1

        # ── WebSocket push (fail-safe — لا يكسر الإشعار) ──
        _push_websocket(user, notif)

    # ── 2. القنوات الخارجية (async عبر Celery) ──────────
    external_channels = [ch for ch in user_channels if ch != "in_app"]

    if not external_channels:
        return None

    # التحقق من ساعات الهدوء
    if prefs and prefs.is_quiet_hours():
        # في ساعات الهدوء: in_app فقط (أُرسل أعلاه)
        logger.info(f"Quiet hours for {user.full_name} — skipping external channels")
        return None

    for channel in external_channels:
        results["queued"][channel] = results["queued"].get(channel, 0) + 1

    return external_channels


def _tracked_pipeline_enabled():
    """[B4-2B] الراية — مُطفأة افتراضياً وفي الإنتاج."""
    return getattr(settings, "NOTIFICATION_HUB_DELIVERY_PIPELINE_ENABLED", False)


def _create_dispatch(school, event_type, related_object_id, related_url, sent_by, intents):
    """[B4-2B] واقعة واحدة للنداء كلّه، وتسليم لكل (مستلم، قناة قابلة للتسليم).

    واقعة واحدة لا واحدة لكل مستلم: `NotificationHub.dispatch` نداءٌ يمثّل حدثاً
    واحداً بلغ عدّة أشخاص، والمستلمون تمييزهم في التسليم لا في الواقعة.

    وتُنشأ الواقعة ما دام هناك مستلم، حتى لو انتهى الأمر إلى إشعار منصّة وحده
    أو منعت ساعاتُ الهدوء الخروج: الواقعة تصف الحدث لا الطابور.

    والقنوات تُحسب بالمساعد المشترك مع العامل، فلا نسختين تنحرفان — والعامل
    يفشل مغلقاً عند النقص، فالانحراف يظهر كإشعار لا يخرج.
    """
    if not _tracked_pipeline_enabled():
        return None

    dispatch = NotificationDispatch.objects.create(
        school=school,
        event_type=event_type,
        related_object_id=str(related_object_id),
        related_url=related_url,
        sent_by=sent_by,
    )

    deliveries = [
        NotificationDelivery(
            dispatch=dispatch,
            school=school,
            recipient=user,
            channel=channel,
        )
        for user, external_channels in intents
        for channel in deliverable_external_channels(user, external_channels)
    ]

    if deliveries:
        NotificationDelivery.objects.bulk_create(deliveries)

    return dispatch


def _filter_consent(recipients, event_type, school, student):
    """يستبعد أولياء الأمور الذين سحبوا موافقتهم (is_given=False) على نوع
    البيانات المرتبط بالحدث — تطبيقاً لـ PDPPL (قانون قطر 13/2016).
    عدم وجود سجل ⇒ مسموح (الافتراضي). 'all' يغطّي كل الأنواع."""
    data_type = _CONSENT_DATA_TYPE.get(event_type)
    if not data_type or not recipients:
        return recipients

    from core.models import ConsentRecord

    withdrawn = set(
        ConsentRecord.objects.filter(
            student=student,
            school=school,
            data_type__in=[data_type, "all"],
            is_given=False,
        ).values_list("parent_id", flat=True)
    )
    if not withdrawn:
        return recipients

    kept = [p for p in recipients if p.pk not in withdrawn]
    dropped = len(recipients) - len(kept)
    if dropped:
        logger.info(
            "PDPPL consent: suppressed %d parent notification(s) | student=%s event=%s",
            dropped,
            getattr(student, "pk", student),
            event_type,
        )
    return kept


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
        "behavior_risk": "behavior",
        "absence": "absence",
        "grade": "grade",
        "fail": "fail",
        "clinic": "clinic",
        "sent_home": "sent_home",
        "meeting": "meeting",
        "parent_summon": "parent_summon",
        "plan_update": "plan_update",
        "plan_deadline": "plan_deadline",
        "plan_overdue": "plan_overdue",
        "review_cycle": "review_cycle",
        "observation": "general",
        "general": "general",
    }
    return mapping.get(hub_event, "general")


def _queue_external_after_commit(
    user, school, channels, title, body, event_type, context, sent_by, dispatch_id=None
):
    """[B4-PRE2] يُؤجّل الخروج إلى القنوات الخارجية حتى تلتزم معاملة المستدعي.

    عشرة من مواضع استدعاء الـHub تقع داخل `@transaction.atomic` — تسجيل غياب،
    وتبادل الحصص، والحصص التعويضية، ودورة حياة الزيارة الصفّية. وكان الطبر
    يقع داخل تلك المعاملة، فإن تراجعت بقي في الطابور عملٌ يشير إلى صفوف لم
    تُكتب. ومع `CELERY_TASK_ALWAYS_EAGER` — وهو وضع الإنتاج اليوم — لا يبقى
    الأمر عند الطابور: المزوّد يُنادى فوراً، فيصل البريد أو الرسالة عن حدث
    تراجع بعد ثوانٍ. ورسالةٌ وصلت لا تُسحب.

    والتسجيل مفصول عن التنفيذ باسمين لا اسم واحد: خلط الطبقتين تحت `_queue_external`
    كان يُخفي أيّهما ينشر فعلاً.

    خارج أي معاملة يُنفّذ Django الـcallback فوراً، فالمسارات غير المعامليّة
    تسلك كما كانت بلا تغيير.

    و`robust` تُترك على قيمتها الافتراضية عمداً: جعلُها `True` يبتلع الاستثناءات
    ويُصعّب التشخيص، وسياسة "الطبر best-effort" تنتظر مصدرَ حقيقة في القاعدة
    ومُصالِحاً يلتقط ما سقط — وكلاهما لم يوجد بعد.
    """
    transaction.on_commit(
        lambda: _queue_external_now(
            user, school, channels, title, body, event_type, context, sent_by, dispatch_id
        )
    )


def _queue_external_now(
    user, school, channels, title, body, event_type, context, sent_by, dispatch_id=None
):
    """يُرسل المهام للقنوات الخارجية عبر Celery — بعد الالتزام.

    [B4-2B] المساران يفترقان عند فشل الوسيط.

    **القديم** (`dispatch_id is None`) يرتدّ إلى الإرسال المتزامن كما كان. لا
    شيء يتتبّعه، فبقاء الإتاحة أولى.

    **والمتتبَّع** لا يرتدّ. صفّ التسليم موجود ومُلتزم، فالقاعدة هي مصدر
    الحقيقة والطبر محاولةٌ أفضل الجهد: يبقى التسليم `pending` ليأخذه المصالِح.
    إرسالٌ متزامن هنا كان سيُخرج رسالةً خارج آلة الحالات — تسليمٌ يقول "معلّق"
    ورسالةٌ وصلت.

    ولا يُعاد رفع خطأ الطبر في المسار المتتبَّع: المعاملة التزمت فعلاً، فرفعُه
    يُنتج خطأ HTTP عن عمليةٍ قبلتها القاعدة، فيُعيدها المستخدم ظنّاً أنها فشلت.
    """
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
            dispatch_id=dispatch_id,
        )
        return True
    except (ImportError, OSError, RuntimeError) as e:
        if dispatch_id:
            logger.exception(
                "Tracked dispatch %s: enqueue failed — deliveries stay pending", dispatch_id
            )
            return False

        # Fallback: إرسال مباشر لو Celery غير متاح — المسار القديم وحده
        logger.warning(f"Celery unavailable, sending sync: {e}")
        _send_sync(user, school, channels, title, body, event_type, context, sent_by)
        return False


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
