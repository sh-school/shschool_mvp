"""
core/htmx_utils.py — SchoolOS v5.1
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
أدوات HTMX مساعدة للـ views

الاستخدام:
    from core.htmx_utils import htmx_toast, htmx_redirect, htmx_response

    # إعادة توجيه مع toast
    return htmx_redirect("/students/", msg="تم الحفظ", msg_type="success")

    # استجابة HTML مع toast
    return htmx_toast(render(...), msg="تم الحذف")

    # استجابة جزئية مع refresh للصفحة
    return htmx_refresh()
"""

import json

from django.http import HttpResponse


def htmx_toast(
    response_or_html: HttpResponse | str,
    msg: str,
    msg_type: str = "success",
) -> HttpResponse:
    """
    يضيف HX-Trigger header لإطلاق toast في المتصفح.

    Args:
        response_or_html: HttpResponse جاهز أو HTML string
        msg: نص الرسالة
        msg_type: success | danger | info | warning

    Returns:
        HttpResponse مع HX-Trigger header
    """
    if isinstance(response_or_html, str):
        r = HttpResponse(response_or_html)
    else:
        r = response_or_html

    r["HX-Trigger"] = json.dumps({"showToast": {"msg": msg, "type": msg_type}})
    return r


def htmx_redirect(
    url: str,
    msg: str = "",
    msg_type: str = "success",
) -> HttpResponse:
    """
    إعادة توجيه HTMX مع toast اختياري.
    تُستخدم بدلاً من HttpResponseRedirect في HTMX requests.

    Args:
        url: المسار المراد التوجيه إليه
        msg: نص toast (اختياري)
        msg_type: success | danger | info | warning

    Returns:
        204 No Content مع HX-Redirect + HX-Trigger headers
    """
    r = HttpResponse(status=204)
    r["HX-Redirect"] = url

    if msg:
        r["HX-Trigger"] = json.dumps({"showToast": {"msg": msg, "type": msg_type}})

    return r


def htmx_refresh(msg: str = "", msg_type: str = "success") -> HttpResponse:
    """
    يُحدِّث الصفحة الحالية (HX-Refresh) مع toast اختياري.
    """
    r = HttpResponse(status=204)
    r["HX-Refresh"] = "true"

    if msg:
        r["HX-Trigger"] = json.dumps({"showToast": {"msg": msg, "type": msg_type}})

    return r


def htmx_trigger(event: str, detail: dict = None) -> dict:
    """
    بناء قيمة HX-Trigger لحدث مخصص.

    مثال:
        response["HX-Trigger"] = json.dumps(htmx_trigger("refreshNotifs"))
    """
    if detail:
        return {event: detail}
    return {event: True}


def is_htmx(request) -> bool:
    """
    تحقق بسيط إذا كان الطلب من HTMX.
    ملاحظة: يُفضَّل استخدام request.htmx (من django-htmx middleware).
    """
    return request.headers.get("HX-Request") == "true"


def htmx_or_full(request, partial_template: str, full_template: str, context: dict) -> HttpResponse:
    """
    يُرجع partial_template إذا كان الطلب HTMX، وإلا full_template.

    مثال:
        return htmx_or_full(
            request,
            "students/partials/list_rows.html",
            "students/list.html",
            {"students": qs}
        )
    """
    from django.shortcuts import render

    template = partial_template if request.htmx else full_template
    return render(request, template, context)
