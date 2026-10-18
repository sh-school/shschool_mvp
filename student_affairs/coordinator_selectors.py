"""أقسامُ لوحة منسّق شؤون الطلبة (W-20261018-001) — بالقدرات القائمة فقط، بلا منحٍ ولا سحب.

كلُّ قسمٍ يظهر لمن يملك قدرتَه وحدَه، فلا يفتح المنسّقُ بهذه الأقسام بابًا لم يكن له:

- متابعةُ الغياب والتواصل: `operations.absence_followup_view` — الغائبون بالحصّتين الأولى والثانية معاً، وعدّادُ حالات المتابعة
  لمن يملك `operations.absence_followup_followup`.
- استلامُ الإجازات المرضيّة: من آخر إجراءٍ في `AbsenceActionLog` (حالتُه `sick_leave_received`).
- المستدعون للتعهد: `behavior.summon_parent` — مخالفاتُ الدرجة الثانية اليومَ، والدرجةُ الرابعة غيرُ المحسومة، وحالةُ الاستدعاء.
- الرحلاتُ المدرسيّة: لا وحدةَ لها في المنصّة بعدُ (فجوةٌ مسجَّلة في بطاقة المهمّة) فلا قسمَ لها.

رقمُ وليّ الأمر وحدَه بلا اسمِ وليٍّ ولا أمّ (D-431م)، ويُعرض لحامل `behavior.guardian_contact` بالآلية القائمة
(`guardian_phones_for`) مع سطر تدقيقٍ بعدده لا برقمه — قرارُ المالك 2026-10-18.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from core.capabilities import has_capability

#: حدُّ ما يُعرض من كلّ قائمة — اللوحةُ مدخلٌ لا تقرير.
LIMIT = 30

_ACTION_LABELS = (
    ("done", "تمّ"),
    ("partial", "تمّ جزئياً"),
    ("not_done", "لم يتمّ"),
    ("not_followed", "لم تتمّ المتابعة"),
)


def _action_counts(rows: list[dict]) -> list[tuple[str, int]]:
    """عدّادُ حالات متابعة الإجراء؛ ومن بلا إجراءٍ مسجَّلٍ يُعدّ «لم تتمّ المتابعة»."""
    tally = dict.fromkeys((key for key, _ in _ACTION_LABELS), 0)
    for row in rows:
        status = row["action"].status if row["action"] else "not_followed"
        tally[status if status in tally else "not_followed"] += 1
    return [(label, tally[key]) for key, label in _ACTION_LABELS]


def _absence(user: Any, today: dt.date) -> dict[str, Any]:
    from operations.services.absence_followup import followup_rows

    rows = followup_rows(user, today)
    panel: dict[str, Any] = {
        "absent_count": len(rows),
        "contacted": sum(1 for r in rows if r["contact"]),
        "sick_leave": [
            {"name": r["student"].full_name, "klass": r["class_group"].short_label}
            for r in rows
            if r["action"] and r["action"].status == "sick_leave_received"
        ][:LIMIT],
    }
    if has_capability(user, "operations.absence_followup_followup"):
        panel["action_counts"] = _action_counts(rows)
    return panel


def _pledge_status(infraction: Any) -> str:
    if infraction.parent_undertaking_signed:
        return "التعهدُ موقَّع"
    if infraction.parent_summoned:
        return (
            f"استُدعي في {infraction.parent_summon_date:%d/%m}"
            if infraction.parent_summon_date
            else "استُدعي"
        )
    return "لم يُستدعَ بعد"


def _pledge_rows(school: Any, today: dt.date, with_phones: bool) -> list[dict[str, Any]]:
    from django.db.models import Q

    from behavior.models import BehaviorInfraction

    qs = (
        BehaviorInfraction.objects.filter(school=school)
        .filter(Q(level=2, date=today) | Q(level=4, is_resolved=False))
        .select_related("student")
        .order_by("-level", "-date")[:LIMIT]
    )
    infractions = list(qs)
    phones: dict[Any, list[str]] = {}
    if with_phones and infractions:
        from operations.services.absence_followup import guardian_phones_for

        phones = guardian_phones_for(school, {inf.student_id for inf in infractions})
    return [
        {
            "name": inf.student.full_name,
            "phones": phones.get(inf.student_id, []),
            "level": inf.level,
            "when": "اليوم" if inf.date == today else f"{inf.date:%d/%m}",
            "status": _pledge_status(inf),
            "signed": inf.parent_undertaking_signed,
        }
        for inf in infractions
    ]


def audit_phone_read(request: Any, count: int, where: str) -> None:
    """أثرُ عرض أرقام الأولياء: العددُ والدورُ وحدَهما — لا رقمَ ولا اسم."""
    if not count:
        return
    from core.models import AuditLog

    AuditLog.log(
        user=request.user,
        action="view",
        model_name="ParentStudentLink",
        object_id=request.school.id,
        object_repr=f"أرقامُ أولياء الأمور — {where}",
        changes={"phones": count, "role": request.user.get_role()},
        school=request.school,
        request=request,
    )


def coordinator_panels(request: Any, today: dt.date) -> dict[str, Any]:
    """سياقُ الأقسام الأربعة لما يملكه المستخدمُ من قدراتها؛ مفتاحٌ غائبٌ = قسمٌ مخفيّ."""
    user = request.user
    out: dict[str, Any] = {}
    if has_capability(user, "operations.absence_followup_view"):
        out["absence"] = _absence(user, today)
    if has_capability(user, "behavior.summon_parent"):
        rows = _pledge_rows(
            user.get_school(), today, has_capability(user, "behavior.guardian_contact")
        )
        audit_phone_read(request, sum(len(r["phones"]) for r in rows), "لوحة شؤون الطلبة")
        out["pledges"] = rows
    return {"panels": out} if out else {}
