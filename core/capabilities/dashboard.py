"""قدراتُ مجال «لوحة التحكّم» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap


def dashboard_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    return [
        # ── لوحة التحكّم ────────────────────────────────────────────
        _cap("dashboard.open", "فتحُ لوحة التحكّم", P.ALL_STAFF_ROLES | {"student", "parent"}),
    ]
