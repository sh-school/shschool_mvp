"""
operations/querysets.py — Custom QuerySets للعمليات المدرسية
=============================================================
"""
from __future__ import annotations

from django.db.models import Count, F, Q, QuerySet
from django.utils import timezone


class SessionQuerySet(QuerySet):
    """QuerySet لـ Session (الحصص الدراسية)."""

    def today(self) -> "SessionQuerySet":
        return self.filter(date=timezone.now().date())

    def this_week(self) -> "SessionQuerySet":
        today = timezone.now().date()
        start = today - timezone.timedelta(days=today.weekday())
        end = start + timezone.timedelta(days=4)
        return self.filter(date__gte=start, date__lte=end)

    def date_range(self, start, end) -> "SessionQuerySet":
        return self.filter(date__gte=start, date__lte=end)

    def for_teacher(self, teacher) -> "SessionQuerySet":
        return self.filter(teacher=teacher)

    def for_class(self, class_group) -> "SessionQuerySet":
        return self.filter(class_group=class_group)

    def for_subject(self, subject) -> "SessionQuerySet":
        return self.filter(subject=subject)

    def completed(self) -> "SessionQuerySet":
        return self.filter(status="completed")

    def scheduled(self) -> "SessionQuerySet":
        return self.filter(status="scheduled")

    def cancelled(self) -> "SessionQuerySet":
        return self.filter(status="cancelled")

    def in_progress(self) -> "SessionQuerySet":
        return self.filter(status="in_progress")

    def with_details(self) -> "SessionQuerySet":
        return self.select_related(
            "teacher",
            "subject",
            "class_group",
        ).prefetch_related("attendances")

    def attendance_summary(self):
        """ملخص حضور لكل حصة."""
        return self.annotate(
            present_count=Count("attendances", filter=Q(attendances__status="present")),
            absent_count=Count("attendances", filter=Q(attendances__status="absent")),
            late_count=Count("attendances", filter=Q(attendances__status="late")),
        )


class AttendanceQuerySet(QuerySet):
    """QuerySet لـ StudentAttendance."""

    def for_student(self, student) -> "AttendanceQuerySet":
        return self.filter(student=student)

    def for_class(self, class_group) -> "AttendanceQuerySet":
        return self.filter(session__class_group=class_group)

    def for_session(self, session) -> "AttendanceQuerySet":
        return self.filter(session=session)

    def present(self) -> "AttendanceQuerySet":
        return self.filter(status="present")

    def absent(self) -> "AttendanceQuerySet":
        return self.filter(status="absent")

    def late(self) -> "AttendanceQuerySet":
        return self.filter(status="late")

    def excused(self) -> "AttendanceQuerySet":
        return self.filter(status="excused")

    def unexcused(self) -> "AttendanceQuerySet":
        """غياب بدون عذر."""
        return self.filter(status="absent", excuse_type__isnull=True)

    def date_range(self, start, end) -> "AttendanceQuerySet":
        return self.filter(session__date__gte=start, session__date__lte=end)

    def last_days(self, n: int = 30) -> "AttendanceQuerySet":
        since = timezone.now().date() - timezone.timedelta(days=n)
        return self.filter(session__date__gte=since)

    def with_details(self) -> "AttendanceQuerySet":
        return self.select_related(
            "student",
            "session",
            "session__subject",
            "session__class_group",
            "recorded_by",
        )

    def absence_streak(self, student, min_days: int = 3) -> "AttendanceQuerySet":
        """
        الطالب الذي غاب min_days أيام متتالية أو أكثر.
        يُرجع سجلات الغياب فقط.
        """
        return self.for_student(student).absent().order_by("session__date")

    def rate_for_student(self, student) -> dict:
        """نسبة الحضور لطالب."""
        total = self.for_student(student).count()
        present = self.for_student(student).present().count()
        return {
            "total": total,
            "present": present,
            "absent": total - present,
            "rate": round((present / total * 100), 1) if total else 0,
        }


class AbsenceAlertQuerySet(QuerySet):

    def pending(self) -> "AbsenceAlertQuerySet":
        return self.filter(notified=False)

    def notified(self) -> "AbsenceAlertQuerySet":
        return self.filter(notified=True)

    def for_student(self, student) -> "AbsenceAlertQuerySet":
        return self.filter(student=student)

    def with_details(self) -> "AbsenceAlertQuerySet":
        return self.select_related("student", "student__profile")
