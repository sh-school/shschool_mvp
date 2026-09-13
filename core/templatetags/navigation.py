"""``{% if request.user|can_open:"quality:dashboard" %}`` — الرابطُ يُعرض لمن يفتحه وحدَه."""

from django import template

from core.navigation import can_open as _can_open

register = template.Library()


@register.filter
def can_open(user, url_name):
    return _can_open(user, url_name)
