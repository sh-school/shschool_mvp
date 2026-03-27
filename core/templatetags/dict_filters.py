import logging
from decimal import Decimal, InvalidOperation

from django import template

register = template.Library()

logger = logging.getLogger(__name__)


@register.filter
def get_item(dictionary, key):
    if isinstance(dictionary, dict):
        return dictionary.get(key)
    return None


@register.filter
def dictkey(dictionary, key):
    """Alias for get_item — dict[key] with int coercion for grid lookups."""
    if isinstance(dictionary, dict):
        result = dictionary.get(key)
        if result is None:
            try:
                result = dictionary.get(int(key))
            except (TypeError, ValueError):
                pass
        return result
    return None


@register.filter
def mul(value, arg):
    try:
        return Decimal(str(value)) * Decimal(str(arg))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        logger.exception("فشل فلتر mul: value=%r, arg=%r", value, arg)
        return 0


@register.filter
def sub(value, arg):
    try:
        return Decimal(str(value)) - Decimal(str(arg))
    except (InvalidOperation, TypeError, ValueError, ArithmeticError):
        logger.exception("فشل فلتر sub: value=%r, arg=%r", value, arg)
        return 0


@register.filter
def pct(value, total):
    try:
        v, t = float(value), float(total)
        return round(v / t * 100) if t else 0
    except (TypeError, ValueError, ZeroDivisionError):
        logger.exception("فشل فلتر pct: value=%r, total=%r", value, total)
        return 0


@register.filter
def grade_color_class(value):
    try:
        t = float(value)
        if t >= 80:
            return "text-green-700"
        if t >= 65:
            return "text-blue-700"
        if t >= 60:
            return "text-amber-600"
        return "text-red-600"
    except (TypeError, ValueError):
        logger.exception("فشل فلتر grade_color_class: value=%r", value)
        return "text-gray-400"
