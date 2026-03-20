"""
notifications/tasks.py
مهام Celery غير المتزامنة للإشعارات
[مهمة 15] بدلاً من الإرسال المباشر في الـ request، تُوضع المهام في queue

الاستخدام:
    # من أي مكان في الكود:
    send_email_task.delay(
        school_id=str(school.id),
        recipient_email="parent@example.com",
        subject="إشعار",
        body_text="...",
        ...
    )
"""
from celery import shared_task
import logging

logger = logging.getLogger(__name__)


# ── إرسال بريد إلكتروني ─────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,   # إعادة المحاولة بعد دقيقة
    name="notifications.send_email",
)
def send_email_task(self, school_id, recipient_email, subject, body_text,
                    body_html=None, student_id=None, notif_type="custom",
                    sent_by_id=None):
    """
    إرسال بريد إلكتروني بشكل غير متزامن.
    يُعيد المحاولة تلقائياً 3 مرات عند الفشل.
    """
    try:
        from core.models import School, CustomUser
        from notifications.services import NotificationService

        school   = School.objects.get(id=school_id)
        student  = CustomUser.objects.filter(id=student_id).first() if student_id else None
        sent_by  = CustomUser.objects.filter(id=sent_by_id).first() if sent_by_id else None

        ok, err = NotificationService.send_email(
            school          = school,
            recipient_email = recipient_email,
            subject         = subject,
            body_text       = body_text,
            body_html       = body_html,
            student         = student,
            notif_type      = notif_type,
            sent_by         = sent_by,
        )

        if not ok:
            logger.warning(f"Email failed to {recipient_email}: {err}")
            raise Exception(err)

        return {"status": "sent", "recipient": recipient_email}

    except Exception as exc:
        logger.error(f"send_email_task error: {exc}")
        raise self.retry(exc=exc)


# ── إرسال SMS ────────────────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_sms",
)
def send_sms_task(self, school_id, phone_number, message,
                  student_id=None, notif_type="custom", sent_by_id=None):
    """إرسال SMS بشكل غير متزامن عبر Twilio"""
    try:
        from core.models import School, CustomUser
        from notifications.services import NotificationService

        school  = School.objects.get(id=school_id)
        student = CustomUser.objects.filter(id=student_id).first() if student_id else None
        sent_by = CustomUser.objects.filter(id=sent_by_id).first() if sent_by_id else None

        ok, err = NotificationService.send_sms(
            school       = school,
            phone_number = phone_number,
            message      = message,
            student      = student,
            notif_type   = notif_type,
            sent_by      = sent_by,
        )

        if not ok:
            raise Exception(err)

        return {"status": "sent", "recipient": phone_number}

    except Exception as exc:
        logger.error(f"send_sms_task error: {exc}")
        raise self.retry(exc=exc)


# ── إشعار غياب الطالب ───────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    name="notifications.notify_absence",
)
def notify_absence_task(self, absence_alert_id, sent_by_id=None):
    """إشعار ولي الأمر بغياب ابنه — يُشغَّل من AbsenceService"""
    try:
        from operations.models import AbsenceAlert
        from core.models import CustomUser
        from notifications.services import NotificationService

        alert   = AbsenceAlert.objects.select_related("school", "student").get(id=absence_alert_id)
        sent_by = CustomUser.objects.filter(id=sent_by_id).first() if sent_by_id else None

        results = NotificationService.notify_absence(alert, sent_by=sent_by)
        sent    = sum(1 for r in results if r["ok"])
        logger.info(f"Absence notification for {alert.student}: {sent}/{len(results)} sent")

        # ✅ v5: إرسال Push للوالدين المشتركين
        try:
            from core.models import ParentStudentLink
            parents = ParentStudentLink.objects.filter(
                student=alert.student, school=alert.school
            ).values_list('parent_id', flat=True)
            for pid in parents:
                send_push_task.delay(
                    str(pid),
                    title=f"⚠️ غياب — {alert.student.full_name}",
                    body="تم تسجيل غياب اليوم. اضغط للتفاصيل.",
                    url="/parents/",
                )
        except Exception as pe:
            logger.warning(f"Push notification failed: {pe}")

        return {"sent": sent, "total": len(results)}

    except Exception as exc:
        logger.error(f"notify_absence_task error: {exc}")
        raise self.retry(exc=exc)


# ── إشعار رسوب الطالب ───────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    name="notifications.notify_fail",
)
def notify_fail_task(self, student_id, school_id, failed_subjects,
                     year="2025-2026", sent_by_id=None):
    """إشعار ولي الأمر برسوب ابنه"""
    try:
        from core.models import School, CustomUser
        from notifications.services import NotificationService

        student = CustomUser.objects.get(id=student_id)
        school  = School.objects.get(id=school_id)
        sent_by = CustomUser.objects.filter(id=sent_by_id).first() if sent_by_id else None

        results = NotificationService.notify_fail(
            student         = student,
            school          = school,
            failed_subjects = failed_subjects,
            year            = year,
            sent_by         = sent_by,
        )
        sent = sum(1 for r in results if r["ok"])
        return {"sent": sent, "total": len(results)}

    except Exception as exc:
        logger.error(f"notify_fail_task error: {exc}")
        raise self.retry(exc=exc)


# ── إرسال جماعي لتنبيهات الغياب المعلقة (مُجدوَل) ──────────────────

@shared_task(name="notifications.send_pending_absence_alerts_all_schools")
def send_pending_absence_alerts_task():
    """
    مهمة مُجدوَلة — تُشغَّل صباح كل يوم من Celery Beat
    ترسل كل تنبيهات الغياب المعلقة لكل المدارس
    """
    from core.models import School
    from notifications.services import NotificationService

    total_sent = total_failed = 0
    for school in School.objects.filter(is_active=True):
        sent, failed = NotificationService.send_pending_absence_alerts(school)
        total_sent   += sent
        total_failed += failed
        logger.info(f"School {school.name}: {sent} sent, {failed} failed")

    logger.info(f"Daily absence alerts: {total_sent} sent, {total_failed} failed")
    return {"total_sent": total_sent, "total_failed": total_failed}


# ── إشعار مخالفة سلوكية ─────────────────────────────────────────────

@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    name="notifications.notify_behavior",
)
def notify_behavior_task(self, infraction_id, reporter_id):
    """إشعار ولي الأمر عند تسجيل مخالفة سلوكية"""
    try:
        from behavior.models import BehaviorInfraction
        from core.models import CustomUser

        infraction = BehaviorInfraction.objects.select_related(
            "student", "school"
        ).get(id=infraction_id)
        reporter = CustomUser.objects.get(id=reporter_id)

        # استدعاء الدالة المباشرة من behavior/views.py
        from behavior.views import _notify_parents_behavior
        _notify_parents_behavior(infraction, infraction.school, reporter)

        return {"status": "done", "infraction": str(infraction_id)}

    except Exception as exc:
        logger.error(f"notify_behavior_task error: {exc}")
        raise self.retry(exc=exc)


# ── إشعار خرق البيانات (PDPPL م.11 + NCSA 72h) ──────────────────────

@shared_task(name="notifications.check_breach_deadlines")
def check_breach_deadlines_task():
    """
    مهمة مُجدوَلة — تُشغَّل كل ساعة من Celery Beat
    تتحقق من مواعيد BreachReport وترسل تنبيهات للمدير والـ DPO
    """
    from django.utils import timezone
    from core.models import BreachReport, School

    now        = timezone.now()
    warnings   = 0
    overdue    = 0

    # تقارير لم يُشعَر عنها بعد
    active = BreachReport.objects.filter(
        status__in=['discovered', 'assessing']
    ).select_related('school', 'reported_by', 'assigned_to')

    for breach in active:
        if not breach.ncsa_deadline:
            continue

        hours_left = breach.hours_remaining

        # تحذير: أقل من 12 ساعة متبقية
        if hours_left is not None and hours_left <= 12:
            _send_breach_alert(breach, hours_left, overdue=False)
            warnings += 1

        # تجاوز المهلة
        if breach.is_overdue:
            _send_breach_alert(breach, 0, overdue=True)
            overdue += 1

    logger.warning(f"Breach check: {warnings} تحذير، {overdue} تجاوز مهلة")
    return {'warnings': warnings, 'overdue': overdue}


def _send_breach_alert(breach, hours_left, overdue=False):
    """إرسال تنبيه بريد للمدير والـ DPO"""
    from django.core.mail import send_mail
    from django.conf import settings

    subject = (
        f"🚨 [عاجل] تجاوز مهلة إشعار NCSA — {breach.title}"
        if overdue else
        f"⚠️ تنبيه: {hours_left} ساعة لإشعار NCSA — {breach.title}"
    )

    body = f"""
تقرير خرق البيانات: {breach.title}
المدرسة: {breach.school.name}
الخطورة: {breach.get_severity_display()}
البيانات المتأثرة: {breach.get_data_type_affected_display()}
عدد الأشخاص: {breach.affected_count}
وقت الاكتشاف: {breach.discovered_at}
موعد NCSA: {breach.ncsa_deadline}
الحالة: {'⛔ تجاوز المهلة' if overdue else f'⚠️ {hours_left} ساعة متبقية'}

الإجراء الفوري: {breach.immediate_action or '—'}

رابط المراجعة: /breach/{breach.pk}/

PDPPL م.11 — يجب إشعار NCSA خلال 72 ساعة من الاكتشاف.
    """.strip()

    # جمع المستلمين: المسؤول (DPO) + المُبلِّغ
    recipients = []
    # DPO الافتراضي من settings
    dpo_email = getattr(settings, 'DPO_EMAIL', 's.mesyef0904@education.qa')
    if dpo_email:
        recipients.append(dpo_email)
    if breach.assigned_to and breach.assigned_to.email:
        recipients.append(breach.assigned_to.email)
    if breach.reported_by and breach.reported_by.email:
        recipients.append(breach.reported_by.email)

    if recipients:
        try:
            send_mail(
                subject=subject,
                message=body,
                from_email=getattr(settings, 'DEFAULT_FROM_EMAIL', 's.mesyef0904@education.qa'),
                recipient_list=list(set(recipients)),
                fail_silently=True,
            )
        except Exception as e:
            logger.error(f"breach alert email failed: {e}")


# ── Push Notification — VAPID (v5) ───────────────────────────────────

@shared_task(
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    name="notifications.send_push",
)
def send_push_task(self, user_id, title, body, url="/parents/", school_id=None):
    """
    إرسال Push Notification لولي الأمر عبر VAPID
    يعمل حتى لو كان المتصفح مغلقاً (شرط قبوله الإذن)
    """
    try:
        import json, base64
        from django.conf import settings
        from django.utils import timezone
        from cryptography.hazmat.primitives.asymmetric.ec import (
            SECP256R1, generate_private_key, EllipticCurvePrivateKey
        )
        from cryptography.hazmat.primitives.serialization import (
            load_pem_private_key, Encoding, PublicFormat
        )
        from notifications.models import PushSubscription

        subs = PushSubscription.objects.filter(
            user_id=user_id, is_active=True
        )
        if not subs.exists():
            return {'status': 'no_subscriptions', 'user': str(user_id)}

        payload = json.dumps({
            'title': title,
            'body':  body,
            'url':   url,
            'icon':  '/static/icons/icon-192.png',
            'badge': '/static/icons/badge-72.png',
        })

        # محاولة استخدام pywebpush إذا كان مثبتاً
        try:
            from pywebpush import webpush, WebPushException

            vapid_private = getattr(settings, 'VAPID_PRIVATE_KEY', '').replace('\\n', '\n')
            vapid_email   = getattr(settings, 'VAPID_CLAIMS_EMAIL', 'admin@shahaniya.edu.qa')

            sent = failed = 0
            for sub in subs:
                try:
                    webpush(
                        subscription_info=sub.to_dict(),
                        data=payload,
                        vapid_private_key=vapid_private,
                        vapid_claims={"sub": f"mailto:{vapid_email}"},
                    )
                    sub.last_used = timezone.now()
                    sub.save(update_fields=['last_used'])
                    sent += 1
                except WebPushException as e:
                    # 410 Gone = اشتراك منتهي → نحذفه
                    if '410' in str(e) or '404' in str(e):
                        sub.is_active = False
                        sub.save(update_fields=['is_active'])
                    failed += 1
                    logger.warning(f"Push failed for {sub.endpoint[:40]}: {e}")

            return {'sent': sent, 'failed': failed}

        except ImportError:
            # pywebpush غير مثبت — نسجّل فقط
            logger.info(f"Push queued (pywebpush not installed): {title} → user {user_id}")
            return {'status': 'queued_no_pywebpush', 'user': str(user_id)}

    except Exception as exc:
        logger.error(f"send_push_task error: {exc}")
        raise self.retry(exc=exc)


@shared_task(name="notifications.send_push_to_school")
def send_push_to_school_task(school_id, title, body, url="/parents/"):
    """إرسال Push لكل أولياء الأمور في مدرسة"""
    from core.models import School
    from notifications.models import PushSubscription

    school = School.objects.get(id=school_id)
    users  = PushSubscription.objects.filter(
        school=school, is_active=True
    ).values_list('user_id', flat=True).distinct()

    for uid in users:
        send_push_task.delay(str(uid), title, body, url, school_id)

    return {'queued': len(users)}


# ════════════════════════════════════════════════════════════════════
# ✅ v6: Hub task — إرسال مركزي مع retry لكل القنوات
# ════════════════════════════════════════════════════════════════════

@shared_task(
    bind=True,
    max_retries=3,
    name="notifications.hub_send",
)
def hub_send_notification_task(self, user_id, school_id, channels, title, body,
                                event_type, context=None, sent_by_id=None):
    """
    مهمة مركزية — يستدعيها NotificationHub لإرسال الإشعارات الخارجية.
    Retry: 3 محاولات مع exponential backoff (60s, 120s, 240s)
    """
    from core.models import CustomUser, School
    from notifications.services import NotificationService

    try:
        user   = CustomUser.objects.get(id=user_id)
        school = School.objects.get(id=school_id)
        sender = CustomUser.objects.get(id=sent_by_id) if sent_by_id else None

        results = []

        # ── Email ──────────────────────────────────────────────
        if "email" in channels and user.email:
            ok, err = NotificationService.send_email(
                school=school,
                recipient_email=user.email,
                subject=title,
                body_text=body,
                notif_type=_hub_to_notif_type(event_type),
                sent_by=sender,
            )
            results.append(("email", ok, err))

        # ── SMS ────────────────────────────────────────────────
        if "sms" in channels and user.phone:
            ok, err = NotificationService.send_sms(
                school=school,
                phone_number=user.phone,
                message=f"{title}\n{body}",
                notif_type=_hub_to_notif_type(event_type),
                sent_by=sender,
            )
            results.append(("sms", ok, err))

        # ── WhatsApp (عبر Twilio WhatsApp API) ────────────────
        if "whatsapp" in channels and user.phone:
            try:
                _send_whatsapp(school, user.phone, title, body)
                results.append(("whatsapp", True, None))
            except Exception as e:
                results.append(("whatsapp", False, str(e)))

        # ── Push ───────────────────────────────────────────────
        if "push" in channels:
            try:
                send_push_task.delay(
                    str(user.id), title, body,
                    context.get("related_url", "/") if context else "/",
                    str(school.id),
                )
                results.append(("push", True, None))
            except Exception as e:
                results.append(("push", False, str(e)))

        # ── تحقق من الفشل ─────────────────────────────────────
        failures = [r for r in results if not r[1]]
        if failures and all(not r[1] for r in results):
            # كل القنوات فشلت → retry
            error_msg = "; ".join(f"{ch}: {err}" for ch, _, err in failures)
            raise Exception(f"All channels failed: {error_msg}")

        logger.info(
            f"hub_send: {user.full_name} | "
            f"success={[r[0] for r in results if r[1]]} | "
            f"failed={[r[0] for r in results if not r[1]]}"
        )
        return {"user": str(user_id), "results": [(r[0], r[1]) for r in results]}

    except (CustomUser.DoesNotExist, School.DoesNotExist) as e:
        logger.error(f"hub_send: object not found: {e}")
        return {"error": str(e)}

    except Exception as exc:
        # Exponential backoff: 60s, 120s, 240s
        countdown = 60 * (2 ** self.request.retries)
        logger.warning(
            f"hub_send retry {self.request.retries + 1}/3 "
            f"for {user_id}: {exc} (next in {countdown}s)"
        )
        raise self.retry(exc=exc, countdown=countdown)


def _hub_to_notif_type(event_type):
    """تحويل event_type من Hub لنوع NotificationLog"""
    mapping = {
        "behavior_l1": "custom",
        "behavior_l2": "custom",
        "behavior_l3": "custom",
        "behavior_l4": "custom",
        "absence":     "absence_alert",
        "grade":       "grade_report",
        "fail":        "fail_alert",
    }
    return mapping.get(event_type, "custom")


def _send_whatsapp(school, phone, title, body):
    """
    إرسال WhatsApp عبر Twilio WhatsApp Business API.
    يحتاج: whatsapp_from_number في NotificationSettings
    """
    from notifications.models import NotificationSettings, NotificationLog

    cfg = NotificationSettings.objects.filter(school=school).first()
    if not cfg:
        raise Exception("لا توجد إعدادات إشعارات للمدرسة")

    whatsapp_from = getattr(cfg, 'whatsapp_from_number', '') or getattr(cfg, 'sms_from_number', '')
    if not whatsapp_from:
        raise Exception("رقم WhatsApp غير مضبوط")

    try:
        from twilio.rest import Client
        client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)
        message = client.messages.create(
            from_='whatsapp:' + whatsapp_from,
            to='whatsapp:' + phone,
            body=f"*{title}*\n{body}",
        )

        # تسجيل في NotificationLog
        NotificationLog.objects.create(
            school=school,
            recipient=f"whatsapp:{phone}",
            channel="sms",  # نستخدم sms كقناة لأن whatsapp غير موجود في choices حالياً
            notif_type="custom",
            subject=title,
            body=body,
            status="sent",
        )
        return message.sid

    except ImportError:
        raise Exception("مكتبة twilio غير مثبتة")

