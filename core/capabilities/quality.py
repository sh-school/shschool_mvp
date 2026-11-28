"""قدراتُ مجال «الجودة» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from typing import Any

from core.capabilities.base import Capability, Shared, _cap


def _is_followed_staff(user: Any) -> bool:
    """منحُ قراءةٍ للموظّف المُتابَع **بدوره**: فلا يرثه حاملُ الجناح بالتعيين (متابعةٌ تخصّ صاحبَها)."""
    return str(user.get_role()) in {"admin_supervisor", "social_worker", "psychologist"}


def quality_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    return [
        # ── الجودة ──────────────────────────────────────────────────
        _cap("quality.access", "وحدةُ الجودة", P.QUALITY_ACCESS),
        _cap("quality.manage", "إدارةُ الخطّة التشغيليّة", P.QUALITY_MANAGE),
        _cap(
            "quality.evaluations",
            "تقييمُ أداء الموظّفين",
            {"principal", "vice_admin", "vice_academic"},
            basis="افتراضُ المنصّة — والنصُّ يجعل الرئيسَ المباشرَ كاتبَ التقييم (م16)",
        ),
        _cap(
            "quality.supervisor_followup",
            "متابعةُ الأداء الإداريّ (إنشاءٌ وتعديل)",
            P.SUPERVISOR_FOLLOWUP_MANAGE,
            basis="قرارُ المالك: استمارة 19 للمدير والنائب الإداريّ (W-20261125-003)",
        ),
        _cap(
            "quality.supervisor_followup_view",
            "قراءةُ متابعات الأداء الإداريّ",
            P.SUPERVISOR_FOLLOWUP_MANAGE,
            scope="الموظّفُ المُتابَع يقرأ متابعاته المحفوظة وحدَها",
            basis="قرارُ المالك: استمارة 19 (W-20261125-003)",
            grant=_is_followed_staff,
        ),
        _cap("observation.create", "الزيارةُ الإشرافيّة", P.OBSERVATION_CREATE),
        _cap("observation.self", "التقييمُ الذاتيّ", P.OBSERVATION_SELF_CREATE),
        _cap("observation.peer", "تبادلُ الزيارات", P.OBSERVATION_PEER_CREATE),
    ]
