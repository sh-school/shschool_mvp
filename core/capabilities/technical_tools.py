"""قدراتُ مجال «الأدوات التقنيّة» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap


def technical_tools_capabilities(shared: Shared) -> list[Capability]:
    return [
        # ── الأدوات التقنيّة ─────────────────────────────────────────
        _cap(
            "it_admin.reset_passwords",
            "إعادةُ تعيين كلمات مرور المستخدمين",
            {"it_technician"},
            basis="قرارُ المالك 2026-09-22",
        ),
        _cap(
            "developer.linked_accounts",
            "إدارةُ الحسابات المرتبطة بالمطوّر",
            {"platform_developer"},
            scope="المنصّة",
            basis=(
                "D-305م وD-306م وشروطُ 0104 (W-20261009-032): جدولُ الربط لمطوّر المنصّة والمشرف الأعلى وحدَهما، "
                "بقدرةٍ منفصلةٍ لا بأدوات المطوّر العامّة"
            ),
        ),
    ]
