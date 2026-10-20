"""قدراتُ مجال «الإشعارات والتحليلات وسجلُّ مصدر الحقيقة» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap
from core.capabilities.ux_survey import ux_survey_capabilities


def notifications_analytics_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    leadership = shared.leadership
    return [
        # ── الإشعارات والتحليلات ────────────────────────────────────
        *ux_survey_capabilities(_cap, P),
        # ── سجلُّ مصدر الحقيقة (W-20261015-007): القراءةُ للكادر، والاقتراحُ للمشرفين فأعلى، والاعتمادُ للمالك وحده ──
        _cap(
            "sot.read",
            "قراءةُ سجلِّ مصدر الحقيقة (الأحكامُ النافذةُ فقط لغير الإدارة)",
            P.ALL_STAFF_ROLES,
            basis="قرارُ المالك 2026-10-15 — القراءةُ لكل الأدوار",
        ),
        _cap(
            "sot.propose",
            "اقتراحُ تصحيحٍ أو حكمٍ في سجلِّ مصدر الحقيقة",
            P.TIER_1_LEADERSHIP | P.TIER_2_DEPUTIES | P.TIER_3_SUPERVISORS,
            basis="قرارُ المالك 2026-10-15 — الاقتراحُ للمشرفين",
        ),
        _cap(
            "sot.approve",
            "اعتمادُ الأحكام وتغييرُ حالتها وحذفُها ناعمًا (المالكُ وحده)",
            {"platform_developer"},
            basis="قرارُ المالك 2026-10-15 — الاعتمادُ للمالك وحده",
        ),
        _cap("notifications.broadcast", "إدارةُ الإشعارات والإرسالُ الجماعيّ", leadership),
        _cap("analytics.school", "تحليلاتُ المدرسة", leadership),
    ]
