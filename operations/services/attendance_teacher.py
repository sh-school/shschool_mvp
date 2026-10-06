"""خدمةُ شاشات رصد المعلّم الفعليّ واعتمادِه (W-20261002-020) — الحدُّ الذي تكلّمه الواجهاتُ وحدَه.

القاعدةُ في `operations.attendance_policy` والكتابةُ في `operations.attendance_entries` والقراءةُ في
`operations.attendance_selectors`؛ وهذه الخدمةُ تجمعها لطلبٍ واحد: تجلب الكائنَ بنطاق مدرسته (404 لا تسريبَ بين المدارس)،
وتنقل القرارَ إلى الوحدة المختصّة، وتُبقي الواجهةَ رقيقةً بلا ORM (سقّاطةُ الطبقات).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.utils import timezone

from core.models import CustomUser
from operations.attendance_entries import (
    EntryError,
    EntryRefusedError,
    correct_without_observation,
    decide_entry,
    settle_before_supervisor_write,
    submit_entry,
)
from operations.attendance_policy import can_correct, holds_leadership_role
from operations.attendance_selectors import (
    CorrectionItem,
    QueueItem,
    StudentLine,
    UnapprovedSession,
    approval_groups,
    approval_queue,
    recent_corrections,
    student_line,
    student_lines,
    teacher_page_context,
    unapproved_by_session,
)
from operations.models import AttendanceDecision, AttendanceEntry, Session
from operations.teacher_period_sheet import (
    EnterResult,
    enter_period_marks,
    late_minutes,
    next_session_of,
    parse_marks,
    teacher_sheet_context,
)

if TYPE_CHECKING:
    from core.models import School

# `settle_before_supervisor_write` يُصدَّر من هنا: `confirm_period` يستدعيه قبل كتابة المشرف (A11) عبر طبقة الخدمات.
__all__ = ["TeacherAttendanceService", "settle_before_supervisor_write"]

#: ساعاتُ تقرير «غيرُ معتمَد»: الافتراضيُّ يوم، وما يُطلب يُحصر في هذا المدى.
REPORT_DEFAULT_HOURS = 24
REPORT_MAX_HOURS = 24 * 14
MAX_TARDINESS_MINUTES = 600


def _student_of(session: Session, student_id: Any) -> CustomUser:
    """طالبٌ من قيد شعبة الحصّة: مُعرِّفٌ ليس UUID أو غريبٌ عن الشعبة ← 404، و`distinct` فقيدان لا يكرّران الصفّ."""
    try:
        wanted = UUID(str(student_id))
    except ValueError:
        raise Http404("طالبٌ غيرُ معروف") from None
    return get_object_or_404(
        CustomUser.objects.filter(enrollments__class_group=session.class_group).distinct(),
        id=wanted,
    )


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
        tapped_at: str | None = None,
    ) -> tuple[Session, StudentLine]:
        """إدخالُ المعلّم الفعليّ لطالبٍ في حصّته. الحصّةُ بنطاق المدرسة والطالبُ من شعبتها وإلّا 404؛ والمنعُ يرفعه الإدخالُ."""
        session = get_object_or_404(
            Session.objects.select_related("class_group__wing"), id=session_id, school=school
        )
        student = _student_of(session, student_id)
        typed = parse_minutes(minutes)
        if status == "late" and typed is None:  # متأخّرٌ بلا رقمٍ مكتوب: من لحظة ضغطه وبدء الحصّة آلياً
            typed = late_minutes(session, {"tapped_at": tapped_at or ""}, timezone.now())
        submit_entry(
            user,
            session,
            student,
            status,
            tardiness_minutes=typed,
            correction_reason=reason,
        )
        return session, student_line(session, student)

    @staticmethod
    def sheet(user: CustomUser, session: Session) -> dict[str, Any]:
        """سياقُ كشف المعلّم المشترك مع كشف المشرف (`attendance/period_sheet.html`)."""
        return teacher_sheet_context(user, session)

    @staticmethod
    def enter_marks(
        user: CustomUser, school: School, session_id: UUID, post: Any
    ) -> tuple[Session, EnterResult, Session | None]:
        """«ثبّتِ الحصّة» من الكشف المشترك: إدخالاتٌ مبدئيّةٌ لكلّ ما اختاره المعلّمُ (والخروجُ `ClassExit`) — يعيد التاليةَ لـ«ثبّت وانتقل»."""
        session = get_object_or_404(
            Session.objects.select_related("class_group__wing"), id=session_id, school=school
        )
        students = {
            s.id: s
            for s in CustomUser.objects.filter(
                enrollments__class_group=session.class_group, enrollments__is_active=True
            ).distinct()
        }
        result = enter_period_marks(user, session, students, parse_marks(post))
        following = next_session_of(session) if post.get("next") else None
        return session, result, following

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
    def approve_all(user: CustomUser, school: School) -> tuple[int, int]:
        """يعتمد **كلَّ** ما يملك هذا المستخدمُ قرارَه في الطابور — كلَّ الشعب وكلَّ الحصص — ويُرجع `(اعتُمد، تُخطّي)`.

        أمرُ المالك 2026-10-04: المشرفُ لا يعتمد حصّةً حصّةً لخمس شعبٍ. كلُّ إدخالٍ يمرّ بـ`decide_entry` نفسِه (الأهليّةُ والقفلُ وسجلُّ التدقيق باسم المعتمِد)
        فلا طريقَ التفافيّاً؛ وما اصطدم برصدٍ بشريٍّ آخر أو حلّت محلَّه نسخةٌ أحدث يُتخطّى ويبقى في الطابور ليُنظر فيه بنفسه. والرفضُ لا يكون جماعيّاً أبداً (يلزمه سببٌ لكلّ إدخال).
        """
        approved = skipped = 0
        for item in approval_queue(user, school):
            try:
                _decision, created = decide_entry(user, item.entry, approve=True)
            except (EntryError, EntryRefusedError):
                skipped += 1
                continue
            approved += 1 if created else 0
        return approved, skipped

    @staticmethod
    def approval_groups(user: CustomUser, school: School) -> list[Any]:
        """الطابورُ مجموعاً بالحصّة — بطاقةٌ لكلّ حصّةٍ لا لكلّ طالب."""
        return approval_groups(user, school)

    @staticmethod
    def approve_session(user: CustomUser, school: School, session_id: UUID) -> tuple[int, int]:
        """يعتمد كلَّ ما ينتظر هذا المستخدمَ في **حصّةٍ واحدة** ويُرجع `(اعتُمد، تُخطّي)`.

        كلُّ إدخالٍ بقراره المسجَّل باسمه عبر `decide_entry` نفسِه كالاعتماد الجماعيّ (الأهليّةُ والقفلُ والتدقيق)؛ وما اصطدم
        يُتخطّى ويبقى في الطابور. والرفضُ لا يكون جماعيّاً أبداً — يلزمه سببٌ لكلّ إدخال.
        """
        approved = skipped = 0
        for item in approval_queue(user, school):
            if item.entry.session_id != session_id:
                continue
            try:
                _decision, created = decide_entry(user, item.entry, approve=True)
            except (EntryError, EntryRefusedError):
                skipped += 1
                continue
            approved += 1 if created else 0
        return approved, skipped

    @staticmethod
    def report(
        user: CustomUser, school: School, raw_hours: str | None
    ) -> tuple[list[UnapprovedSession], float, list[CorrectionItem]]:
        """غيرُ المعتمَد بعد X ساعة، ومعه تصحيحاتُ المشرف الموسومةُ «دون معاينة» — لمن له عليها سلطة.

        السببُ الحرُّ لتصحيحٍ لا يراه إلّا القيادةُ أو حاملُ جناح تلك الحصّة (`can_correct`)؛ ومشرفٌ لجناحٍ آخر يرى العدّادَ
        وحدَه لا التصحيحاتِ ولا أسبابَها (حكمُ 0105).
        """
        hours = parse_hours(raw_hours)
        corrections = recent_corrections(school)
        if not holds_leadership_role(user, school.pk):
            corrections = [c for c in corrections if can_correct(user, c.row.session)]
        return unapproved_by_session(school, hours=hours), hours, corrections

    @staticmethod
    def correction_page(
        user: CustomUser, school: School, session_id: UUID
    ) -> tuple[Session, list[StudentLine]]:
        """شاشةُ تصحيح المشرف: لمن له الاعتمادُ على هذه الحصّة وإلّا رُفض بسبب السياسة."""
        session = get_object_or_404(
            Session.objects.select_related("class_group__wing"), id=session_id, school=school
        )
        verdict = can_correct(user, session)
        if not verdict:
            raise EntryRefusedError(verdict.reason)
        return session, student_lines(session)

    @staticmethod
    def correct(
        user: CustomUser,
        school: School,
        session_id: UUID,
        student_id: Any,
        *,
        status: str,
        evidence_type: str,
        reason: str,
    ) -> tuple[Session, StudentLine]:
        """تصحيحٌ دون معاينة لطالبٍ في حصّةٍ بنطاق المدرسة (404 خارجَه)."""
        session = get_object_or_404(
            Session.objects.select_related("class_group__wing"), id=session_id, school=school
        )
        student = _student_of(session, student_id)
        correct_without_observation(
            user, session, student, status, reason=reason, evidence_type=evidence_type
        )
        return session, student_line(session, student)

    @staticmethod
    def page_context(user: CustomUser, session: Session) -> dict[str, Any]:
        return teacher_page_context(user, session)
