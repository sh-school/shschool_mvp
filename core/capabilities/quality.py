"""قدراتُ مجال «الجودة» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap


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
        _cap("observation.create", "الزيارةُ الإشرافيّة", P.OBSERVATION_CREATE),
        _cap("observation.self", "التقييمُ الذاتيّ", P.OBSERVATION_SELF_CREATE),
        _cap("observation.peer", "تبادلُ الزيارات", P.OBSERVATION_PEER_CREATE),
    ]
