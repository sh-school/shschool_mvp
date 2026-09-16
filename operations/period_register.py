"""كشفُ الحصص — رصدُ مشرف الجناح حصّةً حصّة، وما يترتّب على كلّ رصد.

## لِمَ الحصّةُ لا اليوم

المشرفُ يدخل الفصلَ في كلّ حصّة (قرارُ 2026-09-13): الأولى قبل نهايتها، والبقيّةَ
في بدايتها. والطالبُ يغيب في الأولى ويصل في الثالثة، ويخرج إلى العيادة في الخامسة —
فحالةٌ واحدةٌ لليوم لا تحمل ذلك. وكانت شاشةُ «الموجة الواحدة» تكتب حالةً في الحصص
السبع، فأُزيلت. وأُزيل بعدها زرُّ «انسخ الحصّةَ الأولى إلى التالية» (قرارُ
2026-09-13): كلُّ حصّةٍ دخولٌ إلى الفصل، والنسخُ يُغري بتركه.

## ما يقع عند تثبيت حصّة

- كلُّ طالبٍ لم يُلمس **حاضر** — الحصّةُ تبدأ «الكلُّ حاضر».
- **«متأخّر»**: دقائقُه تُحسب تلقائيّاً من بدء الحصّة إلى **لحظة النقرة** على
  «متأخّر» — لا لحظة التثبيت: من نُقر في 07:20 وثُبّتت حصّتُه في 07:30 تأخّر عشراً لا
  عشرين. وإن غابت لحظةُ النقرة أو خرجت عن الحصّة فلحظةُ التثبيت. وهذا في نافذة الحصّة
  (من بدئها حتى خمس دقائق بعد نهايتها)؛ وخارجَها — تصحيحُ حصّةٍ مضت — يُكتب الرقمُ
  بيد المشرف.
  وبعد **خمس دقائق** تُنشأ مخالفةُ التأخّر (1-01) نافذةً.
- **«غائب» بعد حضورٍ في حصّةٍ سابقةٍ من اليوم**: هروبٌ من الحصّة (2-02) بمادّتها،
  ما لم يكن «أين الطالب» عيادةً أو نشاطاً أو خروجاً بإذن. ومن لم يأتِ أصلاً غائبٌ
  لا هارب.
- **التصحيحُ يُصحّح**: إن عُدّلت الحالةُ فزال سببُ مخالفةٍ أنشأها الرصدُ أُزيلت، ولا
  يُمسّ ما كتبه أحدٌ بيده.
- **«أين الطالب» للغائب وحدَه**: الحاضرُ والمتأخّرُ في فصلهما — فلا «حاضر · في العيادة».

## ما يأتي المشرفَ جاهزاً من المعلّم (`prefill_of`)

يُقرأ عند العرض ولا يُكتب قبل التثبيت، وترتيبُه: **ما رصده المشرف** ← **خروجٌ لم
يعد صاحبُه** ← **نقرةُ «دخل متأخّراً»** ← حاضر.

- **خرج بإذن المعلّم ولم يعد**: «غائب» بمكانه (العيادة، وإلّا «خرج بإذن») وعلامةِ
  «بإذن المعلّم». والنموذجُ يحمل رقمَ الخروج الذي رآه المشرف (`o-<طالب>`)، فيُحفظ
  على السطر (`StudentAttendance.exit`) أيّاً كان ما اختاره — قبِل الغيابَ أو بدّله.
- **دورةُ المياه والحصّةُ جارية**: «حاضر» بشارة «في دورة المياه منذ …».
- **خروجٌ بعد رصد المشرف**: خانتُه «حاضر» أو «متأخّر» لم تحسبه — فتُفتح «غائباً بإذن»
  كأنّها لم تُرصد، ويبقى للمشرف أن يُبقيه حاضراً وهو يراه (فيُحفظ رقمُ الخروج). وغيابٌ
  قاله المشرفُ بنفسه يبقى، والخروجُ شارة.
- **ما بعد التثبيت**: خروجٌ لم يره المشرفُ ولم يعد صاحبُه حتى الجرس يُقلب غياباً
  بإذن في الحصّة المثبّتة (`exit_reflection`) بسجلّ مراجعة، والعودةُ قبل الجرس تُرجع
  الغيابَ المشتقَّ منه حاضراً.

## والفائتة

الحصّةُ التي لم تُثبَّت حتى خمس دقائق بعد نهايتها (`PERIOD_RECORDING_GRACE_MINUTES`)
**فائتة**، وتبقى «لم تُرصد» — لا تُسحب إليها حالةٌ سابقة. ومحاسبةُ المشرف عليها
للنائب الإداريّ. وإن ثُبّتت بعدها صارت «ثُبّتت متأخّرة» وبقيت كذلك.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from operations.absence_policy import PERIOD_RECORDING_GRACE_MINUTES
from operations.day_attendance import SOURCE, enrolled_of
from operations.models import PeriodConfirmation, Session, StudentAttendance
from operations.tardiness import is_period_tardy, minutes_after_start

if TYPE_CHECKING:
    from operations.class_exit import Away

STATES = ("present", "absent", "late")
ATTENDED = ("present", "late")

#: مصدرُ نقرة المعلّم «دخل متأخّراً» — قبل تثبيت المشرف.
TEACHER_LATE = "teacher_late"

#: «أين الطالب» التي يُعذر بها الغيابُ عن الفصل — فلا يُعدّ هروباً.
#: و«خرج دون إذن» ليس منها: هو الهروبُ نفسُه.
AWAY_WITH_LEAVE = ("clinic", "activity", "out_permit", "left_early")
WHEREABOUTS = ("", "clinic", "activity", "out_permit", "out_no_permit", "left_early")

GRACE = dt.timedelta(minutes=PERIOD_RECORDING_GRACE_MINUTES)


@dataclass
class Period:
    """خانةٌ من يوم الشعبة — حصّةٌ أو زوجُ اختيارٍ في الساعة نفسِها."""

    number: int
    start: dt.time
    end: dt.time
    sessions: list
    confirmation: PeriodConfirmation | None = None

    @property
    def subjects(self) -> str:
        names = [s.subject.name_ar for s in self.sessions if s.subject_id]
        return " / ".join(dict.fromkeys(names)) or "حصّة"

    @property
    def key(self) -> str:
        return f"{self.start:%H:%M}"

    def deadline(self, day: dt.date) -> dt.datetime:
        return timezone.make_aware(dt.datetime.combine(day, self.end)) + GRACE

    def in_window(self, day: dt.date, now: dt.datetime) -> bool:
        """نافذةُ الحصّة: من بدئها حتى خمس دقائق بعد نهايتها."""
        start = timezone.make_aware(dt.datetime.combine(day, self.start))
        return start <= now <= self.deadline(day)

    def status(self, day: dt.date, now: dt.datetime) -> str:
        """confirmed · confirmed_late · current · missed · upcoming."""
        if self.confirmation is not None:
            return "confirmed_late" if self.confirmation.confirmed_late else "confirmed"
        if self.in_window(day, now):
            return "current"
        if now > self.deadline(day):
            return "missed"
        return "upcoming"


def periods_of(class_group, day: dt.date) -> list[Period]:
    """خاناتُ الشعبة في اليوم بترتيب الساعة، ومع كلٍّ تثبيتُها إن وُجد."""
    sessions = (
        Session.objects.filter(class_group=class_group, date=day)
        .exclude(status="cancelled")
        .select_related("subject")
        .order_by("start_time")
    )
    confirmations = {
        c.start_time: c
        for c in PeriodConfirmation.objects.filter(class_group=class_group, date=day)
    }
    periods: dict[dt.time, Period] = {}
    for session in sessions:
        period = periods.get(session.start_time)
        if period is None:
            period = periods[session.start_time] = Period(
                number=len(periods) + 1,
                start=session.start_time,
                end=session.end_time,
                sessions=[],
                confirmation=confirmations.get(session.start_time),
            )
        period.sessions.append(session)
    return list(periods.values())


def focus_period(periods: list[Period], day: dt.date, now: dt.datetime) -> Period | None:
    """الحصّةُ التي تُفتح للرصد: الجارية، وإلّا أوّلُ فائتة، وإلّا أوّلُ قادمة."""
    for wanted in ("current", "missed", "upcoming"):
        for period in periods:
            if period.status(day, now) == wanted:
                return period
    return periods[-1] if periods else None


@dataclass(frozen=True)
class Cell:
    status: str
    whereabouts: str
    late_minutes: int | None
    exit_id: object = None

    @property
    def where_label(self) -> str:
        return dict(StudentAttendance.WHEREABOUTS).get(self.whereabouts, "")


def cells_of(class_group, day: dt.date) -> dict:
    """ما رصده المشرفُ: `{student_id: {start_time: Cell}}` — وحصّتا الزوج خانةٌ واحدة."""
    rows = (
        StudentAttendance.objects.filter(
            session__class_group=class_group, session__date=day, source=SOURCE
        )
        .values_list(
            "student_id",
            "session__start_time",
            "status",
            "whereabouts",
            "late_minutes",
            "exit_id",
        )
        .order_by("session__start_time")
    )
    cells: dict = {}
    for student_id, start_time, status, where, minutes, exit_id in rows:
        cells.setdefault(student_id, {}).setdefault(
            start_time, Cell(status, where, minutes, exit_id)
        )
    return cells


def teacher_outs_of(class_group: Any, day: dt.date) -> dict:
    """من خرج بإذن المعلّم ولم يعد قبل نهاية حصّته: `{student_id: {start: Away}}`.

    يُقرأ من `ClassExit` عند الطلب — لا سطرَ حضورٍ مؤقّتاً. ويُضمّ إليه ما كُتب قديماً
    بمصدر `teacher_out` (قبل 2026-09-16)، والخروجُ الحيُّ يغلبه.
    """
    from operations.class_exit import TEACHER_OUT, Away, unreturned_of

    outs = unreturned_of(class_group, day)
    rows = StudentAttendance.objects.filter(
        session__class_group=class_group, session__date=day, source=TEACHER_OUT
    ).values_list("student_id", "session__start_time", "whereabouts")
    for student_id, start_time, where in rows:
        outs.setdefault(student_id, {}).setdefault(start_time, Away(exit=None, whereabouts=where))
    return outs


def teacher_taps_of(class_group, day: dt.date) -> dict:
    """نقراتُ المعلّمين «دخل متأخّراً» التي لم يثبّتها المشرفُ بعد: `{student_id: {start: minutes}}`.

    المعلّمُ يصل الحصّةَ قبل المشرف فيرى من دخل متأخّراً؛ ينقر، فيُسجَّل الوقتُ
    لحظتَها (قرارُ 2026-09-13). وحين يفتح المشرفُ الكشفَ تُملأ خانةُ الطالب «متأخّراً»
    بدقائق المعلّم، ويبقى له أن يبدّلها. ويُحفظ التثبيتُ بمصدر المشرف فتزول النقرة.
    """
    rows = StudentAttendance.objects.filter(
        session__class_group=class_group, session__date=day, source=TEACHER_LATE
    ).values_list("student_id", "session__start_time", "late_minutes")
    taps: dict = {}
    for student_id, start_time, minutes in rows:
        taps.setdefault(student_id, {}).setdefault(start_time, minutes)
    return taps


@dataclass(frozen=True)
class Pick:
    """ما تُفتح عليه خانةُ الطالب في الحصّة المفتوحة — والكشفُ يعرضه ولا يحسبه.

    `marker`: "" · `out` (غائبٌ من خروج المعلّم) · `late` (نقرةُ المعلّم) · `in_wing`
    (في دورة المياه والحصّةُ جارية). و`seen_exit` رقمُ الخروج الذي يُرسَل مع النموذج
    (`o-<طالب>`) فيُحفظ أنّ الرصدَ رآه. و`away_note` نصُّ الشارة.
    """

    status: str = "present"
    whereabouts: str = ""
    marker: str = ""
    tap: int | None = None
    seen_exit: str = ""
    away_note: str = ""


PRESENT = Pick()


def away_note(away: Away | None, now: dt.datetime, end: dt.datetime) -> str:
    """نصُّ شارة الخروج: «خرج 07:20 · العيادة» أو «في دورة المياه منذ 07:20».

    والسطرُ القديمُ بمصدر `teacher_out` لا لحظةَ له ولا وجهة: «خرج» وحدَها — و«بإذن
    المعلّم» يضيفها موضعُ العرض، فلا تتكرّر.
    """
    if away is None:
        return ""
    if away.left_at is None:
        return "خرج"
    moment = f"{timezone.localtime(away.left_at):%H:%M}"
    if not away.counts_as_absent(now, end):
        return f"في {away.destination_label} منذ {moment}"
    return f"خرج {moment} · {away.destination_label}"


def track_note(away: Away | None, now: dt.datetime, end: dt.datetime) -> str:
    """جملةُ الخروج في عمودٍ غيرِ المفتوح — تُعرض عنواناً للخانة ونصّاً لقارئ الشاشة.

    «خرج 07:20 · العيادة بإذن المعلّم ولم يعد»، و«في دورة المياه منذ 07:20 بإذن المعلّم»
    ما دامت الحصّةُ جارية (لم يُحكم بعد أنّه لم يعد).
    """
    note = away_note(away, now, end)
    if away is None:
        return ""
    if away.counts_as_absent(now, end):
        return f"{note} بإذن المعلّم ولم يعد"
    return f"{note} بإذن المعلّم"


def pick_for(
    cell: Cell | None, tap: int | None, away: Away | None, now: dt.datetime, end: dt.datetime
) -> Pick:
    """الأولويّة: ما رصده المشرف ← خروجٌ لم يعد صاحبُه ← نقرةُ التأخّر ← حاضر.

    و«ما رصده المشرف» رصدٌ **رأى** الخروجَ أو لم يُبقِ الطالبَ حاضراً: خانةٌ حاضرةٌ أو
    متأخّرةٌ كُتبت قبل الخروج لا تعلم به، فتُفتح كما تُفتح خانةٌ لم تُرصد — «غائب بإذن»
    برقم الخروج. فإن أبقاه المشرفُ حاضراً بعدها حُفظ أنّه رآه، ولا يُقلب عند الجرس.
    """
    note = away_note(away, now, end)
    exit_id = str(away.exit.pk) if away is not None and away.exit is not None else ""
    out_where = away.whereabouts if away is not None and away.counts_as_absent(now, end) else None
    derived = bool(exit_id) and out_where is not None
    if cell is not None:
        accounts = bool(exit_id) and str(cell.exit_id) == exit_id
        if derived and not accounts and cell.status in ATTENDED:
            return Pick("absent", out_where or "", "out", None, exit_id, note)
        # غيابٌ حسب هذا الخروجَ مشتقٌّ منه: علامتُه «out» فلا يمحوه «الكلُّ حاضر».
        marker = "out" if accounts and derived and cell.status == "absent" else ""
        return Pick(cell.status, cell.whereabouts, marker, None, exit_id if accounts else "", note)
    if out_where is not None:
        return Pick("absent", out_where, "out", None, exit_id, note)
    marker = "in_wing" if away is not None else ""
    if tap is not None:
        return Pick("late", "", "late", tap, "", note)
    return Pick("present", "", marker, None, "", note)


@dataclass(frozen=True)
class Prefill:
    picks: dict
    #: بصمةُ الخانات كما تُفتح (الحالُ والمكانُ والعلامةُ ورقمُ الخروج) — تدخل مفتاحَ
    #: مسوّدة المتصفّح، فمسوّدةٌ كُتبت قبل تبدّل الملء لا تُعيد «حاضراً» فوقه.
    fingerprint: str

    def of(self, student_id: Any) -> Pick:
        pick: Pick = self.picks.get(student_id, PRESENT)
        return pick


def period_end(day: dt.date, period: Period) -> dt.datetime:
    return timezone.make_aware(dt.datetime.combine(day, period.end))


def prefill_of(
    class_group: Any,
    day: dt.date,
    period: Period,
    now: dt.datetime,
    *,
    cells: dict | None = None,
    taps: dict | None = None,
    outs: dict | None = None,
) -> Prefill:
    """خاناتُ الحصّة المفتوحة كما تُعرض — `{student_id: Pick}` وبصمتُها."""
    import hashlib

    cells = cells_of(class_group, day) if cells is None else cells
    taps = teacher_taps_of(class_group, day) if taps is None else taps
    outs = teacher_outs_of(class_group, day) if outs is None else outs
    end = period_end(day, period)
    picks: dict = {}
    for sid in set(cells) | set(taps) | set(outs):
        pick = pick_for(
            cells.get(sid, {}).get(period.start),
            taps.get(sid, {}).get(period.start),
            outs.get(sid, {}).get(period.start),
            now,
            end,
        )
        if pick != PRESENT:
            picks[sid] = pick
    # البصمةُ من الخانات كما تُعرض لا من أرقام الخروج: خروجُ دورة المياه يبقى رقمُه
    # حين يرنّ الجرس ويتبدّل عرضُه من «حاضر» إلى «غائب بإذن» — فتتبدّل البصمةُ معه.
    seed = "|".join(
        f"{sid}:{pick.status}:{pick.whereabouts}:{pick.marker}:{pick.tap}:{pick.seen_exit}"
        for sid, pick in sorted(picks.items(), key=lambda item: str(item[0]))
    )
    return Prefill(picks, hashlib.sha256(seed.encode()).hexdigest()[:12] if seed else "0")


@transaction.atomic
def tap_late(session, student, by, now: dt.datetime | None = None) -> int:
    """نقرةُ المعلّم: الطالبُ دخل الآن متأخّراً — يُسجَّل الوقتُ ولا يُدخله المعلّم.

    لا تكتب فوق ما رصده المشرفُ (سجلُّه بمصدره يبقى)، وتُكرَّر بلا أثر (النقرةُ
    الثانيةُ لا تزيد الدقائق: الأولى هي لحظةُ الدخول). وتُرجع الدقائق.
    """
    now = now or timezone.now()
    existing = StudentAttendance.objects.filter(session=session, student=student).first()
    if existing is not None and existing.source == SOURCE:
        return existing.late_minutes or 0
    if (
        existing is not None
        and existing.source == TEACHER_LATE
        and existing.late_minutes is not None
    ):
        return existing.late_minutes
    minutes = minutes_after_start(session, timezone.localtime(now))
    StudentAttendance.objects.update_or_create(
        session=session,
        student=student,
        defaults={
            "school": session.school,
            "status": "late",
            "source": TEACHER_LATE,
            "marked_by": by,
            "late_minutes": minutes,
        },
    )
    return minutes


def absent_yesterday(class_group, day: dt.date) -> set:
    """من غاب بلا عذرٍ في آخر يومٍ دراسيٍّ قبل هذا — والغيابُ يتكرّر."""
    last = (
        Session.objects.filter(class_group=class_group, date__lt=day)
        .exclude(status="cancelled")
        .order_by("-date")
        .values_list("date", flat=True)
        .first()
    )
    if last is None:
        return set()
    return set(
        StudentAttendance.objects.filter(
            session__class_group=class_group,
            session__date=last,
            status="absent",
            excuse_type="",
        ).values_list("student_id", flat=True)
    )


@dataclass(frozen=True)
class PeriodResult:
    period: Period
    present: int
    absent: int
    late: int
    tardy_infractions: int
    escape_infractions: int

    @property
    def says(self) -> str:
        parts = [f"الحصّة {self.period.number}: غياب {self.absent} · تأخّر {self.late}"]
        if self.tardy_infractions or self.escape_infractions:
            parts.append(f"مخالفات: تأخّر {self.tardy_infractions} · هروب {self.escape_infractions}")
        return " — ".join(parts)


def _tapped(raw, day: dt.date, period: Period, now: dt.datetime) -> dt.datetime | None:
    """لحظةُ النقرة على «متأخّر» إن صدقت: بين بدء الحصّة ولحظة التثبيت.

    تأتي من المتصفّح بساعة الخادم مصحَّحة، فلا يُوثق بها إلّا في حدودها: لحظةٌ قبل بدء
    الحصّة أو بعد التثبيت عبثٌ أو ساعةٌ مختلّة، فتُترك ويُحسب من لحظة التثبيت.
    """
    try:
        moment = dt.datetime.fromtimestamp(int(float(raw)), tz=dt.UTC)
    except (TypeError, ValueError, OverflowError, OSError):
        return None
    start = timezone.make_aware(dt.datetime.combine(day, period.start))
    return moment if start <= moment <= now else None


def _clean_minutes(raw) -> int | None:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    return value if 0 <= value <= 240 else None


@transaction.atomic
def confirm_period(
    class_group, day: dt.date, start: dt.time, marks: dict, by, now: dt.datetime | None = None
) -> PeriodResult:
    """يثبّت حصّةً: يكتب حالةَ كلّ طالبٍ في حصص خانتها، ويُنشئ مخالفاتها أو يُزيلها.

    `marks`: `{student_id: {"status", "whereabouts", "late_minutes", "tapped_at", "exit"}}`
    — ومن لم يُذكر حاضر (إلّا من خرج ولم يعد). و`tapped_at` لحظةُ النقرة على «متأخّر»
    بثواني يونكس، و`exit` رقمُ الخروج الذي عُرض للمشرف في خانة الطالب.
    """
    from operations.class_exit import WHEREABOUTS_OF, close_unreturned, session_end
    from operations.exit_reflection import audit_cell_change, exit_overrides
    from operations.models import ClassExit

    now = now or timezone.now()
    periods = periods_of(class_group, day)
    period = next((p for p in periods if p.start == start), None)
    if period is None:
        raise ValueError("لا حصّةَ لهذه الشعبة في هذا الوقت")
    measured_now = period.in_window(day, now)
    end = period_end(day, period)
    # الخروجُ المفتوحُ يُغلق عند الجرس لا قبله — والتثبيتُ في بدء الحصّة لا يمسّه.
    for session in period.sessions:
        close_unreturned(session, now=now)
    earlier = cells_of(class_group, day)
    taps = teacher_taps_of(class_group, day)
    outs = teacher_outs_of(class_group, day)
    shown = {
        str(exit_.pk): exit_
        for exit_ in ClassExit.objects.filter(session__in=period.sessions).select_related("session")
    }

    tally = {"present": 0, "absent": 0, "late": 0}
    tardy = 0
    absentees = []
    for enrollment in enrolled_of(class_group):
        student = enrollment.student
        mark = marks.get(str(student.id)) or marks.get(student.id) or {}
        status = str(mark["status"]) if mark.get("status") in STATES else "present"
        where = mark.get("whereabouts") if mark.get("whereabouts") in WHEREABOUTS else ""
        away = outs.get(student.id, {}).get(period.start)
        seen = shown.get(str(mark.get("exit") or ""))
        if seen is not None and seen.student_id != student.id:
            seen = None
        exit_ = None
        if away is not None and "status" not in mark and away.counts_as_absent(now, end):
            # خرج ولم يعد ولم يقل المشرفُ فيه شيئاً: «غائبٌ بإذن» بمكانه لا «حاضر».
            status, where, exit_ = "absent", (where or away.whereabouts), away.exit
        elif seen is not None:
            # رأى المشرفُ الخروجَ في خانته: ما اختاره — غائباً أو غيرَه — يحسبه.
            exit_ = seen
        if status != "absent":
            where = ""
        if (
            exit_ is not None
            and status == "absent"
            and not (exit_.returned_at is None or exit_.returned_at >= session_end(exit_.session))
            and where == WHEREABOUTS_OF.get(exit_.destination)
        ):
            # عاد بين عرض الكشف وإرساله: الغيابُ المعروضُ كان من خروجه، وقد زال سببُه.
            audit_cell_change(
                by,
                class_group.school,
                student,
                period.sessions[0],
                before={"status": status, "whereabouts": where},
                after={"status": "present", "whereabouts": ""},
                why="عاد قبل نهاية الحصّة — قبل تثبيت الغياب المعروض",
                exit_=exit_,
            )
            status, where = "present", ""
        if (
            now >= end
            and exit_ is None
            and away is not None
            and away.exit is not None
            and exit_overrides(status, None, away.exit)
        ):
            # الحصّةُ انتهت وفي الكشف «حاضر» لم يرَ صاحبُه الخروج: لا حضورَ كاذب.
            audit_cell_change(
                by,
                class_group.school,
                student,
                period.sessions[0],
                before={"status": status, "whereabouts": where},
                after={"status": "absent", "whereabouts": away.whereabouts},
                why="خرج بإذن المعلّم ولم يعد حتى نهاية الحصّة — ولم يُعرض غياباً في الكشف المُرسَل",
                exit_=away.exit,
            )
            status, where, exit_ = "absent", away.whereabouts, away.exit
        if status == "absent":
            absentees.append(student)
        minutes = None
        if status == "late":
            tapped = _tapped(mark.get("tapped_at"), day, period, now)
            before = earlier.get(student.id, {}).get(period.start)
            if not measured_now:
                minutes = _clean_minutes(mark.get("late_minutes"))
            elif (
                tapped is None
                and before
                and before.status == "late"
                and before.late_minutes is not None
            ):
                # متأخّرٌ من تثبيتٍ سابقٍ لم يُنقر ثانيةً: دقائقُه باقية — التثبيتُ الثاني
                # بعد عشر دقائق لا يزيده عشراً.
                minutes = before.late_minutes
            elif tapped is None and taps.get(student.id, {}).get(period.start) is not None:
                # نقرةُ المعلّم قبل وصول المشرف: لحظةُ الدخول عندها لا عند التثبيت.
                minutes = taps[student.id][period.start]
            else:
                minutes = minutes_after_start(period.sessions[0], timezone.localtime(tapped or now))
        tally[status] += 1

        for session in period.sessions:
            StudentAttendance.objects.update_or_create(
                session=session,
                student=student,
                defaults={
                    "school": class_group.school,
                    "status": status,
                    "source": SOURCE,
                    "marked_by": by,
                    "whereabouts": where,
                    "late_minutes": minutes,
                    "exit": exit_,
                },
            )
        wanted = {period.start} if status == "late" and is_period_tardy(minutes) else set()
        tardy += _sync_rule(
            class_group.school,
            student,
            "period_tardy",
            wanted,
            {period.start: period},
            by,
            scope=period.sessions,
        )

    confirmation, made = PeriodConfirmation.objects.get_or_create(
        class_group=class_group,
        date=day,
        start_time=period.start,
        defaults={
            "school": class_group.school,
            "end_time": period.end,
            "confirmed_by": by,
            "first_confirmed_at": now,
            "confirmed_late": now > period.deadline(day),
            "present_count": tally["present"],
            "absent_count": tally["absent"],
            "late_count": tally["late"],
        },
    )
    if not made:
        # أوّلُ تثبيتٍ ووسمُ التأخير لا يُمسّان: التثبيتُ ثانيةً يُحدّث العدَّ ومن ثبّت.
        confirmation.confirmed_by = by
        confirmation.present_count = tally["present"]
        confirmation.absent_count = tally["absent"]
        confirmation.late_count = tally["late"]
        confirmation.save(
            update_fields=[
                "confirmed_by",
                "present_count",
                "absent_count",
                "late_count",
                "confirmed_at",
            ]
        )
    escapes = sync_escapes(class_group, day, by)
    _warn_of_gates(class_group.school, absentees, day)
    return PeriodResult(period, tally["present"], tally["absent"], tally["late"], tardy, escapes)


def _warn_of_gates(school, absentees, day: dt.date) -> None:
    """إنذاراتُ عتبات الغياب لمن غاب في هذه الحصّة — كما كان يفعل رصدُ المعلّم.

    كان `check_absence_threshold` يُستدعى من رصد المعلّم القديم وحدَه، فلمّا انتقل
    الرصدُ إلى كشف الأجنحة لم يُنشأ تنبيهٌ ولم يُبلَّغ وليُّ أمرٍ (اكتُشف 2026-09-13).
    وهو يعدّ أيّامَ تمدرسٍ لا حصصاً، ولا يكرّر إنذاراً — فاستدعاؤه بعد كلّ حصّةٍ آمن،
    ويُنذر حين تكتمل حصصُ اليوم الغائب.
    """
    from operations.services import AttendanceService

    for student in absentees:
        AttendanceService.check_absence_threshold(student, school, on=day)


RULE_TEXT = {
    "period_tardy": "تأخّرٌ عن الحصّة بعد خمس دقائق من بدئها",
    "class_escape": "هروبٌ من الحصّة بين حضورين",
    "school_escape": "هروبٌ من المدرسة: غيابٌ بعد الحضور حتى آخر حصّةٍ في اليوم",
}


def _codes() -> dict:
    from behavior.conduct_2026 import CLASS_ESCAPE_CODE, PERIOD_TARDY_CODE, SCHOOL_ESCAPE_CODE

    return {
        "period_tardy": PERIOD_TARDY_CODE,
        "class_escape": CLASS_ESCAPE_CODE,
        "school_escape": SCHOOL_ESCAPE_CODE,
    }


def _sync_rule(school, student, rule, wanted_starts, periods_by_start, by, *, scope) -> int:
    """يجعل مخالفاتِ `rule` الآليّةَ لهذا الطالب في `scope` مطابقةً لـ`wanted_starts`.

    يُنشئ الناقصَ ويُزيل ما زال سببُه — ولا يُمسّ ما كتبه أحدٌ بيده (`auto_rule` فارغ).
    ويُرجع عددَ ما أُنشئ.
    """
    from behavior.conduct_2026 import BY_CODE
    from behavior.models import BehaviorInfraction, ViolationCategory
    from behavior.services import BehaviorService

    existing = {
        infraction.session.start_time: infraction
        for infraction in BehaviorInfraction.objects.filter(
            student=student, session__in=scope, auto_rule=rule
        ).select_related("session")
    }
    for start, infraction in existing.items():
        if start not in wanted_starts:
            infraction.delete()

    code = _codes()[rule]
    category = ViolationCategory.objects.filter(code=code, is_active=True).first()
    if category is None:
        return 0
    made = 0
    for start in sorted(set(wanted_starts) - set(existing)):
        period = periods_by_start[start]
        BehaviorService.create_infraction(
            school=school,
            student=student,
            reporter=by,
            level=BY_CODE[code].degree,
            description=f"{RULE_TEXT[rule]} — {period.subjects} ({period.key})",
            violation_category=category,
            session=period.sessions[0],
            auto_rule=rule,
        )
        made += 1
    return made


def escapes_for(track: list) -> tuple[set, set]:
    """يحكم على يوم طالبٍ: `track` = `[(start, status, whereabouts), …]` بترتيب الساعة.

    و`status` فارغٌ للحصّة غير المثبّتة. ويُرجع (خاناتُ الهروب من الحصّة، خانةُ
    الهروب من المدرسة):

    - غيابٌ بلا إذنٍ **بين حضورين** ← هروبٌ من الحصّة لكلّ حصّة (2-02).
    - غيابٌ بلا إذنٍ بعد حضورٍ **متّصلٌ حتى آخر حصّةٍ في اليوم، وكلُّها مثبّتة** ←
      هروبٌ من المدرسة (3-10)، مخالفةٌ واحدةٌ عند أوّل حصّةٍ غابها (قرارُ المدرسة).
    - وإن تخلّلته أو تلته حصّةٌ لم تُثبَّت فـ**لم يُحسم**: قد يكون عاد. فلا يُنشأ شيء.
    - ومن لم يحضر قبلها غائبٌ لا هارب، والغائبُ بإذنٍ لا هارب.
    """
    in_class: set = set()
    in_school: set = set()
    attended = False
    streak: list = []
    unknown = False
    for start, status, where in track:
        if status in ATTENDED:
            in_class.update(streak)
            streak, unknown, attended = [], False, True
        elif not status:
            if streak:
                unknown = True
        elif status == "absent" and attended and where not in AWAY_WITH_LEAVE:
            streak.append(start)
        else:
            streak, unknown = [], False
    if streak and not unknown and track and track[-1][1]:
        in_school.add(streak[0])
    return in_class, in_school


def sync_escapes(class_group, day: dt.date, by) -> int:
    """يحكم على هروب طلاب الشعبة في يومها كلِّه بعد كلّ تثبيت — ويُرجع ما أُنشئ.

    والحكمُ على اليوم لا على الحصّة: الغيابُ في الثانية لا يُعرف أهو هروبٌ من الحصّة
    أم من المدرسة حتى تُرصد الحصصُ بعدها. فيُعاد الحكمُ مع كلّ تثبيت، ويتبدّل ما
    أنشأه الرصدُ بتبدّل الحكم.
    """
    periods = periods_of(class_group, day)
    if not periods:
        return 0
    by_start = {p.start: p for p in periods}
    confirmed = {p.start for p in periods if p.confirmation is not None}
    cells = cells_of(class_group, day)
    scope = [session for p in periods for session in p.sessions]
    made = 0
    for enrollment in enrolled_of(class_group):
        own = cells.get(enrollment.student_id, {})
        track = []
        for p in periods:
            cell = own.get(p.start) if p.start in confirmed else None
            track.append((p.start, cell.status if cell else "", cell.whereabouts if cell else ""))
        in_class, in_school = escapes_for(track)
        for rule, wanted in (("class_escape", in_class), ("school_escape", in_school)):
            made += _sync_rule(
                class_group.school,
                enrollment.student,
                rule,
                wanted,
                by_start,
                by,
                scope=scope,
            )
    return made
