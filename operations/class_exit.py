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

from operations.models import ClassExit

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
    if destination in NOTIFY_SUPERVISOR_FOR:
        _notify_supervisor(exit_)
    return exit_


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
    return ClassExit.objects.filter(
        session=session, returned_at__isnull=True, left_at__lt=end
    ).update(returned_at=end)


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


def exits_of_session(session) -> dict:
    """`{student_id: (open_exit | None, [exits])}` لعرض الشاشة."""
    out: dict = {}
    for exit_ in ClassExit.objects.filter(session=session).order_by("left_at"):
        current, all_ = out.setdefault(exit_.student_id, [None, []])
        all_.append(exit_)
        if exit_.returned_at is None:
            out[exit_.student_id][0] = exit_
    return out
