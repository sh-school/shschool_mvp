"""schedule_linkage_audit.py — فحصُ ربط الجدول المنشور بما يقوم عليه (قراءةٌ فقط، لا يكتب شيئاً).

سؤالُ بوّابة الجاهزيّة: هل الجدولُ الحيّ يصلح أن تعمل عليه المدرسةُ يومَ الأحد؟ أي هل كلُّ حصّةٍ فيه:
  1. مسنَدةٌ إسناداً حيّاً (الشعبة، المادّة، المعلّم) — وإلّا فالرصدُ والإشغالُ يعملان على صفٍّ لا إسنادَ يسنده.
  2. بوقتها من جرس نطاق شعبتها لا غيره — وإلّا تفرّق وقتُ الجدول عن وقت الجلسة والمعلّم يرى ساعةً والنظامُ أخرى.
  3. لمعلّمٍ لا تتداخل حصصُه **بالساعة** (لا بالرقم) — فمعلّمُ الطابقين ثالثتُه في الأوّل تتداخل مع ثانيته في الأرضيّ.
  4. لمعلّمٍ له عضويّةٌ نشطةٌ بدورٍ تدريسيّ — وإلّا لا يراها ولا يُشعَر باعتمادها.
وأنّ جلساتِ يومٍ مطلوبٍ مولَّدةٌ لكلّ حصّةٍ (أو تُولَّد بلا خطأ) — فهنا لا تُولَّد شيئاً: تعدّ الناقصَ فحسب.

كلُّ فئةٍ تُعيد معرّفاتٍ لا أسماء (PDPPL) ويُقدَّر لها «العددُ» و«نماذجُ» مقتطعة.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any

from core.models import ClassGroup, Membership, School
from operations.models import ScheduleSlot, Session, SubjectClassAssignment

SAMPLE = 10
TEACHING_ROLES = (
    "teacher",
    "coordinator",
    "ese_teacher",
    "activities_coordinator",
    "e_projects_coordinator",
)


@dataclass
class Finding:
    code: str
    title: str
    count: int = 0
    sample: list[str] = field(default_factory=list)

    def add(self, ref: Any) -> None:
        self.count += 1
        if len(self.sample) < SAMPLE:
            self.sample.append(str(ref))


@dataclass
class LinkageReport:
    school_id: str
    year: str
    slots: int
    findings: list[Finding]
    sessions_expected: int | None = None
    sessions_missing: int | None = None

    @property
    def blocking(self) -> list[Finding]:
        return [f for f in self.findings if f.count]

    @property
    def ok(self) -> bool:
        return not self.blocking and not self.sessions_missing


def _minutes(t: time) -> int:
    return t.hour * 60 + t.minute


def audit(school: School, year: str | None = None, on: date | None = None) -> LinkageReport:
    """يفحص الجدولَ الحيّ لعام `year`؛ وإن مُرّر `on` فُحصت جلساتُ ذلك اليوم أيضاً."""
    from operations.scheduler import bell_lookup

    slots = list(ScheduleSlot.objects.live(school, year=year).select_related("class_group"))
    year = year or (slots[0].academic_year if slots else "")
    f_assign = Finding("no_assignment", "حصصٌ بلا إسنادٍ حيٍّ للمعلّم والمادّة والشعبة")
    f_time = Finding("bell_mismatch", "حصصٌ وقتُها يخالف جرسَ نطاق شعبتها")
    f_overlap = Finding("teacher_overlap", "معلّمٌ بحصّتين متداخلتين بالساعة")
    f_member = Finding("no_membership", "حصصٌ لمعلّمٍ بلا عضويّةٍ نشطةٍ بدورٍ تدريسيّ")

    assigned = set(
        SubjectClassAssignment.objects.live(school, year=year).values_list(
            "class_group_id", "subject_id", "teacher_id"
        )
    )
    teaching = set(
        Membership.objects.filter(
            school=school, is_active=True, role__name__in=TEACHING_ROLES
        ).values_list("user_id", flat=True)
    )
    bell = bell_lookup(school)
    by_teacher_day: dict[tuple[Any, int], list[ScheduleSlot]] = defaultdict(list)
    for slot in slots:
        if (slot.class_group_id, slot.subject_id, slot.teacher_id) not in assigned:
            f_assign.add(slot.id)
        expected = bell(slot.day_of_week, slot.period_number, slot.class_group.time_band_id)
        if (slot.start_time, slot.end_time) != tuple(expected):
            f_time.add(slot.id)
        if slot.teacher_id not in teaching:
            f_member.add(slot.id)
        by_teacher_day[(slot.teacher_id, slot.day_of_week)].append(slot)

    for (teacher_id, _day), day_slots in by_teacher_day.items():
        day_slots.sort(key=lambda s: (s.start_time, s.end_time))
        for a, b in zip(day_slots, day_slots[1:], strict=False):
            same_split = a.class_group_id == b.class_group_id and a.period_number == b.period_number
            if _minutes(b.start_time) < _minutes(a.end_time) and not same_split:
                f_overlap.add(f"{a.id}|{b.id}")

    report = LinkageReport(
        str(school.id), year, len(slots), [f_assign, f_time, f_overlap, f_member]
    )
    if on is not None:
        qatar_day = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}.get(on.weekday())
        if qatar_day is not None:
            wanted = {
                (s.teacher_id, s.class_group_id, s.start_time, s.elective_group)
                for s in slots
                if s.day_of_week == qatar_day
            }
            have = set(
                Session.objects.filter(school=school, date=on, provisional=False).values_list(
                    "teacher_id", "class_group_id", "start_time", "elective_group"
                )
            )
            report.sessions_expected = len(wanted)
            report.sessions_missing = len(wanted - have)
    return report


def classes_without_slots(school: School, year: str) -> list[str]:
    """معرّفاتُ شعبٍ نشطةٍ لا حصّةَ لها في الجدول الحيّ — شعبةٌ بلا جدول."""
    with_slots = set(
        ScheduleSlot.objects.live(school, year=year).values_list("class_group_id", flat=True)
    )
    return [
        str(pk)
        for pk in ClassGroup.objects.filter(school=school, academic_year=year).values_list(
            "id", flat=True
        )
        if pk not in with_slots
    ]
