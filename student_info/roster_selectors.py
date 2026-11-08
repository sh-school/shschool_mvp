"""
جدولُ طلاب الشعبة: إشاراتُ كلِّ طالبٍ في أعمدةٍ مستقلّة (W-20261108-012).

القراءةُ هنا لا في العرض، وكلُّ إشارةٍ باستعلامٍ مجمَّعٍ للشعبة كلِّها لا لكلّ طالب
(لا N+1): الحضورُ اليوم، وأيّامُ الغياب بلا عذرٍ، والقيد، والبنودُ المفتوحة. والطلبةُ
يصلون مضيَّقين بنطاق الدور (`scope.narrow`) فلا تُحسب إشارةٌ لمن لا يحقّ للقارئ رؤيتُه.

العتبةُ ورقمُها ونصُّها من `operations.absence_policy` المنقولةِ من الدليل التنظيميّ
لسياسة إدارة سلوك الطلبة 2026 (المادة 3.4.1.3) — لا رقمَ جديدٌ هنا. ولا درجاتٍ ولا
رقمَ شخصيٍّ ولا بياناتِ وليّ أمرٍ في الصفوف.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from behavior.models import BehaviorInfraction
from operations.absence_policy import MIN_PERIODS_FOR_PRESENCE, breached, next_gate
from operations.absence_standing import ATTENDED, unexcused_days_for_class
from operations.attendance_policy import is_special_education
from operations.models import StudentAttendance
from operations.services.attendance import AttendanceService
from student_affairs.models import StudentTransfer
from student_info import services

#: مرجعُ العتبة المعروضُ تحت الجدول — الدليلُ التنظيميّ 2026، المادة 3.4.1.3.
THRESHOLD_SOURCE = "الدليل التنظيمي لسياسة إدارة سلوك الطلبة 2026 — م 3.4.1.3"

#: مفاتيحُ التصفية المقبولة من `?filter=` — ما سواها يُهمل فتُعرض القائمةُ كاملة.
FILTERS = ("absent", "near", "open")

#: حضورُ اليوم: المفتاح ← (النصّ، نغمةُ الحالة). المتأخّرُ حاضرٌ يُحتسب حضوراً (3.4.2.2).
TODAY_LABELS = {
    "present": ("حاضر", "success"),
    "late": ("متأخر — يُحتسب حاضراً", "info"),
    "absent": ("غائب", "danger"),
    "unrecorded": ("غير مرصود", "gray"),
}

#: حالةُ القيد من حركة الطالب في العام: المفتاح ← (النصّ، النغمة).
ENROLLMENT_LABELS = {
    "new": ("جديد", "info"),
    "transferred": ("منقول", "warning"),
    "withdrawn": ("منسحب", "danger"),
}

#: البندُ المفتوح: المفتاح ← (النصّ، النغمة). الأشدُّ أولاً: الإحالة ثمّ التعهّد ثمّ حالةُ السلوك.
OPEN_ITEM_LABELS = {
    "referral": ("إحالة", "warning"),
    "pledge": ("تعهّد", "warning"),
    "case": ("حالة سلوك", "warning"),
}
_PLEDGE_ACTIONS = {"written_pledge", "parent_pledge"}


@dataclass
class RosterRow:
    """صفُّ طالبٍ: كلُّ حقلٍ إشارةٌ لعمودٍ، و`None` يعني «–» في الخلية."""

    enrollment: Any
    today: tuple[str, str, str]
    absence_days: int
    absence_text: str
    absence_tone: str
    near_threshold: bool
    enrollment_status: tuple[str, str] | None
    open_item: tuple[str, str] | None

    @property
    def signals(self) -> int:
        """عددُ الإشارات الحيّة — يُرتَّب بها أصحابُ الإشارات أولاً."""
        return (
            (self.today[0] == "absent")
            + self.near_threshold
            + (self.open_item is not None)
            + (self.enrollment_status is not None)
        )


def _today_verdicts(student_ids: list[Any], school: Any, today: Any) -> dict[Any, str]:
    """حكمُ اليوم لكلّ طالبٍ باستعلامٍ واحد: present · late · absent · unrecorded.

    يُحسب حاضراً من حضر ما يكفي من حصصه المرصودة (`MIN_PERIODS_FOR_PRESENCE`)، ويُسمّى
    «متأخّراً» إن كان أوّلُ ما حضره متأخّراً؛ والمتأخّرُ حاضرٌ لا غائب. ومن لا سجلَّ له
    «غيرُ مرصود» لا غائب.
    """
    rows = (
        StudentAttendance.objects.filter(
            school=school, student_id__in=student_ids, session__date=today
        )
        .order_by("session__start_time")
        .values_list("student_id", "status")
    )
    per_student: dict[Any, list[str]] = {}
    for student_id, status in rows:
        per_student.setdefault(student_id, []).append(status)
    verdicts: dict[Any, str] = {}
    for student_id, statuses in per_student.items():
        attended = [s for s in statuses if s in ATTENDED]
        if len(attended) >= min(MIN_PERIODS_FOR_PRESENCE, len(statuses)) and attended:
            verdicts[student_id] = "late" if attended[0] == "late" else "present"
        elif "absent" in statuses or "excused" in statuses:
            verdicts[student_id] = "absent"
    return verdicts


def _enrollment_statuses(
    student_ids: list[Any], group: Any, school: Any, year: str
) -> dict[Any, str]:
    """جديدٌ (وارد) أو منقولٌ إلى هذه الشعبة أو منسحبٌ (صادر) — من انتقالات العام المعتمدة.

    استعلامٌ واحد؛ والأشدُّ يغلب: المنسحبُ ثمّ المنقولُ ثمّ الجديد.
    """
    rank = {"new": 1, "transferred": 2, "withdrawn": 3}
    result: dict[Any, str] = {}
    for student_id, direction, to_group_id in StudentTransfer.objects.filter(
        school=school,
        student_id__in=student_ids,
        academic_year=year,
        status__in=("approved", "completed"),
    ).values_list("student_id", "direction", "to_class_group_id"):
        if direction == "out":
            kind = "withdrawn"
        elif direction == "internal" and to_group_id == group.id:
            kind = "transferred"
        elif direction == "in":
            kind = "new"
        else:
            continue
        if rank[kind] > rank.get(result.get(student_id, ""), 0):
            result[student_id] = kind
    return result


def _open_items(student_ids: list[Any], school: Any) -> dict[Any, str]:
    """أشدُّ بندٍ مفتوحٍ لكلّ طالب — مخالفاتٌ غيرُ معالَجة، باستعلامٍ واحد، بلا تفاصيلها."""
    rank = {"case": 1, "pledge": 2, "referral": 3}
    result: dict[Any, str] = {}
    for student_id, action in BehaviorInfraction.objects.filter(
        school=school, student_id__in=student_ids, is_resolved=False
    ).values_list("student_id", "disciplinary_action_type"):
        if action == "social_specialist_referral":
            kind = "referral"
        elif action in _PLEDGE_ACTIONS:
            kind = "pledge"
        else:
            kind = "case"
        if rank[kind] > rank.get(result.get(student_id, ""), 0):
            result[student_id] = kind
    return result


def _absence_cell(group: Any, days: int) -> tuple[str, str, bool]:
    """(نصُّ الخلية، النغمة، قربُ العتبة) — الغيابُ بلا عذرٍ مقابل أقربِ عتبةٍ لم تُتجاوز.

    «قرب العتبة» يشمل من بقي له يومان أو أقلّ (هامشُ إنذار المنصّة) ومن تجاوز عتبةً.
    وصفرُ أيّامٍ لا إشارة: الخليةُ «–».
    """
    if days == 0:
        return "", "", False
    ese = is_special_education(group)
    gate = next_gate(group.grade, days, ese)
    crossed = bool(breached(group.grade, days, ese))
    if gate is None:
        return f"{days} — تجاوز كلَّ العتبات", "danger", True
    near = gate.max_days - days <= AttendanceService.GATE_WARNING_MARGIN_DAYS
    text = f"{days} من {gate.max_days}"
    if crossed:
        return text + " — تجاوز عتبةً", "danger", True
    return text, "warning" if near else "gray", near


def build_rows(enrollments: Any, group: Any, school: Any, year: str) -> list[RosterRow]:
    """صفوفُ الجدول لطلاب شعبةٍ: أصحابُ الإشارات أولاً ثمّ بالاسم. أربعةُ استعلاماتٍ مجمَّعة وما يجلبه `unexcused_days_for_class`."""
    enrollments = list(enrollments)
    ids = [e.student_id for e in enrollments]
    today = timezone.localdate()
    verdicts = _today_verdicts(ids, school, today)
    days_of = unexcused_days_for_class(group, school)
    statuses = _enrollment_statuses(ids, group, school, year)
    items = _open_items(ids, school)
    rows = []
    for e in enrollments:
        verdict = verdicts.get(e.student_id, "unrecorded")
        label, tone = TODAY_LABELS[verdict]
        days = days_of.get(e.student_id, 0)
        text, absence_tone, near = _absence_cell(group, days)
        status = statuses.get(e.student_id)
        item = items.get(e.student_id)
        rows.append(
            RosterRow(
                enrollment=e,
                today=(verdict, label, tone),
                absence_days=days,
                absence_text=text,
                absence_tone=absence_tone,
                near_threshold=near,
                enrollment_status=ENROLLMENT_LABELS[status] if status else None,
                open_item=OPEN_ITEM_LABELS[item] if item else None,
            )
        )
    rows.sort(key=lambda r: (-r.signals, r.enrollment.student.full_name))
    return rows


def summary(rows: list[RosterRow]) -> dict[str, int]:
    """أعدادُ أزرار الملخّص من القائمة الكاملة — قبل التصفية، فلا يتبدّل العددُ بالضغط."""
    return {
        "absent": sum(r.today[0] == "absent" for r in rows),
        "near": sum(r.near_threshold for r in rows),
        "open": sum(r.open_item is not None for r in rows),
    }


def page_context(scope: Any, group: Any, school: Any, year: str, params: Any) -> dict[str, Any]:
    """سياقُ صفحة الشعبة كاملاً: الصفوفُ المصفّاة والأعدادُ والمرجع — القراءةُ هنا لا في العرض.

    الطالبُ بقيده الجاري مضيَّقاً بنطاق الدور: قيدٌ قديمٌ نشطٌ في هذه الشعبة لا يُظهر
    للمشرف طالباً صار في جناحٍ آخر.
    """
    enrollments = list(scope.narrow(services.students_of_section(group), "student_id"))
    all_rows = build_rows(enrollments, group, school, year)
    key = params.get("filter", "")
    key = key if key in FILTERS else ""
    query = params.get("q", "")
    rows = apply_filters(all_rows, key, query)
    return {
        "enrollments": [r.enrollment for r in rows],
        "rows": rows,
        "total": len(all_rows),
        "counts": summary(all_rows),
        "active_filter": key,
        "q": query,
        "threshold_source": THRESHOLD_SOURCE,
    }


def apply_filters(rows: list[RosterRow], key: str, query: str) -> list[RosterRow]:
    """تصفيةُ الزرّ ثمّ البحثُ بالاسم — كلاهما على قائمةٍ في الذاكرة بلا استعلامٍ زائد."""
    if key == "absent":
        rows = [r for r in rows if r.today[0] == "absent"]
    elif key == "near":
        rows = [r for r in rows if r.near_threshold]
    elif key == "open":
        rows = [r for r in rows if r.open_item is not None]
    needle = query.strip()
    if needle:
        rows = [r for r in rows if needle in r.enrollment.student.full_name]
    return rows
