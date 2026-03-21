"""
api/filters.py — FilterSets الاحترافية للـ API
================================================
يستخدم django-filter لتوحيد الفلترة عبر جميع الـ endpoints.
كل FilterSet يُعلن الحقول المسموح بفلترتها صراحةً
(أمان: لا يتمكن المستخدم من الفلترة على حقول غير مصرَّح بها).
"""
from __future__ import annotations

import django_filters as filters
from django.db.models import Q
from django_filters.rest_framework import FilterSet

from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit
from library.models import BookBorrowing, LibraryBook
from notifications.models import InAppNotification
from operations.models import Session, StudentAttendance


# ─────────────────────────── Students ──────────────────────────────────────

class StudentFilter(FilterSet):
    """
    فلتر الطلاب — يدعم:
    - البحث الذكي: ?search=أحمد
    - الفصل: ?class_id=uuid
    - الفصل الدراسي: ?year=2025-2026
    - الجنس: ?gender=M
    """
    search = filters.CharFilter(method="filter_search", label="بحث بالاسم أو الرقم الوطني")
    class_id = filters.UUIDFilter(
        field_name="studentenrollment__class_group__id",
        label="الفصل الدراسي"
    )
    year = filters.CharFilter(
        field_name="studentenrollment__academic_year",
        label="السنة الدراسية"
    )
    gender = filters.CharFilter(field_name="profile__gender", label="الجنس")
    is_active = filters.BooleanFilter(field_name="is_active", label="نشط")

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        q = value.strip()[:100]
        return queryset.filter(
            Q(full_name__icontains=q)
            | Q(national_id__icontains=q)
        )

    class Meta:
        # لا يوجد model مباشر — يُطبَّق على CustomUser queryset
        fields = ["search", "class_id", "year", "gender", "is_active"]


# ─────────────────────────── Sessions ──────────────────────────────────────

class SessionFilter(FilterSet):
    """
    فلتر الحصص الدراسية:
    - ?date=2026-03-21
    - ?date_from=2026-03-01&date_to=2026-03-31
    - ?class_id=uuid
    - ?teacher_id=uuid
    - ?subject_id=uuid
    - ?status=completed
    """
    date = filters.DateFilter(field_name="date", label="التاريخ")
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte", label="من تاريخ")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte", label="إلى تاريخ")
    class_id = filters.UUIDFilter(field_name="class_group__id", label="الفصل")
    teacher_id = filters.UUIDFilter(field_name="teacher__id", label="المعلم")
    subject_id = filters.UUIDFilter(field_name="subject__id", label="المادة")
    status = filters.ChoiceFilter(
        choices=[
            ("scheduled", "مجدول"),
            ("in_progress", "جارٍ"),
            ("completed", "مكتمل"),
            ("cancelled", "ملغي"),
        ],
        label="الحالة"
    )

    class Meta:
        model = Session
        fields = ["date", "date_from", "date_to", "class_id", "teacher_id", "subject_id", "status"]


# ─────────────────────────── Attendance ────────────────────────────────────

class AttendanceFilter(FilterSet):
    """
    فلتر الحضور:
    - ?student_id=uuid
    - ?class_id=uuid
    - ?status=absent
    - ?date_from=...&date_to=...
    """
    student_id = filters.UUIDFilter(field_name="student__id", label="الطالب")
    class_id = filters.UUIDFilter(field_name="session__class_group__id", label="الفصل")
    status = filters.ChoiceFilter(
        choices=[
            ("present", "حاضر"),
            ("absent", "غائب"),
            ("late", "متأخر"),
            ("excused", "غياب بعذر"),
        ],
        label="الحالة"
    )
    date_from = filters.DateFilter(field_name="session__date", lookup_expr="gte", label="من تاريخ")
    date_to = filters.DateFilter(field_name="session__date", lookup_expr="lte", label="إلى تاريخ")
    session_id = filters.UUIDFilter(field_name="session__id", label="الحصة")

    class Meta:
        model = StudentAttendance
        fields = ["student_id", "class_id", "status", "date_from", "date_to", "session_id"]


# ─────────────────────────── Behavior ──────────────────────────────────────

class InfractionFilter(FilterSet):
    """
    فلتر المخالفات السلوكية:
    - ?student_id=uuid
    - ?level=3
    - ?date_from=...&date_to=...
    - ?is_resolved=false
    - ?category=C
    """
    student_id = filters.UUIDFilter(field_name="student__id", label="الطالب")
    level = filters.NumberFilter(field_name="level", label="درجة المخالفة")
    level_min = filters.NumberFilter(field_name="level", lookup_expr="gte", label="الدرجة من")
    level_max = filters.NumberFilter(field_name="level", lookup_expr="lte", label="الدرجة إلى")
    date_from = filters.DateFilter(field_name="date", lookup_expr="gte", label="من تاريخ")
    date_to = filters.DateFilter(field_name="date", lookup_expr="lte", label="إلى تاريخ")
    is_resolved = filters.BooleanFilter(field_name="is_resolved", label="محلولة")
    category = filters.CharFilter(
        field_name="violation_category__category",
        label="فئة المخالفة (A/B/C/D)"
    )
    class_id = filters.UUIDFilter(
        field_name="student__studentenrollment__class_group__id",
        label="الفصل"
    )

    class Meta:
        model = BehaviorInfraction
        fields = [
            "student_id", "level", "level_min", "level_max",
            "date_from", "date_to", "is_resolved", "category", "class_id"
        ]


# ─────────────────────────── Clinic ────────────────────────────────────────

class ClinicVisitFilter(FilterSet):
    """
    فلتر زيارات العيادة:
    - ?student_id=uuid
    - ?sent_home=true
    - ?parent_notified=false
    - ?date_from=...&date_to=...
    """
    student_id = filters.UUIDFilter(field_name="student__id", label="الطالب")
    sent_home = filters.BooleanFilter(field_name="is_sent_home", label="أُرسل للمنزل")
    parent_notified = filters.BooleanFilter(field_name="parent_notified", label="أُبلغ ولي الأمر")
    date_from = filters.DateTimeFilter(field_name="visit_date", lookup_expr="gte", label="من تاريخ")
    date_to = filters.DateTimeFilter(field_name="visit_date", lookup_expr="lte", label="إلى تاريخ")

    class Meta:
        model = ClinicVisit
        fields = ["student_id", "sent_home", "parent_notified", "date_from", "date_to"]


# ─────────────────────────── Library ───────────────────────────────────────

class BookFilter(FilterSet):
    """
    فلتر كتب المكتبة:
    - ?search=تاريخ
    - ?book_type=PRINT
    - ?available=true
    - ?category=علوم
    """
    search = filters.CharFilter(method="filter_search", label="بحث بالعنوان أو المؤلف")
    book_type = filters.ChoiceFilter(
        choices=[("PRINT", "مطبوع"), ("DIGITAL", "رقمي"), ("PERIODICAL", "دورية")],
        label="نوع الكتاب"
    )
    available = filters.BooleanFilter(method="filter_available", label="متاح للاستعارة")
    category = filters.CharFilter(field_name="category", lookup_expr="icontains", label="التصنيف")

    def filter_search(self, queryset, name, value):
        if not value:
            return queryset
        q = value.strip()[:100]
        return queryset.filter(
            Q(title__icontains=q) | Q(author__icontains=q) | Q(isbn__icontains=q)
        )

    def filter_available(self, queryset, name, value):
        if value is True:
            return queryset.filter(available_qty__gt=0)
        if value is False:
            return queryset.filter(available_qty=0)
        return queryset

    class Meta:
        model = LibraryBook
        fields = ["search", "book_type", "available", "category"]


class BorrowingFilter(FilterSet):
    """
    فلتر الاستعارات:
    - ?status=BORROWED
    - ?student_id=uuid
    - ?overdue=true
    """
    status = filters.ChoiceFilter(
        choices=[
            ("BORROWED", "قيد الإعارة"),
            ("RETURNED", "مُعاد"),
            ("OVERDUE", "متأخر"),
            ("LOST", "مفقود"),
        ],
        label="الحالة"
    )
    student_id = filters.UUIDFilter(field_name="user__id", label="الطالب")
    overdue = filters.BooleanFilter(method="filter_overdue", label="متأخر الإعادة")

    def filter_overdue(self, queryset, name, value):
        from django.utils import timezone
        if value is True:
            return queryset.filter(
                status="BORROWED",
                due_date__lt=timezone.now().date()
            )
        return queryset

    class Meta:
        model = BookBorrowing
        fields = ["status", "student_id", "overdue"]


# ─────────────────────────── Notifications ─────────────────────────────────

class NotificationFilter(FilterSet):
    """
    فلتر الإشعارات:
    - ?unread=true
    - ?event_type=behavior
    - ?priority=urgent
    """
    unread = filters.BooleanFilter(method="filter_unread", label="غير مقروء")
    event_type = filters.ChoiceFilter(
        choices=[
            ("behavior", "سلوك"),
            ("absence", "غياب"),
            ("grade", "درجات"),
            ("fail", "رسوب"),
            ("clinic", "عيادة"),
            ("sent_home", "إرسال للمنزل"),
            ("meeting", "اجتماع"),
            ("plan_update", "تحديث الخطة"),
            ("plan_deadline", "موعد الإجراء"),
            ("plan_overdue", "إجراء متأخر"),
            ("general", "عام"),
        ],
        label="نوع الحدث"
    )
    priority = filters.ChoiceFilter(
        choices=[
            ("low", "منخفض"),
            ("medium", "متوسط"),
            ("high", "عالٍ"),
            ("urgent", "عاجل"),
        ],
        label="الأولوية"
    )

    def filter_unread(self, queryset, name, value):
        if value is True:
            return queryset.filter(is_read=False)
        if value is False:
            return queryset.filter(is_read=True)
        return queryset

    class Meta:
        model = InAppNotification
        fields = ["unread", "event_type", "priority"]
