"""قراءاتُ العمليّات التي تعرضها أكثرُ من شاشة — حضورُ الطلبة وتنبيهاتُه وحصصُ المعلّم وطلباتُه.

كان عدُّ الحاضرين والغائبين يُكتب بحروفه في لوحة التحكم مرّتين (اليوم والأمس)
وفي لوحة الطالب وفي ملخّص شؤون الطلبة وفي وثيقته، وقائمةُ التنبيهات المعلّقة في
أربع لوحات. فهي هنا مرّةً — دوالُّ تُرجع QuerySet أو قاموساً ولا تكتب شيئاً.
"""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from django.db.models import Count, Q, QuerySet

from core.models.academic import ClassGroup
from core.models.school import School
from core.models.user import CustomUser

from .models import (
    AbsenceAlert,
    AbsenceExcuse,
    CompensatorySession,
    Session,
    StudentAttendance,
    TeacherAbsence,
    TeacherSwap,
)

if TYPE_CHECKING:
    from wings.scope import StudentScope


def attendance_status_counts(
    school: School, *, scope: StudentScope | None = None, **filters: Any
) -> dict[str, int]:
    """(حاضر، غائب، متأخّر، معذور، الكلّ) لسجلّات حضور المدرسة المرشَّحة — استعلامٌ واحد.

    والكلُّ كلُّ المرصود بحالاته الأربع؛ ومن يريد الحاضرَ من «حاضر + غائب + متأخّر»
    وحدها (لوحةُ التحكم) يجمعها بنفسه — فالمقامان مختلفان عمداً. والنطاقُ (`wings/scope.py`)
    يضيّق السجلّاتِ بطلبة جناح المقيَّد قبل العدّ.
    """
    records = StudentAttendance.objects.filter(school=school, **filters)
    if scope is not None:
        records = scope.narrow(records)
    counts: dict[str, int] = records.aggregate(
        total=Count("id"),
        present=Count("id", filter=Q(status="present")),
        absent=Count("id", filter=Q(status="absent")),
        late=Count("id", filter=Q(status="late")),
        excused=Count("id", filter=Q(status="excused")),
    )
    return counts


def pending_absence_alerts(
    school: School,
    *,
    order: str = "-absence_count",
    limit: int = 10,
    scope: StudentScope | None = None,
) -> QuerySet[AbsenceAlert]:
    """تنبيهاتُ الغياب المعلّقة — الأكثرُ غياباً أوّلاً افتراضاً، أو الأحدثُ (`-created_at`).

    والنطاقُ قبل الاقتطاع: عشرةُ جناحِ المشرف، لا عشرةُ المدرسةِ ثمّ يُصفّى.
    """
    pending = AbsenceAlert.objects.filter(school=school, status="pending")
    if scope is not None:
        pending = scope.narrow(pending, "student_id")
    alerts: QuerySet[AbsenceAlert] = pending.select_related("student").order_by(order)[:limit]
    return alerts


def teacher_sessions_on(school: School, teacher: CustomUser, day: date) -> QuerySet[Session]:
    """حصصُ المعلّم يومَ `day` بشعبتها ومادّتها، بترتيب بدئها."""
    sessions: QuerySet[Session] = (
        Session.objects.filter(school=school, teacher=teacher, date=day)
        .select_related("class_group", "subject")
        .order_by("start_time")
    )
    return sessions


def swap_count(school: School, *statuses: str, **filters: Any) -> int:
    """طلباتُ تبديل الحصص في المدرسة بإحدى الحالات المذكورة."""
    count: int = TeacherSwap.objects.filter(school=school, status__in=statuses, **filters).count()
    return count


def pending_excuse_count(school: School) -> int:
    """أعذارٌ أرسلها المشرفون بعد مهلة العودة — تنتظر النائبَ الإداريّ (قرارُ 2026-09-14)."""
    count: int = AbsenceExcuse.objects.filter(school=school, status="pending").count()
    return count


def pending_compensatory_count(school: School) -> int:
    count: int = CompensatorySession.objects.filter(school=school, status="pending").count()
    return count


def teacher_absence_count(school: School, day: date) -> int:
    count: int = TeacherAbsence.objects.filter(school=school, date=day).count()
    return count


def session_status_counts(school: School, day: date) -> dict[str, int]:
    """حصصُ اليوم: الكلّ، والمكتملة، والجارية — استعلامٌ واحد."""
    counts: dict[str, int] = Session.objects.filter(school=school, date=day).aggregate(
        total=Count("id"),
        completed=Count("id", filter=Q(status="completed")),
        in_progress=Count("id", filter=Q(status="in_progress")),
    )
    return counts


def chronic_absentee_count(school: School, since: date, min_days: int = 3) -> int:
    """الطلبةُ الغائبون `min_days` مرّةً فأكثر منذ `since`."""
    count: int = (
        StudentAttendance.objects.filter(school=school, status="absent", session__date__gte=since)
        .values("student_id")
        .annotate(absent_count=Count("id"))
        .filter(absent_count__gte=min_days)
        .count()
    )
    return count


def class_sessions_on(school: School, class_group: ClassGroup, day: date) -> QuerySet[Session]:
    """حصصُ الشعبة يومَ `day` بمادّتها ومعلّمها، بترتيب بدئها."""
    sessions: QuerySet[Session] = (
        Session.objects.filter(school=school, class_group=class_group, date=day)
        .select_related("subject", "teacher")
        .order_by("start_time")
    )
    return sessions


def teacher_sessions_between(
    school: School, teacher: CustomUser, start: date, end: date
) -> QuerySet[Session]:
    """حصصُ المعلّم من `start` إلى `end` شاملتين."""
    sessions: QuerySet[Session] = Session.objects.filter(
        school=school, teacher=teacher, date__gte=start, date__lte=end
    )
    return sessions
