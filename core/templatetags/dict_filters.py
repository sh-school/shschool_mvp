import logging
from decimal import Decimal

from django import template

register = template.Library()

logger = logging.getLogger(__name__)


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def mul(value, arg):
    try:
        return Decimal(str(value)) * Decimal(str(arg))
    except Exception:
        logger.exception("فشل فلتر mul: value=%r, arg=%r", value, arg)
        return 0


@register.filter
def sub(value, arg):
    try:
        return Decimal(str(value)) - Decimal(str(arg))
    except Exception:
        logger.exception("فشل فلتر sub: value=%r, arg=%r", value, arg)
        return 0


@register.filter
def pct(value, total):
    try:
        v, t = float(value), float(total)
        return round(v / t * 100) if t else 0
    except Exception:
        logger.exception("فشل فلتر pct: value=%r, total=%r", value, total)
        return 0


@register.filter
def grade_color_class(value):
    try:
        t = float(value)
        if t >= 80:
            return "text-green-700"
        if t >= 60:
            return "text-blue-700"
        if t >= 50:
            return "text-amber-600"
        return "text-red-600"
    except Exception:
        logger.exception("فشل فلتر grade_color_class: value=%r", value)
        return "text-gray-400"
