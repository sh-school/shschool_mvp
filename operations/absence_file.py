"""
operations/absence_file.py — ملفُّ غياب الطالب يوماً بيوم.

قرارُ 2026-09-14: لا آليّةَ كانت للعودة إلى يومِ غيابٍ بعينه — صفحةُ الطالب تعرض آخرَ ستّين
**حصّةً** لا أيّاماً، والعذرُ يُكتب بتاريخٍ من الذاكرة. فالملفُّ هنا يعرض العامَ الدراسيَّ
**أيّامَ الغياب وحدها**، لكلّ يومٍ حكمُه كما يحسبه عدُّ الحرمان (`absence_standing`)،
وإخطارُه، وعذرُه، ومهلتُه — ليضغط المشرفُ «اتّصلتُ» أو «عذر» على اليوم نفسه بلا كتابة تاريخ.

## أيّ الأيّام

- **غائبٌ بلا عذر / بعذر** — كما يعدّها الحرمان.
- **رصدٌ ناقص** — إن كان فيه حصّةٌ غائبة؛ ويومٌ ناقصٌ حضر كلَّ ما رُصد منه ليس غياباً فلا يُعرض.
- **غيابٌ جزئيّ** — حضر أربعَ حصصٍ فأكثر وغاب بعضها بلا عذر (خرج لموعدٍ مثلاً). لا يُعدّ في
  الحرمان، لكنّ المشرف يُخطِر عنه ويقبل عذرَه — والكشفُ يُعلّمه «لم يُخطَر» فيجب أن يجده هنا.

## السلسلة والمهلة

العذرُ من اليوم يشمل **أيّامَ الغياب بلا عذرٍ المتّصلة** به (الجمعةُ والسبتُ وإجازاتُ الوزارة لا
تقطعها، ويومٌ لم يُرصد يقطعها، ويومٌ عذرُه بانتظار النائب يقطعها). ومهلةُ السلسلة تُحسب **بقاعدة
الخدمة نفسها** (`excuses.first_late_day`): لكلّ يومٍ عودتُه، والسلسلةُ متأخّرةٌ إن تأخّر أيُّ يومٍ
فيها — فلا يقول الزرُّ «عذر» والخدمةُ ترسله للنائب. وأيّامُ الحضور والإجازاتُ تُقرأ مرّةً واحدة.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

from core.models import CustomUser, School
from operations.absence_standing import day_verdicts
from operations.excuses import GRACE_DAYS, RETURNED
from operations.models import AbsenceExcuse, GuardianContact, StudentAttendance
from operations.school_days import SchoolDays, student_grade

VERDICT_LABELS = {
    "absent_unexcused": "غائبٌ بلا عذر",
    "absent_excused": "غائبٌ بعذر",
    "incomplete": "رصدٌ ناقص",
    "partial": "غيابٌ جزئيّ",
}


@dataclass(frozen=True)
class AbsenceDay:
    """يومُ غيابٍ واحد بكلّ ما يحتاجه المشرفُ ليتصرّف فيه."""

    date: dt.date
    verdict: str
    absent_periods: int
    scheduled_periods: int
    #: في اليوم حصّةٌ غائبةٌ بلا عذر — شرطُ زرّ العذر.
    has_unexcused: bool
    #: الأيّامُ التي يشملها عذرٌ يُضغط من هذا اليوم.
    run_from: dt.date
    run_to: dt.date
    #: آخرُ يومٍ يقبل فيه المشرفُ عذرَ السلسلة — ولا شيء إن لم يعد الطالبُ بعد.
    deadline: dt.date | None
    late: bool
    excuse: AbsenceExcuse | None
    waiting: AbsenceExcuse | None
    rejected: AbsenceExcuse | None
    contact: GuardianContact | None

    @property
    def label(self) -> str:
        return VERDICT_LABELS[self.verdict]

    @property
    def spans_days(self) -> bool:
        return self.run_from != self.run_to

    @property
    def may_excuse(self) -> bool:
        """زرُّ العذر: في اليوم غيابٌ بلا عذر، ولا عذرَ له ينتظر النائب."""
        return self.has_unexcused and self.waiting is None

    @property
    def may_call(self) -> bool:
        """زرُّ «اتّصلتُ»: لم يُتّصل بعد، أو كانت آخرُ محاولةٍ «لم يردّ»."""
        return self.contact is None or self.contact.outcome == "no_answer"


class _SchoolDays(SchoolDays):
    """أيّامُ الدراسة في نافذة الملفّ — بمهلة العذر الافتراضيّة (`excuses.GRACE_DAYS`)."""

    def grace_after(self, back: dt.date) -> dt.date:
        return super().grace_after(back, GRACE_DAYS)


def _runs(unexcused: set[dt.date], days: _SchoolDays) -> dict[dt.date, tuple[dt.date, dt.date]]:
    """لكلّ يومِ غيابٍ بلا عذر: أوّلُ أيّام سلسلته المتّصلة وآخرُها."""
    spans: dict[dt.date, tuple[dt.date, dt.date]] = {}
    for day in sorted(unexcused):
        if day in spans:
            continue
        first = last = day
        while (before := days.step(first, -1)) in unexcused:
            first = before
        while (after := days.step(last, +1)) in unexcused:
            last = after
        cursor = first
        while cursor <= last:
            if cursor in unexcused:
                spans[cursor] = (first, last)
            cursor += dt.timedelta(days=1)
    return spans


def _run_deadline(
    run_days: list[dt.date], attended: list[dt.date], days: _SchoolDays, today: dt.date
) -> tuple[dt.date | None, bool]:
    """مهلةُ السلسلة وتأخّرُها — بقاعدة `excuses.first_late_day`: أقدمُ يومٍ انقضت مهلتُه.

    ويُعرض الأبكرُ إغلاقاً: هو الذي يحكم السلسلةَ كلَّها.
    """
    earliest: dt.date | None = None
    for day in sorted(run_days):
        back = next((a for a in attended if a >= day), None)
        if back is None:
            break  # لم يعد بعد هذا اليوم — ولا بعد ما يليه
        close = days.grace_after(back)
        if today > close:
            return close, True
        earliest = close if earliest is None else min(earliest, close)
    return earliest, False


def absence_days(
    student: CustomUser, school: School, start: dt.date, today: dt.date
) -> list[AbsenceDay]:
    """أيّامُ غياب الطالب من `start` حتى `today` — الأحدثُ أوّلاً."""
    shown: dict[dt.date, tuple[str, dict]] = {}
    for date, (verdict, slots) in day_verdicts(student, school, start, today).items():
        absent = slots["unexcused"] | slots["excused"]
        if verdict in ("absent_unexcused", "absent_excused"):
            shown[date] = (verdict, slots)
        elif verdict == "incomplete" and absent:
            shown[date] = (verdict, slots)
        elif verdict == "present" and slots["unexcused"]:
            shown[date] = ("partial", slots)
    if not shown:
        return []

    excuses = list(
        AbsenceExcuse.objects.filter(
            student=student, school=school, date_to__gte=start, date_from__lte=today
        ).order_by("-granted_at")
    )

    def covering(status: str, on: dt.date) -> AbsenceExcuse | None:
        return next(
            (x for x in excuses if x.status == status and x.date_from <= on <= x.date_to), None
        )

    # والإجازاتُ إلى ما بعد اليوم: مهلةٌ تُغلق بعد اليوم قد تقفز فوق إجازةٍ قادمة.
    # وصفُّ الطالب يضيّق الإجازاتِ إلى نطاقه — إجازةُ الثاني عشر وحده لا تمسّ مهلةَ سابع.
    school_days = _SchoolDays(
        school, start, today + dt.timedelta(days=60), student_grade(student, school)
    )
    # يومٌ عذرُه بانتظار النائب يقطع السلسلة: لا يُعاد إرسالُه، ولا يُحبط زرَّ ما حوله.
    unexcused = {
        d
        for d, (v, _) in shown.items()
        if v == "absent_unexcused" and covering("pending", d) is None
    }
    runs = _runs(unexcused, school_days)
    attended = sorted(
        set(
            StudentAttendance.objects.filter(
                student=student, school=school, session__date__gte=start, status__in=RETURNED
            ).values_list("session__date", flat=True)
        )
    )
    contacts: dict[dt.date, GuardianContact] = {}
    for contact in GuardianContact.objects.filter(
        student=student, school=school, absence_date__in=list(shown)
    ).order_by("contacted_at"):
        contacts[contact.absence_date] = contact

    run_deadlines: dict[tuple[dt.date, dt.date], tuple[dt.date | None, bool]] = {}
    result = []
    for date in sorted(shown, reverse=True):
        verdict, slots = shown[date]
        run_from, run_to = runs.get(date, (date, date))
        has_unexcused = bool(slots["unexcused"])
        if has_unexcused and (run_from, run_to) not in run_deadlines:
            run_days = [d for d in unexcused if run_from <= d <= run_to] or [date]
            run_deadlines[(run_from, run_to)] = _run_deadline(
                run_days, attended, school_days, today
            )
        deadline, late = run_deadlines.get((run_from, run_to), (None, False))
        result.append(
            AbsenceDay(
                date=date,
                verdict=verdict,
                absent_periods=len(slots["unexcused"] | slots["excused"]),
                scheduled_periods=len(slots["scheduled"]),
                has_unexcused=has_unexcused,
                run_from=run_from,
                run_to=run_to,
                deadline=deadline,
                late=late,
                excuse=covering("accepted", date),
                waiting=covering("pending", date),
                rejected=covering("rejected", date),
                contact=contacts.get(date),
            )
        )
    return result
