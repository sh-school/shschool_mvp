"""schedule_gate.py — بوّابةُ العجز اليقينيّ قبل توليد الجدول (G4-أ).

فحصُ الجدوى (`schedule_feasibility.check`) يعدّ ولا يبحث: ما ظهر عجزُه فيه لن يجده
بحثٌ مهما طال. وكان يُعرض تحذيراً في الصفحة بلا أثرٍ على الزرّ، فمن يضغط «بدء التوليد»
يولّد رغم عجزٍ محسوبٍ سلفاً.

فصار العجزُ اليقينيّ يمنع التوليدَ افتراضيّاً، ولا يتجاوزه إلّا سببٌ صريحٌ يكتبه صاحبُ
الصلاحيّة. والسببُ يُسجَّل في سجلّ التدقيق غير القابل للمحو لا في `config_snapshot`:
هذا يُستبدَل بالكامل حين يكتمل التوليدُ الحقيقيّ فلا يصلح مكاناً دائماً للسبب.
"""

from __future__ import annotations

from dataclasses import dataclass

from core.models import AuditLog, School
from operations import schedule_feasibility
from operations.models import ScheduleGeneration


class FeasibilityBlockedError(Exception):
    """عجزٌ يقينيّ بلا سببٍ صريحٍ للتجاوز — الرسالةُ تُقال للمستخدم كما هي."""


@dataclass(frozen=True)
class GateDecision:
    """ما قرّرته البوّابة: تقريرُ الجدوى، وسببُ التجاوز إن وُجد."""

    year: str
    report: schedule_feasibility.FeasibilityReport
    reason: str

    def create_generation(self, school: School, user) -> ScheduleGeneration:
        """صفُّ التوليد في الطابور، ومعه سطرُ التدقيق إن كان هناك تجاوز."""
        generation = ScheduleGeneration.objects.create(
            school=school,
            academic_year=self.year,
            generated_by=user,
            status="queued",
        )
        if self.reason:
            AuditLog.objects.create(
                school=school,
                user=user,
                action="create",
                model_name="other",
                object_id=str(generation.pk),
                object_repr=f"توليدٌ رغم عجزٍ يقينيّ {self.year}"[:300],
                changes={
                    "event": "schedule_generate_despite_infeasibility",
                    "reason": self.reason,
                    "minimum_unplaceable": self.report.minimum_unplaceable,
                    "blocking_codes": [f.code for f in self.report.blocking],
                },
            )
        return generation


def enforce(school: School, year: str, override_reason: str | None) -> GateDecision:
    """يفحص الجدوى، ويرفض إن كان العجزُ يقينيّاً ولا سببَ صريحاً للتجاوز."""
    report = schedule_feasibility.check(school, year)
    reason = (override_reason or "").strip()
    if report.blocking and not reason:
        raise FeasibilityBlockedError(
            f"عجزٌ يقينيّ يمنع التوليد: {report.blocking[0].summary} — عالِج التوزيعاتِ ثمّ أعد الفحص، "
            "أو اكتب سبباً صريحاً في بطاقة فحص الجدوى وولِّد على أيّ حال."
        )
    return GateDecision(year=year, report=report, reason=reason if report.blocking else "")
