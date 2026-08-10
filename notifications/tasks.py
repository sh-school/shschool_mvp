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

import logging
import re

from celery import shared_task
from celery.exceptions import MaxRetriesExceededError
from django.conf import settings

from core.celery_tasks import TenantRLSTask, school_rls_scope

logger = logging.getLogger(__name__)


#: [P2-B2] أنماط تُنقَّى من نصّ الخطأ قبل تخزينه. الخدمات اليوم تُرجع رسائل
#: عامة، لكن عقد `_to_dlq` يقبل أي استثناء من أي مُستدعٍ مستقبلي — ورسائل
#: مزوّدي البريد وTwilio تحمل عادةً العنوان أو الرقم الذي فشل. الحقل يجب أن
#: يكون آمناً بحكم العقد لا بحكم عادة المُستدعين الحاليين.
_ERROR_REDACTIONS = (
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "<email>"),
    (re.compile(r"\+?\d[\d\s-]{7,}\d"), "<phone>"),
    (re.compile(r"https?://\S+"), "<url>"),
)


def _safe_error(error):
    """[P2-B2] يُزيل ما قد يحمله نصّ الاستثناء من بيانات شخصية."""
    text = str(error)

    for pattern, replacement in _ERROR_REDACTIONS:
        text = pattern.sub(replacement, text)

    return text[:2000]


def _to_dlq(kind, school_id, payload, error):
    """
    [P0-8] يحفظ رسالة فشلت نهائياً في Dead-Letter Queue بدل ضياعها بصمت.

    [P2-B1] المدرسة وسيط صريح لا مفتاح يُستخرج من الـpayload. هي العمود الذي
    تعتمد عليه سياسة العزل، وتمريرها ضمناً داخل JSON هو ما أبقى هذا الجدول
    خارج RLS من الأساس.

    [P2-B2] الـpayload بيانات **تشخيصية**: تكفي لمعرفة ما فشل ومتى ولأي مدرسة،
    ولا تكفي لإعادة الإرسال. `send_email_task` تقبل `student_id=None` مع
    `notif_type="custom"`، فرسالة إلى عنوان خارجي لا يبقى منها ما يستعيد
    المستلم. إعادة الإرسال تحتاج مرجعاً أو snapshot مشفّراً لم يُصمَّم بعد —
    والبديل، أي تخزين البريد والهاتف والنصّ خاماً، يُنشئ مستودع PII جديداً.
    """
    try:
        from notifications.models import DeadLetterMessage

        DeadLetterMessage.objects.create(
            kind=kind,
            school_id=school_id,
            payload=payload,
            error=_safe_error(error),
        )
        logger.error("DLQ: %s message dead-lettered", kind)
    except Exception:  # noqa: BLE001 — لا نُفشل المهمة بسبب فشل الكتابة في DLQ نفسه
        logger.exception("DLQ write failed for kind=%s", kind)


# ── إرسال بريد إلكتروني ─────────────────────────────────────────────


@shared_task(
    base=TenantRLSTask,
    bind=True,
    max_retries=3,
    default_retry_delay=60,  # إعادة المحاولة بعد دقيقة
    name="notifications.send_email",
)
def send_email_task(
    self,
    school_id,
    recipient_email,
    subject,
    body_text,
    body_html=None,
    student_id=None,
    notif_type="custom",
    sent_by_id=None,
):
    """
    إرسال بريد إلكتروني بشكل غير متزامن.
    يُعيد المحاولة تلقائياً 3 مرات عند الفشل.
    """
    try:
        from core.models import CustomUser, School
        from notifications.services import NotificationService

        school = School.objects.get(id=school_id)
        student = CustomUser.objects.filter(id=student_id).first() if student_id else None
        sent_by = CustomUser.objects.filter(id=sent_by_id).first() if sent_by_id else None

        ok, err = NotificationService.send_email(
            school=school,
            recipient_email=recipient_email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            student=student,
            notif_type=notif_type,
            sent_by=sent_by,
        )

        if not ok:
            logger.warning(f"Email failed to {recipient_email}: {err}")
            raise RuntimeError(err)  # نوع مُلتقَط ⇒ يدخل مسار retry ثم DLQ

        return {"status": "sent", "recipient": recipient_email}

    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("send_email_task error: %s", exc)
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            # [P2-B2] تشخيص لا إعادة تشغيل: بلا recipient_email ولا subject.
            # مع student_id=None و notif_type="custom" لا يبقى ما يستعيد المستلم —
            # وهذا مقصود حتى يُصمَّم مرجع/snapshot مشفّر (P2-C).
            _to_dlq(
                "email",
                school_id,
                {
                    "student_id": student_id,
                    "notif_type": notif_type,
                    "sent_by_id": sent_by_id,
                },
                exc,
            )
            return {"status": "dead_letter", "recipient": recipient_email}


# ── إرسال SMS ────────────────────────────────────────────────────────


@shared_task(
    base=TenantRLSTask,
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_sms",
)
def send_sms_task(
    self, school_id, phone_number, message, student_id=None, notif_type="custom", sent_by_id=None
):
    """إرسال SMS بشكل غير متزامن عبر Twilio"""
    try:
        from core.models import CustomUser, School
        from notifications.services import NotificationService

        school = School.objects.get(id=school_id)
        student = CustomUser.objects.filter(id=student_id).first() if student_id else None
        sent_by = CustomUser.objects.filter(id=sent_by_id).first() if sent_by_id else None

        ok, err = NotificationService.send_sms(
            school=school,
            phone_number=phone_number,
            message=message,
            student=student,
            notif_type=notif_type,
            sent_by=sent_by,
        )

        if not ok:
            raise RuntimeError(err)  # نوع مُلتقَط ⇒ يدخل مسار retry ثم DLQ

        return {"status": "sent", "recipient": phone_number}

    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("send_sms_task error: %s", exc)
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            # [P2-B2] تشخيص لا إعادة تشغيل: الهاتف والنصّ بيانات شخصية،
            # وما تبقّى لا يكفي لإعادة البناء عند student_id=None.
            _to_dlq(
                "sms",
                school_id,
                {
                    "student_id": student_id,
                    "notif_type": notif_type,
                    "sent_by_id": sent_by_id,
                },
                exc,
            )
            return {"status": "dead_letter", "recipient": phone_number}


# ── إرسال WhatsApp ───────────────────────────────────────────────────


@shared_task(
    base=TenantRLSTask,
    bind=True,
    max_retries=3,
    default_retry_delay=60,
    name="notifications.send_whatsapp",
)
def send_whatsapp_task(self, school_id, phone_number, title, body, sent_by_id=None):
    """
    [P2-B3] تسليم WhatsApp مستقلّ.

    كان يُرسَل داخل hub_send_notification_task مباشرةً بينما فُوّضت بقيّة
    القنوات، فلم يكن له retry خاص ولا مسار إلى DLQ: فشله يُضاف إلى results
    وتنتهي مهمة الـHub بنجاح. قناة تُرسل بنفسها داخل المنسّق تُبطل عقد
    "الوحدة تسليم" بدل أن تستثني نفسها منه.
    """
    try:
        from core.models import School

        school = School.objects.get(id=school_id)
        _send_whatsapp(school, phone_number, title, body)

        return {"status": "sent", "channel": "whatsapp"}

    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        logger.exception("send_whatsapp_task error: %s", exc)
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            # [P2-B2] تشخيص لا إعادة تشغيل: لا رقم ولا نصّ رسالة.
            _to_dlq(
                "whatsapp",
                school_id,
                {"notif_type": "whatsapp", "sent_by_id": sent_by_id, "user_id": None},
                exc,
            )
            return {"status": "dead_letter", "channel": "whatsapp"}


# ── إشعار غياب الطالب ───────────────────────────────────────────────


@shared_task(
    base=TenantRLSTask,
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    name="notifications.notify_absence",
)
def notify_absence_task(self, absence_alert_id, sent_by_id=None, school_id=None):
    """إشعار ولي الأمر بغياب ابنه — يُشغَّل من AbsenceService"""
    try:
        from core.models import CustomUser
        from notifications.services import NotificationService
        from operations.models import AbsenceAlert

        alert = AbsenceAlert.objects.select_related("school", "student").get(
            id=absence_alert_id, school_id=school_id
        )
        sent_by = CustomUser.objects.filter(id=sent_by_id).first() if sent_by_id else None

        results = NotificationService.notify_absence(alert, sent_by=sent_by)
        sent = sum(1 for r in results if r["ok"])
        logger.info(f"Absence notification for {alert.student}: {sent}/{len(results)} sent")

        # ✅ v5: إرسال Push للوالدين المشتركين
        try:
            from core.models import ParentStudentLink

            parents = ParentStudentLink.objects.filter(
                student=alert.student, school=alert.school
            ).values_list("parent_id", flat=True)
            for pid in parents:
                send_push_task.delay(
                    str(pid),
                    title=f"⚠️ غياب — {alert.student.full_name}",
                    body="تم تسجيل غياب اليوم. اضغط للتفاصيل.",
                    url="/parents/",
                    school_id=str(alert.school_id),
                )
        except (ImportError, OSError, RuntimeError) as pe:
            logger.warning(f"Push notification failed: {pe}")

        return {"sent": sent, "total": len(results)}

    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("notify_absence_task error: %s", exc)
        raise self.retry(exc=exc)


# ── إشعار رسوب الطالب ───────────────────────────────────────────────


@shared_task(
    base=TenantRLSTask,
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    name="notifications.notify_fail",
)
def notify_fail_task(
    self,
    student_id,
    school_id,
    failed_subjects,
    year=settings.CURRENT_ACADEMIC_YEAR,
    sent_by_id=None,
):
    """إشعار ولي الأمر برسوب ابنه"""
    try:
        from core.models import CustomUser, School
        from notifications.services import NotificationService

        student = CustomUser.objects.get(id=student_id)
        school = School.objects.get(id=school_id)
        sent_by = CustomUser.objects.filter(id=sent_by_id).first() if sent_by_id else None

        results = NotificationService.notify_fail(
            student=student,
            school=school,
            failed_subjects=failed_subjects,
            year=year,
            sent_by=sent_by,
        )
        sent = sum(1 for r in results if r["ok"])
        return {"sent": sent, "total": len(results)}

    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("notify_fail_task error: %s", exc)
        raise self.retry(exc=exc)


# ── إرسال جماعي لتنبيهات الغياب المعلقة (مُجدوَل) ──────────────────


@shared_task(name="notifications.send_pending_absence_alerts_all_schools")
def send_pending_absence_alerts_task():
    """Send pending absence alerts one school at a time."""
    from core.models import School
    from notifications.services import NotificationService

    total_sent = 0
    total_failed = 0

    schools = School.objects.filter(is_active=True)

    for school in schools.iterator(chunk_size=100):
        with school_rls_scope(school.id):
            sent, failed = NotificationService.send_pending_absence_alerts(school)

            total_sent += sent
            total_failed += failed

            logger.info(
                "School %s: %d sent, %d failed",
                school.name,
                sent,
                failed,
            )

    logger.info(
        "Daily absence alerts: %d sent, %d failed",
        total_sent,
        total_failed,
    )

    return {
        "total_sent": total_sent,
        "total_failed": total_failed,
    }


# ── إشعار مخالفة سلوكية ─────────────────────────────────────────────


@shared_task(
    base=TenantRLSTask,
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    name="notifications.notify_behavior",
)
def notify_behavior_task(self, infraction_id, reporter_id, school_id=None):
    """إشعار ولي الأمر عند تسجيل مخالفة سلوكية"""
    try:
        from behavior.models import BehaviorInfraction
        from core.models import CustomUser

        infraction = BehaviorInfraction.objects.select_related("student", "school").get(
            id=infraction_id, school_id=school_id
        )
        reporter = CustomUser.objects.get(id=reporter_id)

        from behavior.services import BehaviorService

        BehaviorService.notify_parents(infraction, infraction.school, reporter)

        return {"status": "done", "infraction": str(infraction_id)}

    except (OSError, RuntimeError, ValueError) as exc:
        logger.exception("notify_behavior_task error: %s", exc)
        raise self.retry(exc=exc)


# ── إشعار خرق البيانات (PDPPL م.11 + NCSA 72h) ──────────────────────


@shared_task(name="notifications.check_breach_deadlines")
def check_breach_deadlines_task():
    """Check breach deadlines inside one school scope at a time."""
    from django.utils import timezone

    from core.models import BreachReport, School

    now = timezone.now()
    warnings = 0
    overdue = 0

    schools = School.objects.all()

    for school in schools.iterator(chunk_size=100):
        with school_rls_scope(school.id):
            active = BreachReport.objects.filter(
                school=school,
                status__in=["discovered", "assessing"],
            ).select_related(
                "school",
                "reported_by",
                "assigned_to",
            )

            for breach in active.iterator(chunk_size=100):
                if not breach.ncsa_deadline:
                    continue

                hours_left = breach.hours_remaining

                if hours_left is not None and hours_left <= 12:
                    _send_breach_alert(
                        breach,
                        hours_left,
                        overdue=False,
                    )
                    warnings += 1

                if breach.is_overdue:
                    _send_breach_alert(
                        breach,
                        0,
                        overdue=True,
                    )
                    overdue += 1

    logger.warning(
        "Breach check: %d تحذير، %d تجاوز مهلة",
        warnings,
        overdue,
    )

    return {
        "warnings": warnings,
        "overdue": overdue,
    }


def _send_breach_alert(breach, hours_left, overdue=False):
    """إرسال تنبيه بريد للمدير والـ DPO"""
    from django.conf import settings
    from django.core.mail import send_mail

    subject = (
        f"🚨 [عاجل] تجاوز مهلة إشعار NCSA — {breach.title}"
        if overdue
        else f"⚠️ تنبيه: {hours_left} ساعة لإشعار NCSA — {breach.title}"
    )

    body = f"""
تقرير خرق البيانات: {breach.title}
المدرسة: {breach.school.name}
الخطورة: {breach.get_severity_display()}
البيانات المتأثرة: {breach.get_data_type_affected_display()}
عدد الأشخاص: {breach.affected_count}
وقت الاكتشاف: {breach.discovered_at}
موعد NCSA: {breach.ncsa_deadline}
الحالة: {"⛔ تجاوز المهلة" if overdue else f"⚠️ {hours_left} ساعة متبقية"}

الإجراء الفوري: {breach.immediate_action or "—"}

رابط المراجعة: /breach/{breach.pk}/

PDPPL م.11 — يجب إشعار NCSA خلال 72 ساعة من الاكتشاف.
    """.strip()

    # جمع المستلمين: المسؤول (DPO) + المُبلِّغ
    recipients = []
    # DPO الافتراضي من settings
    dpo_email = getattr(settings, "DPO_EMAIL", "s.mesyef0904@education.qa")
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
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "s.mesyef0904@education.qa"),
                recipient_list=list(set(recipients)),
                fail_silently=True,
            )
        except (OSError, RuntimeError, ValueError) as e:
            logger.error(f"breach alert email failed: {e}")


# ── Push Notification — VAPID (v5) ───────────────────────────────────


@shared_task(
    base=TenantRLSTask,
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
        import json

        from django.conf import settings
        from django.utils import timezone

        from notifications.models import PushSubscription

        subs = PushSubscription.objects.filter(
            user_id=user_id,
            school_id=school_id,
            is_active=True,
        )
        if not subs.exists():
            return {"status": "no_subscriptions", "user": str(user_id)}

        payload = json.dumps(
            {
                "title": title,
                "body": body,
                "url": url,
                "icon": "/static/icons/icon-192.png",
                "badge": "/static/icons/badge-72.png",
            }
        )

        # محاولة استخدام pywebpush إذا كان مثبتاً
        try:
            from pywebpush import WebPushException, webpush

            vapid_private = getattr(settings, "VAPID_PRIVATE_KEY", "").replace("\\n", "\n")
            vapid_email = getattr(settings, "VAPID_CLAIMS_EMAIL", "admin@shahaniya.edu.qa")

            sent = invalidated = 0
            transient = []

            for sub in subs:
                try:
                    webpush(
                        subscription_info=sub.to_dict(),
                        data=payload,
                        vapid_private_key=vapid_private,
                        vapid_claims={"sub": f"mailto:{vapid_email}"},
                    )
                    sub.last_used = timezone.now()
                    sub.save(update_fields=["last_used"])
                    sent += 1
                except WebPushException as e:
                    # [P2-B3] 404/410 ليست تسليماً فاشلاً بل اشتراكاً ميّتاً:
                    # المتصفّح ألغاه. إعادة المحاولة عليه لن تنجح أبداً، وتسجيله
                    # في DLQ يملؤها بضجيج لا إجراء له. التعطيل هو الإجراء.
                    if "410" in str(e) or "404" in str(e):
                        sub.is_active = False
                        sub.save(update_fields=["is_active"])
                        invalidated += 1
                        logger.info("Push subscription invalidated (gone)")
                        continue

                    # وفشل المزوّد على اشتراك صالح تسليمٌ فاشل قابل للإعادة —
                    # كان يُبتلع في عدّاد وتنتهي المهمة بنجاح، فلا retry ولا DLQ.
                    transient.append(e)
                    logger.warning("Push delivery failed (transient): %s", e)

            if transient and sent == 0:
                # كل التسليمات الصالحة فشلت ⇒ لا شيء نجح، فالإعادة لا تُكرّر شيئاً.
                raise RuntimeError(f"push delivery failed for {len(transient)} subscription(s)")

            return {"sent": sent, "invalidated": invalidated, "transient": len(transient)}

        except ImportError:
            # pywebpush غير مثبت — نسجّل فقط
            logger.info(f"Push queued (pywebpush not installed): {title} → user {user_id}")
            return {"status": "queued_no_pywebpush", "user": str(user_id)}

    except (ImportError, OSError, RuntimeError, ValueError) as exc:
        logger.exception("send_push_task error: %s", exc)
        try:
            raise self.retry(exc=exc)
        except MaxRetriesExceededError:
            # [P2-B3] تسليم Push انتهت محاولاته ⇒ يدخل DLQ مثل البريد وSMS.
            # النموذج يُعرّف kind="push" منذ البداية ولم يكن يُكتب قط.
            _to_dlq(
                "push",
                school_id,
                {"user_id": str(user_id), "notif_type": "push", "sent_by_id": None},
                exc,
            )
            return {"status": "dead_letter", "user": str(user_id)}


@shared_task(
    base=TenantRLSTask,
    name="notifications.send_push_to_school",
)
def send_push_to_school_task(school_id, title, body, url="/parents/"):
    """إرسال Push لكل أولياء الأمور في مدرسة"""
    from core.models import School
    from notifications.models import PushSubscription

    school = School.objects.get(id=school_id)
    users = (
        PushSubscription.objects.filter(school=school, is_active=True)
        .values_list("user_id", flat=True)
        .distinct()
    )

    for uid in users:
        send_push_task.delay(str(uid), title, body, url, school_id=school_id)

    return {"queued": len(users)}


# ════════════════════════════════════════════════════════════════════
# ✅ v6: Hub task — إرسال مركزي مع retry لكل القنوات
# ════════════════════════════════════════════════════════════════════


@shared_task(
    base=TenantRLSTask,
    bind=True,
    max_retries=3,
    name="notifications.hub_send",
)
def hub_send_notification_task(
    self, user_id, school_id, channels, title, body, event_type, context=None, sent_by_id=None
):
    """
    مهمة مركزية — يستدعيها NotificationHub لإرسال الإشعارات الخارجية.
    Retry: 3 محاولات مع exponential backoff (60s, 120s, 240s)
    """
    from core.models import CustomUser, School

    try:
        user = CustomUser.objects.get(id=user_id)
        school = School.objects.get(id=school_id)
        sender = CustomUser.objects.get(id=sent_by_id) if sent_by_id else None

        results = []

        # ── Email ──────────────────────────────────────────────
        if "email" in channels and user.email:
            # [P2-B3] تسليم مستقلّ لا إرسال داخل هذه المهمة. كان البريد وSMS
            # يُرسَلان هنا مباشرةً، فصار فشل قناة واحدة إمّا يضيع صامتاً — لأن
            # المهمة تنتهي بنجاح ما دام أحدهما نجح — أو، لو أعدنا المهمة،
            # يُعيد إرسال القناة الناجحة ويُنتج إشعاراً مكرّراً.
            # كل مهمة تسليم تحمل retry الخاص بها ومسارها إلى DLQ.
            send_email_task.delay(
                school_id=str(school.id),
                recipient_email=user.email,
                subject=title,
                body_text=body,
                notif_type=_hub_to_notif_type(event_type),
                sent_by_id=str(sender.id) if sender else None,
            )
            results.append(("email", True, None))

        # ── SMS ────────────────────────────────────────────────
        if "sms" in channels and user.phone:
            send_sms_task.delay(
                school_id=str(school.id),
                phone_number=user.phone,
                message=f"{title}\n{body}",
                notif_type=_hub_to_notif_type(event_type),
                sent_by_id=str(sender.id) if sender else None,
            )
            results.append(("sms", True, None))

        # ── WhatsApp (عبر Twilio WhatsApp API) ────────────────
        if "whatsapp" in channels and user.phone:
            send_whatsapp_task.delay(
                school_id=str(school.id),
                phone_number=user.phone,
                title=title,
                body=body,
                sent_by_id=str(sender.id) if sender else None,
            )
            results.append(("whatsapp", True, None))

        # ── Push ───────────────────────────────────────────────
        if "push" in channels:
            try:
                send_push_task.delay(
                    str(user.id),
                    title,
                    body,
                    context.get("related_url", "/") if context else "/",
                    school_id=str(school.id),
                )
                results.append(("push", True, None))
            except (ImportError, OSError, RuntimeError) as e:
                logger.exception("فشل جدولة مهمة Push للمستخدم %s: %s", user_id, e)
                results.append(("push", False, str(e)))

        # ── تحقق من الفشل ─────────────────────────────────────
        # [P2-B3] لا retry على مستوى المهمة. كان هنا raise Exception(...)
        # و except أدناه يمسك (OSError, RuntimeError, ValueError, KeyError)
        # فقط — فلم يكن يلتقطها، ولم يُستدعَ self.retry() قط رغم أن التعليق
        # يقول "→ retry". وحتى لو التقطها، إعادة المهمة كانت ستُعيد إرسال
        # القنوات الناجحة. الفشل الآن مسؤولية كل مهمة تسليم على حدة.
        failures = [r for r in results if not r[1]]
        if failures:
            logger.warning(
                "hub_send: %d channel(s) failed to dispatch for user %s",
                len(failures),
                user_id,
            )

        logger.info(
            f"hub_send: {user.full_name} | "
            f"success={[r[0] for r in results if r[1]]} | "
            f"failed={[r[0] for r in results if not r[1]]}"
        )
        return {"user": str(user_id), "results": [(r[0], r[1]) for r in results]}

    except (CustomUser.DoesNotExist, School.DoesNotExist) as e:
        logger.error(f"hub_send: object not found: {e}")
        return {"error": str(e)}

    except (OSError, RuntimeError, ValueError, KeyError) as exc:
        # Exponential backoff: 60s, 120s, 240s
        countdown = 60 * (2**self.request.retries)
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
        "absence": "absence_alert",
        "grade": "grade_report",
        "fail": "fail_alert",
    }
    return mapping.get(event_type, "custom")


def _send_whatsapp(school, phone, title, body):
    """
    إرسال WhatsApp عبر Twilio WhatsApp Business API.
    يحتاج: whatsapp_from_number في NotificationSettings
    """
    from notifications.models import NotificationLog, NotificationSettings

    cfg = NotificationSettings.objects.filter(school=school).first()
    if not cfg:
        raise RuntimeError("لا توجد إعدادات إشعارات للمدرسة")

    whatsapp_from = getattr(cfg, "whatsapp_from_number", "") or getattr(cfg, "sms_from_number", "")
    if not whatsapp_from:
        raise RuntimeError("رقم WhatsApp غير مضبوط")

    try:
        from twilio.rest import Client
    except ImportError as exc:
        raise RuntimeError("مكتبة twilio غير مثبتة") from exc

    try:
        client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)
        message = client.messages.create(
            from_="whatsapp:" + whatsapp_from,
            to="whatsapp:" + phone,
            body=f"*{title}*\n{body}",
        )
    except Exception as exc:  # noqa: BLE001 — أخطاء المزوّد أنواع خاصة به
        # [P2-B3] تُلَفّ في RuntimeError لأنها العقد الذي تمسكه مهمة التسليم.
        # بلا ذلك يفلت خطأ Twilio من retry ومن DLQ معاً — وهو الفشل الأكثر
        # احتمالاً في هذه القناة. والرسالة عامة عمداً: نصّ استثناء المزوّد
        # يحمل عادةً الرقم الذي فشل.
        raise RuntimeError("تعذّر إرسال رسالة WhatsApp عبر المزوّد.") from exc

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
