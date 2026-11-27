"""
api/views_erasure.py — Right to Erasure API (PDPPL م.18)

Endpoints:
  POST   /api/v1/erasure/request/              تقديم طلب محو
  GET    /api/v1/erasure/requests/              قائمة الطلبات (مدير)
  GET    /api/v1/erasure/requests/<id>/         تفاصيل طلب
  POST   /api/v1/erasure/requests/<id>/approve/ توقيع (ويُنفَّذ عند التوقيع الثاني)
  POST   /api/v1/erasure/requests/<id>/reject/  الرفض
  POST   /api/v1/erasure/officer/               تعيين مسؤول حماية البيانات (المدير)
"""

from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from api.permissions import (
    IsErasureSigner,
    IsSchoolAdmin,
    NotPlatformDeveloper,
    NotPlatformDeveloperUnlessOfficer,
)
from core.models import CustomUser, ErasureRequest, ParentStudentLink
from governance.erasure_messages import (
    ERASURE_FAILURES,
    ERASURE_REFUSALS,
    ERASURE_RETRY_NOTE,
    ERASURE_SIGNED_MESSAGE,
)
from governance.erasure_service import (
    ErasureFailedError,
    ErasureNotSignerError,
    ErasureOfficerError,
    ErasureService,
)

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
            "id",
            "status",
            "reason",
            "review_note",
            "student_name",
            "requested_by_name",
            "anonymized_id",
            "created_at",
            "reviewed_at",
            "completed_at",
            "summary",
            "admin_signed_at",
            "dpo_signed_at",
        ]

    def get_student_name(self, obj):
        return obj.student.full_name if obj.student else obj.anonymized_id or "—"

    def get_requested_by_name(self, obj):
        return obj.requested_by.full_name if obj.requested_by else "—"


class ErasureOfficerSerializer(serializers.Serializer):
    user_id = serializers.UUIDField()


# ── Views ─────────────────────────────────────────────────────


def _school_scope(request):
    """حصرُ الطلب بمدرسة المستخدم (W-20261002-040) — والمطوّر يرى الكلّ."""
    if request.user.is_superuser:
        return {}
    # get_school() لا request.school: مصادقةُ DRF بالتوكن تجري بعد SchoolContextMiddleware
    # فتكون المدرسةُ هناك None (فيفشل الحصرُ مغلقاً). فالاستدعاءُ الثالثُ مقصود.
    return {"school": request.user.get_school()}


@extend_schema(summary="تقديم طلب محو بيانات طالب", tags=["PDPPL"])
@api_view(["POST"])
@permission_classes([IsAuthenticated, NotPlatformDeveloper])
def create_erasure_request(request):
    """
    ولي الأمر أو المدير يقدّم طلب محو بيانات طالب.
    ولي الأمر يمكنه فقط طلب محو بيانات أبنائه.
    """
    ser = ErasureRequestCreateSerializer(data=request.data)
    ser.is_valid(raise_exception=True)

    student = get_object_or_404(CustomUser, id=ser.validated_data["student_id"])
    school = request.user.get_school()
    is_admin = request.user.is_admin() or request.user.is_superuser

    # Authorization: parent can only request for their own children
    if not is_admin:
        is_parent = ParentStudentLink.objects.filter(parent=request.user, student=student).exists()
        if not is_parent:
            return Response(
                {"detail": "يمكنك فقط طلب محو بيانات أبنائك."},
                status=status.HTTP_403_FORBIDDEN,
            )

    # [W-20261002-040] المحوُ لا رجعةَ فيه: مديرُ مدرسةٍ لا يطلبه لطالبٍ من غير
    # مدرسته. 404 لا 403 فلا يُعرَف وجودُ الطالب. المطوّر (superuser) خارج الحصر.
    # ويسري على وليّ الأمر أيضاً (ParentStudentLink بلا مرشّح مدرسة). وعضويّةُ طالبٍ
    # غيرِ نشطةٍ (تخرّج/انتقال) تكفي: حقُّ المحو لا يسقط بخروجه. والهدفُ طالبٌ لا أيُّ
    # عضوٍ: حسابُ كادرٍ في المدرسة يُردّ بـ404 نفسِها (`student_in_school`).
    if not request.user.is_superuser:
        if not ErasureService.student_in_school(student, school):
            return Response({"detail": "غير موجود."}, status=status.HTTP_404_NOT_FOUND)

    # Check for existing pending request
    existing = ErasureRequest.objects.filter(
        student=student, status__in=["pending", "approved", "processing"]
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
        reason=ser.validated_data["reason"],
    )
    ErasureService.notify_pending_signers(erasure_req, request.user)

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
    obj = get_object_or_404(ErasureRequest, id=request_id, **_school_scope(request))
    is_admin = request.user.is_admin() or request.user.is_superuser
    if not is_admin and obj.requested_by != request.user:
        return Response({"detail": "غير مسموح"}, status=status.HTTP_403_FORBIDDEN)
    return Response(ErasureRequestSerializer(obj).data)


def _refusal(refused_type):
    detail, http_status = ERASURE_REFUSALS[refused_type]
    return Response({"detail": detail}, status=http_status)


@extend_schema(summary="توقيع طلب محو (يُنفَّذ عند التوقيع الثاني)", tags=["PDPPL"])
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsErasureSigner, NotPlatformDeveloperUnlessOfficer])
def approve_erasure(request, request_id):
    """توقيعُ المدير أو مسؤول حماية البيانات؛ التنفيذُ عند اكتمال التوقيعين."""
    obj = get_object_or_404(ErasureRequest, id=request_id, **_school_scope(request))

    # القفلُ والتوقيعُ والتنفيذُ في الخدمة.
    try:
        obj, summary = ErasureService.approve_and_execute(
            obj.pk, request.user, request.data.get("note", "")
        )
    except tuple(ERASURE_REFUSALS) as refused:
        return _refusal(type(refused))
    except ErasureFailedError as exc:
        # رمزٌ وجملةٌ من جدولٍ ثابتٍ لا نصُّ الاستثناء (CodeQL py/stack-trace-exposure): الرمزُ المجهولُ `erasure_error`.
        code, detail = ERASURE_FAILURES.get(exc.code, ERASURE_FAILURES["erasure_error"])
        return Response(
            {"detail": f"{detail} {ERASURE_RETRY_NOTE}", "code": code},
            status=status.HTTP_409_CONFLICT,
        )

    if summary is None:
        return Response({"detail": ERASURE_SIGNED_MESSAGE}, status=status.HTTP_202_ACCEPTED)
    return Response(
        {
            "detail": "تم تنفيذ المحو بنجاح.",
            "anonymized_id": obj.anonymized_id,
            "summary": summary,
        }
    )


@extend_schema(summary="رفض طلب محو", tags=["PDPPL"])
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsErasureSigner, NotPlatformDeveloperUnlessOfficer])
def reject_erasure(request, request_id):
    """رفضُ أحد الموقّعَين مع ذكر السبب."""
    obj = get_object_or_404(ErasureRequest, id=request_id, **_school_scope(request))
    try:
        obj = ErasureService.reject(obj.pk, request.user, request.data.get("note", "").strip())
    except tuple(ERASURE_REFUSALS) as refused:
        return _refusal(type(refused))
    return Response(ErasureRequestSerializer(obj).data)


@extend_schema(summary="تعيين مسؤول حماية البيانات", tags=["PDPPL"])
@api_view(["POST"])
@permission_classes([IsAuthenticated, IsSchoolAdmin, NotPlatformDeveloper])
def assign_data_protection_officer(request):
    """المديرُ وحدَه يعيّن مسؤولَ حماية البيانات لمدرسته."""
    ser = ErasureOfficerSerializer(data=request.data)
    ser.is_valid(raise_exception=True)
    try:
        ErasureService.assign_officer(request.user, ser.validated_data["user_id"])
    except ErasureNotSignerError:
        return Response(
            {"detail": "تعيينُ مسؤول حماية البيانات للمدير وحدَه."},
            status=status.HTTP_403_FORBIDDEN,
        )
    except ErasureOfficerError:
        return Response(
            {"detail": "المسؤولُ يُختار من كادر المدرسة النشط."},
            status=status.HTTP_400_BAD_REQUEST,
        )
    return Response({"detail": "تم تعيين مسؤول حماية البيانات."})
