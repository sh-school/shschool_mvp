"""بوّابةُ اعتماد جدول V2 — معاملةٌ واحدة، بصمةٌ للمعروض، دورٌ وقدرةٌ في الخدمة، ومرجعُ إذنٍ متحقَّق (W-20261003-020).

الاعتمادُ هو النشر (يفعّل الحصصَ ويشعر المعلّمين)، فهذه البوّابةُ هي نقطةُ الضبط الوحيدة، وسندُها سطرُ STRIDE
`docs/architecture/stride_v2_approval_gate.md` (وافق عليه المالكُ 2026-10-20):

- T (عبث/تسابق): قفلٌ `select_for_update` على كلّ مسوّدات المدرسة والعام بترتيب الرقم، ثمّ إعادةُ قراءة الحالة تحت القفل؛
  فلا يمرّ اعتمادان متزامنان، وإعادةُ التقييم ومقارنةُ البصمة والاعتمادُ وسطرُ التدقيق في المعاملة نفسِها.
- بصمةُ المعروض: المستدعي يمرّر البصمةَ التي رآها المعتمِدُ؛ فإن اختلفت عن بصمة المسوّدة المقبولة أو عن إعادة التقييم رُفض.
- E (رفعُ صلاحية): `has_capability("schedule.approve")` **داخل** الخدمة، وحصرُ المطوّر `schedule_developer_only_blocks`؛
  ولا `is_superuser` استثناءً.
- R (إنكار): مرجعُ إذنٍ = معرّفُ قرارٍ + الرأسُ المعتمد معاً؛ يُتحقَّق من وجود القرار في سجلّ القرارات
  (`decisions_registry.Decision`) أو في القائمة المغلقة المؤقّتة `SCHEDULE_APPROVAL_DECISIONS` في الإعدادات؛ ويُدوَّنان في
  سطر التدقيق. وفشلُ التحقّق يمنع الاعتمادَ (مغلقٌ بالافتراض). والرأسُ يُتحقَّق من شكله وتدوينه؛ أمّا مطابقتُه لإيداعٍ
  فهي في سلسلة الفلو (approval_check) لا في وقت التشغيل.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from django.conf import settings
from django.db import transaction

HEAD_RE = re.compile(r"^[0-9a-f]{7,40}$")


class ApprovalGateError(Exception):
    """اعتمادٌ مرفوضٌ من البوّابة (رسالتُه عربيّةٌ عامّةٌ بلا بياناتٍ شخصيّة)."""


@dataclass(frozen=True)
class ApprovalAuthorization:
    decision_id: str
    approved_head: str


def verify_authorization(auth: ApprovalAuthorization | None) -> ApprovalAuthorization:
    """يرفع ApprovalGateError ما لم يصحّ المرجع: قرارٌ موجود + رأسٌ بشكلٍ صحيح."""
    if auth is None or not (auth.decision_id or "").strip():
        raise ApprovalGateError("لا مرجعَ إذنٍ: يلزم معرّفُ قرارٍ ورأسٌ معتمد")
    if not HEAD_RE.match((auth.approved_head or "").lower()):
        raise ApprovalGateError("مرجعُ الإذن بلا رأسٍ معتمدٍ صحيح")
    allowed = set(getattr(settings, "SCHEDULE_APPROVAL_DECISIONS", ()) or ())
    if auth.decision_id in allowed:
        return auth
    from decisions_registry.models import Decision

    if not Decision.objects.filter(decision_id=auth.decision_id).exists():
        raise ApprovalGateError("معرّفُ القرار غيرُ موجودٍ في سجلّ القرارات")
    return auth


def approve(
    generation: Any,
    *,
    user: Any,
    request: Any,
    authorization: ApprovalAuthorization | None,
    presented_fingerprint: str,
) -> dict:
    """الاعتمادُ الذرّيّ لمسوّدة V2 — انظر وثيقةَ الوحدة."""
    from core.capabilities import has_capability
    from core.capabilities.schedule_developer_only import schedule_developer_only_blocks
    from core.models.audit import AuditLog
    from operations.models import ScheduleGeneration
    from operations.schedule_evaluator import generation_slots
    from operations.scheduler_v2.runner import evaluate_slots, is_displayable
    from operations.services.schedule import ScheduleService

    if not has_capability(user, "schedule.approve") or schedule_developer_only_blocks(
        user, "schedule.approve"
    ):
        raise ApprovalGateError("لا تملك قدرة اعتماد الجدول")
    authorization = verify_authorization(authorization)
    with transaction.atomic():
        # القفلُ على كلّ مسوّدات المدرسة والعام بترتيبٍ ثابت: يسلسل المتسابقين ولا يُوقع تشابكاً (deadlock).
        locked = list(
            ScheduleGeneration.objects.select_for_update()
            .filter(school=generation.school, academic_year=generation.academic_year)
            .order_by("pk")
        )
        current = next((g for g in locked if g.pk == generation.pk), None)
        if current is None or current.status != "draft" or not is_displayable(current):
            raise ApprovalGateError("ليست مسودّةً مقبولةً من المُقيِّم — لا تُعتمد (ربّما اعتُمدت للتوّ)")
        snap = current.config_snapshot or {}
        accepted_fp = (snap.get("evaluation") or {}).get("fingerprint")
        if not presented_fingerprint or presented_fingerprint != accepted_fp:
            raise ApprovalGateError(
                "النسخةُ المعروضةُ لم تعد هي المسوّدةَ الحاليّة — أعد العرضَ ثمّ اعتمد"
            )
        fresh = evaluate_slots(
            current.school, current.academic_year, generation_slots(current), snap.get("solver")
        )
        if not fresh.accepted or fresh.fingerprint != accepted_fp:
            raise ApprovalGateError("تغيّرت المسودّةُ بعد قبولها أو لم تعد مقبولة — أعد التوليد")
        result = ScheduleService.approve_generation(current, acknowledged=False)
        AuditLog.log(
            user=user,
            action="update",
            model_name="other",
            object_id=current.pk,
            object_repr=f"اعتمادُ جدول V2 {current.academic_year}",
            changes={
                "event": "schedule_v2_approved",
                "fingerprint": fresh.fingerprint,
                "solver": snap.get("solver"),
                "objective_value": fresh.objective_value,
                "decision_id": authorization.decision_id,
                "approved_head": authorization.approved_head.lower(),
            },
            school=current.school,
            request=request,
        )
    generation.status = current.status
    return result
