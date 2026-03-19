"""
notifications/services.py
محرك الإشعارات — بريد إلكتروني + SMS
"""
import django.core.mail
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone

from .models import NotificationLog, NotificationSettings
from core.models import ParentStudentLink


class NotificationService:

    # ── إرسال بريد إلكتروني ──────────────────────────────────

    @staticmethod
    def send_email(school, recipient_email, subject, body_text, body_html=None,
                   student=None, notif_type="custom", sent_by=None):
        """إرسال بريد إلكتروني وتسجيله"""
        log = NotificationLog.objects.create(
            school     = school,
            student    = student,
            recipient  = recipient_email,
            channel    = "email",
            notif_type = notif_type,
            subject    = subject,
            body       = body_text,
            status     = "pending",
            sent_by    = sent_by,
        )

        try:
            cfg = NotificationSettings.objects.filter(school=school).first()
            from_name = cfg.from_name if cfg else school.name
            from_email = getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@schoolos.qa")

            if body_html:
                msg = EmailMultiAlternatives(
                    subject   = subject,
                    body      = body_text,
                    from_email= f"{from_name} <{from_email}>",
                    to        = [recipient_email],
                )
                msg.attach_alternative(body_html, "text/html")
                if cfg and cfg.reply_to:
                    msg.reply_to = [cfg.reply_to]
                msg.send()
            else:
                django.core.mail.send_mail(
                    subject      = subject,
                    message      = body_text,
                    from_email   = f"{from_name} <{from_email}>",
                    recipient_list=[recipient_email],
                    fail_silently= False,
                )

            log.status  = "sent"
            log.save(update_fields=["status"])
            return True, None

        except Exception as e:
            log.status    = "failed"
            log.error_msg = str(e)
            log.save(update_fields=["status", "error_msg"])
            return False, str(e)

    # ── إرسال SMS ────────────────────────────────────────────

    @staticmethod
    def send_sms(school, phone_number, message, student=None, notif_type="custom", sent_by=None):
        """إرسال SMS عبر Twilio"""
        log = NotificationLog.objects.create(
            school     = school,
            student    = student,
            recipient  = phone_number,
            channel    = "sms",
            notif_type = notif_type,
            subject    = "",
            body       = message,
            status     = "pending",
            sent_by    = sent_by,
        )

        try:
            cfg = NotificationSettings.objects.filter(school=school).first()
            if not cfg or not cfg.sms_enabled:
                log.status    = "failed"
                log.error_msg = "SMS معطّل في الإعدادات"
                log.save(update_fields=["status", "error_msg"])
                return False, "SMS معطّل"

            if cfg.sms_provider == "twilio":
                try:
                    from twilio.rest import Client
                    client = Client(cfg.twilio_account_sid, cfg.twilio_auth_token)
                    client.messages.create(
                        body = message,
                        from_= cfg.sms_from_number,
                        to   = phone_number,
                    )
                except ImportError:
                    raise RuntimeError("مكتبة twilio غير مثبتة — شغّل: pip install twilio")

            log.status = "sent"
            log.save(update_fields=["status"])
            return True, None

        except Exception as e:
            log.status    = "failed"
            log.error_msg = str(e)
            log.save(update_fields=["status", "error_msg"])
            return False, str(e)

    # ── إشعار غياب الطالب لولي الأمر ─────────────────────────

    @staticmethod
    def notify_absence(absence_alert, sent_by=None):
        """إشعار ولي الأمر بغياب ابنه المتكرر"""
        student = absence_alert.student
        school  = absence_alert.school

        cfg = NotificationSettings.objects.filter(school=school).first()
        if cfg and not cfg.absence_email_enabled and not cfg.sms_enabled:
            return []

        # أولياء الأمور المرتبطون بالطالب
        links = ParentStudentLink.objects.filter(
            student=student, school=school, can_view_attendance=True
        ).select_related("parent")

        results = []

        for link in links:
            parent = link.parent
            ctx = {
                "student_name":   student.full_name,
                "parent_name":    parent.full_name,
                "absence_count":  absence_alert.absence_count,
                "period_start":   absence_alert.period_start,
                "period_end":     absence_alert.period_end,
                "school_name":    school.name,
                "relationship":   link.get_relationship_display(),
            }

            # البريد الإلكتروني
            if parent.email and (not cfg or cfg.absence_email_enabled):
                subject = (cfg.absence_email_subject if cfg else
                           "تنبيه: غياب متكرر للطالب {student_name}"
                           ).format(**ctx)

                body_text = render_to_string("notifications/email/absence_text.txt", ctx)
                body_html = render_to_string("notifications/email/absence_html.html", ctx)

                ok, err = NotificationService.send_email(
                    school       = school,
                    recipient_email = parent.email,
                    subject      = subject,
                    body_text    = body_text,
                    body_html    = body_html,
                    student      = student,
                    notif_type   = "absence_alert",
                    sent_by      = sent_by,
                )
                results.append({"channel": "email", "recipient": parent.email, "ok": ok, "error": err})

            # SMS
            if parent.phone and cfg and cfg.sms_enabled:
                sms_body = (
                    f"مدرسة {school.name}: الطالب {student.full_name} تغيّب "
                    f"{absence_alert.absence_count} مرات خلال الفترة "
                    f"{absence_alert.period_start} – {absence_alert.period_end}. "
                    f"يُرجى التواصل مع الإدارة."
                )
                ok, err = NotificationService.send_sms(
                    school       = school,
                    phone_number = parent.phone,
                    message      = sms_body,
                    student      = student,
                    notif_type   = "absence_alert",
                    sent_by      = sent_by,
                )
                results.append({"channel": "sms", "recipient": parent.phone, "ok": ok, "error": err})

        # تحديث حالة التنبيه
        if results and any(r["ok"] for r in results):
            absence_alert.status = "notified"
            absence_alert.save(update_fields=["status"])

        return results

    # ── إشعار رسوب الطالب لولي الأمر ─────────────────────────

    @staticmethod
    def notify_fail(student, school, failed_subjects, year="2025-2026", sent_by=None):
        """إشعار ولي الأمر بنتيجة الرسوب"""
        cfg = NotificationSettings.objects.filter(school=school).first()
        if cfg and not cfg.fail_email_enabled and not cfg.sms_enabled:
            return []

        links = ParentStudentLink.objects.filter(
            student=student, school=school, can_view_grades=True
        ).select_related("parent")

        results = []

        for link in links:
            parent = link.parent
            ctx = {
                "student_name":    student.full_name,
                "parent_name":     parent.full_name,
                "failed_subjects": failed_subjects,
                "fail_count":      len(failed_subjects),
                "year":            year,
                "school_name":     school.name,
                "relationship":    link.get_relationship_display(),
            }

            if parent.email and (not cfg or cfg.fail_email_enabled):
                subject = (cfg.fail_email_subject if cfg else
                           "إشعار: نتيجة الطالب {student_name}"
                           ).format(**ctx)

                body_text = render_to_string("notifications/email/fail_text.txt", ctx)
                body_html = render_to_string("notifications/email/fail_html.html", ctx)

                ok, err = NotificationService.send_email(
                    school          = school,
                    recipient_email = parent.email,
                    subject         = subject,
                    body_text       = body_text,
                    body_html       = body_html,
                    student         = student,
                    notif_type      = "fail_alert",
                    sent_by         = sent_by,
                )
                results.append({"channel": "email", "recipient": parent.email, "ok": ok, "error": err})

            if parent.phone and cfg and cfg.sms_enabled:
                subjects_str = "، ".join(failed_subjects[:3])
                sms_body = (
                    f"مدرسة {school.name}: الطالب {student.full_name} راسب في "
                    f"{len(failed_subjects)} مادة ({subjects_str}) للعام {year}. "
                    f"يُرجى التواصل مع الإدارة."
                )
                ok, err = NotificationService.send_sms(
                    school       = school,
                    phone_number = parent.phone,
                    message      = sms_body,
                    student      = student,
                    notif_type   = "fail_alert",
                    sent_by      = sent_by,
                )
                results.append({"channel": "sms", "recipient": parent.phone, "ok": ok, "error": err})

        return results

    # ── إرسال جماعي لكل التنبيهات المعلقة ────────────────────

    @staticmethod
    def send_pending_absence_alerts(school, sent_by=None):
        """إرسال كل تنبيهات الغياب المعلقة دفعةً واحدة"""
        from operations.models import AbsenceAlert
        alerts = AbsenceAlert.objects.filter(school=school, status="pending")
        total_sent = 0
        total_failed = 0
        for alert in alerts:
            results = NotificationService.notify_absence(alert, sent_by=sent_by)
            for r in results:
                if r["ok"]:
                    total_sent += 1
                else:
                    total_failed += 1
        return total_sent, total_failed

    @staticmethod
    def send_fail_alerts_for_year(school, year="2025-2026", sent_by=None):
        """إرسال إشعارات الرسوب لكل الطلاب الراسبين"""
        from assessments.models import AnnualSubjectResult
        # الطلاب الراسبون في مادة أو أكثر
        fail_results = AnnualSubjectResult.objects.filter(
            school=school, academic_year=year, status="fail"
        ).select_related("student", "setup__subject")

        # تجميع المواد الراسب فيها لكل طالب
        by_student = {}
        for r in fail_results:
            sid = r.student_id
            if sid not in by_student:
                by_student[sid] = {"student": r.student, "subjects": []}
            by_student[sid]["subjects"].append(r.setup.subject.name_ar)

        total_sent = total_failed = 0
        for data in by_student.values():
            results = NotificationService.notify_fail(
                student          = data["student"],
                school           = school,
                failed_subjects  = data["subjects"],
                year             = year,
                sent_by          = sent_by,
            )
            for r in results:
                if r["ok"]:
                    total_sent += 1
                else:
                    total_failed += 1

        return total_sent, total_failed
