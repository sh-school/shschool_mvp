"""
operations/api_views.py
نقاط API للحضور والجداول والبحث
[مهمة 7] إضافة Rate Limiting على كل نقطة API
"""

from django.utils.decorators import method_decorator
from django_ratelimit.decorators import ratelimit
from rest_framework import generics, permissions

from .models import Session, StudentAttendance
from .serializers import AttendanceSerializer, SessionSerializer

# ── [مهمة 7] Rate Limit: 60 طلب/دقيقة لكل IP على Class-Based Views ──


@method_decorator(ratelimit(key="user", rate="60/m", method="GET", block=True), name="dispatch")
class SessionListView(generics.ListAPIView):
    """قائمة حصص المعلم — محدودة بـ 60 طلب/دقيقة"""

    serializer_class = SessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        school = self.request.user.get_school()
        return (
            Session.objects.filter(school=school, teacher=self.request.user)
            .select_related("class_group", "subject")
            .order_by("-date", "start_time")
        )


@method_decorator(ratelimit(key="user", rate="60/m", method="GET", block=True), name="dispatch")
class AttendanceListView(generics.ListAPIView):
    """سجل الحضور — محدود بـ 60 طلب/دقيقة"""

    serializer_class = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        school = self.request.user.get_school()
        session_id = self.request.query_params.get("session")
        qs = StudentAttendance.objects.filter(school=school)
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs.select_related("student", "session")


# ── بحث الطلاب ────────────────────────────────────────────────────────

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import JsonResponse

from core.models import CustomUser, StudentEnrollment
from core.permissions import ALL_STAFF_ROLES, role_required


@login_required
@role_required(ALL_STAFF_ROLES)
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

    student_ids = StudentEnrollment.objects.filter(
        class_group__school=school, is_active=True
    ).values_list("student_id", flat=True)

    qs = CustomUser.objects.filter(id__in=student_ids).filter(
        Q(full_name__icontains=q) | Q(national_id__icontains=q)
    )[:10]  # حد أقصى 10 نتائج دائماً

    return JsonResponse(
        {
            "results": [
                {
                    "id": str(s.id),
                    "full_name": s.full_name,
                    "national_id": s.national_id,
                }
                for s in qs
            ]
        }
    )
