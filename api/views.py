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

from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema, OpenApiParameter

from core.models import (
    CustomUser, ClassGroup, StudentEnrollment, ParentStudentLink,
)
from assessments.models import AnnualSubjectResult
from behavior.models import BehaviorInfraction
from notifications.models import InAppNotification, UserNotificationPreference
from operations.models import Session, StudentAttendance
from clinic.models import ClinicVisit
from library.models import LibraryBook, BookBorrowing

from .permissions import IsSchoolAdmin, IsTeacherOrAdmin, IsParentOrAdmin
from .serializers import (
    MeSerializer, UserBriefSerializer, ClassGroupSerializer,
    StudentEnrollmentSerializer, SubjectSerializer,
    SessionSerializer, AttendanceSerializer,
    AnnualSubjectResultSerializer, StudentGradeSummarySerializer,
    BehaviorInfractionSerializer, InAppNotificationSerializer,
    UserNotificationPreferenceSerializer, ParentStudentLinkSerializer,
    ChildSummarySerializer, ClinicVisitSerializer,
    LibraryBookSerializer, BookBorrowingSerializer,
)

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
#  مساعدات
# ══════════════════════════════════════════════════════════════════════

def _school(request):
    """يُعيد school للمستخدم الحالي"""
    return request.user.get_school()


def _year(request, default="2025-2026"):
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

@extend_schema(
    summary="قائمة الطلاب",
    parameters=[
        OpenApiParameter("year",  str, description="السنة الدراسية (مثال: 2025-2026)"),
        OpenApiParameter("class", str, description="معرّف الفصل (UUID)"),
        OpenApiParameter("q",     str, description="بحث بالاسم أو الرقم الوطني"),
    ],
    tags=["students"],
)
@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def student_list(request):
    school = _school(request)
    year   = _year(request)

    enrollments = (
        StudentEnrollment.objects.filter(
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        )
        .select_related("student", "class_group")
        .order_by("student__full_name")
    )

    class_id = request.query_params.get("class")
    if class_id:
        enrollments = enrollments.filter(class_group_id=class_id)

    q = request.query_params.get("q", "").strip()
    if q:
        enrollments = enrollments.filter(
            student__full_name__icontains=q
        ) | enrollments.filter(
            student__national_id__icontains=q
        )

    return Response(StudentEnrollmentSerializer(enrollments, many=True).data)


@extend_schema(
    summary="درجات طالب",
    parameters=[OpenApiParameter("year", str, description="السنة الدراسية")],
    tags=["students"],
)
@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def student_grades(request, student_id):
    school  = _school(request)
    year    = _year(request)
    student = get_object_or_404(CustomUser, id=student_id)

    annual = AnnualSubjectResult.objects.filter(
        student=student, school=school, academic_year=year
    ).select_related("setup__subject").order_by("setup__subject__name_ar")

    grades  = [float(a.annual_total) for a in annual if a.annual_total]
    average = round(sum(grades) / len(grades), 2) if grades else None

    data = {
        "student":       student,
        "year":          year,
        "total_subjects": annual.count(),
        "passed":        annual.filter(status="pass").count(),
        "failed":        annual.filter(status="fail").count(),
        "average":       average,
        "subjects":      annual,
    }
    return Response(StudentGradeSummarySerializer(data).data)


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

    school  = _school(request)
    student = get_object_or_404(CustomUser, id=student_id)

    try:
        days = int(request.query_params.get("days", 30))
    except ValueError:
        days = 30

    since = timezone.now().date() - timedelta(days=days)
    att   = StudentAttendance.objects.filter(
        student=student, session__school=school, session__date__gte=since,
    ).select_related("session__subject").order_by("-session__date")

    total   = att.count()
    absent  = att.filter(status="absent").count()
    late    = att.filter(status="late").count()
    present = att.filter(status="present").count()

    return Response({
        "student_id": str(student_id),
        "since":      since,
        "days":       days,
        "total":      total,
        "present":    present,
        "absent":     absent,
        "late":       late,
        "att_pct":    round(present / total * 100) if total else 0,
        "records":    AttendanceSerializer(att, many=True).data,
    })


# ══════════════════════════════════════════════════════════════════════
#  Classes — الفصول الدراسية
# ══════════════════════════════════════════════════════════════════════

@extend_schema(
    summary="قائمة الفصول الدراسية",
    parameters=[OpenApiParameter("year", str, description="السنة الدراسية")],
    tags=["classes"],
)
@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def class_list(request):
    school = _school(request)
    year   = _year(request)
    qs     = ClassGroup.objects.filter(
        school=school, academic_year=year
    ).prefetch_related("enrollments").order_by("grade", "section")
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
    school      = _school(request)
    year        = _year(request)
    class_group = get_object_or_404(ClassGroup, id=class_id, school=school)
    data        = ReportDataService.get_class_results(class_group, school, year)

    rows = []
    for row in data["student_rows"]:
        rows.append({
            "rank":       row["rank"],
            "student":    UserBriefSerializer(row["student"]).data,
            "avg":        row["avg"],
            "passed":     row["passed"],
            "failed":     row["failed"],
            "status":     row["status"],
            "grades":     {
                subj: {
                    "annual_total": float(ann.annual_total) if ann and ann.annual_total else None,
                    "status":       ann.status if ann else None,
                    "letter_grade": ann.letter_grade if ann else None,
                }
                for subj, ann in row["grades"].items()
            },
        })

    return Response({
        "class_group":    str(class_group),
        "year":           year,
        "total_students": data["total_students"],
        "total_passed":   data["total_passed"],
        "total_failed":   data["total_failed"],
        "subjects":       [s.name_ar for s in data["subjects"]],
        "rows":           rows,
    })


# ══════════════════════════════════════════════════════════════════════
#  Sessions & Attendance (operations) — موجودة + محسّنة
# ══════════════════════════════════════════════════════════════════════

class SessionListView(generics.ListAPIView):
    """
    GET /api/v1/sessions/ — قائمة الحصص
    ?date=YYYY-MM-DD  ?class=<id>  ?teacher=<id>
    """
    serializer_class   = SessionSerializer
    permission_classes = [IsTeacherOrAdmin]

    @extend_schema(
        summary="قائمة الحصص الدراسية",
        parameters=[
            OpenApiParameter("date",    str, description="تاريخ الحصة YYYY-MM-DD"),
            OpenApiParameter("class",   str, description="معرّف الفصل"),
            OpenApiParameter("teacher", str, description="معرّف المعلم"),
        ],
        tags=["sessions"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        qs     = Session.objects.filter(
            school=school
        ).select_related("class_group", "subject").order_by("-date", "start_time")

        if d := self.request.query_params.get("date"):
            qs = qs.filter(date=d)
        if c := self.request.query_params.get("class"):
            qs = qs.filter(class_group_id=c)
        if t := self.request.query_params.get("teacher"):
            qs = qs.filter(teacher_id=t)

        return qs


class AttendanceListView(generics.ListAPIView):
    """
    GET /api/v1/attendance/ — سجل الحضور
    ?session=<id>  ?student=<id>  ?date=YYYY-MM-DD
    """
    serializer_class   = AttendanceSerializer
    permission_classes = [IsTeacherOrAdmin]

    @extend_schema(
        summary="سجل الحضور والغياب",
        parameters=[
            OpenApiParameter("session", str, description="معرّف الحصة"),
            OpenApiParameter("student", str, description="معرّف الطالب"),
            OpenApiParameter("date",    str, description="تاريخ YYYY-MM-DD"),
        ],
        tags=["attendance"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        qs     = StudentAttendance.objects.filter(
            session__school=school
        ).select_related("student", "session__subject").order_by("-session__date")

        if s := self.request.query_params.get("session"):
            qs = qs.filter(session_id=s)
        if st := self.request.query_params.get("student"):
            qs = qs.filter(student_id=st)
        if d := self.request.query_params.get("date"):
            qs = qs.filter(session__date=d)

        return qs


# ══════════════════════════════════════════════════════════════════════
#  Behavior — المخالفات السلوكية
# ══════════════════════════════════════════════════════════════════════

@extend_schema(
    summary="قائمة المخالفات السلوكية",
    parameters=[
        OpenApiParameter("level",   int, description="مستوى المخالفة 1-4"),
        OpenApiParameter("student", str, description="معرّف الطالب"),
        OpenApiParameter("year",    str, description="السنة الدراسية"),
    ],
    tags=["behavior"],
)
@api_view(["GET"])
@permission_classes([IsTeacherOrAdmin])
def behavior_list(request):
    school = _school(request)
    qs     = BehaviorInfraction.objects.filter(
        school=school
    ).select_related("student", "reported_by").order_by("-date")

    if level := request.query_params.get("level"):
        qs = qs.filter(level=level)
    if student := request.query_params.get("student"):
        qs = qs.filter(student_id=student)

    return Response(BehaviorInfractionSerializer(qs[:200], many=True).data)


# ══════════════════════════════════════════════════════════════════════
#  Notifications — الإشعارات الداخلية
# ══════════════════════════════════════════════════════════════════════

@extend_schema(
    summary="قائمة الإشعارات الداخلية",
    parameters=[
        OpenApiParameter("unread", bool, description="true = غير مقروءة فقط"),
        OpenApiParameter("limit",  int,  description="عدد الإشعارات (افتراضي: 50)"),
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

    unread_only = request.query_params.get("unread", "").lower() == "true"

    if unread_only:
        qs = InAppNotification.objects.unread_for_user(request.user)[:limit]
    else:
        qs = InAppNotification.objects.for_user(request.user, limit=limit)

    return Response({
        "unread_count": InAppNotification.objects.unread_count(request.user),
        "results":      InAppNotificationSerializer(qs, many=True).data,
    })


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
    count = InAppNotification.objects.mark_all_read(request.user)
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
        serializer = UserNotificationPreferenceSerializer(
            prefs, data=request.data, partial=True
        )
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
    year   = _year(request)
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
    school   = request.user.get_school()
    year     = _year(request)
    children = ParentService.get_children_data(request.user, school, year)

    result = []
    for child in children:
        enr = child.get("enrollment")
        result.append({
            "student":    UserBriefSerializer(child["student"]).data,
            "class_name": str(enr.class_group) if enr else None,
            "total_subj": child["total_subj"],
            "passed":     child["passed"],
            "failed":     child["failed"],
            "incomplete": child["incomplete"],
            "absent_30":  child["absent_30"],
            "late_30":    child["late_30"],
            "can_view_grades":     child["link"].can_view_grades,
            "can_view_attendance": child["link"].can_view_attendance,
        })

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
    school  = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)

    # التحقق من الصلاحية
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
    return Response({
        "student":  UserBriefSerializer(student).data,
        "year":     year,
        "total":    data["total"],
        "passed":   data["passed"],
        "failed":   data["failed"],
        "avg":      data["avg"],
        "subjects": AnnualSubjectResultSerializer(annual, many=True).data,
    })


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
    school  = request.user.get_school()
    student = get_object_or_404(CustomUser, id=student_id)

    link = ParentStudentLink.objects.filter(
        parent=request.user, student=student, school=school
    ).first()
    if not link and not request.user.is_superuser:
        return Response({"detail": "غير مسموح"}, status=status.HTTP_403_FORBIDDEN)
    if link and not link.can_view_attendance:
        return Response({"detail": "ليس لديك صلاحية عرض الغياب"}, status=status.HTTP_403_FORBIDDEN)

    try:
        days = int(request.query_params.get("days", 30))
    except ValueError:
        days = 30

    data = ParentService.get_student_attendance(student, school, days)
    return Response({
        "student":  UserBriefSerializer(student).data,
        "since":    data["since"],
        "days":     days,
        "total":    data["total"],
        "present":  data["present"],
        "absent":   data["absent"],
        "late":     data["late"],
        "att_pct":  data["att_pct"],
    })


# ══════════════════════════════════════════════════════════════════════
#  Library — المكتبة
# ══════════════════════════════════════════════════════════════════════

class LibraryBookListView(generics.ListAPIView):
    """GET /api/v1/library/books/ — قائمة الكتب"""
    serializer_class   = LibraryBookSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="قائمة كتب المكتبة",
        parameters=[
            OpenApiParameter("q",    str, description="بحث في العنوان أو المؤلف"),
            OpenApiParameter("type", str, description="PRINT / DIGITAL / PERIODICAL"),
        ],
        tags=["library"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        qs     = LibraryBook.objects.filter(school=school).order_by("title")
        if q := self.request.query_params.get("q"):
            qs = qs.filter(title__icontains=q) | qs.filter(author__icontains=q)
        if t := self.request.query_params.get("type"):
            qs = qs.filter(book_type=t.upper())
        return qs


class BorrowingListView(generics.ListAPIView):
    """GET /api/v1/library/borrowings/ — سجل الاستعارات"""
    serializer_class   = BookBorrowingSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(
        summary="سجل استعارات الكتب",
        parameters=[
            OpenApiParameter("status", str, description="BORROWED / RETURNED / OVERDUE"),
        ],
        tags=["library"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        qs     = BookBorrowing.objects.filter(
            book__school=school
        ).select_related("book", "user").order_by("-borrow_date")
        if s := self.request.query_params.get("status"):
            qs = qs.filter(status=s.upper())
        return qs


# ══════════════════════════════════════════════════════════════════════
#  Clinic — زيارات العيادة (للممرض والمدير)
# ══════════════════════════════════════════════════════════════════════

class ClinicVisitListView(generics.ListAPIView):
    """GET /api/v1/clinic/visits/ — سجل زيارات العيادة"""
    serializer_class   = ClinicVisitSerializer
    permission_classes = [IsSchoolAdmin]

    @extend_schema(
        summary="سجل زيارات العيادة",
        parameters=[
            OpenApiParameter("student",   str,  description="معرّف الطالب"),
            OpenApiParameter("sent_home", bool, description="true = مَن أُرسل للمنزل فقط"),
        ],
        tags=["clinic"],
    )
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        school = _school(self.request)
        qs     = ClinicVisit.objects.filter(
            school=school
        ).select_related("student", "nurse").order_by("-visit_date")
        if s := self.request.query_params.get("student"):
            qs = qs.filter(student_id=s)
        if self.request.query_params.get("sent_home", "").lower() == "true":
            qs = qs.filter(is_sent_home=True)
        return qs
