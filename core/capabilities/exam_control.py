"""قدراتُ مجال «الكنترول» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap


def exam_control_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    return [
        # ── الكنترول ────────────────────────────────────────────────
        _cap(
            "exam_control.access",
            "نظامُ الكنترول",
            P.EXAM_CONTROL_ACCESS,
            basis="افتراضُ المنصّة — والنصُّ الوزاريُّ يجعله لجنةً موقوتة (الدراسة، ملحق د)",
        ),
        _cap(
            "exam_control.report_incident",
            "تسجيلُ حادثةِ اختبارٍ ومراجعتُها",
            P.EXAM_CONTROL_REPORT_INCIDENT,
            basis="قرارُ 2026-09-15 (النطاق) وقرارُ المستخدم 2026-09-17 (لا شيءَ آخر من الكنترول)",
        ),
    ]
