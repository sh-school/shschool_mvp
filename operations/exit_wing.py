"""بطاقةُ الخروج: لحظتا العيادة والخروجُ المبرَّر الدائم وعدّادا الخروج باسم الطالب (إدارةُ الأجنحة 3/4).

قراراتُ المالك 2026-11-19:

- **العيادة**: الممرّضُ يضغط «وصل العيادة» ثمّ «غادر»؛ اللحظتان على `ClassExit` نفسِه ويراهما المشرفُ، وسببُ الزيارة
  لا يدخل هذا الملفَّ ولا هذا الجدولَ أصلاً (هو في `ClinicVisit` وحدَها).
- **الخروجُ المبرَّر الدائم**: وسمٌ بمدّة يضعه الممرّضُ أو الأخصائيُّ؛ يُسقط **تأخّرَ العودة** وحدَه عن الطالب، ولا يُنشأ له
  تأخّرٌ ولا يُعدّ عليه في العدّاد. سببُه لواضعه، ولا يُكتب في سجلّ المراجعة (يُسجَّل طولُه).
- **العدّادان** (دقائقُ الخروج وتأخّرُ العودة): بالطالب، وللمعلّم في **مادّته** فقط (`subject_ids`)، ولا يصلان لوليّ الأمر
  (لا يقرؤهما أيُّ عرضٍ في بوّابته).
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from django.db import transaction
from django.utils import timezone

from operations.exit_card import _audit
from operations.models import ClassExit, ExcusedExit

if TYPE_CHECKING:
    from core.models import CustomUser, School

#: من يضع الوسمَ: الممرّضُ والأخصائيُّ الاجتماعيُّ والنفسيّ.
EXCUSE_ROLES = ("nurse", "social_worker", "psychologist")

#: مدّةُ العدّادين المعروضة بالأيّام (آخرُ شهرٍ يُقاس به «كم خرج وكم تأخّر»).
COUNTER_DAYS = 30

#: أقصى مدّةٍ للوسم بالأيّام — وسمٌ أطولُ من عامٍ دراسيٍّ يُجدَّد بقرارٍ جديد.
MAX_EXCUSE_DAYS = 366


def may_excuse(user: CustomUser | None) -> bool:
    return user is not None and user.get_role() in EXCUSE_ROLES  # type: ignore[no-untyped-call]


def excused_spans(school: School, student_ids: Any) -> dict[Any, list[tuple[dt.date, dt.date]]]:
    """مدداً الوسم لكلّ طالبٍ — استعلامٌ واحد."""
    spans: dict[Any, list[tuple[dt.date, dt.date]]] = {}
    for student_id, start, end in ExcusedExit.objects.filter(
        school=school, student_id__in=student_ids
    ).values_list("student_id", "starts_on", "ends_on"):
        spans.setdefault(student_id, []).append((start, end))
    return spans


def covered(spans: dict[Any, list[tuple[dt.date, dt.date]]], student_id: Any, day: dt.date) -> bool:
    return any(start <= day <= end for start, end in spans.get(student_id, ()))


def is_excused(school_id: Any, student_id: Any, day: dt.date) -> bool:
    return ExcusedExit.objects.filter(
        school_id=school_id, student_id=student_id, starts_on__lte=day, ends_on__gte=day
    ).exists()


def excused_ids(school: School, day: dt.date) -> set[Any]:
    """طلبةُ المدرسة الموسومون في `day`."""
    return set(
        ExcusedExit.objects.filter(school=school, starts_on__lte=day, ends_on__gte=day).values_list(
            "student_id", flat=True
        )
    )


@transaction.atomic
def set_excused(
    school: School,
    student: CustomUser,
    by: CustomUser,
    ends_on: dt.date,
    reason: str,
    starts_on: dt.date | None = None,
) -> ExcusedExit:
    """يضع وسمَ «خروجٍ مبرَّرٍ دائم» بمدّة — للممرّض والأخصائيّ وحدَهما، والسببُ مكتوبٌ شرطٌ لواضعه."""
    if not may_excuse(by):
        raise PermissionError("وسمُ الخروج المبرَّر للممرّض أو الأخصائيّ.")
    start = starts_on or timezone.localdate()
    if ends_on < start:
        raise ValueError("نهايةُ المدّة قبل بدايتها.")
    if (ends_on - start).days > MAX_EXCUSE_DAYS:
        raise ValueError("المدّةُ أطولُ من عامٍ — جدِّدها بقرارٍ جديد.")
    text = (reason or "").strip()
    if not text:
        raise ValueError("اكتب سببَ الوسم (لا يراه غيرُك).")
    mark = ExcusedExit.objects.create(
        school=school,
        student=student,
        starts_on=start,
        ends_on=ends_on,
        set_by=by,
        set_by_role=by.get_role(),  # type: ignore[no-untyped-call]
        reason=text,
    )
    # السببُ بيانٌ صحّيٌّ: يُسجَّل طولُه لا نصُّه ولا اسمُ الطالب.
    _audit(
        by,
        school,
        "excused_exit",
        "وسم خروج مبرَّر",
        {
            "mark": str(mark.pk),
            "by": str(by.pk),
            "reason_chars": len(text),
            "days": (ends_on - start).days + 1,
        },
    )
    return mark


def clinic_arrive(exit_id: Any, by: CustomUser, now: dt.datetime | None = None) -> bool:
    """«وصل العيادة» — مرّةٌ واحدةٌ بشرطٍ ذرّيٍّ على الفراغ، لخروجٍ مفتوحٍ وجهتُه العيادة. يُرجع هل هذه النقرةُ سجّلته."""
    done = ClassExit.objects.filter(
        pk=exit_id,
        destination="clinic",
        returned_at__isnull=True,
        clinic_arrived_at__isnull=True,
    ).update(clinic_arrived_at=now or timezone.now())
    return bool(done)


def clinic_depart(exit_id: Any, by: CustomUser, now: dt.datetime | None = None) -> bool:
    """«غادر» — بعد الوصول وقبل المغادرة فقط، مرّةً واحدة. لا يُغلق الخروجَ: عودةُ الطالب إلى فصله نقرةٌ أخرى."""
    done = ClassExit.objects.filter(
        pk=exit_id,
        destination="clinic",
        clinic_arrived_at__isnull=False,
        clinic_left_at__isnull=True,
    ).update(clinic_left_at=now or timezone.now())
    return bool(done)


@dataclass(frozen=True)
class ExitCounter:
    """عدّادا طالبٍ في مدّة: مرّاتُ الخروج ودقائقُه المغلقة وتأخّرُ العودة بالدقائق (بعد إسقاط الموسوم)."""

    count: int = 0
    minutes: int = 0
    late_minutes: int = 0


def grid_counters(
    school: School, klass: Any, student_ids: Any, day: dt.date, *, teacher: CustomUser | None
) -> dict[Any, ExitCounter]:
    """عدّاداتُ طلبة شعبةٍ لصفحة كشفها: المعلّمُ (`teacher`) في **مادّته** فقط، ومن لا مادّةَ له في الشعبة لا يرى شيئاً.

    `teacher=None` للمشرف وحاملِ الجناح والقيادة: يرون الكلَّ بلا تقييد بمادّة.
    """
    if teacher is None:
        return exit_counters(school, student_ids, day)
    from operations.models import SubjectClassAssignment

    subjects = set(
        SubjectClassAssignment.objects.filter(
            school=school, class_group=klass, teacher=teacher
        ).values_list("subject_id", flat=True)
    )
    if not subjects:
        return {}
    return exit_counters(school, student_ids, day, subject_ids=subjects)


def exit_counters(
    school: School,
    student_ids: Any,
    day: dt.date,
    *,
    subject_ids: Any = None,
    days: int = COUNTER_DAYS,
) -> dict[Any, ExitCounter]:
    """عدّادا كلّ طالبٍ في آخر `days` يوماً حتى `day` — وللمعلّم `subject_ids` فلا يرى إلا حصصَ مادّته.

    الامتدادُ (`continued_from`) مدّةٌ لا مرّةٌ؛ والإغلاقُ بالجرس «مجهول» لا تأخّرَ فيه؛ والموسومُ لا يُحسب عليه تأخّرٌ في
    أيّام وسمه حتى لو وُضع الوسمُ بعد عودته.
    """
    qs = ClassExit.objects.filter(
        school=school,
        student_id__in=student_ids,
        session__date__gte=day - dt.timedelta(days=days),
        session__date__lte=day,
    )
    if subject_ids is not None:
        qs = qs.filter(session__subject_id__in=list(subject_ids))
    exits = list(
        qs.values(
            "student_id",
            "session__date",
            "continued_from_id",
            "left_at",
            "returned_at",
            "late_return_seconds",
        )
    )
    if not exits:
        return {}  # بلا خروجٍ لا حاجةَ لقراءة الوسوم (يُبقي صفحةَ الكشف في سقف استعلاماتها)
    spans = excused_spans(school, student_ids)
    totals: dict[Any, list[int]] = {}
    for e in exits:
        row = totals.setdefault(e["student_id"], [0, 0, 0])
        if e["continued_from_id"] is None:
            row[0] += 1
        if e["returned_at"] is not None:
            row[1] += max(0, int((e["returned_at"] - e["left_at"]).total_seconds() // 60))
        if not covered(spans, e["student_id"], e["session__date"]):
            row[2] += (e["late_return_seconds"] or 0) // 60
    return {sid: ExitCounter(*vals) for sid, vals in totals.items()}


@dataclass
class WeekTotal:
    """خروجُ طالبٍ في أسبوعٍ: مرّاتُه وتأخّرُ عودته بالدقائق وجناحُ آخر خروجٍ له."""

    student_id: Any
    student_name: str
    wing_id: Any
    wing_name: str
    count: int = 0
    late_minutes: int = 0


def week_start_of(day: dt.date) -> dt.date:
    """أحدُ الأسبوع الدراسيّ الذي يضمّ `day` (الأسبوعُ من الأحد)."""
    return day - dt.timedelta(days=(day.weekday() + 1) % 7)


def week_totals(school: School, scope: Any, week_start: dt.date) -> dict[Any, WeekTotal]:
    """مجاميعُ خروج كلّ طالبٍ في أسبوعٍ دراسيّ — مضيَّقةً بنطاق `scope` (None = المدرسةُ كلُّها).

    الامتدادُ (`continued_from`) مدّةٌ لا مرّة. والموسومُ بخروجٍ مبرَّرٍ في يوم وسمه يسقط من الحساب كلِّه
    (فلا يظهر في التقرير ولا يُقترح له) — «للمتابعة لا للعقوبة» ولا حاجةَ لمتابعة من سببُه معروفٌ ودائم.
    """
    qs = ClassExit.objects.filter(
        school=school,
        session__date__gte=week_start,
        session__date__lte=week_start + dt.timedelta(days=6),
    )
    if scope is not None:
        qs = scope.narrow(qs)
    exits = list(
        qs.order_by("left_at").values(
            "student_id",
            "student__full_name",
            "session__date",
            "session__class_group__wing_id",
            "session__class_group__wing__name",
            "continued_from_id",
            "late_return_seconds",
        )
    )
    spans = excused_spans(school, {e["student_id"] for e in exits})
    totals: dict[Any, WeekTotal] = {}
    for e in exits:
        if covered(spans, e["student_id"], e["session__date"]):
            continue
        row = totals.setdefault(
            e["student_id"], WeekTotal(e["student_id"], e["student__full_name"], None, "")
        )
        row.wing_id = e["session__class_group__wing_id"]
        row.wing_name = e["session__class_group__wing__name"] or ""
        if e["continued_from_id"] is None:
            row.count += 1
        row.late_minutes += (e["late_return_seconds"] or 0) // 60
    return totals
