"""قدراتُ مجال «الأجنحة» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.capabilities.base import Capability, Shared, _cap, _delegated, _holds_a_wing


def wings_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول
    from core.models.academic import WingCoverage

    return [
        # ── الأجنحة ─────────────────────────────────────────────────
        _cap(
            "wings.floors",
            "شاشةُ الأجنحة والطوابق",
            {
                "principal",
                "vice_admin",
                "vice_academic",
                "admin_supervisor",
                "platform_developer",
                "student_affairs_coordinator",  # بندٌ في قائمة إدارة شؤون الطلاب (D-273م)
            },
        ),
        _cap("wings.assign_cover", "تكليفُ بديلٍ لجناح", WingCoverage.ASSIGNER_ROLES),
        _cap(
            "wings.record_day",
            "رصدُ يوم الشعبة في الجناح",
            P.WING_DAY_RECORD,
            scope="أجنحةُ المشرف (أصيلاً أو بديلاً)",
            basis=(
                "قرارُ 2026-09-12: المشرفُ الإداريّ يحصر الغياب — وقرارُ المدير: البديلُ "
                "مشرفٌ إداريٌّ أو ملاحظُ طلبةٍ أو عاملُ خدمات، فيرصد بتكليفه لا بدوره"
            ),
            grant=_holds_a_wing,
        ),
        _cap(
            "wings.exit_permit_request",
            "طلبُ إذن خروج طالب",
            frozenset(P.WING_DAY_RECORD | {"teacher"}),
            scope="المعلّم لشُعبه، وحاملُ الجناح لأجنحته",
            basis="مواصفة W-20261005-010: المعلّم يطلب فقط؛ والاعتمادُ لحامل الجناح والنائب الإداريّ (`wings.record_day`)",
            grant=_holds_a_wing,
            # قرارُ المالك 2026-10-17: المعلّمُ وحدَه لا من يرثه (المساعدان وأخصائيّو التربية الخاصة والمنسّقون).
            not_inherited_by={
                "teacher_assistant",
                "ese_teacher",
                "ese_assistant",
                "coordinator",
                "activities_coordinator",
                "e_projects_coordinator",
            },
        ),
        _cap(
            "wings.school_wide",
            "حاصرُ الغياب العامّ — الأجنحةُ الخمسةُ كلُّها",
            P.SCHOOL_WIDE_ABSENCE_ROLES,
            scope="أجنحةُ المدرسة كلُّها، للغياب وحدَه",
            basis=(
                "قرارُ المالك 2026-10-06: موظّفٌ إداريٌّ (مشرفٌ إداريّ) يحصر الغيابَ في المدرسة كلِّها، "
                "فيرى الأجنحةَ الخمسةَ ويعتمد رصدَ المعلّمين ويصحّحه ويحوّل العذرَ بمهلته، ويرفع ملخّصَ الحصّتين "
                "الأولى والثانية للوزارة يدويّاً. قدرةٌ مفوَّضةٌ باسمه (يمنحها المديرُ أو النائبُ الأكاديميّ) "
                "لا دورٌ جديد؛ ويبقى عنه ما يُحجب عن مشرف الجناح (الدرجاتُ وملاحظاتُ الأخصائيّين وسببُ العيادة)"
            ),
            grant=_delegated("wings.school_wide"),
        ),
        _cap(
            "wings.excuse_after_deadline",
            "قبولُ عذرِ غيابٍ بعد مهلة اليومين",
            P.EXCUSE_AFTER_DEADLINE,
            basis=(
                "الدليل التنظيميّ 2026 م 3.4.1.5: إن لم يردّ وليُّ الأمر خلال يومين حُسب "
                "الغيابُ بلا عذر — فما بعد المهلة استثناءٌ يقرّره النائبُ الإداريّ بسبب"
            ),
        ),
    ]
