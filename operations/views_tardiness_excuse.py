"""صفحةُ «أعذار التأخّر» لمعلّم الحصّة: متأخّرو حصصه اليوم، واعتمادُ العذر وإلغاؤه (W-20261002-028).

الحكمُ كلُّه في `operations/tardiness_excuse_services.py`؛ هنا ترجمةٌ إلى HTTP فقط.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.capabilities import capability_required

from . import tardiness_excuse_services as service


@login_required
@capability_required("attendance.mark")
def tardiness_excuses(request):
    school = request.school
    day = timezone.localdate()
    return render(
        request,
        "operations/tardiness_excuses.html",
        {"day": day, "rows": service.todays_lates(school, request.user, day)},
    )


@login_required
@capability_required("attendance.mark")
@require_POST
def tardiness_excuse_decide(request, attendance_id):
    school = request.school
    try:
        if request.POST.get("action") == "revoke":
            service.revoke(school, request.user, attendance_id)
            messages.success(request, "أُلغي العذرُ وعاد التأخّرُ كما رُصد.")
        else:
            service.grant(school, request.user, attendance_id, request.POST.get("reason", ""))
            messages.success(request, "اعتُمد عذرُ التأخّر ولم يُحتسب على الطالب.")
    except service.TardinessExcuseError as error:
        messages.error(request, str(error))
    return redirect("tardiness_excuses")
