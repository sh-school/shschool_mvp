"""قدراتُ مجال «وليّ الأمر» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap
from core.parent_consent import holds_parent_membership


def parents_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    return [
        # ── وليّ الأمر ──────────────────────────────────────────────
        _cap(
            "parents.portal",
            "بوّابةُ وليّ الأمر",
            P.PARENT_PORTAL,
            scope="أبناؤه وحدَهم",
            basis=(
                "قرارُ المالك 2026-09-16: الكادرُ الذي له عضويّةُ وليّ أمرٍ يدخل بوّابتَه "
                "ليرى أبناءه وحدَهم، بعد الموافقة على سياسة البيانات"
            ),
            grant=holds_parent_membership,
        ),
        _cap("parents.admin", "إدارةُ ربط أولياء الأمور", P.PARENT_PORTAL_ADMIN),
    ]
