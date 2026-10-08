"""
operations/day_selectors.py — مُجمِّعُ يومِ المدرسة للوحة المدير (W-20261008-004، قرارات D-249م وD-251م وD-257م).

**أرقامٌ لا أسماء** (D-171م): الطالبُ يُعدّ **مرّةً واحدة** مهما تعدّدت صفوفُ حضوره، وحكمُه اليوميُّ هو `_judge` من
[`absence_standing`](absence_standing.py) نفسُه — لا حكمَ ثانياً يفترق عنه. فالعدّادُ في اللوحة هو ما يحسبه موقفُ الطالب وعدُّ الحرمان.

الاستعلاماتُ ثابتةٌ مهما كثر الطلاب (حارسُها `tests/test_day_summary.py`):
  ١ خاناتُ الشعب اليوم مع جناحها · ٢ تسجيلُ الطلاب النشط · ٣ صفوفُ الحضور اليوم · ٤ تثبيتاتُ الحصص اليوم ·
  ٥ إدخالاتُ الجدول المعلَّقة وغيرُها (رأسُ الإدخال) · ٦ ملخّصُ الخروج `DailyExitTally`.

القرارات في الكود:
- **14:00 بتوقيت الدوحة ثابتةٌ** (`FINAL_HOUR`): قبلها «غائبون عن أوّل خانتين» ولا يُسمّى «غائب اليوم»؛ وبعدها حكمُ السياسة بخمس خانات
  منفصلة (بلا عذر · بعذر · لم يُحسم · غير مرصود · حاضر) — «غير مرصود» لا يُدمج في الغائب.
- **حصصُ الجدول المؤقّت** (`provisional`) تدخل **حكمَ اليوم** (ما رُصد فيها يُحسب) وتُستثنى من **عدّاد خانات الجرس** و«شعب مسجَّلة».
- **«سُجِّلت»**: الخانةُ مسجَّلةٌ إن وُجد لها تثبيتُ مشرفٍ أو صفُّ حضورٍ معتمَدٌ أو رأسُ إدخالِ جدولٍ (فمسارُ الجدول لا يكتب
  `PeriodConfirmation` — مقيس) — فلا تُقرأ من التثبيت وحدَه.
- **الخارج بإذن** (عيادة/نشاط): خانةٌ مرحليّةٌ مستقلّة بعدد الطلاب؛ لا يتغيّر `_judge` ولا `absence_standing` (D-251م، مواصفةُ full لاحقة).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from django.utils import timezone

from operations.absence_standing import ATTENDED, _judge

#: ساعةُ حسمِ اليوم بتوقيت الدوحة (قرارُ المالك D-249م: ثابتةٌ لا «آخرُ خانة»).
FINAL_HOUR = 14

#: خاناتُ «الغياب المبكّر» قبل الحسم: أوّلُ خانتين من جرس اليوم.
EARLY_SLOTS = 2

PHASE_LIVE = "live"
PHASE_FINAL = "final"
PHASE_CLOSED = "closed"

#: «أين الطالب» (`StudentAttendance.whereabouts`) بإذنٍ لا تُحسب هروباً: العيادةُ والنشاط (D-251م).
PERMITTED_WHEREABOUTS = ("clinic", "activity")


@dataclass
class DayCounts:
    """أعدادُ نطاقٍ واحد (المدرسة أو جناح) — طلابٌ مميَّزون لا صفوف."""

    students: int = 0
    present: int = 0
    absent_unexcused: int = 0
    absent_excused: int = 0
    incomplete: int = 0
    unrecorded: int = 0
    #: غائبون عن أوّل خانتين معاً (قبل الحسم).
    early_absent: int = 0
    #: طلابٌ لهم رصدُ معلّمٍ بانتظار الاعتماد (يُعدّون ولا يُحتسبون حاضرين ولا غائبين).
    pending: int = 0
    sections_total: int = 0
    sections_registered: int = 0
    #: غائبون بإذنٍ خارجَ الفصل (عيادة/نشاط) — وسمٌ مرحليٌّ لا حكم.
    away_permitted: int = 0
    #: الزمنُ خارج الفصل لهذا النطاق: طلابٌ · مرّاتٌ · دقائق (مجموعُ الأجزاء المغلقة من `DailyExitTally`).
    exit_students: int = 0
    exit_count: int = 0
    exit_minutes: int = 0

    def as_dict(self) -> dict[str, int]:
        return {key: getattr(self, key) for key in self.__dataclass_fields__}


@dataclass
class WingRow:
    wing_id: Any
    name: str
    counts: DayCounts


#: حالةُ جدول الشعبة اليوم: لم يُبدأ (لا تسجيلَ لأيّ خانة) · حُفظ جزئياً (خانةٌ منتهيةٌ بلا تسجيل) · مكتمل.
STATE_NOT_STARTED = "not_started"
STATE_PARTIAL = "partial"
STATE_COMPLETE = "complete"
STATE_LABELS = {
    STATE_NOT_STARTED: "لم يُبدأ",
    STATE_PARTIAL: "حُفظ جزئياً",
    STATE_COMPLETE: "مكتمل",
}


@dataclass
class SectionRow:
    """شعبةٌ: خاناتُها المسجَّلةُ من المجدولة وحالُ جدولها وأعدادُها — أرقامٌ لا أسماء (D-171م)."""

    section_id: Any
    wing_id: Any
    code: str
    counts: DayCounts
    slots_total: int = 0
    slots_registered: int = 0
    slots_ended: int = 0
    state: str = STATE_NOT_STARTED

    @property
    def gap(self) -> bool:
        """فجوةٌ: خانةٌ منتهيةٌ بلا تسجيل (لم يُبدأ بعد انتهاء خانة، أو حُفظ جزئياً)."""
        return self.state == STATE_PARTIAL or (
            self.state == STATE_NOT_STARTED and self.slots_ended > 0
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "id": str(self.section_id),
            "wing_id": None if self.wing_id is None else str(self.wing_id),
            "code": self.code,
            "slots_total": self.slots_total,
            "slots_registered": self.slots_registered,
            "slots_ended": self.slots_ended,
            "recorded": f"{self.slots_registered}/{self.slots_total}",
            "state": self.state,
            "state_label": STATE_LABELS[self.state],
            "gap": self.gap,
            **self.counts.as_dict(),
        }


@dataclass
class DaySummary:
    day: dt.date
    phase: str
    generated_at: dt.datetime
    school: DayCounts = field(default_factory=DayCounts)
    wings: list[WingRow] = field(default_factory=list)
    sections: list[SectionRow] = field(default_factory=list)
    #: خاناتُ الجرس (غيرُ المؤقّتة وغيرُ الملغاة): العددُ ومنتهيتُها وجاريتُها.
    bell_slots: int = 0
    slots_ended: int = 0
    slots_running: int = 0
    #: رقمُ الخانة الجارية في ترتيب الجرس (1..n) أو 0.
    current_slot: int = 0
    #: الزمنُ خارج الفصل: طلابٌ · مرّات · دقائق · وجهاتٌ، وما زال خارجاً.
    exits_students: int = 0
    exits_count: int = 0
    exits_minutes: int = 0
    exits_by_destination: dict[str, int] = field(default_factory=dict)

    @property
    def headline(self) -> int:
        """رقمُ أوّل بطاقة: «غائب بلا عذر» بعد 14:00، و«غائبون عن أوّل خانتين» قبلها (D-249م)."""
        school = self.school
        return school.absent_unexcused if self.phase == PHASE_FINAL else school.early_absent

    def as_dict(self) -> dict[str, Any]:
        """حمولةٌ JSON بلا أسماء ولا أرقامٍ شخصيّة (حارسُها نصّيٌّ في الاختبار)."""
        return {
            "day": self.day.isoformat(),
            "phase": self.phase,
            "generated_at": self.generated_at.isoformat(),
            "school": {**self.school.as_dict(), "headline": self.headline},
            "wings": [
                {
                    "id": None if w.wing_id is None else str(w.wing_id),
                    "name": w.name,
                    **w.counts.as_dict(),
                }
                for w in self.wings
            ],
            "sections": [section.as_dict() for section in self.sections],
            "bell_slots": self.bell_slots,
            "slots_ended": self.slots_ended,
            "slots_running": self.slots_running,
            "current_slot": self.current_slot,
            "exits": {
                "students": self.exits_students,
                "count": self.exits_count,
                "minutes": self.exits_minutes,
                "by_destination": self.exits_by_destination,
            },
        }


def day_phase(school: Any, day: dt.date, now: dt.datetime) -> str:
    """`closed` ليومٍ بلا دوام · `final` من 14:00 بتوقيت الدوحة (حكمُ اليوم) · `live` قبلها."""
    from operations.school_days import is_school_day

    if not is_school_day(school, day):
        return PHASE_CLOSED
    local = timezone.localtime(now)
    return PHASE_FINAL if local.hour >= FINAL_HOUR else PHASE_LIVE


def _new_day() -> dict[str, set]:
    return {
        "scheduled": set(),
        "recorded": set(),
        "attended": set(),
        "unexcused": set(),
        "excused": set(),
    }


@dataclass
class _Day:
    """ما تقرؤه الاستعلاماتُ الستّة مرّةً واحدة — يُحسب منها كلُّ شيءٍ في الذاكرة."""

    section_slots: dict[Any, set] = field(default_factory=dict)
    section_real_slots: dict[Any, set] = field(default_factory=dict)
    section_wing: dict[Any, Any] = field(default_factory=dict)
    section_code: dict[Any, str] = field(default_factory=dict)
    wing_names: dict[Any, tuple[int, str]] = field(default_factory=dict)
    bell: dict[dt.time, dt.time] = field(default_factory=dict)
    enrollments: list[tuple[Any, Any]] = field(default_factory=list)
    days: dict[Any, dict[str, set]] = field(default_factory=dict)
    registered: set[tuple[Any, dt.time]] = field(default_factory=set)
    away_students: set[Any] = field(default_factory=set)
    pending_students: set[Any] = field(default_factory=set)


def _load_sessions(school: Any, day: dt.date, data: _Day) -> None:
    """١ خاناتُ الشعب اليوم (غيرُ الملغاة): المؤقّتةُ فيها تدخل الحكم لا عدّادَ الجرس."""
    from core.models.academic import ClassGroup
    from operations.models import Session

    rows = (
        Session.objects.filter(school=school, date=day)
        .exclude(status="cancelled")
        .values_list(
            "class_group_id",
            "class_group__wing_id",
            "class_group__wing__name",
            "class_group__wing__order",
            "class_group__grade",
            "class_group__section",
            "start_time",
            "end_time",
            "provisional",
        )
    )
    for section, wing_id, wing_name, wing_order, grade, section_no, start, end, provisional in rows:
        data.section_code.setdefault(
            section, ClassGroup(grade=grade, section=section_no).short_code
        )
        data.section_slots.setdefault(section, set()).add(start)
        data.section_wing[section] = wing_id
        if wing_id is not None:
            data.wing_names[wing_id] = (wing_order or 0, wing_name or "")
        if not provisional:
            data.section_real_slots.setdefault(section, set()).add(start)
            data.bell.setdefault(start, end)


def _load_enrollments(data: _Day) -> None:
    """٢ تسجيلُ الطلاب النشط في شعب اليوم."""
    from core.models.academic import StudentEnrollment

    data.enrollments = list(
        StudentEnrollment.objects.filter(
            is_active=True, class_group_id__in=list(data.section_slots)
        ).values_list("student_id", "class_group_id")
    )


def _load_attendance(school: Any, day: dt.date, data: _Day) -> None:
    """٣ صفوفُ الحضور اليوم: تُبنى منها خاناتُ كلِّ طالبٍ كما يبنيها `_day_map` — ثمّ يحكم `_judge`."""
    from operations.models import StudentAttendance

    rows = StudentAttendance.objects.filter(school=school, session__date=day).values_list(
        "student_id",
        "session__class_group_id",
        "session__start_time",
        "status",
        "excuse_type",
        "whereabouts",
    )
    for student, section, start, status, excuse, where in rows:
        entry = data.days.setdefault(student, _new_day())
        entry["recorded"].add(start)
        data.registered.add((section, start))
        if status in ATTENDED:
            entry["attended"].add(start)
        elif status == "absent":
            entry["excused" if excuse else "unexcused"].add(start)
            if where in PERMITTED_WHEREABOUTS:
                data.away_students.add(student)


def _load_registration(school: Any, day: dt.date, data: _Day) -> None:
    """٤ تثبيتاتُ المشرف و٥ رؤوسُ إدخالات الجدول (عبر القارئ المراجَع): كلُّها تسجّل الخانة، والمعلَّقُ (بلا قرار) يُعدّ ولا يُحتسب."""
    from operations.attendance_selectors import day_entry_heads
    from operations.models import PeriodConfirmation

    confirmations = PeriodConfirmation.objects.filter(school=school, date=day)
    for section, start in confirmations.values_list("class_group_id", "start_time"):
        data.registered.add((section, start))
    for student, section, start, undecided in day_entry_heads(school, day):
        data.registered.add((section, start))
        if undecided:
            data.pending_students.add(student)


def _fill_bell(summary: DaySummary, data: _Day, local_now: dt.time) -> set[dt.time]:
    """خاناتُ الجرس (غيرُ المؤقّتة): عددُها ومنتهيتُها وجاريتُها؛ وتُعيد خاناتِ «الغياب المبكّر»."""
    ordered = sorted(data.bell)
    summary.bell_slots = len(ordered)
    for number, start in enumerate(ordered, start=1):
        end = data.bell[start]
        if end <= local_now:
            summary.slots_ended += 1
        elif start <= local_now:
            summary.slots_running += 1
            summary.current_slot = number
    return set(ordered[:EARLY_SLOTS])


def _count_sections(
    data: _Day, scopes: dict[Any, DayCounts], school_counts: DayCounts, local_now: dt.time
) -> None:
    """Y = شعبٌ ذاتُ حصةٍ غيرِ مؤقّتة؛ X = كلُّ خاناتها المنتهية بالساعة مسجَّلة."""
    ended = {start for start, end in data.bell.items() if end <= local_now}
    for section, real in data.section_real_slots.items():
        scope = scopes.setdefault(data.section_wing.get(section), DayCounts())
        done = all((section, start) in data.registered for start in real & ended)
        for target in (scope, school_counts):
            target.sections_total += 1
            target.sections_registered += int(done)


def _build_sections(
    data: _Day, section_counts: dict[Any, DayCounts], local_now: dt.time
) -> list[SectionRow]:
    """سطرُ كلّ شعبةٍ ذاتِ حصةٍ غيرِ مؤقّتة: خاناتُها المسجَّلةُ من المجدولة وحالُ جدولها (لم يُبدأ · حُفظ جزئياً · مكتمل)."""
    ended = {start for start, end in data.bell.items() if end <= local_now}
    rows = []
    for section, real in data.section_real_slots.items():
        registered = {start for start in real if (section, start) in data.registered}
        due = real & ended
        if not registered:
            state = STATE_NOT_STARTED
        elif due - registered:
            state = STATE_PARTIAL
        else:
            state = STATE_COMPLETE
        rows.append(
            SectionRow(
                section_id=section,
                wing_id=data.section_wing.get(section),
                code=data.section_code.get(section, ""),
                counts=section_counts.setdefault(section, DayCounts()),
                slots_total=len(real),
                slots_registered=len(registered),
                slots_ended=len(due),
                state=state,
            )
        )
    return sorted(rows, key=lambda row: row.code)


_VERDICT_FIELD = {
    "present": "present",
    "absent_unexcused": "absent_unexcused",
    "absent_excused": "absent_excused",
    "incomplete": "incomplete",
}


def _count_students(
    data: _Day,
    scopes: dict[Any, DayCounts],
    school_counts: DayCounts,
    section_counts: dict[Any, DayCounts],
    early: set[dt.time],
) -> None:
    """الطالبُ مرّةً واحدة بحكم `_judge`؛ و«غير مرصود» ما لا رصدَ فيه أصلاً."""
    seen: set[Any] = set()
    for student, section in data.enrollments:
        if student in seen:
            continue
        seen.add(student)
        entry = data.days.get(student) or _new_day()
        entry["scheduled"] |= data.section_slots.get(section, set())
        field_name = _VERDICT_FIELD.get(_judge(entry), "unrecorded")
        absent_early = bool(early) and early <= (entry["unexcused"] | entry["excused"])
        scope = scopes.setdefault(data.section_wing.get(section), DayCounts())
        for target in (scope, school_counts, section_counts.setdefault(section, DayCounts())):
            target.students += 1
            setattr(target, field_name, getattr(target, field_name) + 1)
            target.early_absent += int(absent_early)
            target.pending += int(student in data.pending_students)
            target.away_permitted += int(student in data.away_students)


def _fill_exits(
    summary: DaySummary,
    school: Any,
    day: dt.date,
    data: _Day,
    scopes: dict[Any, DayCounts],
    section_counts: dict[Any, DayCounts],
) -> None:
    """٦ الزمنُ خارج الفصل — استعلامٌ واحد على الملخّص اليوميّ، مجمَّعٌ في الذاكرة بوجهاته العربيّة."""
    from operations.models import ClassExit, DailyExitTally

    labels = dict(ClassExit.DESTINATIONS)
    section_of = dict(data.enrollments)
    students: set[Any] = set()
    rows = DailyExitTally.objects.filter(school=school, date=day).values_list(
        "student_id", "exit_count", "total_seconds", "by_destination"
    )
    for student, count, seconds, destinations in rows:
        section = section_of.get(student)
        if section is None or not count:
            continue
        students.add(student)
        summary.exits_count += count
        summary.exits_minutes += round(seconds / 60)
        scope = scopes.setdefault(data.section_wing.get(section), DayCounts())
        for target in (scope, section_counts.setdefault(section, DayCounts())):
            target.exit_students += 1
            target.exit_count += count
            target.exit_minutes += round(seconds / 60)
        for code, detail in (destinations or {}).items():
            label = labels.get(code, code)
            summary.exits_by_destination[label] = summary.exits_by_destination.get(label, 0) + int(
                (detail or {}).get("count", 0)
            )
    summary.exits_students = len(students)


def school_day_summary(school: Any, day: dt.date, now: dt.datetime | None = None) -> DaySummary:
    """مُجمِّعُ يومِ المدرسة: عدّاداتُ المدرسة وأجنحتُها بالحكم نفسِه — بستّة استعلاماتٍ ثابتة."""
    now = now or timezone.now()
    summary = DaySummary(day=day, phase=day_phase(school, day, now), generated_at=now)
    if summary.phase == PHASE_CLOSED:
        return summary
    local_now = timezone.localtime(now).time()

    data = _Day()
    _load_sessions(school, day, data)
    _load_enrollments(data)
    _load_attendance(school, day, data)
    _load_registration(school, day, data)

    scopes: dict[Any, DayCounts] = {}
    section_counts: dict[Any, DayCounts] = {}
    early = _fill_bell(summary, data, local_now)
    _count_sections(data, scopes, summary.school, local_now)
    _count_students(data, scopes, summary.school, section_counts, early)
    _fill_exits(summary, school, day, data, scopes, section_counts)
    summary.sections = _build_sections(data, section_counts, local_now)
    summary.school.exit_students = summary.exits_students
    summary.school.exit_count = summary.exits_count
    summary.school.exit_minutes = summary.exits_minutes

    # الأجنحةُ بترتيبها ثمّ «بلا جناح» آخراً.
    ordered = sorted(data.wing_names.items(), key=lambda item: (item[1][0], item[1][1]))
    summary.wings = [
        WingRow(wing_id, name, scopes[wing_id])
        for wing_id, (_, name) in ordered
        if wing_id in scopes
    ]
    if None in scopes:
        summary.wings.append(WingRow(None, "بلا جناح", scopes[None]))
    return summary


#: عمرُ الملخّص في الذاكرة المشتركة (ثانية) — ما وُجد الإنتاجُ على Redis فهو مشتركٌ بين العمليّات (REDIS_URL).
LIVE_TTL = 20
#: الاستطلاعُ الحيّ: فاصلُه من الخادم فيتغيّر دون نشر عميل.
LIVE_NEXT_IN = 45
LIVE_SCHEMA = 1


def live_payload(school: Any, day: dt.date, now: dt.datetime | None = None) -> dict[str, Any]:
    """حمولةُ نقطة الاستطلاع الحيّ للمدير: الملخّصُ مخزَّنٌ 20 ث بمفتاح `live:{school}:{day}` وحساباتُه بقفل `cache.add`.

    فاستعلاماتُ القاعدة لا تتبع عددَ المستخدمين: يحسبه طلبٌ واحدٌ والباقون يقرؤون المخزَّنَ أو آخرَ نسخةٍ قديمةٍ إن فاتهم القفل.
    ولا اسمَ ولا رقماً شخصيّاً في المخزَّن (أعدادٌ مجمَّعة)، فتسرُّبُه لا يكشف طالباً.
    """
    from django.core.cache import cache

    key = f"live:{school.pk}:{day.isoformat()}"
    data = cache.get(key)
    if data is not None:
        return data
    last = cache.get(f"{key}:last")
    if cache.add(f"{key}:lock", 1, 10) or last is None:
        try:
            data = school_day_summary(school, day, now).as_dict()
            data = {**data, "schema": LIVE_SCHEMA, "next_in": LIVE_NEXT_IN}
            cache.set(key, data, LIVE_TTL)
            cache.set(f"{key}:last", data, LIVE_TTL * 6)
        finally:
            cache.delete(f"{key}:lock")
        return data
    return last


def director_day_section(user: Any, school: Any, today: dt.date) -> dict[str, Any]:
    """قسمُ «غياب اليوم» في سياق لوحة المدير — تسجّله `OperationsConfig.ready` فلا تستورد النواةُ هذه الوحدة (سقّاطةُ الطبقات).

    الرابطُ إلى «متابعة الحضور» لمن يحمل قدرتَها وحدَه (D-171م: العددُ والرابطُ لا الأسماء).
    """
    from core.capabilities import has_capability

    return {
        "day": school_day_summary(school, today),
        "can_follow_up": has_capability(user, "student_affairs.follow_up"),
    }


_COUNT_FIELDS = tuple(DayCounts.__dataclass_fields__)
_SHARED_KEYS = (
    "schema",
    "next_in",
    "day",
    "phase",
    "generated_at",
    "bell_slots",
    "slots_ended",
    "slots_running",
    "current_slot",
)


def scope_to_wings(payload: dict[str, Any], wing_ids: set[str]) -> dict[str, Any]:
    """حمولةُ المشرف: الملخّصُ المخزَّنُ للمدرسة كلِّها مقتطَعاً لأجنحته وحدَها — بعد القراءة لا قبلها (D-249م 9.3).

    الجناحُ لا يأتي من الطلب: يحدّده مستدعي هذه الدالّة من `wings_of(user)`. فلا تسرّب حمولةٌ جناحَ غيره، ولا اسمَ ولا رقماً شخصيّاً فيها.
    """
    wings = [row for row in payload["wings"] if row["id"] in wing_ids]
    sections = [row for row in payload["sections"] if row["wing_id"] in wing_ids]
    total = {name: sum(row[name] for row in wings) for name in _COUNT_FIELDS}
    final = payload["phase"] == PHASE_FINAL
    return {
        **{key: payload[key] for key in _SHARED_KEYS if key in payload},
        "school": {
            **total,
            "headline": total["absent_unexcused"] if final else total["early_absent"],
        },
        "wings": wings,
        "sections": sections,
        "exits": {
            "students": total["exit_students"],
            "count": total["exit_count"],
            "minutes": total["exit_minutes"],
        },
    }
