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
    ]
