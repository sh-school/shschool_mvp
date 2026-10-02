"""خدمةُ شاشات رصد المعلّم الفعليّ واعتمادِه (W-20261002-020) — الحدُّ الذي تكلّمه الواجهاتُ وحدَه.

القاعدةُ في `operations.attendance_policy` والكتابةُ في `operations.attendance_entries` والقراءةُ في
`operations.attendance_selectors`؛ وهذه الخدمةُ تجمعها لطلبٍ واحد: تجلب الكائنَ بنطاق مدرسته (404 لا تسريبَ بين المدارس)،
وتنقل القرارَ إلى الوحدة المختصّة، وتُبقي الواجهةَ رقيقةً بلا ORM (سقّاطةُ الطبقات).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.shortcuts import get_object_or_404

from core.models import CustomUser
from operations.attendance_entries import (
    decide_entry,
    settle_before_supervisor_write,
    submit_entry,
)
from operations.attendance_selectors import (
    QueueItem,
    StudentLine,
    UnapprovedSession,
    approval_queue,
    student_line,
    teacher_page_context,
    unapproved_by_session,
)
from operations.models import AttendanceDecision, AttendanceEntry, Session

if TYPE_CHECKING:
    from core.models import School

# `settle_before_supervisor_write` يُصدَّر من هنا: `confirm_period` يستدعيه قبل كتابة المشرف (A11) عبر طبقة الخدمات.
__all__ = ["TeacherAttendanceService", "settle_before_supervisor_write"]

#: يُستدعى من `confirm_period` قبل كتابة المشرف: يُسوّي أثرَ رصد المعلّم (A11) — يُصدَّر من هنا ليبقى المسارُ عبر طبقة الخدمات.
#: ساعاتُ تقرير «غيرُ معتمَد»: الافتراضيُّ يوم، وما يُطلب يُحصر في هذا المدى.
REPORT_DEFAULT_HOURS = 24
REPORT_MAX_HOURS = 24 * 14
MAX_TARDINESS_MINUTES = 600


def parse_minutes(raw: str | None) -> int | None:
    """دقائقُ التأخّر من النموذج: عددٌ صحيحٌ موجبٌ معقول، وما سواه `None`."""
    try:
        value = int(raw or "")
    except ValueError:
        return None
    return value if 0 < value <= MAX_TARDINESS_MINUTES else None


def parse_hours(raw: str | None) -> float:
    """ساعاتُ التقرير من الاستعلام: رقمٌ داخل المدى، وما سواه الافتراضيّ."""
    try:
        hours = float(raw if raw is not None else REPORT_DEFAULT_HOURS)
    except ValueError:
        hours = float(REPORT_DEFAULT_HOURS)
    return float(min(max(hours, 1), REPORT_MAX_HOURS))


class TeacherAttendanceService:
    @staticmethod
    def enter(
        user: CustomUser,
        school: School,
        session_id: UUID,
        student_id: Any,
        *,
        status: str,
        minutes: str | None,
        reason: str,
    ) -> tuple[Session, StudentLine]:
        """إدخالُ المعلّم الفعليّ لطالبٍ في حصّته. الحصّةُ بنطاق المدرسة والطالبُ من شعبتها وإلّا 404؛ والمنعُ يرفعه الإدخالُ."""
        session = get_object_or_404(
            Session.objects.select_related("class_group__wing"), id=session_id, school=school
        )
        student = get_object_or_404(
            CustomUser, id=student_id, enrollments__class_group=session.class_group
        )
        submit_entry(
            user,
            session,
            student,
            status,
            tardiness_minutes=parse_minutes(minutes),
            correction_reason=reason,
        )
        return session, student_line(session, student)

    @staticmethod
    def decide(
        user: CustomUser, school: School, entry_id: UUID, *, approve: bool, reason: str
    ) -> tuple[AttendanceEntry, AttendanceDecision]:
        """اعتمادُ إدخالٍ معلَّقٍ أو رفضُه. الإدخالُ بنطاق المدرسة وإلّا 404؛ والأهليّةُ تُفحص داخل قفل الصفّ."""
        entry = get_object_or_404(
            AttendanceEntry.objects.select_related("student"), id=entry_id, school=school
        )
        decision, _created = decide_entry(user, entry, approve=approve, reason=reason)
        return entry, decision

    @staticmethod
    def queue(user: CustomUser, school: School) -> list[QueueItem]:
        return approval_queue(user, school)

    @staticmethod
    def report(school: School, raw_hours: str | None) -> tuple[list[UnapprovedSession], float]:
        hours = parse_hours(raw_hours)
        return unapproved_by_session(school, hours=hours), hours

    @staticmethod
    def page_context(user: CustomUser, session: Session) -> dict[str, Any]:
        return teacher_page_context(user, session)
