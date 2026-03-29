"""
api/views.py
━━━━━━━━━━━
SchoolOS REST API v1 — ViewSets + APIViews

نقاط النهاية:
  /api/v1/me/                           — ملف المستخدم الحالي
  /api/v1/students/                     — قائمة الطلاب
  /api/v1/students/{id}/grades/         — درجات طالب
  /api/v1/students/{id}/attendance/     — غياب طالب
  /api/v1/classes/                      — قائمة الفصول
  /api/v1/classes/{id}/results/         — نتائج فصل كامل
  /api/v1/sessions/                     — الحصص
  /api/v1/attendance/                   — سجل الحضور
  /api/v1/behavior/                     — المخالفات السلوكية
  /api/v1/notifications/                — الإشعارات الداخلية
  /api/v1/notifications/{id}/read/      — تحديد إشعار مقروءاً
  /api/v1/notifications/mark-all-read/  — تحديد الكل مقروءاً
  /api/v1/notification-preferences/     — تفضيلات الإشعارات
  /api/v1/kpis/                         — مؤشرات الأداء
  /api/v1/parent/children/              — أبناء ولي الأمر
  /api/v1/parent/children/{id}/grades/  — درجات الابن
  /api/v1/parent/children/{id}/attendance/ — غياب الابن
  /api/v1/library/books/               — الكتب
  /api/v1/library/borrowings/          — الاستعارات
  /api/v1/clinic/visits/               — زيارات العيادة
"""

import logging

from django.conf import settings
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django_filters.rest_framework import DjangoFilterBackend
from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.filters import OrderingFilter, SearchFilter
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from assessments.models import AnnualSubjectResult
from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit
from core.models import (
    ClassGroup,
    CustomUser,
    ParentStudentLink,
    StudentEnrollment,
)
from library.models import BookBorrowing, LibraryBook
from notifications.models import InAppNotification, UserNotificationPreference
from operations.models import Session, StudentAttendance

from .filters import (
    AttendanceFilter,
    BookFilter,
    BorrowingFilter,
    ClinicVisitFilter,
    InfractionFilter,
    SessionFilter,
)
from .pagination import StandardPagination
from .permissions import IsParentOrAdmin, IsSchoolAdmin, IsTeacherOrAdmin
from .serializers import (
    AnnualSubjectResultSerializer,
    AttendanceSerializer,
    BehaviorInfractionSerializer,
    BookBorrowingSerializer,
    ClassGroupSerializer,
    ClinicVisitSerializer,
    InAppNotificationSerializer,
    LibraryBookSerializer,
    MeSerializer,
    SessionSerializer,
    StudentEnrollmentSerializer,
    StudentGradeSummarySerializer,
    UserBriefSerializer,
    UserNotificationPreferenceSerializer,
    UserSafeSerializer,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  مساعدات
# ══════════════════════════════════════════════════════════════════════


def _school(request):
    """يُعيد school للمستخدم الحالي"""
    return request.user.get_school()


def _year(request, default=settings.CURRENT_ACADEMIC_YEAR):
    return request.query_params.get("year", default)


# ══════════════════════════════════════════════════════════════════════
#  Me — ملف المستخدم الحالي
# ══════════════════════════════════════════════════════════════════════


@extend_schema(
    summary="ملف المستخدم الحالي",
    description="يُعيد بيانات المستخدم المسجّل دخولاً مع مدرسته ودوره.",
    tags=["auth"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def me_view(request):
    return Response(MeSerializer(request.user).data)


# ══════════════════════════════════════════════════════════════════════
#  Students — الطلاب (للمدير والمعلم)
# ══════════════════════════════════════════════════════════════════════


class StudentListView(generics.ListAPIView):
    """
    GET /api/v1/students/

    الفلترة:
      ?year=2025-2026
      ?class_id=<uuid>
      ?search=اسم أو رقم وطني

    الفرز:
      ?ordering=name | -name | national_id | class | -class
    """

    serializer_class = StudentEnrollmentSerializer
    permission_classes = [IsTeacherOrAdmin]
    filter_backends = [SearchFilter, OrderingFilter]
    search_fields = ["student__full_name", "student__national_id"]
    ordering_fields = [
        "student__full_name",
        "student__national_id",
        "class_group__grade",
    ]
    ordering = ["student__full_name"]

    @extend_schema(
        summary="قائمة الطلاب",
        parameters=[
            OpenApiParameter("year", str, description="السنة الدراسية (مثال: 2025-2026)"),
            OpenApiParameter("class_id", str, description="معرّف الفصل (UUID)"),
        ],
        tags=["students"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        year = _year(self.request)

        qs = StudentEnrollment.objects.filter(
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        ).select_related("student", "class_group")

        if class_id := self.request.query_params.get("class_id"):
            qs = qs.filter(class_group_id=class_id)

        return qs


# Backward-compatible function alias
student_list = StudentListView.as_view()


@extend_schema(
    summary="درجات طالب",
    parameters=[OpenApiParameter("year", str, description="السنة الدراسية")],
    tags=["students"],
)
@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def student_grades(request, student_id):
    school = _school(request)
    year = _year(request)
    student = get_object_or_404(CustomUser, id=student_id)

    # ── VULN-002 Fix: IDOR Protection — المعلم يرى طلابه فقط ──────
    if not request.user.is_admin():
        from assessments.models import SubjectClassSetup

        teaches = SubjectClassSetup.objects.filter(
            teacher=request.user,
            school=school,
            academic_year=year,
            class_group__enrollments__student=student,
            class_group__enrollments__is_active=True,
        ).exists()
        if not teaches:
            return Response(
                {"detail": "ليس لديك صلاحية عرض بيانات هذا الطالب"},
                status=status.HTTP_403_FORBIDDEN,
            )

    annual = (
        AnnualSubjectResult.objects.filter(student=student, school=school, academic_year=year)
        .select_related("setup__subject")
        .order_by("setup__subject__name_ar")
    )

    # ⚡ Pre-fetch semester results لتجنب N+1 queries
    from assessments.models import StudentSubjectResult

    semester_results = StudentSubjectResult.objects.filter(
        student=student, setup__in=[a.setup_id for a in annual]
    ).select_related("setup__subject")  # تجنب N+1 عند الوصول لاسم المادة
    semester_map = {(r.student_id, r.setup_id, r.semester): r for r in semester_results}

    grades = [float(a.annual_total) for a in annual if a.annual_total]
    average = round(sum(grades) / len(grades), 2) if grades else None

    data = {
        "student": student,
        "year": year,
        "total_subjects": annual.count(),
        "passed": annual.filter(status="pass").count(),
        "failed": annual.filter(status="fail").count(),
        "average": average,
        "subjects": annual,
    }
    return Response(
        StudentGradeSummarySerializer(data, context={"semester_map": semester_map}).data
    )


@extend_schema(
    summary="غياب طالب",
    parameters=[
        OpenApiParameter("days", int, description="عدد الأيام (افتراضي: 30)"),
    ],
    tags=["students"],
)
@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def student_attendance(request, student_id):
    from datetime import timedelta

    from django.utils import timezone

    school = _school(request)
    student = get_object_or_404(CustomUser, id=student_id)

    # ── VULN-002 Fix: IDOR Protection — المعلم يرى طلابه فقط ──────
    if not request.user.is_admin():
        from assessments.models import SubjectClassSetup

        teaches = SubjectClassSetup.objects.filter(
            teacher=request.user,
            school=school,
            academic_year=_year(request),
            class_group__enrollments__student=student,
            class_group__enrollments__is_active=True,
        ).exists()
        if not teaches:
            return Response(
                {"detail": "ليس لديك صلاحية عرض بيانات هذا الطالب"},
                status=status.HTTP_403_FORBIDDEN,
            )

    try:
        days = max(1, min(int(request.query_params.get("days", 30)), 365))
    except ValueError:
        days = 30

    since = timezone.now().date() - timedelta(days=days)
    att = (
        StudentAttendance.objects.filter(
            student=student, session__school=school, session__date__gte=since
        )
        .select_related("session__subject")
        .order_by("-session__date")
    )

    total = att.count()
    absent = att.filter(status="absent").count()
    late = att.filter(status="late").count()
    present = att.filter(status="present").count()

    return Response(
        {
            "student_id": str(student_id),
            "since": since,
            "days": days,
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "att_pct": round(present / total * 100) if total else 0,
            "records": AttendanceSerializer(att, many=True).data,
        }
    )


# ══════════════════════════════════════════════════════════════════════
#  Classes — الفصول الدراسية
# ══════════════════════════════════════════════════════════════════════


@extend_schema(
    summary="قائمة الفصول الدراسية",
    parameters=[
        OpenApiParameter("year", str, description="السنة الدراسية"),
        OpenApiParameter("ordering", str, description="grade | section | -grade"),
    ],
    tags=["classes"],
)
@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def class_list(request):
    school = _school(request)
    year = _year(request)

    ordering_map = {
        "grade": ("grade", "section"),
        "-grade": ("-grade", "section"),
        "section": ("section",),
        "-section": ("-section",),
    }
    ordering = request.query_params.get("ordering", "grade")
    db_ordering = ordering_map.get(ordering, ("grade", "section"))

    qs = (
        ClassGroup.objects.filter(school=school, academic_year=year)
        .prefetch_related("enrollments")
        .order_by(*db_ordering)
    )
    return Response(ClassGroupSerializer(qs, many=True).data)


@extend_schema(
    summary="نتائج فصل دراسي كامل",
    parameters=[OpenApiParameter("year", str, description="السنة الدراسية")],
    tags=["classes"],
)
@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def class_results(request, class_id):
    from reports.services import ReportDataService

    school = _school(request)
    year = _year(request)
    class_group = get_object_or_404(ClassGroup, id=class_id, school=school)
    data = ReportDataService.get_class_results(class_group, school, year)

    rows = []
    for row in data["student_rows"]:
        rows.append(
            {
                "rank": row["rank"],
                "student": UserBriefSerializer(row["student"]).data,
                "avg": row["avg"],
                "passed": row["passed"],
                "failed": row["failed"],
                "status": row["status"],
                "grades": {
                    subj: {
                        "annual_total": float(ann.annual_total)
                        if ann and ann.annual_total
                        else None,
                        "status": ann.status if ann else None,
                        "letter_grade": ann.letter_grade if ann else None,
                    }
                    for subj, ann in row["grades"].items()
                },
            }
        )

    return Response(
        {
            "class_group": str(class_group),
            "year": year,
            "total_students": data["total_students"],
            "total_passed": data["total_passed"],
            "total_failed": data["total_failed"],
            "subjects": [s.name_ar for s in data["subjects"]],
            "rows": rows,
        }
    )


# ══════════════════════════════════════════════════════════════════════
#  Sessions — الحصص الدراسية (مع django-filter + OrderingFilter)
# ══════════════════════════════════════════════════════════════════════


class SessionListView(generics.ListAPIView):
    """
    GET /api/v1/sessions/

    الفلترة:
      ?date=2026-03-21
      ?date_from=2026-03-01&date_to=2026-03-31
      ?class_id=<uuid>
      ?teacher_id=<uuid>
      ?subject_id=<uuid>
      ?status=completed

    الفرز:
      ?ordering=date | -date | start_time | class_group__grade
    """

    serializer_class = SessionSerializer
    permission_classes = [IsTeacherOrAdmin]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = SessionFilter
    ordering_fields = ["date", "start_time", "status", "class_group__grade"]
    ordering = ["-date", "start_time"]

    @extend_schema(
        summary="قائمة الحصص الدراسية",
        tags=["sessions"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        return (
            Session.objects.filter(school=school)
            .select_related("class_group", "subject", "teacher")
            .order_by("-date", "start_time")
        )


# ══════════════════════════════════════════════════════════════════════
#  Attendance — سجل الحضور (مع django-filter + OrderingFilter)
# ══════════════════════════════════════════════════════════════════════


class AttendanceListView(generics.ListAPIView):
    """
    GET /api/v1/attendance/

    الفلترة:
      ?student_id=<uuid>
      ?class_id=<uuid>
      ?status=absent | present | late | excused
      ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
      ?session_id=<uuid>

    الفرز:
      ?ordering=-session__date | student__full_name | status
    """

    serializer_class = AttendanceSerializer
    permission_classes = [IsTeacherOrAdmin]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = AttendanceFilter
    ordering_fields = ["session__date", "student__full_name", "status"]
    ordering = ["-session__date"]

    @extend_schema(
        summary="سجل الحضور والغياب",
        tags=["attendance"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        return (
            StudentAttendance.objects.filter(session__school=school)
            .select_related("student", "session__subject", "session__class_group")
            .order_by("-session__date")
        )


# ══════════════════════════════════════════════════════════════════════
#  Behavior — المخالفات السلوكية (مع django-filter + OrderingFilter)
# ══════════════════════════════════════════════════════════════════════


class BehaviorListView(generics.ListAPIView):
    """
    GET /api/v1/behavior/

    الفلترة:
      ?student_id=<uuid>
      ?level=3
      ?level_min=2&level_max=4
      ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD
      ?is_resolved=false
      ?category=C
      ?class_id=<uuid>

    الفرز:
      ?ordering=-date | level | -points_deducted | student__full_name
    """

    serializer_class = BehaviorInfractionSerializer
    permission_classes = [IsTeacherOrAdmin]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = InfractionFilter
    ordering_fields = ["date", "level", "points_deducted", "student__full_name"]
    ordering = ["-date"]

    @extend_schema(
        summary="قائمة المخالفات السلوكية",
        tags=["behavior"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        return BehaviorInfraction.objects.filter(school=school).with_student().order_by("-date")


# للتوافق مع URLs القديمة
@extend_schema(
    summary="قائمة المخالفات السلوكية (deprecated — استخدم GET /api/v1/behavior/)",
    tags=["behavior"],
    deprecated=True,
)
@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def behavior_list(request):
    view = BehaviorListView.as_view()
    return view(request._request)


# ══════════════════════════════════════════════════════════════════════
#  Notifications — الإشعارات الداخلية
# ══════════════════════════════════════════════════════════════════════


@extend_schema(
    summary="قائمة الإشعارات الداخلية",
    parameters=[
        OpenApiParameter("unread", bool, description="true = غير مقروءة فقط"),
        OpenApiParameter(
            "event_type", str, description="نوع الحدث: behavior | absence | grade ..."
        ),
        OpenApiParameter("priority", str, description="الأولوية: low | medium | high | urgent"),
        OpenApiParameter("limit", int, description="عدد الإشعارات (افتراضي: 50، أقصى: 200)"),
    ],
    tags=["notifications"],
)
@api_view(["GET"])
@permission_classes([IsAuthenticated])
def notification_list(request):
    try:
        limit = min(int(request.query_params.get("limit", 50)), 200)
    except ValueError:
        limit = 50

    qs = InAppNotification.objects.filter(user=request.user).order_by("-created_at")

    # ── فلترة ──────────────────────────────────────────────────────────
    unread_only = request.query_params.get("unread", "").lower() == "true"
    if unread_only:
        qs = qs.filter(is_read=False)

    if event_type := request.query_params.get("event_type"):
        qs = qs.filter(event_type=event_type)

    if priority := request.query_params.get("priority"):
        qs = qs.filter(priority=priority)

    unread_count = InAppNotification.objects.filter(user=request.user, is_read=False).count()

    return Response(
        {
            "unread_count": unread_count,
            "results": InAppNotificationSerializer(qs[:limit], many=True).data,
        }
    )


@extend_schema(
    summary="تحديد إشعار مقروءاً",
    tags=["notifications"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_mark_read(request, notif_id):
    notif = get_object_or_404(InAppNotification, id=notif_id, user=request.user)
    notif.mark_read()
    return Response({"status": "read"})


@extend_schema(
    summary="تحديد كل الإشعارات مقروءة",
    tags=["notifications"],
)
@api_view(["POST"])
@permission_classes([IsAuthenticated])
def notification_mark_all_read(request):
    from django.utils import timezone

    count = InAppNotification.objects.filter(user=request.user, is_read=False).update(
        is_read=True, read_at=timezone.now()
    )
    return Response({"marked": count})


@extend_schema(
    summary="تفضيلات الإشعارات",
    tags=["notifications"],
)
class NotificationPreferencesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = UserNotificationPreference.objects.get_or_create(user=request.user)
        return Response(UserNotificationPreferenceSerializer(prefs).data)

    def patch(self, request):
        prefs, _ = UserNotificationPreference.objects.get_or_create(user=request.user)
        serializer = UserNotificationPreferenceSerializer(prefs, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


# ══════════════════════════════════════════════════════════════════════
#  KPIs — مؤشرات الأداء
# ══════════════════════════════════════════════════════════════════════


@extend_schema(
    summary="مؤشرات الأداء الرئيسية (KPIs)",
    parameters=[OpenApiParameter("year", str, description="السنة الدراسية")],
    tags=["analytics"],
)
@api_view(["GET"])
@permission_classes([IsSchoolAdmin])
def kpi_list(request):
    from analytics.services import KPIService

    school = _school(request)
    year = _year(request)
    return Response(KPIService.compute(school=school, year=year))


# ══════════════════════════════════════════════════════════════════════
#  Parent Portal — بوابة ولي الأمر
# ══════════════════════════════════════════════════════════════════════


@extend_schema(
    summary="قائمة الأبناء لولي الأمر",
    parameters=[OpenApiParameter("year", str, description="السنة الدراسية")],
    tags=["parent"],
)
@api_view(["GET"])
@permission_classes([IsParentOrAdmin])
def parent_children(request):
    from parents.services import ParentService

    school = request.user.get_school()
    year = _year(request)
    children = ParentService.get_children_data(request.user, school, year)

    result = []
    for child in children:
        enr = child.get("enrollment")
        result.append(
            {
                "student": UserSafeSerializer(child["student"]).data,
                "class_name": str(enr.class_group) if enr else None,
                "total_subj": child["total_subj"],
                "passed": child["passed"],
                "failed": child["failed"],
                "incomplete": child["incomplete"],
                "absent_30": child["absent_30"],
                "late_30": child["late_30"],
                "can_view_grades": child["link"].can_view_grades,
                "can_view_attendance": child["link"].can_view_attendance,
            }
        )

    return Response(result)


@extend_schema(
    summary="درجات ابن ولي الأمر",
    parameters=[OpenApiParameter("year", str, description="السنة الدراسية")],
    tags=["parent"],
)
@api_view(["GET"])
@permission_classes([IsParentOrAdmin])
def parent_child_grades(request, student_id):
    from parents.services import ParentService

    school = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)

    link = ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).first()
    if not link and not request.user.is_superuser:
        return Response({"detail": "غير مسموح"}, status=status.HTTP_403_FORBIDDEN)
    if link and not link.can_view_grades:
        return Response({"detail": "ليس لديك صلاحية عرض الدرجات"}, status=status.HTTP_403_FORBIDDEN)

    year = _year(request)
    data = ParentService.get_student_grades(student, school, year)
    annual = data["annual_results"]

    # ⚡ Pre-fetch semester results لتجنب N+1 queries
    from assessments.models import StudentSubjectResult

    semester_results = StudentSubjectResult.objects.filter(
        student=student, setup__in=[a.setup_id for a in annual]
    ).select_related("setup__subject")  # تجنب N+1 عند الوصول لاسم المادة
    semester_map = {(r.student_id, r.setup_id, r.semester): r for r in semester_results}

    return Response(
        {
            "student": UserSafeSerializer(student).data,
            "year": year,
            "total": data["total"],
            "passed": data["passed"],
            "failed": data["failed"],
            "avg": data["avg"],
            "subjects": AnnualSubjectResultSerializer(
                annual, many=True, context={"semester_map": semester_map}
            ).data,
        }
    )


@extend_schema(
    summary="غياب ابن ولي الأمر",
    parameters=[
        OpenApiParameter("days", int, description="عدد الأيام (افتراضي: 30)"),
    ],
    tags=["parent"],
)
@api_view(["GET"])
@permission_classes([IsParentOrAdmin])
def parent_child_attendance(request, student_id):
    from parents.services import ParentService

    school = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)

    link = ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).first()
    if not link and not request.user.is_superuser:
        return Response({"detail": "غير مسموح"}, status=status.HTTP_403_FORBIDDEN)
    if link and not link.can_view_attendance:
        return Response({"detail": "ليس لديك صلاحية عرض الغياب"}, status=status.HTTP_403_FORBIDDEN)

    try:
        days = max(1, min(int(request.query_params.get("days", 30)), 365))
    except ValueError:
        days = 30

    data = ParentService.get_student_attendance(student, school, days)
    return Response(
        {
            "student": UserSafeSerializer(student).data,
            "since": data["since"],
            "days": days,
            "total": data["total"],
            "present": data["present"],
            "absent": data["absent"],
            "late": data["late"],
            "att_pct": data["att_pct"],
        }
    )


# ══════════════════════════════════════════════════════════════════════
#  Library — المكتبة (مع django-filter + SearchFilter + OrderingFilter)
# ══════════════════════════════════════════════════════════════════════


class LibraryBookListView(generics.ListAPIView):
    """
    GET /api/v1/library/books/

    الفلترة:
      ?search=تاريخ       ← بحث في العنوان والمؤلف
      ?book_type=PRINT    ← PRINT | DIGITAL | PERIODICAL
      ?available=true     ← الكتب المتاحة فقط
      ?category=علوم      ← التصنيف

    الفرز:
      ?ordering=title | -title | author | available_qty | -available_qty
    """

    serializer_class = LibraryBookSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_class = BookFilter
    search_fields = ["title", "author", "isbn", "category"]
    ordering_fields = ["title", "author", "available_qty", "book_type"]
    ordering = ["title"]

    @extend_schema(
        summary="قائمة كتب المكتبة",
        tags=["library"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        return LibraryBook.objects.filter(school=school)


class BorrowingListView(generics.ListAPIView):
    """
    GET /api/v1/library/borrowings/

    الفلترة:
      ?status=BORROWED | RETURNED | OVERDUE | LOST
      ?student_id=<uuid>
      ?overdue=true

    الفرز:
      ?ordering=-borrow_date | due_date | status
    """

    serializer_class = BookBorrowingSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = BorrowingFilter
    ordering_fields = ["borrow_date", "due_date", "status"]
    ordering = ["-borrow_date"]

    @extend_schema(
        summary="سجل استعارات الكتب",
        tags=["library"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        return BookBorrowing.objects.filter(book__school=school).with_details()


# ══════════════════════════════════════════════════════════════════════
#  Clinic — زيارات العيادة (مع django-filter + OrderingFilter)
# ══════════════════════════════════════════════════════════════════════


class ClinicVisitListView(generics.ListAPIView):
    """
    GET /api/v1/clinic/visits/

    الفلترة:
      ?student_id=<uuid>
      ?sent_home=true
      ?parent_notified=false
      ?date_from=YYYY-MM-DD&date_to=YYYY-MM-DD

    الفرز:
      ?ordering=-visit_date | student__full_name
    """

    serializer_class = ClinicVisitSerializer
    permission_classes = [IsSchoolAdmin]
    pagination_class = StandardPagination
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_class = ClinicVisitFilter
    ordering_fields = ["visit_date", "student__full_name", "is_sent_home"]
    ordering = ["-visit_date"]

    @extend_schema(
        summary="سجل زيارات العيادة",
        tags=["clinic"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        return ClinicVisit.objects.filter(school=school).with_details()
