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
from typing import TYPE_CHECKING

from django.db import transaction
from django.utils import timezone

from operations.models import ClassExit, DailyExitTally

if TYPE_CHECKING:
    from core.models import CustomUser, School
    from operations.models import Session

#: وجهاتٌ تُخرج الطالبَ من الجناح فيحتاج بطاقةَ المشرف — فيُشعَر فوراً (قرارُ 2026-09-14).
#: دورةُ المياه داخل الجناح، بلا إشعار.
NOTIFY_SUPERVISOR_FOR = ("clinic", "admin")


#: وجهةُ الخروج → «أين الطالب» في سجلّ الحضور لمن لم يعد.
WHEREABOUTS_OF = {
    "clinic": "clinic",
    "admin": "out_permit",
    "restroom": "out_permit",
    "other": "out_permit",
}


def open_exit(session: Session, student: CustomUser) -> ClassExit | None:
    return ClassExit.objects.filter(
        session=session, student=student, returned_at__isnull=True
    ).first()


@transaction.atomic
def leave(
    session: Session,
    student: CustomUser,
    destination: str,
    by: CustomUser | None,
    now: dt.datetime | None = None,
) -> ClassExit | None:
    """نقرةُ «خرج بإذن» — والنقرةُ الثانية على طالبٍ خارجٍ تُعيد سطرَه لا تكرّره."""
    now = now or timezone.now()
    current = open_exit(session, student)
    if current is not None:
        return current
    from operations.attendance_entries import teacher_marked_absent

    if teacher_marked_absent(session, student):
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


def refresh_tally(school: School, student: CustomUser, day: dt.date) -> DailyExitTally:
    """يُعيد **حسابَ** ملخّص اليوم من `ClassExit` (لا يزيد فوقه): فتكرارُه لا يضاعف شيئاً (idempotent).

    العددُ سطورُ الخروج بلا `continued_from` (الامتدادُ مدّةٌ لا مرّةٌ جديدة)، والمجموعُ للأجزاء المغلقة كلِّها.
    """
    count = 0
    seconds = 0
    by_destination: dict[str, dict[str, int]] = {}
    for exit_ in ClassExit.objects.filter(student=student, session__date=day):
        slot = by_destination.setdefault(exit_.destination, {"count": 0, "seconds": 0})
        if exit_.continued_from_id is None:
            count += 1
            slot["count"] += 1
        if exit_.returned_at is not None:
            span = max(0, int((exit_.returned_at - exit_.left_at).total_seconds()))
            seconds += span
            slot["seconds"] += span
    tally, _ = DailyExitTally.objects.update_or_create(
        student=student,
        date=day,
        defaults={
            "school": school,
            "exit_count": count,
            "total_seconds": seconds,
            "by_destination": by_destination,
        },
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
            related_url=reverse("class_grid", args=[exit_.session.class_group_id])
            + f"?date={exit_.session.date.isoformat()}",
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


def root_of(exit_: ClassExit) -> ClassExit:
    """أصلُ سلسلة الامتدادات — منه يبدأ عدّادُ الخروج المتّصل عبر الحصص."""
    for _ in range(12):
        parent = exit_.continued_from
        if parent is None:
            break
        exit_ = parent
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


def _day_end_time(session: Session) -> dt.time:
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
    result: dt.time = min(last, cap) if cap else last
    return result
