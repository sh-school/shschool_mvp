"""تبديلُ الدور العامل — صفحةُ `/auth/choose-role/` (W-20261019-008).

كان رابطُ «تبديل الدور» في القائمة يشير إلى مسارٍ لا عرضَ له (404)، فلا يبلغ موظّفٌ بعضويّتين
عضويّتَه الثانية. والعرضُ هنا يسرد عضويّاتِه **النشطةَ** وحدَها، ويحفظ اختيارَه في الجلسة، ويرفض
عضويّةَ غيره أو غير النشطة. ولا يغيّر دورَ أحدٍ تلقائيّاً ولا يمنح قدرةً.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from core.active_role import SESSION_KEY


@never_cache
@login_required
@require_http_methods(["GET", "POST"])
def choose_role(request):
    memberships = request.user.active_memberships
    if request.method == "POST":
        picked = request.POST.get("membership_id", "")
        chosen = next((m for m in memberships if str(m.pk) == picked), None)
        if chosen is None:
            messages.error(request, "العضويّة المختارة غير متاحة لك.")
            return redirect("choose_role")
        request.session[SESSION_KEY] = str(chosen.pk)
        messages.success(request, f"تمّ التبديل إلى: {chosen.role.get_name_display()}")
        return redirect("dashboard")
    current = request.user.active_membership
    return render(
        request,
        "auth/choose_role.html",
        {"memberships": memberships, "current_id": current.pk if current else None},
    )
