"""طابورُ اقتراحات المخالفة 1-01 لمشرف الجناح (W-20261013-034) — لطلبة جناحه وحدَه، ولحامل الجناح وحدَه.

راصدُ الغياب العامّ (`wings.school_wide`) وكلُّ من لا يحمل جناحاً بنفسه يُحجب عن الصفحة والاعتماد (`_scope`)؛ والمعلّمون خارج بوّابتها.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from core.academic_calendar import academic_year_for_school
from core.capabilities import capability_required
from wings import conduct_proposals as service
from wings.scope import StudentScope
from wings.services import wings_of


def _scope(request):
    """نطاقُ المشرف بأجنحته هو (أصيلاً أو بديلاً) وحدَها؛ ومن لا جناحَ يحمله — راصدُ الغياب العامّ والقيادةُ — لا صفحةَ له ولا اعتماد."""
    school = request.user.get_school()
    year = academic_year_for_school(school)
    own = [
        w for w in wings_of(request.user, school, year) if w.current_supervisor() == request.user
    ]
    if not own:
        raise PermissionDenied
    return StudentScope(school, frozenset(w.pk for w in own), year)


@login_required
@capability_required("wings.record_day")
def conduct_proposals(request):
    scope = _scope(request)
    queue = service.queue_for(request.user.get_school(), scope)
    return render(request, "wings/conduct_proposals.html", {"proposals": queue})


@login_required
@capability_required("wings.record_day")
@require_POST
def conduct_proposal_decide(request, pk):
    scope = _scope(request)
    decision = request.POST.get("decision")
    try:
        if decision == "approve":
            proposal = service.approve(pk, request.user, scope)
            name = proposal.student.full_name
            messages.success(request, f"اعتُمد الاقتراحُ وسُجّلت مخالفة 1-01 على {name}.")
        elif decision == "reject":
            proposal = service.reject(pk, request.user, scope)
            messages.success(request, f"رُدَّ الاقتراحُ لـ{proposal.student.full_name}.")
        else:
            raise service.ProposalError("اختر اعتماداً أو رداً.")
    except service.ProposalError as err:
        messages.error(request, str(err))
    return redirect("wings:conduct_proposals")
