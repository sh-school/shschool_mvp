"""قدراتُ مجال «السلوك» — قسمٌ من سجلّ القدرات نُقل حرفاً بلا تغيير قدرةٍ ولا حامل (W-20261019-007)."""

from __future__ import annotations

from core.behavior_committee_roles import BEHAVIOR_COMMITTEE_CASE_SCOPED
from core.capabilities.base import Capability, Shared, _cap


def behavior_capabilities(shared: Shared) -> list[Capability]:
    from core import permissions as P  # noqa: N812 — اختصارٌ يُقرأ به السجلُّ كجدول

    family_callers = shared.family_callers
    return [
        # ── السلوك ──────────────────────────────────────────────────
        _cap(
            "behavior.view",
            "ملفُّ السلوك ولوحتُه",
            P.BEHAVIOR_MANAGE | P.BEHAVIOR_RECORD | P.BEHAVIOR_VIEW_ALL,
        ),
        _cap(
            "behavior.record",
            "تسجيلُ مخالفةٍ وتقريرُها",
            P.BEHAVIOR_MANAGE | P.BEHAVIOR_RECORD,
            # رصدُ مخالفةٍ تأديبيّةٍ لقاصرٍ كتابةٌ حسّاسة؛ المساعدان يرثان جدولَ المعلّم وحضورَه لا رصدَه (حكم 0104، W-20261010-013).
            not_inherited_by={"teacher_assistant", "ese_assistant"},
        ),
        _cap("behavior.manage", "إدارةُ المخالفات والإجراءات", P.BEHAVIOR_MANAGE_HOLDERS),
        _cap(
            "behavior.committee",
            "لجنةُ الانضباط",
            P.BEHAVIOR_COMMITTEE | {"student_affairs_coordinator"},
        ),
        _cap(
            "behavior.statistics",
            "إحصاءاتُ السلوك",
            (P.BEHAVIOR_COMMITTEE - BEHAVIOR_COMMITTEE_CASE_SCOPED)
            | P.BEHAVIOR_VIEW_ALL
            | P.BEHAVIOR_STATS_TEACHING
            | {"student_affairs_coordinator"},
            scope="المدرسةُ كلُّها",
            basis=(
                "المشرفُ الإداريّ عضوٌ في قضيّة جناحه وحدَها (م5.7، D-207م) فلا يرث بعضويّته إحصاءَ "
                "المدرسة كلِّها — حكمُ 0104 على W-20261001-023"
            ),
        ),
        _cap("behavior.summon_parent", "استدعاءُ وليّ الأمر", family_callers),
        _cap(
            "behavior.guardian_contact",
            "اسمُ وليّ الأمر وإرسالُ التقرير السلوكيّ إليه",
            family_callers | {"admin_supervisor"},
            scope="طلبةُ صاحب الشاشة (المشرفُ لجناحه)",
            basis=(
                "قاعدةُ الحاجة (PDPPL): الاسمُ لمن يتّصل بالأسرة أو يستدعيها أو يتابع — قيادةٌ وأخصائيٌّ "
                "اجتماعيٌّ ومنسّقُ شؤون الطلبة (قدرةُ الاستدعاء نفسُها) وحاملُ الجناح (قرارُ DPO 2026-09-16)؛ "
                "ومن يسجّل مخالفةً ولا يتّصل (معلّمٌ ومنسّقٌ ومنسّقُ أنشطةٍ ومشاريع) يرى «وليّ الأمر مسجَّل» بلا اسم "
                "— بطاقة W-20261005-009"
            ),
        ),
    ]
