"""
api/serializers.py
━━━━━━━━━━━━━━━━━
Serializers شاملة لـ SchoolOS REST API v1

المجموعات:
  - Core:         School, User, ClassGroup, Enrollment
  - Operations:   Subject, Session, Attendance
  - Assessments:  SubjectResult, AnnualResult
  - Behavior:     BehaviorInfraction
  - Notifications: InAppNotification, UserNotificationPreference
  - Parents:      ParentStudentLink
  - Clinic:       ClinicVisit
  - Library:      LibraryBook, BookBorrowing
"""

from rest_framework import serializers

from assessments.models import (
    AnnualSubjectResult,
    StudentSubjectResult,
)
from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit
from core.models import (
    ClassGroup,
    CustomUser,
    ParentStudentLink,
    School,
    StudentEnrollment,
)
from library.models import BookBorrowing, LibraryBook
from notifications.models import InAppNotification, UserNotificationPreference
from operations.models import Session, StudentAttendance, Subject

# ══════════════════════════════════════════════════════════════════════
#  Core
# ══════════════════════════════════════════════════════════════════════


class SchoolSerializer(serializers.ModelSerializer):
    class Meta:
        model = School
        fields = ["id", "name", "code", "city", "phone", "is_active"]


class UserBriefSerializer(serializers.ModelSerializer):
    """تمثيل مختصر للمستخدم — للقوائم والروابط"""

    class Meta:
        model = CustomUser
        fields = ["id", "full_name", "national_id", "email", "phone"]


class MeSerializer(serializers.ModelSerializer):
    """ملف المستخدم الحالي + مدرسته ودوره"""

    school = serializers.SerializerMethodField()
    role = serializers.SerializerMethodField()

    class Meta:
        model = CustomUser
        fields = [
            "id",
            "full_name",
            "national_id",
            "email",
            "phone",
            "school",
            "role",
            "date_joined",
        ]

    def get_school(self, obj):
        school = obj.get_school()
        return SchoolSerializer(school).data if school else None

    def get_role(self, obj):
        m = obj.memberships.filter(is_active=True).select_related("role").first()
        return m.role.name if m else None


class ClassGroupSerializer(serializers.ModelSerializer):
    grade_display = serializers.CharField(source="get_grade_display", read_only=True)
    level_display = serializers.CharField(source="get_level_type_display", read_only=True)
    student_count = serializers.SerializerMethodField()

    class Meta:
        model = ClassGroup
        fields = [
            "id",
            "grade",
            "grade_display",
            "section",
            "level_type",
            "level_display",
            "academic_year",
            "student_count",
        ]

    def get_student_count(self, obj):
        return obj.enrollments.filter(is_active=True).count()


class StudentEnrollmentSerializer(serializers.ModelSerializer):
    student = UserBriefSerializer(read_only=True)
    class_name = serializers.CharField(source="class_group.__str__", read_only=True)

    class Meta:
        model = StudentEnrollment
        fields = ["id", "student", "class_name", "is_active", "enrolled_at"]


# ══════════════════════════════════════════════════════════════════════
#  Operations
# ══════════════════════════════════════════════════════════════════════


class SubjectSerializer(serializers.ModelSerializer):
    class Meta:
        model = Subject
        fields = ["id", "name_ar", "code"]


class SessionSerializer(serializers.ModelSerializer):
    class_group_name = serializers.CharField(source="class_group.__str__", read_only=True)
    subject_name = serializers.CharField(source="subject.name_ar", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Session
        fields = [
            "id",
            "class_group_name",
            "subject_name",
            "date",
            "start_time",
            "end_time",
            "status",
            "status_display",
        ]


class AttendanceSerializer(serializers.ModelSerializer):
    student_id = serializers.UUIDField(source="student.id", read_only=True)
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    national_id = serializers.CharField(source="student.national_id", read_only=True)
    status_display = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = StudentAttendance
        fields = [
            "id",
            "student_id",
            "student_name",
            "national_id",
            "status",
            "status_display",
            "excuse_type",
            "marked_at",
        ]


# ══════════════════════════════════════════════════════════════════════
#  Assessments
# ══════════════════════════════════════════════════════════════════════


class StudentSubjectResultSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="setup.subject.name_ar", read_only=True)
    semester_label = serializers.CharField(source="get_semester_display", read_only=True)

    class Meta:
        model = StudentSubjectResult
        fields = ["id", "subject_name", "semester", "semester_label", "total"]


class AnnualSubjectResultSerializer(serializers.ModelSerializer):
    subject_name = serializers.CharField(source="setup.subject.name_ar", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    s1_result = serializers.SerializerMethodField()
    s2_result = serializers.SerializerMethodField()

    class Meta:
        model = AnnualSubjectResult
        fields = [
            "id",
            "subject_name",
            "academic_year",
            "s1_result",
            "s2_result",
            "annual_total",
            "status",
            "status_label",
            "letter_grade",
        ]

    def get_s1_result(self, obj):
        r = StudentSubjectResult.objects.filter(
            student=obj.student, setup=obj.setup, semester="S1"
        ).first()
        return float(r.total) if r and r.total else None

    def get_s2_result(self, obj):
        r = StudentSubjectResult.objects.filter(
            student=obj.student, setup=obj.setup, semester="S2"
        ).first()
        return float(r.total) if r and r.total else None


class StudentGradeSummarySerializer(serializers.Serializer):
    """ملخص درجات طالب لسنة دراسية"""

    student = UserBriefSerializer(read_only=True)
    year = serializers.CharField()
    total_subjects = serializers.IntegerField()
    passed = serializers.IntegerField()
    failed = serializers.IntegerField()
    average = serializers.FloatField(allow_null=True)
    subjects = AnnualSubjectResultSerializer(many=True)


# ══════════════════════════════════════════════════════════════════════
#  Behavior
# ══════════════════════════════════════════════════════════════════════


class BehaviorInfractionSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    national_id = serializers.CharField(source="student.national_id", read_only=True)
    reported_by = serializers.CharField(source="reported_by.full_name", read_only=True)
    level_label = serializers.SerializerMethodField()

    class Meta:
        model = BehaviorInfraction
        fields = [
            "id",
            "student_name",
            "national_id",
            "level",
            "level_label",
            "description",
            "points_deducted",
            "reported_by",
            "date",
            "is_resolved",
        ]

    def get_level_label(self, obj):
        labels = {1: "بسيطة", 2: "متوسطة", 3: "جسيمة", 4: "شديدة"}
        return labels.get(obj.level, str(obj.level))


# ══════════════════════════════════════════════════════════════════════
#  Notifications
# ══════════════════════════════════════════════════════════════════════


class InAppNotificationSerializer(serializers.ModelSerializer):
    event_label = serializers.CharField(source="get_event_type_display", read_only=True)
    priority_label = serializers.CharField(source="get_priority_display", read_only=True)

    class Meta:
        model = InAppNotification
        fields = [
            "id",
            "title",
            "body",
            "event_type",
            "event_label",
            "priority",
            "priority_label",
            "related_url",
            "is_read",
            "read_at",
            "created_at",
        ]
        read_only_fields = ["id", "is_read", "read_at", "created_at"]


class UserNotificationPreferenceSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserNotificationPreference
        fields = [
            "in_app_enabled",
            "push_enabled",
            "whatsapp_enabled",
            "email_enabled",
            "sms_enabled",
            "event_channels",
            "quiet_hours_start",
            "quiet_hours_end",
        ]


# ══════════════════════════════════════════════════════════════════════
#  Parents
# ══════════════════════════════════════════════════════════════════════


class ParentStudentLinkSerializer(serializers.ModelSerializer):
    student = UserBriefSerializer(read_only=True)
    relationship_label = serializers.CharField(source="get_relationship_display", read_only=True)
    class_name = serializers.SerializerMethodField()

    class Meta:
        model = ParentStudentLink
        fields = [
            "id",
            "student",
            "relationship",
            "relationship_label",
            "can_view_grades",
            "can_view_attendance",
            "class_name",
        ]

    def get_class_name(self, obj):
        enr = (
            StudentEnrollment.objects.filter(student=obj.student, is_active=True)
            .select_related("class_group")
            .first()
        )
        return str(enr.class_group) if enr else None


class ChildSummarySerializer(serializers.Serializer):
    """ملخص الطالب في بوابة ولي الأمر"""

    student = UserBriefSerializer()
    class_name = serializers.CharField(allow_null=True)
    total_subj = serializers.IntegerField()
    passed = serializers.IntegerField()
    failed = serializers.IntegerField()
    incomplete = serializers.IntegerField()
    absent_30 = serializers.IntegerField()
    late_30 = serializers.IntegerField()
    can_view_grades = serializers.BooleanField()
    can_view_attendance = serializers.BooleanField()


# ══════════════════════════════════════════════════════════════════════
#  Clinic
# ══════════════════════════════════════════════════════════════════════


class ClinicVisitSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source="student.full_name", read_only=True)
    nurse_name = serializers.CharField(source="nurse.full_name", read_only=True)

    class Meta:
        model = ClinicVisit
        fields = [
            "id",
            "student_name",
            "nurse_name",
            "visit_date",
            "reason",
            "diagnosis",
            "is_sent_home",
            "parent_notified",
        ]


# ══════════════════════════════════════════════════════════════════════
#  Library
# ══════════════════════════════════════════════════════════════════════


class LibraryBookSerializer(serializers.ModelSerializer):
    type_label = serializers.CharField(source="get_book_type_display", read_only=True)

    class Meta:
        model = LibraryBook
        fields = [
            "id",
            "title",
            "author",
            "isbn",
            "category",
            "book_type",
            "type_label",
            "quantity",
            "available_qty",
        ]


class BookBorrowingSerializer(serializers.ModelSerializer):
    book_title = serializers.CharField(source="book.title", read_only=True)
    user_name = serializers.CharField(source="user.full_name", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model = BookBorrowing
        fields = [
            "id",
            "book_title",
            "user_name",
            "borrow_date",
            "due_date",
            "return_date",
            "status",
            "status_label",
            "is_overdue",
        ]

    def get_is_overdue(self, obj):
        from datetime import date

        return obj.status == "BORROWED" and obj.due_date and obj.due_date < date.today()
