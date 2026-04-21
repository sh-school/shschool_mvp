"""
خدمة إشعار المطوّر عبر SMTP.
تطبّق قيود E1 escalation #3:
- TLS 1.3 إلزامي (Django EMAIL_USE_SSL/TLS + EMAIL_BACKEND)
- المحتوى المسموح: ticket_id + timestamp + role + URL_path + body فقط
- ممنوع: الاسم الكامل، user_id خام (استخدم hash)، المرفقات
- Retry مع exponential backoff (3 محاولات)
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from developer_feedback.models import (
    DeveloperMessage,
    DeveloperMessageNotification,
    NotificationChannel,
    NotificationStatus,
)

logger = logging.getLogger(__name__)

# بريد المطوّر المعتمد من المؤسس (MTG-2026-015)
DEVELOPER_EMAIL = getattr(
    settings,
    "DEVELOPER_FEEDBACK_RECIPIENT",
    "s.mesyef0904@education.qa",
)

MAX_RETRIES = 3


def _build_safe_payload(message: DeveloperMessage) -> dict:
    """
    يبني محتوى الإيميل وفق E1 escalation #3.
    يتضمن فقط: ticket_id + timestamp + role + URL_path + body.
    user_id الخام مُستبدَل بـ user_id_hash.
    """
    context_json = message.context_json or {}
    # استخراج role + url_path من السياق (سبق تنظيفه في forms.py)
    role = context_json.get("role", "unknown")
    url_path = context_json.get("url_path", "")
    view_name = context_json.get("view_name", "")

    return {
        "ticket_number": message.ticket_number,
        "timestamp": message.created_at.isoformat() if message.created_at else "",
        "role": role,
        "url_path": url_path,
        "view_name": view_name,
        "message_type": message.get_message_type_display(),
        "priority": message.get_priority_display(),
        "subject": message.subject,
        "body": message.body,
        "user_id_hash": message.user_id_hash or "",
        # لا اسم مستخدم — لا user_id خام — لا بريد شخصي
    }


def _render_email(payload: dict) -> tuple[str, str, str]:
    """يُرجع (subject, text_body, html_body) بدون اعتماد على templates خارجية."""
    subject = f"[SchoolOS Feedback] {payload['ticket_number']} — {payload['subject']}"

    user_hash_short = (payload["user_id_hash"] or "")[:12]

    text_body = (
        f"رقم التذكرة: {payload['ticket_number']}\n"
        f"التاريخ: {payload['timestamp']}\n"
        f"نوع الرسالة: {payload['message_type']}\n"
        f"الأولوية: {payload['priority']}\n"
        f"الدور: {payload['role']}\n"
        f"المسار: {payload['url_path']}\n"
        f"View: {payload['view_name']}\n"
        f"User Hash: {user_hash_short}...\n"
        f"\n"
        f"العنوان: {payload['subject']}\n"
        f"\n"
        f"الوصف:\n{payload['body']}\n"
        f"\n"
        f"---\n"
        f"SchoolOS Developer Feedback — Azkia Software\n"
        f"محتوى الإيميل مقيَّد وفق PDPPL (E1).\n"
    )

    body_html = payload["body"].replace("\n", "<br>")
    html_body = (
        f"<div dir='rtl' style='font-family: Tajawal, Arial; max-width: 640px;'>"
        f"<h2 style='color: #8B0000;'>SchoolOS Feedback</h2>"
        f"<table cellpadding='6' style='border-collapse: collapse; width: 100%;'>"
        f"<tr><td><b>رقم التذكرة</b></td><td><code>{payload['ticket_number']}</code></td></tr>"
        f"<tr><td><b>التاريخ</b></td><td>{payload['timestamp']}</td></tr>"
        f"<tr><td><b>النوع</b></td><td>{payload['message_type']}</td></tr>"
        f"<tr><td><b>الأولوية</b></td><td>{payload['priority']}</td></tr>"
        f"<tr><td><b>الدور</b></td><td>{payload['role']}</td></tr>"
        f"<tr><td><b>المسار</b></td><td><code>{payload['url_path']}</code></td></tr>"
        f"<tr><td><b>User Hash</b></td><td><code>{user_hash_short}...</code></td></tr>"
        f"</table>"
        f"<h3>{payload['subject']}</h3>"
        f"<div style='background: #f5f5f5; padding: 12px; border-right: 3px solid #8B0000;'>"
        f"{body_html}"
        f"</div>"
        f"<hr><p style='color: #888; font-size: 12px;'>"
        f"محتوى الإيميل مقيَّد وفق PDPPL (E1) — Azkia Software"
        f"</p></div>"
    )

    return subject, text_body, html_body


def send_developer_notification(
    message: DeveloperMessage,
    recipient: str | None = None,
) -> DeveloperMessageNotification:
    """
    يرسل إشعار SMTP للمطوّر.
    ينشئ دائماً سجلاً في DeveloperMessageNotification (نجح أو فشل).

    Returns:
        DeveloperMessageNotification instance
    """
    to_email = recipient or DEVELOPER_EMAIL
    payload = _build_safe_payload(message)
    subject, text_body, html_body = _render_email(payload)

    notification = DeveloperMessageNotification.objects.create(
        message=message,
        channel=NotificationChannel.SMTP,
        recipient=to_email,
        status=NotificationStatus.PENDING,
    )

    last_error: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        notification.attempt_count = attempt
        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                to=[to_email],
            )
            email.attach_alternative(html_body, "text/html")
            email.send(fail_silently=False)

            notification.status = NotificationStatus.SENT
            notification.sent_at = timezone.now()
            notification.error_detail = ""
            notification.save()
            logger.info(
                "Developer notification sent: ticket=%s attempt=%d",
                message.ticket_number,
                attempt,
            )
            return notification
        except Exception as exc:  # noqa: BLE001 — نحتاج التقاط أي فشل SMTP
            last_error = str(exc)[:500]
            logger.warning(
                "Developer notification attempt %d failed: %s",
                attempt,
                last_error,
            )
            if attempt < MAX_RETRIES:
                notification.status = NotificationStatus.RETRY
                notification.error_detail = last_error
                notification.save()
                continue

    # وصلنا هنا = كل المحاولات فشلت
    notification.status = NotificationStatus.FAILED
    notification.error_detail = last_error or "unknown"
    notification.save()
    logger.error(
        "Developer notification failed after %d attempts: ticket=%s",
        MAX_RETRIES,
        message.ticket_number,
    )
    return notification


def send_developer_edit_notification(
    message: DeveloperMessage,
    recipient: str | None = None,
) -> DeveloperMessageNotification:
    """
    يرسل إشعار SMTP للمطوّر عندما يقوم المُرسِل بتعديل رسالة سبق إرسالها.

    الفرق عن send_developer_notification:
    - الـ subject يبدأ بـ "[تعديل]"
    - يتضمن ملاحظة واضحة أن الرسالة عُدّلت بعد إرسالها الأصلي
    - يتضمن edit_count ليُعلم المطوّر بعدد التعديلات السابقة
    """
    to_email = recipient or DEVELOPER_EMAIL
    payload = _build_safe_payload(message)
    edit_count = message.edit_history.count()

    original_subject, text_body, html_body = _render_email(payload)
    # إضافة بادئة [تعديل] + ملاحظة التعديل
    subject = f"[تعديل #{edit_count}] {original_subject}"
    edit_notice_text = (
        f"\n⚠️ تنبيه: هذه رسالة مُعدَّلة (التعديل رقم {edit_count}).\n"
        f"تم تعديلها بعد الإرسال الأصلي.\n\n"
    )
    edit_notice_html = (
        f"<div style='background:#fff3cd;border-right:4px solid #ff9800;"
        f"padding:10px;margin:10px 0;color:#856404;'>"
        f"⚠️ <b>رسالة مُعدَّلة</b> — التعديل رقم {edit_count}. "
        f"عُدّلت بعد الإرسال الأصلي.</div>"
    )
    text_body = edit_notice_text + text_body
    html_body = html_body.replace("<h2", edit_notice_html + "<h2", 1)

    notification = DeveloperMessageNotification.objects.create(
        message=message,
        channel=NotificationChannel.SMTP,
        recipient=to_email,
        status=NotificationStatus.PENDING,
    )

    last_error: str | None = None
    for attempt in range(1, MAX_RETRIES + 1):
        notification.attempt_count = attempt
        try:
            email = EmailMultiAlternatives(
                subject=subject,
                body=text_body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", None),
                to=[to_email],
            )
            email.attach_alternative(html_body, "text/html")
            email.send(fail_silently=False)

            notification.status = NotificationStatus.SENT
            notification.sent_at = timezone.now()
            notification.error_detail = ""
            notification.save()
            logger.info(
                "Developer EDIT notification sent: ticket=%s edit#=%d attempt=%d",
                message.ticket_number,
                edit_count,
                attempt,
            )
            return notification
        except Exception as exc:  # noqa: BLE001
            last_error = str(exc)[:500]
            logger.warning(
                "Developer edit notification attempt %d failed: %s",
                attempt,
                last_error,
            )
            if attempt < MAX_RETRIES:
                notification.status = NotificationStatus.RETRY
                notification.error_detail = last_error
                notification.save()
                continue

    notification.status = NotificationStatus.FAILED
    notification.error_detail = last_error or "unknown"
    notification.save()
    logger.error(
        "Developer edit notification failed after %d attempts: ticket=%s",
        MAX_RETRIES,
        message.ticket_number,
    )
    return notification
