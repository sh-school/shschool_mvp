"""وسمُ القائمة الأفقيّة للوحة الإدارة — `{% admin_nav %}` في `templates/admin/base_site.html`.

بنيةُ الإدارة العامّة في `core` (OWN-24)؛ وبطاقاتُ مراقبة المطوّر (`{% dev_cards %}`) في
`roadmap/templatetags/admin_monitor.py` لأنّها تقرأ `roadmap` و`core` لا يستورد ما تحته.
"""

import re
from typing import Any

from django import template

from core.admin_menu import APP_LABELS, build_menu, search_index

register = template.Library()


@register.inclusion_tag("admin/_nav.html", takes_context=True)
def admin_nav(context: Any) -> dict[str, Any]:
    request = context.get("request")
    path = request.path if request is not None else ""
    groups = build_menu(context.get("available_apps") or [], path)
    return {"groups": groups, "search_index": search_index(groups)}


_LONG_NUMBER = re.compile(r"\d{8,}")


@register.filter
def hide_ids(value: object) -> str:
    """يستر كلَّ رقمٍ من ثمانيةِ أرقامٍ فأكثر (رقمٌ شخصيّ أو وظيفيّ) في نصّ السجلّ — PDPPL."""
    return _LONG_NUMBER.sub("••••", str(value))


@register.filter
def app_label(app_label_key: str, default_name: str) -> str:
    """اسمُ تطبيقٍ عربيّاً في app_list.html — لتطبيقات الطرف الثالث المسجَّلة في APP_LABELS."""
    return APP_LABELS.get(app_label_key, default_name)
