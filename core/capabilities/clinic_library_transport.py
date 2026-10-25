"""قدراتُ مجال «العيادة والمكتبة والنقل» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap


def clinic_library_transport_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    return [
        # ── العيادة والمكتبة والنقل ─────────────────────────────────
        _cap(
            "clinic.access",
            "وحدةُ العيادة (قراءة)",
            {"nurse", "principal", "vice_admin", "student_affairs_coordinator"},
        ),
        _cap(
            "clinic.write",
            "تعديلُ السجلّ الصحّيّ وتسجيلُ الزيارات",
            {"nurse", "principal", "vice_admin"},
            basis="بيانات صحّيّة لقاصرين: الكتابةُ سريريّةٌ — حكم 0104 على W-20261001-020 (المنسّقُ قراءةً فقط)",
        ),
        _cap(
            "clinic.export",
            "تصديرُ التقرير الشهريّ للعيادة (أعدادٌ بلا أسماء)",
            {"nurse", "principal"},
            basis="قدرةُ تصديرٍ مستقلّةٌ عن القراءة (W-20261020-032): ملفٌّ عدديٌّ يغادر المنصّة فيُسجَّل في سجلّ التدقيق",
        ),
        _cap("library.view", "المكتبةُ والكتب", P.LIBRARY_VIEW | P.LIBRARY_FULL),
        _cap("library.lend", "الإعارةُ والإرجاع", {"librarian", "principal", "vice_admin"}),
        _cap("library.borrowings_all", "سجلُّ استعارات المدرسة", P.LIBRARY_BORROWINGS_ALL),
        _cap(
            "transport.access",
            "وحدةُ النقل",
            P.TRANSPORT_FULL | P.TRANSPORT_MANAGE | {"student_affairs_coordinator"},
        ),
    ]
