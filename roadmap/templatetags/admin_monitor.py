"""بطاقاتُ مراقبة المطوّر في الصفحة الرئيسيّة للإدارة — `{% dev_cards %}` في `templates/admin/index.html`.

منفصلةٌ عن وسوم القائمة (`core/templatetags/admin_menu.py`) لأنّها تقرأ `roadmap.admin_monitor`.
"""

from django import template

from core.developer_access import is_platform_developer
from roadmap.admin_monitor import build_cards

register = template.Library()


@register.inclusion_tag("admin/_dev_cards.html", takes_context=True)
def dev_cards(context):
    """بطاقاتُ المراقبة للمطوّر وحدَه — لغيره قائمةٌ فارغةٌ فلا شيءَ يُرسَم."""
    request = context.get("request")
    user = getattr(request, "user", None)
    return {"cards": build_cards() if is_platform_developer(user) else []}
