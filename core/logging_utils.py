"""
core/logging_utils.py
أدوات التسجيل المنظم — Structured Logging لـ SchoolOS
"""

import logging
import uuid

from django.utils import timezone


class CorrelationIdFilter(logging.Filter):
    """
    Filter يضيف correlation_id لكل سجل — يربط كل الأحداث بطلب واحد.

    الاستخدام في LOGGING settings:
        "filters": {
            "correlation_id": {"()": "core.logging_utils.CorrelationIdFilter"},
        }
    """

    def filter(self, record):
        if not hasattr(record, "correlation_id"):
            record.correlation_id = getattr(record, "correlation_id", "-")
        return True


def get_logger(name: str) -> logging.Logger:
    """
    إنشاء logger موحد لجميع وحدات SchoolOS.

    الاستخدام:
        from core.logging_utils import get_logger
        logger = get_logger(__name__)
        logger.info("عملية ناجحة", extra={"user_id": user.id, "action": "login"})
    """
    return logging.getLogger(name)


def log_action(
    logger: logging.Logger,
    action: str,
    *,
    user=None,
    model: str = "",
    object_id: str = "",
    details: str = "",
    level: int = logging.INFO,
):
    """
    تسجيل إجراء بتنسيق موحد.

    الاستخدام:
        log_action(logger, "grade_entry", user=request.user, model="Assessment", object_id=str(obj.id))
    """
    extra = {
        "action": action,
        "user_id": str(user.id) if user else "-",
        "user_name": getattr(user, "full_name", "-"),
        "model": model,
        "object_id": str(object_id),
        "timestamp": timezone.now().isoformat(),
    }
    logger.log(level, "%s | %s | %s | %s", action, extra["user_name"], model, details, extra=extra)
