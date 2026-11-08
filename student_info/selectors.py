"""
قراءةُ إشارات الاستثناء لطلاب شعبةٍ — استعلاماتٌ مجمَّعةٌ بعددٍ ثابتٍ لا يتبع عددَ الطلاب.

صفحةُ طلاب الشعبة لا تُظهر إلّا ما يستحقّ نظراً: غائبٌ اليوم، أو قريبٌ من عتبة الغياب،
أو بندٌ مفتوح، أو قيدٌ جديدٌ/منقول. والخليّةُ الفارغةُ تعني «لا شيء».

الاستعلامات (ثابتةٌ مهما كثر الطلاب): حضورُ اليوم (1)، وأيّامُ الغياب بلا عذرٍ لكلّ الشعبة
(`unexcused_days_for_class`: استعلامان)، وقيودُ النقل (1)، والبنودُ المفتوحة (1).

والنطاقُ: كلُّ شيءٍ هنا يُحسب لمن في `enrollments` وحدَهم — وهم المضيَّقون سلفاً بـ`scope.narrow`.
ولا درجاتٍ ولا ملاحظاتِ أخصائيّين في هذه الإشارات، فلا يُجلب منها شيءٌ لأيّ دور.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from behavior.models import BehaviorInfraction
from core.models.academic import StudentEnrollment
from operations.absence_policy import Gate, gates_for
from operations.absence_standing import ATTENDED, unexcused_days_for_class
from operations.models import StudentAttendance

#: حالاتُ حضور اليوم.
PRESENT, ABSENT, UNRECORDED = "present", "absent", "unrecorded"

#: «قريبٌ من العتبة»: يفصله عن حدّ العتبة هذا العددُ من الأيّام أو أقلّ.
#: **قرارُ عرضٍ لا نصٌّ وزاريّ** — العتباتُ نفسُها (5 · 8 · 11 · 15) من `operations/absence_policy.py`
#: المنقولةِ حرفاً من 08_conduct_policy_2026.md م3.4.1.3 (ص29)؛ وهذا الهامشُ وحدَه اختيارُ الواجهة.
NEAR_GATE_DAYS = 2

#: القيدُ «جديد» إن بدأ قبل هذا العددِ من الأيّام أو أقلّ — قرارُ عرضٍ كذلك.
NEW_ENROLLMENT_DAYS = 14

#: مفاتيحُ التصفية المقبولة من `?flag=` — ما عداها يُهمل.
FLAGS = ("absent", "near", "open")
#: نصُّ كلّ زرٍّ في شريط الملخّص ولونُه (من ألوان `kpi`).
FLAG_LABELS = {
    "absent": ("غائب اليوم", "red"),
    "near": ("قرب العتبة", "amber"),
    "open": ("بندٌ مفتوح", "blue"),
}


@dataclass
class Signals:
    """إشاراتُ طالبٍ واحد. كلُّ حقلٍ فارغٌ = لا إشارة."""

    attendance: str = UNRECORDED
    late: bool = False
    absence_days: int = 0
    gate: Gate | None = None
    gate_exceeded: bool = False
    enrollment: str = ""  # "new" | "transferred" | ""
    has_open_item: bool = False
    flags: set[str] = field(default_factory=set)

    @property
    def is_flagged(self) -> bool:
        """هل له إشارةٌ تُعرض؟ (غيرُ المرصود ليس إشارةً: فالخليّةُ تبقى فارغةً إلّا عند غياب)."""
        return bool(
            self.attendance == ABSENT
            or self.late
            or self.gate
            or self.gate_exceeded
            or self.enrollment
            or self.has_open_item
        )


def _today_attendance(student_ids: list[Any], school: Any, today: dt.date) -> dict[Any, Signals]:
    """حضورُ اليوم: استعلامٌ واحدٌ. حضر حصّةً (حاضر/متأخّر) فهو حاضر — والمتأخّرُ يُحتسب حاضراً.

    لا سجلَّ له اليومَ فغيرُ مرصود، وسجلاتٌ كلُّها غيابٌ فغائب.
    """
    result: dict[Any, Signals] = {sid: Signals() for sid in student_ids}
    rows = StudentAttendance.objects.filter(
        school=school, student_id__in=student_ids, session__date=today
    ).values_list("student_id", "status")
    for student_id, status in rows:
        sig = result[student_id]
        if status in ATTENDED:
            sig.attendance = PRESENT
            sig.late = sig.late or status == "late"
        elif status == "absent" and sig.attendance != PRESENT:
            sig.attendance = ABSENT
    return result


def _gate_signal(grade: str, days: int) -> tuple[Gate | None, bool]:
    """(العتبةُ القريبة، هل تجاوز العتباتِ كلَّها): العتبةُ هي أولُ عتبةٍ لم تُتجاوَز والباقي لها ≤ الهامش."""
    if days <= 0:
        return None, False
    gates = gates_for(grade)
    if not gates:
        return None, False
    for gate in gates:
        if days <= gate.max_days:
            return (gate if gate.max_days - days <= NEAR_GATE_DAYS else None), False
    return None, True


def section_signals(
    group: Any, enrollments: list[Any], school: Any, today: dt.date, year: str
) -> dict[Any, Signals]:
    """إشاراتُ كلّ طالبٍ في `enrollments` — `{student_id: Signals}` بعددٍ ثابتٍ من الاستعلامات."""
    student_ids = [e.student_id for e in enrollments]
    if not student_ids:
        return {}
    signals = _today_attendance(student_ids, school, today)
    days = unexcused_days_for_class(group, school, today)
    transferred = set(
        StudentEnrollment.objects.filter(
            student_id__in=student_ids,
            class_group__academic_year=year,
            left_at__isnull=False,
        )
        .exclude(class_group=group)
        .values_list("student_id", flat=True)
    )
    open_items = set(
        BehaviorInfraction.objects.filter(
            school=school, student_id__in=student_ids, is_resolved=False
        ).values_list("student_id", flat=True)
    )
    cutoff = today - dt.timedelta(days=NEW_ENROLLMENT_DAYS)
    for e in enrollments:
        sig = signals[e.student_id]
        sig.absence_days = days.get(e.student_id, 0)
        sig.gate, sig.gate_exceeded = _gate_signal(group.grade, sig.absence_days)
        if e.student_id in transferred:
            sig.enrollment = "transferred"
        elif e.enrolled_at >= cutoff:
            sig.enrollment = "new"
        sig.has_open_item = e.student_id in open_items
        if sig.attendance == ABSENT:
            sig.flags.add("absent")
        if sig.gate or sig.gate_exceeded:
            sig.flags.add("near")
        if sig.has_open_item:
            sig.flags.add("open")
    return signals


def section_roster(
    group: Any,
    enrollments: Any,
    school: Any,
    today: dt.date,
    year: str,
    q: str = "",
    flag: str = "",
) -> dict[str, Any]:
    """صفوفُ الجدول والملخّص: `{"rows", "enrollments", "summary", "total"}`.

    الملخّصُ يُعدّ على الشعبة كلِّها (لا على ما صفّاه البحثُ) فلا يتغيّر رقمُ الزرّ بكتابة اسم،
    ويُخفي ما صفرُه. والترتيبُ: أصحابُ الإشارات أولاً ثمّ البقيّة، وكلٌّ بالاسم.
    """
    rows_all = list(enrollments)
    signals = section_signals(group, rows_all, school, today, year)
    all_rows = [(e, signals[e.student_id]) for e in rows_all]
    rows = list(all_rows)
    summary = [
        {"key": key, "label": FLAG_LABELS[key][0], "tone": FLAG_LABELS[key][1], "count": n}
        for key in FLAGS
        if (n := sum(1 for _, s in rows if key in s.flags)) > 0  # الصفرُ يُخفى
    ]
    needle = q.strip()
    if needle:
        rows = [(e, s) for e, s in rows if needle in e.student.full_name]
    if flag in FLAGS:
        rows = [(e, s) for e, s in rows if flag in s.flags]
    rows.sort(key=lambda r: (not r[1].is_flagged, r[0].student.full_name))
    return {
        "rows": rows,
        "enrollments": [e for e, _ in rows],
        "summary": summary,
        "total": len(rows_all),
        "recorded_any": any(s.attendance != UNRECORDED for _, s in all_rows),
    }
