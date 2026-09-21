"""
notifications/services.py
محرك الإشعارات — بريد إلكتروني + SMS
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import TYPE_CHECKING, NamedTuple

import django.core.mail

logger = logging.getLogger(__name__)
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone
from kombu.exceptions import OperationalError

from core.academic_calendar import academic_year_for_school
from core.models import ParentStudentLink

from . import quiet_hours
from .models import NotificationLog, NotificationSettings

_EMAIL_FAILURE_MESSAGE = "تعذر إرسال البريد الإلكتروني."
_EMAIL_UNDELIVERED_MESSAGE = "لم يُسلَّم البريد: لا مزوّد بريد مُهيَّأ."
_SMS_FAILURE_MESSAGE = "تعذر إرسال رسالة SMS."

if TYPE_CHECKING:
    from core.models import CustomUser, School
    from operations.models import AbsenceAlert


_QUIET_UNHELD_MESSAGE = "ساعات هدوء المستلم — لا عاملَ يحفظ الإرسال المؤجَّل."
_QUIET_HOLD_FAILED_MESSAGE = "تعذّر جدولة الإرسال المؤجَّل إلى انتهاء ساعات الهدوء."


class DeliveryOutcome(NamedTuple):
    """نتيجةُ إرسالٍ خارجيّ لمستلمٍ يحترم ساعات الهدوء.

    `deferred_until` غيرُ فارغ ⇒ لم يخرج شيءٌ بعد: جُدوِل ليخرج عند انتهاء ساعات
    هدوء المستلم، و`ok=True` تعني «قُبل للجدولة» لا «وصل».
    """

    ok: bool
    error: str | None
    deferred_until: datetime | None = None


class SendCounts(tuple):
    """`(sent, failed)` كما كانت — ومعها `.deferred` لما جُدوِل لا لما خرج.

    صنفُ tuple لا NamedTuple ثلاثيّ: المستدعون كلّهم يفكّكون اثنين، وثالثٌ يكسرهم.
    `sent` يشمل المؤجَّل (قُبل)، و`deferred` يقول كم منه لم يخرج بعد.
    """

    deferred: int

    def __new__(cls, sent: int, failed: int, deferred: int = 0):
        obj = super().__new__(cls, (sent, failed))
        obj.deferred = deferred
        return obj


def _result(channel: str, recipient: str, outcome: DeliveryOutcome) -> dict:
    """صفُّ نتيجةٍ موحَّد؛ `deferred` يقول إنّ الإرسال جُدوِل ولم يخرج بعد."""
    return {
        "channel": channel,
        "recipient": recipient,
        "ok": outcome.ok,
        "error": outcome.error,
        "deferred": outcome.deferred_until is not None,
    }


class NotificationService:
    # ── إرسال خارجيّ يحترم ساعات الهدوء ─────────────────────────
    #
    # المدخلُ الموحَّد لكلّ إرسالٍ خارجيّ إلى مستخدمٍ معروف (وليّ أمر…). الـHub يطرح
    # السؤالَ نفسه عند الطبر (`hub._queue_external_now`)؛ وكلاهما يسأل
    # `quiet_hours.plan`. `send_email`/`send_sms` أدناه تبقيان المنفِّذَ الخامَ
    # بلا حكمٍ: هما تُستدعيان بعد أن قُرّر أنّ اللحظة مناسبة.

    @staticmethod
    def _hold(user, school, target: str, payload: dict, eta: datetime) -> DeliveryOutcome:
        from .tasks import release_after_quiet_hours_task

        try:
            release_after_quiet_hours_task.apply_async(
                kwargs={
                    "school_id": str(school.id),
                    "user_id": str(user.id),
                    "target": target,
                    "payload": payload,
                },
                eta=eta,
            )
        except (OperationalError, OSError):
            logger.warning("quiet hours — hold failed target=%s recipient_id=%s", target, user.pk)
            return DeliveryOutcome(False, _QUIET_HOLD_FAILED_MESSAGE)

        logger.info("quiet hours — held target=%s recipient_id=%s", target, user.pk)
        return DeliveryOutcome(True, None, eta)

    @staticmethod
    def deliver_email(
        user: CustomUser,
        school: School,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        student: CustomUser | None = None,
        notif_type: str = "custom",
        sent_by: CustomUser | None = None,
    ) -> DeliveryOutcome:
        """بريدٌ إلى `user` على عنوانه: الآن، أو مؤجَّلاً إلى انتهاء ساعات هدوئه."""
        plan = quiet_hours.plan(user)

        if plan.action == quiet_hours.SKIP:
            return DeliveryOutcome(False, _QUIET_UNHELD_MESSAGE)

        if plan.action == quiet_hours.HOLD:
            return NotificationService._hold(
                user,
                school,
                "email",
                {
                    "school_id": str(school.id),
                    "recipient_email": user.email,
                    "subject": subject,
                    "body_text": body_text,
                    "body_html": body_html,
                    "student_id": str(student.id) if student else None,
                    "notif_type": notif_type,
                    "sent_by_id": str(sent_by.id) if sent_by else None,
                },
                plan.eta,
            )

        ok, err = NotificationService.send_email(
            school=school,
            recipient_email=user.email,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            student=student,
            notif_type=notif_type,
            sent_by=sent_by,
        )
        return DeliveryOutcome(ok, err)

    @staticmethod
    def deliver_sms(
        user: CustomUser,
        school: School,
        phone_number: str,
        message: str,
        student: CustomUser | None = None,
        notif_type: str = "custom",
        sent_by: CustomUser | None = None,
    ) -> DeliveryOutcome:
        """رسالةٌ نصّيّة إلى `user`: الآن، أو مؤجَّلةً إلى انتهاء ساعات هدوئه."""
        plan = quiet_hours.plan(user)

        if plan.action == quiet_hours.SKIP:
            return DeliveryOutcome(False, _QUIET_UNHELD_MESSAGE)

        if plan.action == quiet_hours.HOLD:
            return NotificationService._hold(
                user,
                school,
                "sms",
                {
                    "school_id": str(school.id),
                    "phone_number": phone_number,
                    "message": message,
                    "student_id": str(student.id) if student else None,
                    "notif_type": notif_type,
                    "sent_by_id": str(sent_by.id) if sent_by else None,
                },
                plan.eta,
            )

        ok, err = NotificationService.send_sms(
            school=school,
            phone_number=phone_number,
            message=message,
            student=student,
            notif_type=notif_type,
            sent_by=sent_by,
        )
        return DeliveryOutcome(ok, err)

    # ── إرسال بريد إلكتروني ──────────────────────────────────

    @staticmethod
    def send_email(
        school: School,
        recipient_email: str,
        subject: str,
        body_text: str,
        body_html: str | None = None,
        student: CustomUser | None = None,
        notif_type: str = "custom",
        sent_by: CustomUser | None = None,
        delivery=None,
    ) -> tuple:
        """إرسال بريد إلكتروني وتسجيله

        [B4-1] `delivery` اختياري: يربط هذه المحاولة بتسليمها حين يعرفه
        المُستدعي. لا شيء يُنشئه هنا — الخدمة تنفّذ ولا تُقرّر الهوية.
        """
        log = NotificationLog.objects.create(
            school=school,
            delivery=delivery,
            student=student,
            recipient=recipient_email,
            channel="email",
            notif_type=notif_type,
            subject=subject,
            body=body_text,
            status="pending",
            sent_by=sent_by,
        )

        try:
            cfg = NotificationSettings.objects.filter(school=school).first()
            from_name = cfg.from_name if cfg else school.name
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@schoolos.qa")

            if body_html:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=body_text,
                    from_email=f"{from_name} <{from_email}>",
                    to=[recipient_email],
                )
                msg.attach_alternative(body_html, "text/html")
                if cfg and cfg.reply_to:
                    msg.reply_to = [cfg.reply_to]
                delivered = msg.send()
            else:
                delivered = django.core.mail.send_mail(
                    subject=subject,
                    message=body_text,
                    from_email=f"{from_name} <{from_email}>",
                    recipient_list=[recipient_email],
                    fail_silently=False,
                )

            if not delivered:
                logger.error("البريد لم يُسلَّم: الـbackend ردّ صفراً")
                log.status = "failed"
                log.error_msg = _EMAIL_UNDELIVERED_MESSAGE
                log.save(update_fields=["status", "error_msg"])
                return False, _EMAIL_UNDELIVERED_MESSAGE

            log.status = "sent"
            log.save(update_fields=["status"])
            return True, None

        except (OSError, RuntimeError, ValueError):
            logger.error("فشل إرسال البريد الإلكتروني")
            log.status = "failed"
            log.error_msg = _EMAIL_FAILURE_MESSAGE
            log.save(update_fields=["status", "error_msg"])
            return False, _EMAIL_FAILURE_MESSAGE

    # ── إرسال SMS ────────────────────────────────────────────

    @staticmethod
    def send_sms(
        school: School,
        phone_number: str,
        message: str,
        student: CustomUser | None = None,
        notif_type: str = "custom",
        sent_by: CustomUser | None = None,
        delivery=None,
    ) -> tuple:
        """إرسال SMS عبر Twilio

        [B4-1] `delivery` اختياري — انظر `send_email`.
        """
        log = NotificationLog.objects.create(
            school=school,
            delivery=delivery,
            student=student,
            recipient=phone_number,
            channel="sms",
            notif_type=notif_type,
            subject="",
            body=message,
            status="pending",
            sent_by=sent_by,
        )

        try:
            cfg = NotificationSettings.objects.filter(school=school).first()
            if not cfg or not cfg.sms_enabled:
                log.status = "failed"
                log.error_msg = "SMS معطّل في الإعدادات"
                log.save(update_fields=["status", "error_msg"])
                return False, "SMS معطّل"

            if cfg.sms_provider == "twilio":
                try:
                    from twilio.rest import Client

                    client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)
                    client.messages.create(
                        body=message,
                        from_=cfg.sms_from_number,
                        to=phone_number,
                    )
                except ImportError:
                    raise RuntimeError("مكتبة twilio غير مثبتة — شغّل: pip install twilio")

            log.status = "sent"
            log.save(update_fields=["status"])
            return True, None

        except (OSError, RuntimeError, ValueError):
            logger.error("فشل إرسال SMS")
            log.status = "failed"
            log.error_msg = _SMS_FAILURE_MESSAGE
            log.save(update_fields=["status", "error_msg"])
            return False, _SMS_FAILURE_MESSAGE

    # ── إشعار غياب الطالب لولي الأمر ─────────────────────────

    @staticmethod
    def notify_absence(absence_alert: AbsenceAlert, sent_by: CustomUser | None = None) -> list:
        """إشعار ولي الأمر بغياب ابنه المتكرر"""
        student = absence_alert.student
        school = absence_alert.school

        cfg = NotificationSettings.objects.filter(school=school).first()
        if cfg and not cfg.absence_email_enabled and not cfg.sms_enabled:
            return []

        # أولياء الأمور المرتبطون بالطالب
        links = ParentStudentLink.objects.filter(
            student=student, school=school, can_view_attendance=True
        ).select_related("student", "parent", "parent__notification_preferences")

        results: list = []

        for link in links:
            parent = link.parent
            ctx = {
                "student_name": student.full_name,
                "parent_name": parent.full_name,
                "absence_count": absence_alert.absence_count,
                "period_start": absence_alert.period_start,
                "period_end": absence_alert.period_end,
                "school_name": school.name,
                "relationship": link.get_relationship_display(),
            }

            # البريد الإلكتروني
            if parent.email and (not cfg or cfg.absence_email_enabled):
                subject = (
                    cfg.absence_email_subject if cfg else "تنبيه: غياب متكرر للطالب {student_name}"
                ).format(**ctx)

                body_text = render_to_string("notifications/email/absence_text.txt", ctx)
                body_html = render_to_string("notifications/email/absence_html.html", ctx)

                outcome = NotificationService.deliver_email(
                    user=parent,
                    school=school,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    student=student,
                    notif_type="absence_alert",
                    sent_by=sent_by,
                )
                results.append(_result("email", parent.email, outcome))

            # SMS
            if parent.get_phone_decrypted() and cfg and cfg.sms_enabled:
                sms_body = (
                    f"مدرسة {school.name}: الطالب {student.full_name} تغيّب "
                    f"{absence_alert.absence_count} مرات خلال الفترة "
                    f"{absence_alert.period_start} – {absence_alert.period_end}. "
                    f"يُرجى التواصل مع الإدارة."
                )
                outcome = NotificationService.deliver_sms(
                    user=parent,
                    school=school,
                    phone_number=parent.get_phone_decrypted(),
                    message=sms_body,
                    student=student,
                    notif_type="absence_alert",
                    sent_by=sent_by,
                )
                results.append(_result("sms", parent.get_phone_decrypted(), outcome))

        # تحديث حالة التنبيه
        if results and any(r["ok"] for r in results):
            absence_alert.status = "notified"
            absence_alert.save(update_fields=["status"])

        return results

    # ── إشعار رسوب الطالب لولي الأمر ─────────────────────────

    @staticmethod
    def notify_fail(
        student: CustomUser,
        school: School,
        failed_subjects: list,
        year: str | None = None,
        sent_by: CustomUser | None = None,
    ) -> list:
        """إشعار ولي الأمر بنتيجة الرسوب"""
        year = year or academic_year_for_school(school)
        cfg = NotificationSettings.objects.filter(school=school).first()
        if cfg and not cfg.fail_email_enabled and not cfg.sms_enabled:
            return []

        links = ParentStudentLink.objects.filter(
            student=student, school=school, can_view_grades=True
        ).select_related("student", "parent", "parent__notification_preferences")

        results: list = []

        for link in links:
            parent = link.parent
            ctx = {
                "student_name": student.full_name,
                "parent_name": parent.full_name,
                "failed_subjects": failed_subjects,
                "fail_count": len(failed_subjects),
                "year": year,
                "school_name": school.name,
                "relationship": link.get_relationship_display(),
            }

            if parent.email and (not cfg or cfg.fail_email_enabled):
                subject = (
                    cfg.fail_email_subject if cfg else "إشعار: نتيجة الطالب {student_name}"
                ).format(**ctx)

                body_text = render_to_string("notifications/email/fail_text.txt", ctx)
                body_html = render_to_string("notifications/email/fail_html.html", ctx)

                outcome = NotificationService.deliver_email(
                    user=parent,
                    school=school,
                    subject=subject,
                    body_text=body_text,
                    body_html=body_html,
                    student=student,
                    notif_type="fail_alert",
                    sent_by=sent_by,
                )
                results.append(_result("email", parent.email, outcome))

            if parent.get_phone_decrypted() and cfg and cfg.sms_enabled:
                subjects_str = "، ".join(failed_subjects[:3])
                sms_body = (
                    f"مدرسة {school.name}: الطالب {student.full_name} راسب في "
                    f"{len(failed_subjects)} مادة ({subjects_str}) للعام {year}. "
                    f"يُرجى التواصل مع الإدارة."
                )
                outcome = NotificationService.deliver_sms(
                    user=parent,
                    school=school,
                    phone_number=parent.get_phone_decrypted(),
                    message=sms_body,
                    student=student,
                    notif_type="fail_alert",
                    sent_by=sent_by,
                )
                results.append(_result("sms", parent.get_phone_decrypted(), outcome))

        return results

    # ── إرسال جماعي لكل التنبيهات المعلقة ────────────────────

    @staticmethod
    def send_pending_absence_alerts(school: School, sent_by: CustomUser | None = None) -> tuple:
        """إرسال كل تنبيهات الغياب المعلقة دفعةً واحدة"""
        from operations.models import AbsenceAlert

        alerts = AbsenceAlert.objects.filter(school=school, status="pending")
        total_sent = 0
        total_failed = 0
        total_deferred = 0
        for alert in alerts:
            results = NotificationService.notify_absence(alert, sent_by=sent_by)
            for r in results:
                if r["ok"]:
                    total_sent += 1
                    total_deferred += bool(r.get("deferred"))
                else:
                    total_failed += 1
        return SendCounts(total_sent, total_failed, total_deferred)

    @staticmethod
    def send_fail_alerts_for_year(
        school: School,
        year: str | None = None,
        sent_by: CustomUser | None = None,
    ) -> tuple:
        """إرسال إشعارات الرسوب لكل الطلاب الراسبين"""
        year = year or academic_year_for_school(school)
        from assessments.models import AnnualSubjectResult

        # الطلاب الراسبون في مادة أو أكثر
        fail_results = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year, status="fail"
        ).select_related("student", "setup__subject")

        # تجميع المواد الراسب فيها لكل طالب
        by_student: dict = {}
        for r in fail_results:
            sid = r.student_id
            if sid not in by_student:
                by_student[sid] = {"student": r.student, "subjects": []}
            by_student[sid]["subjects"].append(r.setup.subject.name_ar)

        total_sent = total_failed = total_deferred = 0
        for data in by_student.values():
            results = NotificationService.notify_fail(
                student=data["student"],
                school=school,
                failed_subjects=data["subjects"],
                year=year,
                sent_by=sent_by,
            )
            for r in results:
                if r["ok"]:
                    total_sent += 1
                    total_deferred += bool(r.get("deferred"))
                else:
                    total_failed += 1

        return SendCounts(total_sent, total_failed, total_deferred)

    @staticmethod
    def count_alert_recipients(school: School, year: str) -> dict:
        """كم وليَّ أمرٍ سيبلغه زرُّ الغياب وزرُّ الرسوب — استعلامان بلا حلقة.

        الأولياءُ لا التنبيهات: وليٌّ واحدٌ لأخوين يُشعَر مرّتين بحدثين لكنّه شخصٌ
        واحد. والشرطُ صلاحيةُ الرؤية نفسُها التي تفرضها `notify_absence`/`notify_fail`.
        """
        from assessments.models import AnnualSubjectResult
        from operations.models import AbsenceAlert

        absent_students = AbsenceAlert.objects.filter(school=school, status="pending").values(
            "student"
        )
        failing_students = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year, status="fail"
        ).values("student")

        return {
            "absence": ParentStudentLink.objects.filter(
                school=school, can_view_attendance=True, student__in=absent_students
            )
            .values("parent")
            .distinct()
            .count(),
            "fail": ParentStudentLink.objects.filter(
                school=school, can_view_grades=True, student__in=failing_students
            )
            .values("parent")
            .distinct()
            .count(),
        }

    @staticmethod
    def get_dashboard_stats(school: School, year: str) -> dict:
        """
        إحصائيات لوحة الإشعارات — 5 استعلامات في service layer.

        ✅ v5.4: ينقل جميع queries من notifications_dashboard view.

        Args:
            school: كائن المدرسة
            year: العام الدراسي

        Returns:
            dict يحتوي: total, sent, failed, total_pending,
                        channel_stats, daily_notifs,
                        pending_absence, failing_students
        """
        from datetime import timedelta

        from django.db.models import Count, Q
        from django.db.models.functions import TruncDate
        from django.utils import timezone

        from assessments.models import AnnualSubjectResult
        from operations.models import AbsenceAlert

        today = timezone.now().date()

        # aggregate واحد بدل 3 queries
        notif_stats = NotificationLog.objects.filter(school=school).aggregate(
            total=Count("id"),
            sent=Count("id", filter=Q(status="sent")),
            failed=Count("id", filter=Q(status="failed")),
        )
        total_pending = NotificationLog.objects.filter(school=school, status="pending").count()

        channel_stats = list(
            NotificationLog.objects.filter(school=school)
            .values("channel")
            .annotate(
                total=Count("id"),
                success=Count("id", filter=Q(status="sent")),
                failed=Count("id", filter=Q(status="failed")),
            )
            .order_by("-total")
        )

        two_weeks_ago = today - timedelta(days=14)
        daily_notifs = list(
            NotificationLog.objects.filter(school=school, sent_at__date__gte=two_weeks_ago)
            .values(day=TruncDate("sent_at"))
            .annotate(
                total=Count("id"),
                success=Count("id", filter=Q(status="sent")),
                failed=Count("id", filter=Q(status="failed")),
            )
            .order_by("day")
        )

        pending_absence = (
            # لا `select_related` قبل `count()`: لا كائناتٍ تُقرأ، وضمُّ الطالب
            # كلفةٌ بلا مقابل.
            AbsenceAlert.objects.filter(school=school, status="pending").count()
        )

        failing_students = (
            AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail")
            .values("student")
            .distinct()
            .count()
        )

        return {
            "total": notif_stats["total"],
            "sent": notif_stats["sent"],
            "failed": notif_stats["failed"],
            "total_sent": notif_stats["sent"],
            "total_failed": notif_stats["failed"],
            "total_pending": total_pending,
            "channel_stats": channel_stats,
            "daily_notifs": daily_notifs,
            "pending_absence": pending_absence,
            "pending_absence_count": pending_absence,
            "failing_students": failing_students,
        }


# ══════════════════════════════════════════════════════════════
# خدمة إشعار اختراق البيانات — PDPPL م.27 (مهلة 72 ساعة)
# ══════════════════════════════════════════════════════════════


class BreachNotificationService:
    """
    قانون حماية البيانات الشخصية 13/2016 — المادة 27:
    يجب إخطار المسؤول عن حماية البيانات خلال 72 ساعة من اكتشاف الاختراق.
    يوفر هذا الكلاس workflow موحداً للإبلاغ والتوثيق.
    """

    BREACH_TYPES = [
        ("unauthorized_access", "وصول غير مصرح"),
        ("data_leak", "تسريب بيانات"),
        ("ransomware", "برنامج فدية"),
        ("accidental_disclosure", "إفصاح عرضي"),
        ("other", "أخرى"),
    ]

    @staticmethod
    def report_breach(
        school: School,
        reported_by: CustomUser,
        breach_type: str,
        description: str,
        affected_count: int = 0,
        affected_data_types: list | None = None,
    ) -> dict:
        """
        توثيق حادثة اختراق وإرسال إشعار فوري للمسؤول.
        يُعيد dict يحتوي على: breach_id, deadline_72h, logged.
        """
        import uuid

        from core.models import AuditLog

        breach_id = str(uuid.uuid4())[:8].upper()
        discovered = timezone.now()
        deadline = discovered + timezone.timedelta(hours=72)

        details = {
            "breach_id": breach_id,
            "breach_type": breach_type,
            "description": description,
            "affected_count": affected_count,
            "affected_data_types": affected_data_types or [],
            "discovered_at": discovered.isoformat(),
            "notification_deadline": deadline.isoformat(),
            "reported_by": str(reported_by),
        }

        # تسجيل في AuditLog كدليل قانوني
        AuditLog.objects.create(
            school=school,
            user=reported_by,
            action="other",
            model_name="other",
            object_id=breach_id,
            object_repr=f"DATA BREACH — {breach_type}",
            changes=details,
        )

        # إرسال إشعار بريد للمسؤولين في المدرسة
        from core.models import Membership

        admins = Membership.objects.filter(
            school=school,
            is_active=True,
            role__name__in=["principal", "admin"],
        ).select_related("user")

        subject = "[تنبيه عاجل] حادثة بيانات #" + breach_id + " — " + school.name
        NL = "\n"
        body = (
            "تم الإبلاغ عن حادثة بيانات شخصية بتاريخ "
            + discovered.strftime("%Y-%m-%d %H:%M")
            + "."
            + NL
            + NL
            + "نوع الحادثة: "
            + breach_type
            + NL
            + "الوصف: "
            + description
            + NL
            + "عدد المتأثرين: "
            + str(affected_count)
            + NL
            + "أنواع البيانات: "
            + ", ".join(affected_data_types or [])
            + NL
            + NL
            + "⚠️ الموعد النهائي للإخطار القانوني (PDPPL م.27): "
            + deadline.strftime("%Y-%m-%d %H:%M")
            + NL
            + NL
            + "يجب إخطار المسؤول عن حماية البيانات خلال 72 ساعة من الاكتشاف."
        )

        for m in admins:
            if m.user.email:
                try:
                    NotificationService.send_email(
                        school=school,
                        recipient_email=m.user.email,
                        subject=subject,
                        body_text=body,
                        notif_type="custom",
                        sent_by=reported_by,
                    )
                except (OSError, RuntimeError, ValueError) as e:
                    logger.exception("فشل إرسال إشعار خرق البيانات عبر البريد الإلكتروني: %s", e)

        return {
            "breach_id": breach_id,
            "deadline_72h": deadline,
            "logged": True,
        }
