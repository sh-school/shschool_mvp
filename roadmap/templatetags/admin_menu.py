"""وسمُ القائمة الأفقيّة للوحة الإدارة — `{% admin_nav %}` في `templates/admin/base_site.html`."""

from django import template

from roadmap.admin_menu import build_menu

register = template.Library()


@register.inclusion_tag("admin/_nav.html", takes_context=True)
def admin_nav(context):
    request = context.get("request")
    path = request.path if request is not None else ""
    return {"groups": build_menu(context.get("available_apps") or [], path)}
