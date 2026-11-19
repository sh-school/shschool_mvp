"""قرارُ مشرف الجناح في اقتراح متابعة تأخّر العودة (W-20261119-004) — قبولٌ أو رفضٌ بلا مخالفةٍ آليّة.

القائمةُ تُعرض في صفحة اقتراحات المخالفات نفسِها (`views_proposals`)، ونطاقُ القرار أجنحةُ الحامل وحدَها.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.views.decorators.http import require_POST

from core.capabilities import capability_required
from wings import return_late_services as service
from wings.views_proposals import _scope


@login_required
@capability_required("wings.record_day")
@require_POST
def return_late_decide(request, pk):
    scope = _scope(request)
    decision = request.POST.get("decision")
    try:
        if decision == "accept":
            service.accept(pk, request.user, scope)
            messages.success(request, "قُبلت المتابعةُ وسُجّل قرارُك.")
        elif decision == "dismiss":
            service.dismiss(pk, request.user, scope)
            messages.success(request, "رُفض الاقتراحُ وسُجّل قرارُك.")
        else:
            raise service.SuggestionError("اختر قبولاً أو رفضاً.")
    except service.SuggestionError as err:
        messages.error(request, str(err))
    return redirect("wings:conduct_proposals")
