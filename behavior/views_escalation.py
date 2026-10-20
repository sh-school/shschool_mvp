"""معاينةُ الخطوة التصعيديّة قبل الحفظ (W-20260928-007) — قراءةٌ فقط، مفصولةٌ عن views.py لحدّ حجمه."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from core.capabilities import capability_required

from .selectors import _get_scoped_students, escalation_preview_targets
from .services import BehaviorService


@login_required
@capability_required("behavior.record")
def escalation_preview(request):
    """خطوةُ التصعيد التي ستُحسب عند الحفظ — تُطلب عند اختيار الطالب والفئة؛ لا تكتب شيئاً."""
    school = request.school
    targets = escalation_preview_targets(
        _get_scoped_students(request, school),
        request.GET.get("student_id", ""),
        request.GET.get("violation_category", ""),
    )
    if targets is None:
        return HttpResponse("")
    student, category = targets
    preview = BehaviorService.preview_escalation(student, school, category.degree, category)
    return render(request, "behavior/partials/escalation_preview.html", {"preview": preview})
