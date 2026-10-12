"""أدوارُ لجنة الضبط السلوكي (م5.7) — مصدرٌ واحدٌ تعيد `core/permissions.py` تصديرَه.

في وحدةٍ مستقلّةٍ لأنّ `core/permissions.py` على حدّ سقّاطة الحجم (W-20261001-023).
"""

from __future__ import annotations

#: أعضاءُ فريق إدارة سلوك الطلبة الأساسيّون — م5.7 من سياسة إدارة سلوك الطلبة (08_conduct_policy_2026.md):
#: «مدير المدرسة، نائب المدير للشؤون الإدارية وشؤون الطلاب، نائب المدير للشؤون الأكاديمية، منسق شؤون
#: الطلبة، الاختصاصي الاجتماعي، الاختصاصي النفسي، المشرف الإداري» (W-20261001-023). مصدرٌ واحدٌ
#: تقرؤه `BehaviorPermissions.COMMITTEE_ROLES` ونصابُ التصويت — فلا قائمةَ ثانيةً تتباعد عنه.
BEHAVIOR_COMMITTEE_ART_5_7 = frozenset(
    {
        "principal",
        "vice_admin",
        "vice_academic",
        "student_affairs_coordinator",
        "social_worker",
        "psychologist",
        "admin_supervisor",
    }
)
#: و`specialist` («أخصائي قديم») يبقى إصداراً واحداً للتوافق ثمّ يُحذف بعد عدّ مستخدميه (قرارُ 0301).
BEHAVIOR_COMMITTEE = BEHAVIOR_COMMITTEE_ART_5_7 | frozenset({"specialist"})
#: المشرفُ الإداريّ يدخل **قضيّةَ طالب جناحه وحدَها** — واحدٌ لكلّ قضيّة (قرارُ المالك 2026-10-05):
#: م5.7 تذكره بصيغة المفرد «المشرف الإداري» ولا تنصّ على نصابٍ عدديّ. فلا يصوّت كلُّ حاملي الدور
#: (11 في المدرسة اليوم): يصوّت مشرفُ جناح الطالب وحدَه (`WingCoverage`)، ولا يرى غيرَ قضايا جناحه.
BEHAVIOR_COMMITTEE_CASE_SCOPED = frozenset({"admin_supervisor"})
