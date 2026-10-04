"""خروجُ الطالب من الفصل بإذن المعلّم — النقرتان، وكيف يبلغ أثرُهما كشفَ المشرف.

- **«خرج بإذن»**: سطرُ `ClassExit` بلحظته ووجهته، ولا يُكتب في سجلّ الحضور شيءٌ
  قبل تثبيت المشرف: التقريرُ اليوميّ وملفُّ الغياب وحكمُ اليوم تقرأ السجلَّ بكلّ
  مصادره، فسطرٌ مؤقّتٌ كان سيظهر غياباً لم يثبّته أحد.
- **«عاد»**: يُغلق السطرَ بلحظة العودة. وإن عاد قبل الجرس وكان المشرفُ قد ثبّته
  غائباً **من هذا الخروج** رجع حاضراً تلقائيّاً، بسطرٍ في سجلّ المراجعة.
- **ملءُ الكشف عند القراءة** (`period_register.prefill_of`): من لم يعد يُعرض للمشرف
  «غائباً» بمكانه — العيادة أو «خرج بإذن» — بعلامة «بإذن المعلّم»، فتثبيتُه بلا
  تغييرٍ يحفظه كذلك ولا يُحسب هارباً (`AWAY_WITH_LEAVE`). ودورةُ المياه داخلَ الجناح:
  تبقى «حاضراً» بشارةٍ ما دامت الحصّةُ جاريةً.
- **نهايةُ الحصّة** (`exit_reflection.finalize_exits_for_day`، مهمّةٌ مجدولة): يُغلق
  الخروجُ المفتوحُ عند الجرس، ومن لم يعد في حصّةٍ مثبّتةٍ حاضراً دون أن يرى المشرفُ
  خروجَه يُكتب «غائباً بإذن» — بسجلّ مراجعة. ولا يُغلق خروجٌ قبل نهاية حصّته أبداً.

المعلّمُ لا يُدخل وقتاً: اللحظاتُ كلُّها من النقرة (قرارُ 2026-09-13).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from operations.models import ClassExit, DailyExitTally

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser
    from operations.models import Session

#: وجهاتٌ تُخرج الطالبَ من الجناح فيحتاج بطاقةَ المشرف — فيُشعَر فوراً (قرارُ 2026-09-14).
#: دورةُ المياه داخل الجناح، بلا إشعار.
NOTIFY_SUPERVISOR_FOR = ("clinic", "admin")

#: الوجهةُ التي لا تُغيّب الطالبَ ما دامت الحصّةُ جارية — داخلَ الجناح ودقائقُها قليلة
#: (قرارُ 2026-09-16). فإن بقي خارجاً حتى الجرس حُسب غائباً بإذن.
IN_WING = "restroom"

#: وجهةُ الخروج → «أين الطالب» في سجلّ الحضور لمن لم يعد.
WHEREABOUTS_OF = {
    "clinic": "clinic",
    "admin": "out_permit",
    "restroom": "out_permit",
    "other": "out_permit",
}
#: مصدرٌ قديمٌ كان يُكتب عند التثبيت — يُقرأ ولا يُكتب بعد اليوم.
TEACHER_OUT = "teacher_out"


def open_exit(session, student) -> ClassExit | None:
    return ClassExit.objects.filter(
        session=session, student=student, returned_at__isnull=True
    ).first()


@transaction.atomic
def leave(session, student, destination: str, by, now: dt.datetime | None = None) -> ClassExit:
    """نقرةُ «خرج بإذن» — والنقرةُ الثانية على طالبٍ خارجٍ تُعيد سطرَه لا تكرّره."""
    now = now or timezone.now()
    current = open_exit(session, student)
    if current is not None:
        return current
    if is_marked_absent(session, student):
        return None  # غائبٌ وخروجٌ لا يجتمعان (أمرُ المالك 2026-10-04): الغائبُ لا يُفتح له خروج
    if destination not in dict(ClassExit.DESTINATIONS):
        destination = "other"
    exit_ = ClassExit.objects.create(
        school=session.school,
        session=session,
        student=student,
        destination=destination,
        left_at=now,
        allowed_by=by,
    )
    refresh_tally(session.school, student, session.date)
    if destination in NOTIFY_SUPERVISOR_FOR:
        _notify_supervisor(exit_)
    return exit_


def is_marked_absent(session, student) -> bool:
    """هل وسمه معلّمُ الحصّة غائباً (إدخالٌ مبدئيٌّ)؟ — رصدُ المشرف لا يمنع: تثبيتُه يُقرأ ولا يُكتب فوقه من هنا."""
    from operations.models import AttendanceEntry

    return AttendanceEntry.objects.filter(
        session=session, student=student, status="absent"
    ).exists()


def close_for_absence(session, student, now: dt.datetime | None = None) -> ClassExit | None:
    """وسمُ الطالب غائباً يُغلق خروجَه المفتوح (غائبٌ وخروجٌ لا يجتمعان) — بلا سجلّ مراجعة غيابٍ مشتقّ."""
    current = open_exit(session, student)
    if current is None:
        return None
    current.returned_at = now or timezone.now()
    current.save(update_fields=["returned_at"])
    refresh_tally(session.school, student, session.date)
    return current


def refresh_tally(school, student, day: dt.date) -> DailyExitTally:
    """يُعيد **حسابَ** ملخّص اليوم من `ClassExit` (لا يزيد فوقه): فتكرارُه لا يضاعف شيئاً (idempotent).

    العددُ سطورُ الخروج بلا `continued_from` (الامتدادُ مدّةٌ لا مرّةٌ جديدة)، والمجموعُ للأجزاء المغلقة كلِّها.
    """
    rows = list(
        ClassExit.objects.filter(student=student, session__date=day).values_list(
            "continued_from_id", "left_at", "returned_at"
        )
    )
    count = sum(1 for origin, _, _ in rows if origin is None)
    seconds = sum(
        max(0, int((back - left).total_seconds())) for _, left, back in rows if back is not None
    )
    tally, _ = DailyExitTally.objects.update_or_create(
        student=student,
        date=day,
        defaults={"school": school, "exit_count": count, "total_seconds": seconds},
    )
    return tally


def _notify_supervisor(exit_: ClassExit) -> None:
    """يُشعِر من يحمل الجناحَ اليوم (أصيلاً أو بديلاً) — الطالبُ قادمٌ إليه لبطاقة الخروج.

    الإشعارُ لا يُسقط الخروجَ إن تعذّر: نقرةُ المعلّم حقيقةٌ تُحفظ أوّلاً. والرابطُ
    يفتح عمودَ الحصّة نفسِها (`p=`)، لا الحصّةَ الجاريةَ حين يُقرأ الإشعار.
    """
    import logging

    from django.urls import reverse

    logger = logging.getLogger(__name__)
    wing = exit_.session.class_group.wing if exit_.session.class_group.wing_id else None
    holder = wing.current_supervisor(exit_.session.date) if wing is not None else None
    if holder is None:
        return
    try:
        from notifications.hub import NotificationHub

        NotificationHub.dispatch(
            event_type="class_exit",
            school=exit_.school,
            recipients=[holder],
            title=f"خروجٌ من الفصل — {exit_.student.full_name}",
            body=(
                f"{exit_.student.full_name} ({exit_.session.class_group}) خرج إلى "
                f"{exit_.get_destination_display()} الساعة {timezone.localtime(exit_.left_at):%H:%M} "
                f"بإذن {exit_.allowed_by.full_name if exit_.allowed_by else 'المعلّم'} — "
                "يحتاج بطاقةَ خروجٍ من الجناح."
            ),
            related_url=reverse("wings:record_section", args=[exit_.session.class_group_id])
            + f"?date={exit_.session.date.isoformat()}&p={exit_.session.start_time:%H:%M}",
            related_object_id=str(exit_.pk),
            sent_by=exit_.allowed_by,
        )
    except Exception as exc:  # noqa: BLE001 — الإشعارُ تابعٌ للحدث لا شرطٌ له
        logger.warning("class_exit: إشعارُ المشرف تعذّر [exit=%s]: %s", exit_.pk, exc)


@transaction.atomic
def come_back(
    session: Session,
    student: CustomUser,
    now: dt.datetime | None = None,
    by: CustomUser | None = None,
) -> ClassExit | None:
    """نقرةُ «عاد» — تُغلق الخروجَ المفتوح؛ ولا شيءَ إن لم يكن خارجاً.

    والعودةُ قبل الجرس تُرجع «حاضراً» غيابَ المشرف المشتقَّ من هذا الخروج وحدَه
    (`exit_reflection.revert_derived_absence`) — فلا غيابَ كاذبٌ على من حضر أكثرَ الحصّة.
    """
    current = open_exit(session, student)
    if current is None:
        return None
    current.returned_at = now or timezone.now()
    current.save(update_fields=["returned_at"])
    refresh_tally(session.school, student, session.date)
    if current.returned_at < session_end(session):
        from operations.exit_reflection import revert_derived_absence

        revert_derived_absence(current, by=by or current.allowed_by, why="عاد قبل نهاية الحصّة")
    return current


def session_end(session) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(session.date, session.end_time))


def is_unreturned(exit_: ClassExit) -> bool:
    """لم يعد قبل نهاية حصّته: خروجٌ مفتوح، أو عودةٌ عند الجرس أو بعده."""
    end = session_end(exit_.session)
    return exit_.left_at < end and (exit_.returned_at is None or exit_.returned_at >= end)


@transaction.atomic
def close_unreturned(session: Session, now: dt.datetime | None = None) -> int:
    """يُغلق عند نهاية الحصّة كلَّ خروجٍ بقي مفتوحاً — ويُرجع عددَها.

    لا يُغلق قبل الجرس: خروجٌ أُغلق مبكّراً يُسقط «عاد» و«إلغاء» من يد المعلّم، ويُضخّم
    دقائقَ الغياب إلى نهاية الحصّة (كان التثبيتُ في بدء الحصّة يفعل ذلك). ولا يكتب في
    سجلّ الحضور: أثرُ الخروج هناك يُقرأ عند العرض ويُحسم بالتثبيت أو بنهاية الحصّة.
    """
    end = session_end(session)
    if (now or timezone.now()) < end:
        return 0
    pending = ClassExit.objects.filter(session=session, returned_at__isnull=True, left_at__lt=end)
    students = [e.student for e in pending.select_related("student")]
    closed = pending.update(returned_at=end)
    for student in students:
        refresh_tally(session.school, student, session.date)
    following = (
        type(session)
        .objects.filter(
            class_group=session.class_group, date=session.date, start_time__gt=session.start_time
        )
        .exclude(status="cancelled")
        .order_by("start_time")
        .first()
    )
    if following is not None and students and following.start_time < _day_end_time(session):
        carry_over(following, now=now, at_bell=True)  # يمتدّ إلى الحصّة التالية حتى آخر حصّةٍ للطالب
    else:
        # آخرُ جرسٍ ولم يعد: يُغلق بعلامةٍ صريحةٍ لا صامتاً — مؤشّرُ «لم يعد» للمشرف يقرؤها.
        ClassExit.objects.filter(
            session=session, returned_at=end, continuations__isnull=True
        ).update(system_closed=True)
    return closed


@dataclass(frozen=True)
class Away:
    """خروجٌ لم يعد صاحبُه قبل نهاية حصّته — كما يُعرض في الكشف.

    `exit` فارغٌ لسطرٍ قديمٍ بمصدر `teacher_out` لا خروجَ وراءه يُقرأ.
    """

    exit: ClassExit | None
    whereabouts: str
    destination: str = ""
    left_at: dt.datetime | None = None
    still_open: bool = False

    @property
    def destination_label(self) -> str:
        return dict(ClassExit.DESTINATIONS).get(self.destination, "")

    def counts_as_absent(self, now: dt.datetime, end: dt.datetime) -> bool:
        """هل يُحسب غائباً الآن؟ — دورةُ المياه الجاريةُ لا، حتى يرنّ الجرسُ وهو خارج."""
        return not (self.destination == IN_WING and self.still_open and now < end)


def away_of(exit_: ClassExit) -> Away:
    return Away(
        exit=exit_,
        whereabouts=WHEREABOUTS_OF.get(exit_.destination, "out_permit"),
        destination=exit_.destination,
        left_at=exit_.left_at,
        still_open=exit_.returned_at is None,
    )


def unreturned_of(class_group: ClassGroup, day: dt.date) -> dict:
    """`{student_id: {start_time: Away}}` — من لم يعد قبل نهاية حصّته، باستعلامٍ واحد.

    والمفتاحُ وقتُ البدء: خروجٌ من إحدى حصّتَي زوج الاختيار يملأ خانتَهما الواحدة.
    وإن تعدّد في الخانة فالأحدثُ، والمفتوحُ يغلب ما أُغلق عند الجرس.
    """
    out: dict = {}
    exits = (
        ClassExit.objects.filter(session__class_group=class_group, session__date=day)
        .exclude(session__status="cancelled")
        .select_related("session")
        .order_by("left_at")
    )
    for exit_ in exits:
        if not is_unreturned(exit_):
            continue
        slot = out.setdefault(exit_.student_id, {})
        current = slot.get(exit_.session.start_time)
        if current is not None and current.still_open and exit_.returned_at is not None:
            continue
        slot[exit_.session.start_time] = away_of(exit_)
    return out


def root_of(exit_: ClassExit) -> ClassExit:
    """أصلُ سلسلة الامتدادات — منه يبدأ عدّادُ الخروج المتّصل عبر الحصص."""
    seen = 0
    while exit_.continued_from_id is not None and seen < 12:
        exit_ = exit_.continued_from
        seen += 1
    return exit_


@transaction.atomic
def carry_over(session: Session, now: dt.datetime | None = None, at_bell: bool = False) -> int:
    """يُرحِّل إلى هذه الحصّة خروجَ من لم يعد من حصّةٍ سبقتها اليومَ — ويُرجع عددَ الامتدادات المنشأة.

    أمرُ المالك 2026-10-04: عدّادُ الخروج يمتدّ إلى الحصص التالية حتى نهاية دوام اليوم ما لم يعد الطالب، وفي الغد يبدأ من الصفر
    (الترحيلُ في اليوم نفسه فقط). السطرُ الجديد `continued_from` أصلَه: لا يُعدّ خروجاً جديداً، وزمنُه متّصلٌ بلا ثغرة
    (يبدأ حيث انتهى أصلُه عند جرس حصّته). ومن ثُبّت غائباً بإذن في حصّته السابقة يبقى كذلك: الترحيلُ لا يكتب في سجلّ الحضور.
    وهو **مثبِّتُ التكرار**: لا ينشئ إلا للطالب الذي ليس له سطرٌ في هذه الحصّة ولا امتدادٌ لهذا الأصل.
    """
    now = now or timezone.now()
    if not at_bell and now < timezone.make_aware(
        dt.datetime.combine(session.date, session.start_time)
    ):
        return 0  # حصّةٌ لم تبدأ: لا ترحيلَ قبل أوانه (إلا عند الجرس: الإغلاقُ هو الذي يرحّل)
    earlier = ClassExit.objects.filter(
        session__class_group=session.class_group,
        session__date=session.date,
        session__start_time__lt=session.start_time,
        left_at__lt=timezone.make_aware(dt.datetime.combine(session.date, session.start_time)),
    ).select_related("session", "student")
    here = set(ClassExit.objects.filter(session=session).values_list("student_id", flat=True))
    made = 0
    pending: dict = {}
    for exit_ in earlier.order_by("left_at"):
        end = session_end(exit_.session)
        if exit_.returned_at is not None and exit_.returned_at < end:
            continue  # عاد قبل الجرس
        if ClassExit.objects.filter(continued_from=exit_).exists():
            continue
        pending[exit_.student_id] = exit_  # الأحدثُ يغلب لكلّ طالب
    for student_id, exit_ in pending.items():
        if student_id in here:
            continue
        end = session_end(exit_.session)
        if exit_.returned_at is None:
            ClassExit.objects.filter(pk=exit_.pk).update(returned_at=end)
        ClassExit.objects.create(
            school=session.school,
            session=session,
            student_id=student_id,
            destination=exit_.destination,
            left_at=end,
            allowed_by=exit_.allowed_by,
            continued_from=exit_,
        )
        made += 1
        refresh_tally(session.school, exit_.student, session.date)
    return made


@dataclass(frozen=True)
class ExitDay:
    """خروجُ طالبٍ في يومٍ: عددُ المرّات، ومجموعُ الثواني، وتفصيلُها بالحصّة والمادّة."""

    count: int
    seconds: int
    parts: list
    open_left: int = 0
    open_span: int = 0

    @property
    def label(self) -> str:
        minutes, sec = divmod(self.seconds, 60)
        return f"{minutes:02d}:{sec:02d}"


def _day_end_time(session) -> dt.time:
    """نهايةُ دوام طلاّب فصل هذه الحصّة: آخرُ حصّةٍ مجدولةٍ للفصل ذلك اليوم، مقصوصةً بنهاية اليوم الدراسيّ للمدرسة."""
    from django.db.models import Max

    from operations.attendance_policy import school_day_end
    from operations.models import Session as SessionModel

    last = (
        (
            SessionModel.objects.filter(class_group=session.class_group, date=session.date)
            .exclude(status="cancelled")
            .aggregate(last=Max("end_time"))["last"]
        )
        or session.end_time
    )
    cap = school_day_end(session.school, session.date, band=session.class_group.time_band)
    return min(last, cap) if cap else last


def day_end_of(student, day: dt.date) -> dt.datetime | None:
    """لحظةُ نهاية دوام الطالب في اليوم (آخرُ حصّةٍ مجدولةٍ لفصله بسقف نهاية اليوم الدراسيّ) أو `None` بلا حصّة."""
    session = (
        ClassExit.objects.filter(student=student, session__date=day)
        .select_related("session", "session__class_group", "session__school")
        .order_by("-session__start_time")
        .first()
    )
    if session is None:
        return None
    return timezone.make_aware(dt.datetime.combine(day, _day_end_time(session.session)))


def exit_day_summary(student, day: dt.date, now: dt.datetime | None = None) -> ExitDay:
    """**دالةُ القراءة الواحدة** لملخّص خروج الطالب في يوم — تستعملها كلُّ الشاشات.

    المخزَّنُ في `DailyExitTally` (عددُ المرّات ومجموعُ الأجزاء المغلقة)، ويُضمّ إليه الخروجُ المفتوحُ **إلى لحظة الاستعلام**
    مقصوصاً عند نهاية دوام الطالب (`day_end_of`): فمن لم يعد لا يتضخّم مجموعُه بعد الدوام، وتغلقه مهمّةُ نهاية اليوم بعلامة
    `system_closed`. وتفصيلُ كلّ خروجٍ (حصّته ومادّته) من `ClassExit` عبر `session`.
    """
    now = now or timezone.now()
    row = DailyExitTally.objects.filter(student=student, date=day).first()
    count, seconds = (row.exit_count, row.total_seconds) if row else (0, 0)
    limit = day_end_of(student, day)
    cut = min(now, limit) if limit else now
    parts: list = []
    open_left = open_span = 0
    for exit_ in (
        ClassExit.objects.filter(student=student, session__date=day)
        .select_related("session", "session__subject")
        .order_by("left_at")
    ):
        if exit_.returned_at is None:
            open_span = max(0, int((cut - exit_.left_at).total_seconds()))
            open_left = int(exit_.left_at.timestamp())
            seconds += open_span
            span = open_span
        else:
            span = max(0, int((exit_.returned_at - exit_.left_at).total_seconds()))
        subject = exit_.session.subject.name_ar if exit_.session.subject_id else ""
        parts.append((exit_.session.start_time, subject, span))
    return ExitDay(count, seconds, parts, open_left, open_span)


def exits_of_session(session) -> dict:
    """`{student_id: (open_exit | None, [exits])}` لعرض الشاشة."""
    out: dict = {}
    for exit_ in ClassExit.objects.filter(session=session).order_by("left_at"):
        current, all_ = out.setdefault(exit_.student_id, [None, []])
        all_.append(exit_)
        if exit_.returned_at is None:
            out[exit_.student_id][0] = exit_
    return out
