"""
clinic/queue.py — طابور العيادة اليوم (W-20261020-030)
════════════════════════════════════════════════════════
ثلاثُ حالاتٍ تُشتقّ من الحقول المرمَّزة (لا عمودَ حالةٍ جديد):
بانتظار (لا خدمةَ ولا شكوى بعد) ← تحت الرعاية ← انتهت (لها وقتُ إغلاق).

استعلامٌ واحد مهما كثرت الصفوف (طالبُ كلّ زيارةٍ بـ`select_related`)، والنصوصُ الحرّةُ المشفَّرة
تُؤجَّل فلا تُفكّ ولا تصل القالب. وأسماءُ الطلبة لا تظهر إلا لمن يحمل `clinic.write`.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from clinic.choices import OUTCOME_AUTO, STATE_DONE, STATE_IN_CARE, STATE_WAITING
from clinic.models import ClinicVisit


def visit_state(visit: ClinicVisit) -> str:
    if visit.closed_at is not None:
        return STATE_DONE
    if visit.service_code or visit.complaint_code:
        return STATE_IN_CARE
    return STATE_WAITING


@dataclass
class ClinicQueue:
    waiting: list[ClinicVisit] = field(default_factory=list)
    in_care: list[ClinicVisit] = field(default_factory=list)
    done: list[ClinicVisit] = field(default_factory=list)

    @property
    def auto_closed(self) -> list[ClinicVisit]:
        """ما أُغلق تلقائياً اليوم — تنبيهٌ للممرّض ليراجعه."""
        return [v for v in self.done if v.outcome == OUTCOME_AUTO]


def todays_queue(school, day) -> ClinicQueue:
    visits = (
        ClinicVisit.objects.filter(school=school, visit_date__date=day)
        .select_related("student")
        .defer("reason", "symptoms", "treatment")
        .order_by("visit_date")
    )
    queue = ClinicQueue()
    buckets = {
        STATE_WAITING: queue.waiting,
        STATE_IN_CARE: queue.in_care,
        STATE_DONE: queue.done,
    }
    for visit in visits:
        buckets[visit_state(visit)].append(visit)
    return queue


def search_students(school, term: str, limit: int) -> list:
    """طلبةُ المدرسة النشطون بالاسم (احتواء)، وصفُّ كلٍّ منهم النشط في `active_enrollments` — استعلامان لا أكثر."""
    from django.db.models import Prefetch

    from core.models import CustomUser, StudentEnrollment

    return list(
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__role__name="student",
            memberships__is_active=True,
            full_name__icontains=term,
        )
        .distinct()
        .prefetch_related(
            Prefetch(
                "enrollments",
                queryset=StudentEnrollment.objects.filter(is_active=True).select_related(
                    "class_group"
                ),
                to_attr="active_enrollments",
            )
        )
        .order_by("full_name")[:limit]
    )
