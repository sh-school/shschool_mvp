"""
خدمة كتابة سجل التدقيق (AuditLog).
تُستدعى من الـ views لتسجيل كل وصول لصندوق المطوّر أو تغيير حالة.
تلتقط IP بشكل آمن (X-Forwarded-For مع fallback إلى REMOTE_ADDR).
"""

from __future__ import annotations

from django.http import HttpRequest

from developer_feedback.models import AuditAction, AuditLog, DeveloperMessage


def _get_client_ip(request: HttpRequest) -> str | None:
    """يستخرج IP العميل بشكل آمن من الـ request."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        # أول IP في السلسلة هو العميل الأصلي
        ip = xff.split(",")[0].strip()
        if ip:
            return ip
    return request.META.get("REMOTE_ADDR")


def log_audit(
    request: HttpRequest,
    action: str,
    target_message: DeveloperMessage | None = None,
) -> AuditLog:
    """
    يكتب إدخالاً جديداً في AuditLog.

    Args:
        request: الـ HttpRequest الحالي (لاستخراج actor + IP)
        action: إحدى قيم AuditAction.choices
        target_message: الرسالة المستهدفة (اختياري)

    Returns:
        AuditLog instance المُنشأ
    """
    actor = request.user if request.user.is_authenticated else None
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        target_message=target_message,
        ip_address=_get_client_ip(request),
    )


def log_inbox_view(request: HttpRequest) -> AuditLog:
    """اختصار: تسجيل عرض قائمة Inbox."""
    return log_audit(request, AuditAction.VIEW_INBOX)


def log_message_view(request: HttpRequest, message: DeveloperMessage) -> AuditLog:
    """اختصار: تسجيل فتح رسالة معينة."""
    return log_audit(request, AuditAction.VIEW_MESSAGE, message)


def log_status_update(request: HttpRequest, message: DeveloperMessage) -> AuditLog:
    """اختصار: تسجيل تغيير حالة رسالة."""
    return log_audit(request, AuditAction.UPDATE_STATUS, message)


def log_message_delete(request: HttpRequest, message: DeveloperMessage) -> AuditLog:
    """اختصار: تسجيل حذف رسالة."""
    return log_audit(request, AuditAction.DELETE_MESSAGE, message)
