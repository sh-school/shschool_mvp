"""قدراتُ مجال «الأدوات التقنيّة» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from typing import Any

from core.capabilities.base import Capability, Shared, _cap


def _data_protection_officer(user: Any) -> bool:
    """المعيَّنُ مسؤولاً لحماية البيانات في مدرسته — الصفةُ بالتعيين لا بالدور."""
    school = user.get_school()
    return bool(school is not None and school.data_protection_officer_id == user.pk)


def technical_tools_capabilities(shared: Shared) -> list[Capability]:
    return [
        # ── الأدوات التقنيّة ─────────────────────────────────────────
        _cap(
            "it_admin.reset_passwords",
            "إعادةُ تعيين كلمات مرور المستخدمين",
            {"it_technician"},
            basis="قرارُ المالك 2026-09-22",
        ),
        # ── حمايةُ البيانات (U-11) ───────────────────────────────────
        _cap(
            "governance.erasure_sign",
            "توقيعُ طلبات محو بيانات الطالب ورفضُها",
            {"principal", "vice_admin"},
            basis="قرارُ المالك 2026-11-27 (U-11) — PDPPL م.18",
            grant=_data_protection_officer,
        ),
        _cap(
            "governance.appoint_dpo",
            "تعيينُ مسؤول حماية البيانات",
            {"principal"},
            basis="قرارُ المالك 2026-11-27 (U-11)",
        ),
    ]
