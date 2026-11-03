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
from django.core.cache import cache
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from clinic import choices
from clinic.models import ClinicVisit
from clinic.queue import todays_queue
from clinic.selectors import (
    MIN_QUERY,
    class_options,
    recent_visitors,
    search_students,
    student_choice,
    students_of_class,
)
from clinic.services import ClinicService
from clinic.views import _audit_health_screen
from core.capabilities import capability_required
from core.models import CustomUser

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


def _queue_rows(queue) -> int:
    return len(queue.waiting) + len(queue.in_care) + len(queue.done)


def _changed(response: HttpResponse) -> HttpResponse:
    """يُعلم الطابورَ بالتحديث فيُعيد جلب نفسه."""
    response["HX-Trigger"] = json.dumps({"clinic-visit-changed": True})
    return response


@_protected
@require_GET
def quick_entry(request):
    school = request.school
    queue = todays_queue(school, timezone.localdate())
    # الطابورُ يعرض أسماءَ طلبةٍ وحالتَهم الصحّيّة: وصولٌ إلى بيانٍ صحّيّ يُدقَّق بمعرّفاتٍ فقط.
    _audit_health_screen(
        request, "الإدخال السريع", model_name="ClinicVisit", rows=_queue_rows(queue)
    )
    return render(
        request,
        "clinic/quick_entry.html",
        {
            "queue": queue,
            "classes": class_options(school),
            "recent": recent_visitors(school, timezone.localdate()),
            "mode": "quick",
        },
    )


def _picker_mode(request) -> str:
    """«form»: يملأ حقلَ نموذجٍ؛ وما سواه: الإدخالُ السريع (تأكيدٌ ثمّ فتحُ زيارة)."""
    return "form" if request.GET.get("mode") == "form" else "quick"


def _results(request, students, **extra) -> HttpResponse:
    ctx = {"students": students, "mode": _picker_mode(request), **extra}
    return render(request, "clinic/partials/_student_results.html", ctx)


@_protected
@require_GET
def quick_search(request):
    q = (request.GET.get("q") or "").strip()
    students = search_students(request.school, q, user=request.user)
    # دون الحدّ الأدنى لا بحثَ جرى فلا «لا نتائج» (الممرّضُ ما زال يكتب).
    return _results(request, students, q=q if len(q) >= MIN_QUERY else "")


@_protected
@require_GET
def quick_class(request):
    """صفٌّ ثمّ شعبة: قيمةُ الخيار `G9|1`."""
    grade, _, section = (request.GET.get("cls") or "").partition("|")
    students = students_of_class(request.school, grade, section) if section else []
    return _results(request, students, browsing=True)


@_protected
@require_GET
def quick_recent(request):
    """زوّارُ آخر 7 أيام — يملأون القائمةَ قبل أن يكتب الممرّضُ شيئاً."""
    students = recent_visitors(request.school, timezone.localdate())
    return _results(request, students, recent=True)


@_protected
@require_GET
def quick_pick(request):
    """تأكيدٌ قبل الفتح: يعرض الطالبَ بصفّه وسنةِ ميلاده، ولا يكتب شيئاً — الفتحُ في `quick_start` وحدَه."""
    choice = student_choice(request.school, request.GET.get("student_id"))
    if choice is None:
        raise Http404
    return render(request, "clinic/partials/_quick_confirm.html", {"s": choice})


@_protected
@require_POST
def quick_start(request):
    school = request.school
    student = get_object_or_404(
        CustomUser,
        id=request.POST.get("student_id"),
        memberships__school=school,
        memberships__role__name="student",
        memberships__is_active=True,
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
    # الجلبُ الدوريّ بـHTMX يُخفَّف إلى سطرٍ في الدقيقة كقائمة الزيارات؛ والفتحُ الكاملُ يُدقَّق دائماً.
    is_htmx = bool(getattr(request, "htmx", None) or request.headers.get("HX-Request"))
    if not is_htmx or cache.add(f"clinic_audit_live:{request.user.pk}:quick_queue", 1, 60):
        _audit_health_screen(
            request, "طابور الإدخال السريع", model_name="ClinicVisit", rows=_queue_rows(queue)
        )
    return render(request, "clinic/partials/_quick_queue.html", {"queue": queue})
