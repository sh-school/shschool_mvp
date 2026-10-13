"""views.py — نقطتا الشريط: قراءةُ التقدّم الخفيفة (JSON) وطلبُ الإيقاف المبكر. بلا واجهة (شريطُ التقدّم لجلسة الواجهة)."""

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from core.capabilities import capability_required
from core.models.audit import AuditLog
from operations.models import ScheduleGeneration

from . import progress


@login_required
@capability_required("schedule.admin")
@require_GET
@never_cache
def v2_progress(request, generation_id):
    """لقطةُ التقدّم — تُستعلَم كلَّ ثانيتين. حقلٌ واحدٌ من الصفّ بلا حسابٍ ثقيل."""
    generation = get_object_or_404(ScheduleGeneration, id=generation_id, school=request.school)
    return JsonResponse(progress.read_progress(generation))


@login_required
@capability_required("schedule.admin")
@require_POST
def v2_stop(request, generation_id):
    """إيقافٌ مبكّر يحتفظ بأفضل حلّ — يُقبل ويُسجَّل، والعاملُ يلتقطه خلال ثانية."""
    generation = get_object_or_404(ScheduleGeneration, id=generation_id, school=request.school)
    accepted = progress.request_stop(generation)
    if accepted:
        AuditLog.log(
            user=request.user,
            action="update",
            model_name="other",
            object_id=generation.pk,
            object_repr=f"إيقافٌ مبكّر لتوليد V2 {generation.academic_year}",
            changes={"event": "schedule_v2_early_stop"},
            school=generation.school,
            request=request,
        )
    return JsonResponse({"accepted": accepted}, status=200 if accepted else 409)
