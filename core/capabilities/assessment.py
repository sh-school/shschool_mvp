"""قدراتُ مجال «التقييم والدرجات» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap


def assessment_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    leadership = shared.leadership
    return [
        # ── التقييم والدرجات ────────────────────────────────────────
        _cap(
            "assessments.enter_grades",
            "إنشاءُ التقييمات وإدخالُ الدرجات",
            {"principal", "vice_academic", "coordinator", "teacher", "ese_teacher"},
            scope="بحسب الشُّعب والموادّ داخلَ الشاشة",
        ),
        _cap(
            "assessments.view_results",
            "لوحةُ التقييم وسجلُّ درجات الشعبة",
            {
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "academic_advisor",
            },
        ),
        _cap("assessments.oversee", "إعدادُ الموادّ ومتابعةُ المتعثّرين", leadership),
        _cap(
            "grades.import",
            "استيرادُ الدرجات من ملفّ",
            {
                "principal",
                "vice_academic",
                "vice_admin",
                "coordinator",
                "teacher",
                "ese_teacher",
                "admin",
                "secretary",
            },
        ),
        _cap(
            "reports.results",
            "كشوفُ النتائج وشهاداتُ الطلبة",
            {"principal", "vice_academic", "vice_admin", "coordinator", "teacher", "ese_teacher"},
        ),
        _cap(
            "reports.school",
            "تقاريرُ الحضور والسلوك والشهادات للشعبة",
            leadership | {"student_affairs_coordinator"},
        ),
        _cap(
            "academic.reports_school",
            "التقاريرُ الأكاديميّةُ على مستوى المدرسة",
            P.ACADEMIC_REPORTS_VIEW,
            basis="مراجعةُ الصلاحيّات 2026-09-13 (#222)",
        ),
    ]
