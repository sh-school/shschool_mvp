"""
quality/reporting_lines.py
خطُّ التبعيّة لتقييم الأداء: من «الرئيسُ المباشر» الذي «يضع» التقرير (المادة 16).

المادة 16 من النظام الوظيفي (قرار مجلس الوزراء 32/2019، `02_staff_affairs.md:200`): «يضع الرئيس
المباشر تقييم أداء الموظف ويعتمد من مدير المدرسة». والاستماراتُ السبع لا تسمّي مُقيِّماً، فمصدرُ
«الرئيس المباشر» بطاقةُ الوصف الوظيفيّ: خانةُ «المسؤول المباشر» في
`data/2026-2027/02- شؤون الموظفين/05- الوصف الوظيفي/*.pdf` (قُرئت الصفحةُ الأولى من كلّ ملفٍّ
من الصورة 2026-09-19 — الجدولُ الكاملُ في `AAdocs/ministry_data/2026_2027/03_job_descriptions_rbac.md`
وقرارُه في ADR-0002 §6.6 بنود 7 و9):

  - نائبُ المدير للشؤون الأكاديمية (1033): المعلّم (384)، ومعلّمُ الدعم الإضافيّ (389)، ومنسّقُ
    المادة (1049)، ومنسّقُ المشاريع الإلكترونيّة (2537)، ومحضّرُ المختبر (373)، ومسؤولُ مركز
    مصادر التعلّم.
  - نائبُ المدير للشؤون الإداريّة وشؤون الطلاب (1034): الأخصائيّان الاجتماعيّ والنفسيّ (1320)،
    وأمينُ المخزن (253)، وعاملُ الخدمات (928)، ومرافقُ الدعم (2548)، ومسؤولُ تقنية المعلومات
    (3042)، والمشرفُ الإداريّ (425)، ومشرفُ المقصف (447)، وملاحظُ الطلبة (1005)، والممرّض (1878)،
    والمندوب (965)، وموظّفُ الاستقبال.
  - مديرُ المدرسة: النائبان (1033، 1034) والسكرتير (333). فلا يتبع أحدُ النائبين الآخر، ولا
    يضع تقريرَه.

ومن لا بطاقةَ له في المصدر (المحاسب، ومشرفُ الحافلة، ومسؤولُ النقل، والمرشد الأكاديميّ، ومنسّقُ
الأنشطة، والأخصائيّ، ومساعدا المعلّم والدعم، وأخصائيّا النطق والعلاج الوظيفيّ) لا خطَّ تبعيّةٍ
له في المصدر. **قرارُ المالك 2026-09-19 (لا نصُّ المصدر): يتبعون النائبَ الإداريّ** — «كلُّ هذا
يتبع الجانبَ الإداريّ» (ADR-0002 §6.6 بند 9). فإن وردت لهم بطاقاتٌ لاحقاً غيّرها الجدولُ أدناه.

وبطاقتان لهما مسؤولٌ مباشر ولا دورَ لهما في المنصّة ولا حاملَ في سجلّ الكادر (فُحص 2026-09-21): «منسّق شؤون
الطالب» (1033 ← النائب الإداريّ) و«منسّق الدعم الإضافي» (2827 ← النائب الأكاديميّ). يُضافان هنا عند أوّل
تعيين (ADR-0002 §6.6 بند 12-ج).

والمديرُ يضع لأيّ موظّف: هو رأسُ الهرم ومعتمِدُ كلّ تقرير — **قرارُ المالك 2026-09-19** (المصدرُ
لا يمنعه ولا يجيزه صراحةً لمن ليس مرؤوسَه المباشر).
"""

from __future__ import annotations

from collections.abc import Collection

PRINCIPAL = "principal"
VICE_ACADEMIC = "vice_academic"
VICE_ADMIN = "vice_admin"

#: الدورُ ← «المسؤول المباشر» في بطاقته (أسماءُ `Role.ROLES`).
DIRECT_SUPERVISOR: dict[str, str] = {
    **dict.fromkeys(
        (
            "teacher",
            "ese_teacher",
            "coordinator",
            "e_projects_coordinator",
            "lab_technician",
            "librarian",
        ),
        VICE_ACADEMIC,
    ),
    **dict.fromkeys(
        (
            "social_worker",
            "psychologist",
            "storekeeper",
            "services_worker",
            "support_companion",
            "it_technician",
            "admin_supervisor",
            "canteen_supervisor",
            "student_observer",
            "nurse",
            "messenger",
            "receptionist",
        ),
        VICE_ADMIN,
    ),
    **dict.fromkeys((VICE_ACADEMIC, VICE_ADMIN, "secretary"), PRINCIPAL),
}

#: أدوارٌ لا بطاقةَ لها في المصدر، حسمها المالكُ إداريّة (2026-09-19) — لا استنتاجَ من الـPDF.
OWNER_DECIDED_ADMIN: frozenset[str] = frozenset(
    {
        "accountant",
        "bus_supervisor",
        "transport_officer",
        "academic_advisor",
        "activities_coordinator",
        "specialist",
        "teacher_assistant",
        "ese_assistant",
        "speech_therapist",
        "occupational_therapist",
    }
)
DIRECT_SUPERVISOR.update(dict.fromkeys(OWNER_DECIDED_ADMIN, VICE_ADMIN))

NOT_DIRECT_SUPERVISOR = (
    "المادة 16: «يضع الرئيس المباشر تقييم أداء الموظف» — والمسؤولُ المباشر عن هذا الدور في بطاقة "
    "الوصف الوظيفيّ هو {supervisor}، فلا يضع تقريرَه غيرُه (ويعتمد من مدير المدرسة)."
)

_LABELS = {
    PRINCIPAL: "مدير المدرسة",
    VICE_ACADEMIC: "نائب المدير للشؤون الأكاديمية",
    VICE_ADMIN: "نائب المدير للشؤون الإدارية وشؤون الطلاب",
}


def may_place(evaluator_roles: Collection[str], employee_role: str | None) -> bool:
    """أيضعُ من يحمل هذه الأدوارَ في المدرسة تقريرَ موظّفٍ دورُه `employee_role`؟"""
    if PRINCIPAL in evaluator_roles:
        return True
    supervisor = DIRECT_SUPERVISOR.get(employee_role or "")
    return supervisor is None or supervisor in evaluator_roles


def rejection_reason(employee_role: str | None) -> str:
    supervisor = DIRECT_SUPERVISOR.get(employee_role or "", PRINCIPAL)
    return NOT_DIRECT_SUPERVISOR.format(supervisor=_LABELS[supervisor])
