"""
قراءةُ إشارات الاستثناء لصفحة طلاب الشعبة — استعلاماتٌ مجمَّعةٌ بعددٍ ثابتٍ مهما بلغ الطلاب.

القاعدةُ «الخليّةُ فارغةٌ إلا عند إشارة»: لا يُكتب «لا شيء» لمن لا شيءَ عليه. والإشارةُ تمرّ على
نطاق الدور: من لا يحقّ له ملاحظاتُ الأخصائيَّين (`scope.hides_specialist_notes`) لا يُجلب له
ما يحمل قرارَهم أصلاً، فلا يُحسب ولا يظهر في عدّاد الشريط.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from django.db.models import QuerySet
from django.utils import timezone

from behavior.models import BehaviorInfraction
from core.academic_calendar import academic_year_window
from core.models.academic import ClassGroup, StudentEnrollment
from operations.absence_policy import gates_for, next_gate
from operations.absence_standing import unexcused_days_for_class
from operations.attendance_policy import is_special_education
from operations.models import StudentAttendance
from operations.models.absence_followup import AbsenceActionLog
from operations.services.attendance import AttendanceService
from wings.scope import StudentScope

#: مفاتيحُ التصفية المسموحة من `?f=` — نصٌّ من المستخدم لا يُستعمل إلا مطابقاً لها.
FILTERS = ("absent", "near", "open")

#: المصدرُ الذي يُسنَد إليه رقمُ العتبة في الشارة — [LEGAL].
LEGAL_SOURCE = "المصدر: 08_conduct_policy_2026.md م3.4.1.3"

#: حالاتُ إجراء الغياب التي لم يُغلق أمرُها: لم يتمّ، أو جزئيّ، أو لم تتمّ متابعتُه.
_OPEN_ACTION_STATUSES = ("not_done", "partial", "not_followed")

#: أنواعُ الإجراء التي تُعدّ تعهّداً أو إحالة — والإحالةُ للأخصائي الاجتماعيّ ممّا يحجبه النطاقُ.
_PLEDGE_OR_REFERRAL = ("written_notice", "refer_coordinator", "refer_social")
_SPECIALIST_KINDS = ("refer_social",)


@dataclass
class StudentSignals:
    """إشاراتُ طالبٍ واحد — الحقولُ الفارغةُ تعني خليّةً فارغة."""

    enrollment: Any
    today: str = ""  # present | late | absent | unrecorded | فارغ (لا رصدَ في الشعبة)
    near: dict[str, int] | None = None
    new: bool = False
    transferred: bool = False
    open_item: bool = False
    sort_key: tuple[int, str] = field(default=(1, ""))

    @property
    def has_signal(self) -> bool:
        return bool(
            self.today in ("absent", "unrecorded", "late")
            or self.near
            or self.new
            or self.transferred
            or self.open_item
        )


def _today_status(student_ids: list[Any], school: Any, day: dt.date) -> dict[Any, str]:
    """حضورُ اليوم: استعلامٌ واحد. حاضرٌ إن حضر أيَّ حصّةٍ (والمتأخّرُ حاضر)، وإلا غائب."""
    rows = StudentAttendance.objects.filter(
        school=school, student_id__in=student_ids, session__date=day
    ).values_list("student_id", "status")
    seen: dict[Any, set[str]] = {}
    for student_id, status in rows:
        seen.setdefault(student_id, set()).add(status)
    result: dict[Any, str] = {}
    for student_id, statuses in seen.items():
        if statuses & {"present", "late"}:
            result[student_id] = (
                "late" if "late" in statuses and "present" not in statuses else "present"
            )
        else:
            result[student_id] = "absent"
    return result


def _open_items(student_ids: list[Any], school: Any, scope: StudentScope) -> set[Any]:
    """من عليه بندٌ مفتوح: حالةُ سلوكٍ غيرُ معالَجة، أو تعهّدٌ/إحالةٌ لم يُغلق — استعلامان."""
    behavior = BehaviorInfraction.objects.filter(
        school=school, student_id__in=student_ids, is_resolved=False
    ).values_list("student_id", flat=True)
    actions = AbsenceActionLog.objects.filter(
        school=school,
        student_id__in=student_ids,
        action_kind__in=_PLEDGE_OR_REFERRAL,
        status__in=_OPEN_ACTION_STATUSES,
        corrected_by__isnull=True,
    )
    if scope.hides_specialist_notes:
        actions = actions.exclude(action_kind__in=_SPECIALIST_KINDS)
    return set(behavior) | set(actions.values_list("student_id", flat=True))


def _transferred_in(student_ids: list[Any], group: ClassGroup) -> set[Any]:
    """من له قيدٌ أُغلق بالنقل في عامٍ هذه الشعبة نفسِه — استعلامٌ واحد."""
    return set(
        StudentEnrollment.objects.filter(
            student_id__in=student_ids,
            class_group__school=group.school,
            class_group__academic_year=group.academic_year,
            left_at__isnull=False,
        )
        .exclude(class_group=group)
        .values_list("student_id", flat=True)
    )


def _near_gate(days: int, group: ClassGroup, ese: bool) -> dict[str, int] | None:
    """أقربُ عتبةٍ لم تُتجاوَز إن كان الفاصلُ عنها في هامش الإنذار — وإلا `None`."""
    gate = next_gate(group.grade, days, ese)
    if gate is None or gate.max_days - days > AttendanceService.GATE_WARNING_MARGIN_DAYS:
        return None
    return {"days": days, "max": gate.max_days}


def section_signals(
    group: ClassGroup,
    enrollments: QuerySet[Any],
    scope: StudentScope,
    today: dt.date | None = None,
) -> list[StudentSignals]:
    """إشاراتُ كلِّ طالبٍ في الشعبة، مرتّبةً: أصحابُ الإشارات أولاً ثم البقيّة بالاسم."""
    day = today or timezone.localdate()
    rows = list(enrollments)
    ids = [e.student_id for e in rows]
    school = group.school
    ese = is_special_education(group)
    has_gates = bool(gates_for(group.grade, ese))
    status = _today_status(ids, school, day)
    absences = unexcused_days_for_class(group, school, on=day) if has_gates else {}
    items = _open_items(ids, school, scope)
    moved = _transferred_in(ids, group)
    window = academic_year_window(school, day)
    result = []
    for e in rows:
        sig = StudentSignals(e)
        # لا رصدَ في الشعبة كلِّها (عطلةٌ أو حصّةٌ لم تبدأ) فلا يُشار إلى كلّ طالبٍ «غير مرصود».
        sig.today = status.get(e.student_id, "unrecorded" if status else "")
        sig.near = _near_gate(absences.get(e.student_id, 0), group, ese) if has_gates else None
        sig.new = bool(window and e.enrolled_at > window[0])
        sig.transferred = e.student_id in moved
        sig.open_item = e.student_id in items
        sig.sort_key = (0 if sig.has_signal else 1, e.student.full_name)
        result.append(sig)
    result.sort(key=lambda s: s.sort_key)
    return result


def summary_counts(signals: list[StudentSignals]) -> dict[str, Any]:
    """عدّاداتُ الشريط وعدّادُ اليوم: حاضر (منهم متأخر) · غائب · غير مرصود."""
    return {
        "absent": sum(1 for s in signals if s.today == "absent"),
        "near": sum(1 for s in signals if s.near),
        "open": sum(1 for s in signals if s.open_item),
        "present": sum(1 for s in signals if s.today in ("present", "late")),
        "late": sum(1 for s in signals if s.today == "late"),
        "unrecorded": sum(1 for s in signals if s.today == "unrecorded"),
    }


def today_line(counts: dict[str, Any]) -> str:
    """سطرُ حضور اليوم للبطاقة: المتأخّرُ يُحتسب حاضراً ويُكتب «منهم متأخر»؛ والصفرُ لا يُكتب."""
    parts = []
    if counts["present"]:
        late = f" منهم متأخر {counts['late']}" if counts["late"] else ""
        parts.append(f"حاضر {counts['present']}{late}")
    if counts["absent"]:
        parts.append(f"غائب {counts['absent']}")
    if counts["unrecorded"]:
        parts.append(f"غير مرصود {counts['unrecorded']}")
    return " · ".join(parts)


def narrow_signals(signals: list[StudentSignals], query: str, flt: str) -> list[StudentSignals]:
    """البحثُ بالاسم والتصفيةُ بزرّ الشريط — على القائمة الجاهزة لا استعلامٌ جديد."""
    needle = query.strip().casefold()
    out = signals
    if needle:
        out = [s for s in out if needle in s.enrollment.student.full_name.casefold()]
    if flt == "absent":
        out = [s for s in out if s.today == "absent"]
    elif flt == "near":
        out = [s for s in out if s.near]
    elif flt == "open":
        out = [s for s in out if s.open_item]
    return out
