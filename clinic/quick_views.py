"""
clinic/quick_views.py — شاشةُ الإدخال السريع وطابور اليوم للممرّض (W-20261020-030)
════════════════════════════════════════════════════════════════════════════════
بحثٌ فوريّ ← مسوّدةُ زيارةٍ عند اختيار الطالب ← أزرارُ خدماتٍ من القائمة المعتمدة (029) ← إغلاق.
كلُّ نقاط النهاية HTMX تُعيد أجزاءً، وكلُّها بلا تخزين (`never_cache`): فيها أسماءُ طلبةٍ وحالةٌ صحّيّة.
المستعلِمُ الممرّضُ وحدَه (`clinic.write`)، والزيارةُ تُجلب دائماً بمدرسة المستخدم.
"""

from __future__ import annotations

import json

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from clinic import choices
from clinic.models import ClinicVisit
from clinic.queue import todays_queue
from clinic.selectors import search_students
from clinic.services import ClinicService
from core.capabilities import capability_required
from core.models import CustomUser

#: أقلّ حروفٍ للبحث وأقصى نتائج — قائمةٌ قصيرةٌ تُلمس، لا جدولٌ يُمرَّر.
MIN_QUERY = 2
MAX_RESULTS = 5

_guard = (login_required, capability_required("clinic.write"), never_cache)


def _protected(view):
    for deco in reversed(_guard):
        view = deco(view)
    return view


def _panel_ctx(visit: ClinicVisit) -> dict:
    return {
        "visit": visit,
        "service_groups": [
            (
                label,
                [(code, name) for code, name, g in choices.SERVICES if g == group],
            )
            for group, label in choices.SERVICE_GROUPS
        ],
        "complaints": choices.COMPLAINT_CHOICES,
        "outcomes": choices.OUTCOME_CHOICES,
        "followups": choices.FOLLOWUP_CHOICES,
    }


def _changed(response: HttpResponse) -> HttpResponse:
    """يُعلم الطابورَ بالتحديث فيُعيد جلب نفسه."""
    response["HX-Trigger"] = json.dumps({"clinic-visit-changed": True})
    return response


@_protected
@require_GET
def quick_entry(request):
    school = request.school
    queue = todays_queue(school, timezone.localdate())
    return render(request, "clinic/quick_entry.html", {"queue": queue})


@_protected
@require_GET
def quick_search(request):
    school = request.school
    q = (request.GET.get("q") or "").strip()
    students = search_students(school, q, MAX_RESULTS) if len(q) >= MIN_QUERY else []
    return render(request, "clinic/partials/_quick_results.html", {"students": students, "q": q})


@_protected
@require_POST
def quick_start(request):
    school = request.school
    student = get_object_or_404(
        CustomUser,
        id=request.POST.get("student_id"),
        memberships__school=school,
        memberships__role__name="student",
    )
    visit = ClinicService.start_visit(school, student, request.user)
    return _changed(render(request, "clinic/partials/_quick_panel.html", _panel_ctx(visit)))


@_protected
@require_POST
def quick_service(request, visit_id):
    school = request.school
    visit = get_object_or_404(ClinicVisit, id=visit_id, school=school)
    try:
        ClinicService.set_coding(
            visit,
            service_code=request.POST.get("service_code", ""),
            complaint_code=request.POST.get("complaint_code", ""),
        )
    except ValueError:
        return HttpResponse("طلبٌ غير صالح", status=400)
    return _changed(render(request, "clinic/partials/_quick_panel.html", _panel_ctx(visit)))


@_protected
@require_POST
def quick_close(request, visit_id):
    school = request.school
    visit = get_object_or_404(ClinicVisit, id=visit_id, school=school)
    try:
        ClinicService.close_visit(
            visit, request.POST.get("outcome", ""), request.POST.get("follow_up_party", "")
        )
    except ValueError:
        return HttpResponse("طلبٌ غير صالح", status=400)
    return _changed(render(request, "clinic/partials/_quick_closed.html", {"visit": visit}))


@_protected
@require_GET
def quick_queue(request):
    school = request.school
    queue = todays_queue(school, timezone.localdate())
    return render(request, "clinic/partials/_quick_queue.html", {"queue": queue})
