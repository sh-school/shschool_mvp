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
