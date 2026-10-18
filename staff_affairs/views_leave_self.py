"""طلبُ الإجازة للموظّف نفسِه (قرارُ المالك D-301م، W-20261009-023).

المسارُ القديم ``leave/request/`` يقدّم نيابةً عن موظّفٍ يختاره من يملك «إدارةَ شؤون الموظّفين»،
فلا يصله إلّا خمسةُ أدوار. وهذا المسارُ للكادر كلِّه (``staff_affairs.own_leave``) والموظّفُ فيه
الحسابُ الداخلُ وحدَه: لا حقلَ ``staff_id`` في النموذج، وما يُرسَل باسمه يُتجاهل.
القواعدُ كلُّها في ``LeaveService.create_leave_request`` كما هي.
"""

from __future__ import annotations

from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from core.capabilities import capability_required
from core.middleware import SchoolRequest
from core.models.user import CustomUser

from .forms import LeaveRequestSelfForm
from .selectors import has_active_membership, own_recent_leaves
from .services import LeaveService

#: عددُ طلباته الأخيرة المعروضة تحت النموذج — ليرى حالةَ ما قدّمه دون صفحةِ إدارةٍ لا يملكها.
RECENT_LIMIT = 10


@login_required
@capability_required("staff_affairs.own_leave")  # type: ignore[misc]  # الحارسُ بلا أنواع في core
def leave_request_self(request: HttpRequest) -> HttpResponse:
    """تقديمُ الموظّف طلبَ إجازةٍ لنفسه، وعرضُ آخر طلباته."""
    school = cast(SchoolRequest, request).school
    if school is None:
        raise Http404("لا مدرسةَ لهذا الحساب")
    user = cast(CustomUser, request.user)
    is_member = has_active_membership(school, user)

    form = LeaveRequestSelfForm(request.POST or None, request.FILES or None, school=school)
    if request.method == "POST" and is_member and form.is_valid():
        cd = form.cleaned_data
        try:
            LeaveService.create_leave_request(
                school=school,
                staff=user,
                leave_type=cd["leave_type"],
                start_date=cd["start_date"],
                end_date=cd["end_date"],
                days_count=cd["days_count"],
                reason=cd["reason"],
                attachment=cd.get("attachment"),
                created_by=user,
            )
        except ValueError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(
                request, f"قُدِّم طلبُ إجازتك ({cd['days_count']} يوم) وهو بانتظار المراجعة."
            )
            return redirect("staff_affairs:leave_request_self")

    return render(
        request,
        "staff_affairs/leave_request_self.html",
        {
            "form": form,
            "is_member": is_member,
            "recent": own_recent_leaves(school, user, RECENT_LIMIT),
        },
    )
