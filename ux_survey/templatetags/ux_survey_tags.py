from django import template

from core.capabilities import has_capability
from ux_survey import services

register = template.Library()


@register.inclusion_tag("ux_survey/prompt.html", takes_context=True)
def survey_prompt(context):
    """بطاقةُ الدعوة: تظهر للموظف المؤهَّل بعد مهمةٍ أُنجزت (رسالةُ نجاحٍ في الصفحة) لا قبلها."""
    request = context.get("request")
    user = getattr(request, "user", None)
    done = any(getattr(m, "level_tag", "") == "success" for m in context.get("messages") or [])
    show = bool(
        done
        and user is not None
        and user.is_authenticated
        and has_capability(user, services.RESPOND)
        and services.is_eligible(user)
    )
    return {"show": show, "request": request}
