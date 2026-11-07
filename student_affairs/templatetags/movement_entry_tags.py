"""[STUDENT_AFFAIRS] W-20261107-020: وسمُ نموذج تسجيل التحرّك في شاشة «تحركات الطلبة».

يحسب سياقَ النموذج خارج دالّة العرض حفاظاً على سقفها (`tests/test_layering.py`).
"""

from django import template

from student_affairs.movement_entry import entry_context
from wings.scope import student_scope_for

register = template.Library()


@register.inclusion_tag("student_affairs/_movement_entry.html", takes_context=True)
def movement_entry_form(context):
    request = context["request"]
    ctx = entry_context(request, student_scope_for(request))
    ctx["selected_date"] = context["selected_date"].isoformat()
    ctx["csrf_token"] = context.get("csrf_token", "")
    return ctx
