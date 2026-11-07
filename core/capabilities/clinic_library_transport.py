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
            "clinic.health_full",
            "الملفُّ الصحّيُّ كاملاً (تشخيصٌ وأدويةٌ وحساسيّة)",
            {"nurse"},
            basis="قرار المالك 2026-10-21 (W-20261020-033): الممرّضُ وحدَه يرى الكامل؛ المدير والنائب مختصرٌ ويفتحان الكاملَ بسببٍ مغلقٍ يُسجَّل",
        ),
        _cap(
            "clinic.chronic_name",
            "كشفُ اسم الحالة المزمنة في صفحة الطالب (بنقرةٍ مسجَّلة)",
            {"nurse", "principal", "vice_admin", "student_affairs_coordinator"},
            basis="بطاقة W-20261107-001: المعنيّون بالطالب يرون اسمَ الحالة فقط بنقرةٍ مقصودةٍ يُسجَّل فتحُها؛ والمعلّمُ يرى «يحتاج مراعاةً» بلا اسمٍ",
        ),
        _cap(
            "clinic.counts",
            "اللوحةُ العدديّةُ للعيادة (أعدادٌ بلا أسماء)",
            {"nurse", "principal", "vice_admin", "student_affairs_coordinator"},
            basis="أعدادٌ مجمَّعةٌ بقمع الخلايا الأقلّ من 5 وبلا أسماءٍ ولا نصٍّ صحّيّ — والمنسّقُ يراها بالقدرة لا بدورٍ جديد (W-20261020-031)",
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
