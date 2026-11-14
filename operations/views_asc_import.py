"""views_asc_import.py — صفحةُ رفع ملفَّي aSc: تقريرٌ ثمّ مسودّةُ جدولٍ غيرُ مفعَّلة (W-20261114-005).

عروضٌ رقيقة: التحقّقُ والكاشُ والمنطقُ في `academic_management`، والقراءةُ في مهمّة Celery
`operations.asc_import_run`، والصفحةُ تستطلع الحالةَ بـHTMX. لا اعتمادَ ولا تفعيلَ من هنا.
"""

from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.urls import reverse
from django.views.decorators.http import require_GET, require_POST

from academic_management import asc_import_job as job
from core.capabilities import capability_required
from core.htmx_utils import htmx_redirect

from .tasks import asc_import_run_task

PARTIAL = "schedule/partials/asc_import_result.html"


@login_required
@capability_required("schedule.admin")
@require_GET
def asc_import_page(request):
    """نموذجُ الرفع — وحدَه، فلا شيءَ يُقرأ قبل الضغط."""
    return render(request, "schedule/asc_import.html")


@login_required
@capability_required("schedule.admin")
@require_POST
def asc_import_submit(request):
    """يتحقّق من الملفّات ويحفظها في الكاش ويُرسل المهمّة؛ والردُّ جزءُ نتيجةٍ يستطلع الحالة."""
    create = request.POST.get("action") == "create"
    try:
        files = job.StagedFiles(
            job.validate_pdf(request.FILES.get("teachers_pdf"), "ملفّ المعلّمين"),
            job.validate_pdf(request.FILES.get("classes_pdf"), "ملفّ الشعب"),
            job.validate_rules(request.FILES.get("rules_json")),
        )
    except job.UploadError as refusal:
        return render(request, PARTIAL, {"state": {"state": "error", "error": str(refusal)}})
    token = job.stage(request.school.id, files)
    replace = create and request.POST.get("replace") == "1"
    asc_import_run_task.delay(token, str(request.school.id), str(request.user.pk), create, replace)
    return render(request, PARTIAL, {"state": {"state": "running"}, "token": token})


@login_required
@capability_required("schedule.admin")
@require_GET
def asc_import_status(request, token):
    """حالةُ التشغيل: جارٍ فيُستطلع، أو منتهٍ فيُعرض ويُحذف، أو إحالةٌ إلى الجدول الذكي بعد كتابة مسودّة."""
    state = job.poll(token, request.school.id)
    if state is None:
        raise Http404
    if state.get("create") and state.get("written") and not state.get("error"):
        messages.success(request, f"كُتبت مسودّةٌ بـ{state['written']} حصّةً غيرِ مفعَّلة.")
        return htmx_redirect(f"{reverse('smart_schedule')}?year={state['year']}")
    response = render(request, PARTIAL, {"state": state, "token": token})
    response["Cache-Control"] = "no-store"
    return response
