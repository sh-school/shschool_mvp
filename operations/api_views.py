"""
operations/api_views.py
نقطة بحث الطلاب — [مهمة 7] محدودةٌ بمعدّل.

كانت هنا ``SessionListView`` و``AttendanceListView`` بـ``IsAuthenticated``، وحُذفتا مع
مساريهما: نظيراهما في ``api/views.py`` تحت ``/api/v1/`` (مراجعةُ 2026-09-13، ن١).
"""

# ── بحث الطلاب ────────────────────────────────────────────────────────
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse

from core.capabilities import capability_required
from core.models import CustomUser, StudentEnrollment
from core.privacy import mask_national_id
from core.ratelimit_safe import ratelimit


@login_required
@capability_required("students.search")
@ratelimit(key="user", rate="30/m", method="GET", block=True)
def student_search_api(request):
    """
    بحث سريع عن الطلاب للتقارير والتكميل التلقائي
    [مهمة 7] محدود بـ 30 طلب/دقيقة لكل مستخدم
    النتائج محدودة بـ 10 — لا يمكن استخراج قائمة كاملة
    Staff-only: الطلاب وأولياء الأمور لا يحتاجون بحث طلاب.
    """
    school = request.user.get_school()
    q = request.GET.get("q", "").strip()

    if not q or len(q) < 2:
        return JsonResponse({"results": []})

    # المقيَّدُ بجناحه لا يجد إلّا طلبةَ جناحه — ولمن خرج عنه نتيجةٌ فارغةٌ لا 403
    # (قرارُ 2026-09-15). وغيرُه كما كان.
    from wings.scope import student_scope_for

    student_ids = (
        student_scope_for(request)
        .narrow(
            StudentEnrollment.objects.filter(class_group__school=school, is_active=True),
            "student_id",
        )
        .values_list("student_id", flat=True)
    )

    qs = CustomUser.objects.filter(id__in=student_ids).filter(
        Q(full_name__icontains=q) | Q(national_id__icontains=q)
    )[:10]  # حد أقصى 10 نتائج دائماً

    return JsonResponse(
        {
            "results": [
                {
                    "id": str(s.id),
                    "full_name": s.full_name,
                    "national_id": mask_national_id(s.national_id),
                }
                for s in qs
            ]
        }
    )
