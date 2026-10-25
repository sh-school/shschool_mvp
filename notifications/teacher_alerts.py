"""تنبيها المعلّم الصباحيّان: «خارج لم يعد» و«حصّة بلا رصد» (W-20261010-042، عصف W-037 المقترح 14).

مهمّتان مجدولتان تُنبّهان **معلّمَ الحصّة وحده** دون أن يفتح لوحته:

- `notifications.alert_teachers_unreturned_exits` — طالبٌ خرج بإذن المعلّم من حصّةٍ جاريةٍ ولم يعد خلال العتبة.
- `notifications.alert_teachers_unmarked_sessions` — حصّةٌ انتهت بلا أيّ رصدٍ حتى انقضت مهلةُ السماح، والمعلّمُ ما زال في نافذة الكتابة.

لا أولياء ولا طلبة (D-268م): المستلمُ `Session.teacher` فقط. ولا اسمَ طالبٍ في العنوان ولا النصّ.

**منعُ التكرار** — `NotificationHub.dispatch` لا يحمل مفتاحَ إلغاء تكرار ولا نغيّر واجهتَه: يُبنى المفتاح هنا
(معلّم، نوع الحدث، معرّف الكائن، اليوم) ويُفحص في `InAppNotification` **قبل** النداء باستعلامٍ واحد لكلّ مدرسة، فتكرارُ
المهمّة في الدقيقة نفسها أو بعد ساعة يترك إشعاراً واحداً. لا جدولَ جديد: الإشعارُ نفسُه هو سجلُّ ما أُرسل.

**الاستعلامات** ثابتةٌ بالنسبة لعدد الخروج والحصص (استعلامٌ للمرشَّحين واحد، وآخر للتكرار)؛ ما يزيد بعددها
هو النداءاتُ نفسُها، وكلٌّ منها إشعارٌ مقصود.

**العتبات** بالبيئة (`TEACHER_EXIT_ALERT_MINUTES`، `TEACHER_UNMARKED_GRACE_MINUTES`) لا بملفّ الإعدادات.
**الجدولة معطَّلةٌ افتراضياً** — `TEACHER_ALERTS_BEAT=1` وحدَه يُدخلها `beat_schedule` (`teacher_alerts_beat.py`)، وبعد إعادة نشر خدمة beat بأمر المالك.
"""

from __future__ import annotations

import datetime as dt
import logging
import os
from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from celery import shared_task
from django.db.models import Exists, OuterRef
from django.urls import reverse
from django.utils import timezone

from core.celery_tasks import school_rls_scope

if TYPE_CHECKING:
    from core.models import School
    from operations.models import ClassExit, Session

logger = logging.getLogger(__name__)

#: نوعا الحدث الجديدان — يُسجَّلان في `InAppNotification.EVENT_TYPES` (هجرةٌ توسيعيّة) وفي `hub.py`.
EXIT_NOT_RETURNED = "exit_not_returned"
SESSION_UNMARKED = "session_unmarked"

#: دقائقُ خروجٍ بلا عودةٍ قبل التنبيه.
DEFAULT_EXIT_MINUTES = 15
#: دقائقُ سماحٍ بعد نهاية الحصّة قبل «بلا رصد».
DEFAULT_UNMARKED_GRACE_MINUTES = 10

#: مصادرُ صفوف `StudentAttendance` التي يكتبها النظامُ نفسُه لا إنسانٌ يرصد — لا تُعدّ رصداً.
_SYSTEM_SOURCES = ("system", "teacher_out")


def _minutes(name: str, default: int, environ: Mapping[str, str] | None = None) -> int:
    """عتبةٌ بالدقائق من البيئة؛ القيمةُ غيرُ الموجبة أو المعطوبة تعود للافتراضيّ (لا عتبةَ صفر تُغرق المعلّم)."""
    raw = (environ if environ is not None else os.environ).get(name, "")
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _day_start(now: dt.datetime) -> dt.datetime:
    """بدايةُ اليوم بتوقيت الدوحة — حدُّ «اليوم» في مفتاح منع التكرار."""
    local = timezone.localtime(now)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _already_sent(
    event_type: str, pairs: set[tuple[Any, str]], now: dt.datetime
) -> set[tuple[Any, str]]:
    """أزواج (معلّم، كائن) التي أُرسل لها هذا النوعُ اليومَ — استعلامٌ واحد مهما كثرت الأزواج."""
    from notifications.models import InAppNotification

    if not pairs:
        return set()
    users = {user_id for user_id, _ in pairs}
    objects = {obj for _, obj in pairs}
    rows = InAppNotification.objects.filter(
        user_id__in=users,
        event_type=event_type,
        related_object_id__in=objects,
        created_at__gte=_day_start(now),
    ).values_list("user_id", "related_object_id")
    return {(user_id, str(obj)) for user_id, obj in rows}


def unreturned_exits(school: School, now: dt.datetime, minutes: int) -> list[ClassExit]:
    """خروجٌ مفتوحٌ في حصّةٍ جاريةٍ مضى عليه `minutes` فأكثر — استعلامٌ واحد بلا استعلامٍ لكلّ خروج."""
    from operations.models import ClassExit

    local = timezone.localtime(now)
    return list(
        ClassExit.objects.filter(
            school=school,
            returned_at__isnull=True,
            left_at__lte=now - dt.timedelta(minutes=minutes),
            session__date=local.date(),
            session__start_time__lte=local.time(),
            session__end_time__gt=local.time(),
        )
        .exclude(session__status="cancelled")
        .select_related("session", "session__class_group")
        .order_by("left_at")
    )


def unmarked_sessions(school: School, now: dt.datetime, grace_minutes: int) -> list[Session]:
    """حصصُ اليوم المنتهيةُ منذ `grace_minutes` فأكثر بلا رصدٍ — والمعلّمُ ما زال في نافذة الكتابة.

    «بلا رصد»: لا `AttendanceEntry` للحصّة ولا صفُّ `StudentAttendance` من إنسانٍ (لا من النظام ولا من اشتقاق الخروج).
    وشعبةٌ بلا طلبةٍ قيدُهم نشطٌ لا يُطلب رصدُها. والحصّةُ المؤقّتة خارجٌ: ينشئها المعلّمُ ليرصد.
    """
    from core.models import StudentEnrollment
    from operations.attendance_policy import grid_window
    from operations.models import AttendanceEntry, Session, StudentAttendance

    local = timezone.localtime(now)
    day = local.date()
    if now > grid_window(day)[1]:
        return []  # أُغلقت نافذةُ كتابة المعلّم: لا نفعَ في تنبيهٍ لا يستطيع بعده شيئاً
    cutoff = (local - dt.timedelta(minutes=grace_minutes)).time()
    if cutoff > local.time():  # تجاوز التحويلُ منتصفَ الليل
        return []
    human_rows = StudentAttendance.objects.filter(session=OuterRef("pk")).exclude(
        source__in=_SYSTEM_SOURCES
    )
    enrolled = StudentEnrollment.objects.filter(
        class_group=OuterRef("class_group"), is_active=True, enrolled_at__lte=day
    )
    return list(
        Session.objects.filter(school=school, date=day, provisional=False, end_time__lte=cutoff)
        .exclude(status="cancelled")
        .filter(Exists(enrolled))
        .exclude(Exists(AttendanceEntry.objects.filter(session=OuterRef("pk"))))
        .exclude(Exists(human_rows))
        .select_related("class_group")
        .order_by("end_time")
    )


def _class_label(session: Session) -> str:
    klass = session.class_group
    return f"{klass.get_grade_display()}/{klass.section}"


def _dispatch(
    event_type: str, school: School, session: Session, obj_id: str, title: str, body: str, url: str
) -> int:
    from notifications.hub import NotificationHub

    result = NotificationHub.dispatch(
        event_type=event_type,
        school=school,
        recipients=[session.teacher],
        title=title,
        body=body,
        related_url=url,
        related_object_id=obj_id,
    )
    return int(result.get("in_app", 0))


def alert_unreturned_exits(
    school: School, now: dt.datetime | None = None, environ: Mapping[str, str] | None = None
) -> int:
    """يُنبّه معلّمَ كلّ حصّةٍ فيها خروجٌ لم يعد — مرّةً واحدةً لكلّ (معلّم، خروج، يوم). يُرجع عددَ الإشعارات المنشأة."""
    now = now or timezone.now()
    minutes = _minutes("TEACHER_EXIT_ALERT_MINUTES", DEFAULT_EXIT_MINUTES, environ)
    exits = unreturned_exits(school, now, minutes)
    sent = _already_sent(EXIT_NOT_RETURNED, {(e.session.teacher_id, str(e.pk)) for e in exits}, now)
    created = 0
    for exit_ in exits:
        key = (exit_.session.teacher_id, str(exit_.pk))
        if key in sent:
            continue
        sent.add(key)
        session = exit_.session
        away = max(minutes, int((now - exit_.left_at).total_seconds() // 60))
        created += _dispatch(
            EXIT_NOT_RETURNED,
            school,
            session,
            str(exit_.pk),
            "طالبٌ خرج من حصّتك ولم يعد",
            f"مضى على خروج أحد طلاّب {_class_label(session)} بإذنك نحو {away} دقيقة ولم يعد — تحقّق من عودته أو بلّغ المشرف.",
            reverse("class_grid", args=[session.class_group_id])
            + f"?date={session.date.isoformat()}",
        )
    return created


def alert_unmarked_sessions(
    school: School, now: dt.datetime | None = None, environ: Mapping[str, str] | None = None
) -> int:
    """يُنبّه معلّمَ كلّ حصّةٍ انتهت بلا رصد — مرّةً لكلّ (معلّم، حصّة، يوم). يُرجع عددَ الإشعارات المنشأة."""
    from operations.services import provisional_session

    if provisional_session.enabled():
        return 0  # الرصدُ المؤقّت: حصصُ المنصّة غيرُ المعتمَدة مخفيّةٌ عن المعلّم، فلا يُنبَّه إلى ما لا يراه
    now = now or timezone.now()
    grace = _minutes("TEACHER_UNMARKED_GRACE_MINUTES", DEFAULT_UNMARKED_GRACE_MINUTES, environ)
    sessions = unmarked_sessions(school, now, grace)
    sent = _already_sent(SESSION_UNMARKED, {(s.teacher_id, str(s.pk)) for s in sessions}, now)
    created = 0
    for session in sessions:
        key = (session.teacher_id, str(session.pk))
        if key in sent:
            continue
        sent.add(key)
        created += _dispatch(
            SESSION_UNMARKED,
            school,
            session,
            str(session.pk),
            "حصّتك انتهت ولم يُرصد حضورُها",
            f"حصّة {_class_label(session)} المنتهيةُ {session.end_time:%H:%M} بلا رصد — ارصد الحضور قبل إغلاق النافذة.",
            reverse("class_grid", args=[session.class_group_id])
            + f"?date={session.date.isoformat()}",
        )
    return created


def _for_each_school(work: Any, label: str) -> dict[str, int]:
    from core.models import School
    from operations.school_days import is_school_day

    today = timezone.localdate()
    created = 0
    failed = 0
    for school in School.objects.filter(is_active=True).iterator(chunk_size=100):
        try:
            with school_rls_scope(school.id):
                if is_school_day(school, today):
                    created += work(school)
        except Exception:  # noqa: BLE001 — مدرسةٌ معطوبةٌ لا تُسقط غيرَها
            failed += 1
            logger.exception("%s: تعذّر في المدرسة %s", label, school.pk)
    return {"created": created, "failed_schools": failed}


@shared_task(name="notifications.alert_teachers_unreturned_exits")
def alert_teachers_unreturned_exits_task() -> dict[str, int]:
    """مهمّة «خارج لم يعد»: مدرسةً مدرسةً بنطاق RLS، وثابتةُ التكرار (الدورةُ الثانية لا تُنشئ شيئاً)."""
    return _for_each_school(alert_unreturned_exits, "alert_teachers_unreturned_exits")


@shared_task(name="notifications.alert_teachers_unmarked_sessions")
def alert_teachers_unmarked_sessions_task() -> dict[str, int]:
    """مهمّة «حصّة بلا رصد»: كما سابقتها."""
    return _for_each_school(alert_unmarked_sessions, "alert_teachers_unmarked_sessions")
