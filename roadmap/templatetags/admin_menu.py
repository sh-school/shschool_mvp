"""وسمُ القائمة الأفقيّة للوحة الإدارة — `{% admin_nav %}` في `templates/admin/base_site.html`."""

import re

from django import template

from core.developer_access import is_platform_developer
from roadmap.admin_menu import APP_LABELS, build_menu, search_index
from roadmap.admin_monitor import build_cards

register = template.Library()


@register.inclusion_tag("admin/_nav.html", takes_context=True)
def admin_nav(context):
    request = context.get("request")
    path = request.path if request is not None else ""
    groups = build_menu(context.get("available_apps") or [], path)
    return {"groups": groups, "search_index": search_index(groups)}


@register.inclusion_tag("admin/_dev_cards.html", takes_context=True)
def dev_cards(context):
    """بطاقاتُ المراقبة للمطوّر وحدَه — لغيره قائمةٌ فارغةٌ فلا شيءَ يُرسَم."""
    request = context.get("request")
    user = getattr(request, "user", None)
    return {"cards": build_cards() if is_platform_developer(user) else []}


_LONG_NUMBER = re.compile(r"\d{8,}")


@register.filter
def hide_ids(value):
    """يستر كلَّ رقمٍ من ثمانيةِ أرقامٍ فأكثر (رقمٌ شخصيّ أو وظيفيّ) في نصّ السجلّ — PDPPL."""
    return _LONG_NUMBER.sub("••••", str(value))


@register.filter
def app_label(app_label_key, default_name):
    """اسمُ تطبيقٍ عربيّاً في app_list.html — لتطبيقات الطرف الثالث المسجَّلة في APP_LABELS."""
    return APP_LABELS.get(app_label_key, default_name)
