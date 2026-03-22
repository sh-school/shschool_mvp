"""
api/views_erasure.py — Right to Erasure API (PDPPL م.18)

Endpoints:
  POST   /api/v1/erasure/request/              تقديم طلب محو
  GET    /api/v1/erasure/requests/              قائمة الطلبات (مدير)
  GET    /api/v1/erasure/requests/<id>/         تفاصيل طلب
  POST   /api/v1/erasure/requests/<id>/approve/ الموافقة والتنفيذ
  POST   /api/v1/erasure/requests/<id>/reject/  الرفض
"""
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from django.shortcuts import get_object_or_404
from django.utils import timezone

from api.permissions import IsSchoolAdmin
from core.erasure_service import ErasureService
from core.models import CustomUser, ErasureRequest, ParentStudentLink


# ── Serializers ───────────────────────────────────────────────

class ErasureRequestCreateSerializer(serializers.Serializer):
    student_id = serializers.UUIDField()
    reason = serializers.CharField(min_length=10)


class ErasureRequestSerializer(serializers.ModelSerializer):
    student_name = serializers.SerializerMethodField()
    requested_by_name = serializers.SerializerMethodField()

    class Meta:
        model = ErasureRequest
        fields = [
            'id', 'status', 'reason', 'review_note',
            'student_name', 'requested_by_name', 'anonymized_id',
            'created_at', 'reviewed_at', 'completed_at', 'summary',
        ]

    def get_student_name(self, obj):
        return obj.student.full_name if obj.student else obj.anonymized_id or "—"

    def get_requested_by_name(self, obj):
        return obj.requested_by.full_name if obj.requested_by else "—"


# ── Views ─────────────────────────────────────────────────────

@extend_schema(summary="تقديم طلب محو بيانات طالب", tags=["PDPPL"])
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def create_erasure_request(request):
    """
    ولي الأمر أو المدير يقدّم طلب محو بيانات طالب.
    ولي الأمر يمكنه فقط طلب محو بيانات أبنائه.
    """
    ser = ErasureRequestCreateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)

    student = get_object_or_404(CustomUser, id=ser.validated_data['student_id'])
    school = request.user.get_school()
    is_admin = request.user.is_admin() or request.user.is_superuser

    # Authorization: parent can only request for their own children
    if not is_admin:
        is_parent = ParentStudentLink.objects.filter(
            parent=request.user, student=student
        ).exists()
        if not is_parent:
            return Response(
                {"detail": "يمكنك فقط طلب محو بيانات أبنائك."},
                status=status.HTTP_403_FORBIDDEN,
            )

    # Check for existing pending request
    existing = ErasureRequest.objects.filter(
        student=student, status__in=['pending', 'approved', 'processing']
    ).first()
    if existing:
        return Response(
            {"detail": "يوجد طلب محو قائم بالفعل لهذا الطالب.", "request_id": str(existing.id)},
            status=status.HTTP_409_CONFLICT,
        )

    erasure_req = ErasureRequest.objects.create(
        school=school,
        student=student,
        requested_by=request.user,
        reason=ser.validated_data['reason'],
    )

    return Response(
        ErasureRequestSerializer(erasure_req).data,
        status=status.HTTP_201_CREATED,
    )


@extend_schema(summary="قائمة طلبات المحو", tags=["PDPPL"])
@api_view(["GET"])
@permission_classes([IsSchoolAdmin])
def list_erasure_requests(request):
    """قائمة كل طلبات المحو للمدرسة (مدير فقط)."""
    school = request.user.get_school()
    status_filter = request.query_params.get("status", "")
    qs = ErasureRequest.objects.filter(school=school)
    if status_filter:
        qs = qs.filter(status=status_filter)
    return Response(ErasureRequestSerializer(qs, many=True).data)


@extend_schema(summary="تفاصيل طلب محو", tags=["PDPPL"])
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def erasure_request_detail(request, request_id):
    """تفاصيل طلب محو — للمقدّم أو المدير."""
    obj = get_object_or_404(ErasureRequest, id=request_id)
    is_admin = request.user.is_admin() or request.user.is_superuser
    if not is_admin and obj.requested_by != request.user:
        return Response({"detail": "غير مسموح"}, status=status.HTTP_403_FORBIDDEN)
    return Response(ErasureRequestSerializer(obj).data)


@extend_schema(summary="الموافقة على طلب محو وتنفيذه", tags=["PDPPL"])
@api_view(["POST"])
@permission_classes([IsSchoolAdmin])
def approve_erasure(request, request_id):
    """المدير يوافق على الطلب ويُنفَّذ فوراً."""
    obj = get_object_or_404(ErasureRequest, id=request_id)

    if obj.status != 'pending':
        return Response(
            {"detail": f"لا يمكن الموافقة — الحالة الحالية: {obj.get_status_display()}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    obj.status = 'approved'
    obj.reviewed_by = request.user
    obj.reviewed_at = timezone.now()
    obj.review_note = request.data.get('note', '')
    obj.save()

    # Execute immediately
    obj.status = 'processing'
    obj.save()

    summary = ErasureService.execute(obj)

    return Response({
        "detail": "تم تنفيذ المحو بنجاح.",
        "anonymized_id": obj.anonymized_id,
        "summary": summary,
    })


@extend_schema(summary="رفض طلب محو", tags=["PDPPL"])
@api_view(["POST"])
@permission_classes([IsSchoolAdmin])
def reject_erasure(request, request_id):
    """المدير يرفض الطلب مع ذكر السبب."""
    obj = get_object_or_404(ErasureRequest, id=request_id)

    if obj.status != 'pending':
        return Response(
            {"detail": f"لا يمكن الرفض — الحالة الحالية: {obj.get_status_display()}"},
            status=status.HTTP_400_BAD_REQUEST,
        )

    note = request.data.get('note', '').strip()
    if not note:
        return Response(
            {"detail": "سبب الرفض مطلوب."},
            status=status.HTTP_400_BAD_REQUEST,
        )

    obj.status = 'rejected'
    obj.reviewed_by = request.user
    obj.reviewed_at = timezone.now()
    obj.review_note = note
    obj.save()

    return Response(ErasureRequestSerializer(obj).data)
