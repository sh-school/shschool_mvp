"""views_schedule_drafts.py — حذفُ توليدٍ لم يُعتمد من صفحة الجدول الذكي.

عرضٌ رقيق: الصلاحيّةُ نفسُها التي تعتمد (`schedule.settings`)، والشروطُ كلُّها في
`services.schedule_drafts` — فلا يُحذف معتمَدٌ ولا جارٍ ولو وصل الطلبُ من غير الزرّ.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from core.capabilities import capability_required

from .models import ScheduleGeneration
from .services.schedule_drafts import DiscardRefusedError, discard_generation, stop_generation


@login_required
@capability_required("schedule.settings")
@require_POST
def discard_schedule(request, generation_id):
    """يحذف مسودّةً أو محاولةً فاشلة — ثمّ يعود إلى الصفحة على عامها."""
    generation = get_object_or_404(ScheduleGeneration, id=generation_id, school=request.school)
    year = generation.academic_year
    try:
        removed = discard_generation(generation, user=request.user, request=request)
    except DiscardRefusedError as refusal:
        messages.error(request, str(refusal))
    else:
        messages.success(request, f"حُذف التوليد ({removed} حصّة من مسودّته).")
    return redirect(f"{reverse('smart_schedule')}?year={year}")


@login_required
@capability_required("schedule.admin")
@require_POST
def stop_schedule_generation(request, generation_id):
    """يوقف توليداً جارياً — بالصلاحيّة نفسِها التي تبدؤه."""
    generation = get_object_or_404(ScheduleGeneration, id=generation_id, school=request.school)
    try:
        stop_generation(generation, user=request.user, request=request)
    except DiscardRefusedError as refusal:
        messages.error(request, str(refusal))
    else:
        messages.success(request, "أُوقف التوليد — ويمكنك حذفُه من السجلّ.")
    return redirect(f"{reverse('smart_schedule')}?year={generation.academic_year}")
