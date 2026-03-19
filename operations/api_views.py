from rest_framework import generics, permissions
from .models import Session, StudentAttendance
from .serializers import SessionSerializer, AttendanceSerializer


class SessionListView(generics.ListAPIView):
    serializer_class   = SessionSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        school = self.request.user.get_school()
        return Session.objects.filter(school=school, teacher=self.request.user).select_related(
            "class_group", "subject"
        ).order_by("-date", "start_time")


class AttendanceListView(generics.ListAPIView):
    serializer_class   = AttendanceSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        school     = self.request.user.get_school()
        session_id = self.request.query_params.get("session")
        qs         = StudentAttendance.objects.filter(school=school)
        if session_id:
            qs = qs.filter(session_id=session_id)
        return qs.select_related("student", "session")


from django.http import JsonResponse
from django.contrib.auth.decorators import login_required
from core.models import CustomUser, StudentEnrollment


@login_required
def student_search_api(request):
    """بحث سريع عن الطلاب للتقارير"""
    school = request.user.get_school()
    q      = request.GET.get("q", "").strip()
    if not q or len(q) < 2:
        return JsonResponse({"results": []})

    from django.db.models import Q
    student_ids = StudentEnrollment.objects.filter(
        class_group__school=school, is_active=True
    ).values_list("student_id", flat=True)

    qs = CustomUser.objects.filter(id__in=student_ids).filter(
        Q(full_name__icontains=q) | Q(national_id__icontains=q)
    )[:10]

    return JsonResponse({
        "results": [
            {"id": str(s.id), "full_name": s.full_name, "national_id": s.national_id}
            for s in qs
        ]
    })
