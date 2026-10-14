"""مجموعاتُ الصفة: الدورُ على الخادم يُحوَّل إلى مجموعةٍ عند الحفظ — فلا تُخزَّن الصفةُ أدقَّ من اللازم.

الأدوارُ الصغيرةُ (المدير والنائبان ومنسّق شؤون الطلبة) تُدمج في «الإدارة» من لحظة الحفظ، فلا يبقى في
قاعدة البيانات ما يُخرج مجيباً بعينه من مجموعةٍ صغيرة. والطلبةُ والأولياءُ لا مجموعةَ لهم: لا استبانةَ لهم.
"""

from __future__ import annotations

GROUPS: dict[str, str] = {
    "teacher": "معلم",
    "wing": "مشرف جناح",
    "admin": "الإدارة",
    "coordinator": "منسق",
    "support": "كادر الدعم",
}

_BY_ROLE: dict[str, str] = {
    **dict.fromkeys(("teacher", "ese_teacher", "teacher_assistant", "ese_assistant"), "teacher"),
    "admin_supervisor": "wing",
    **dict.fromkeys(
        ("principal", "vice_admin", "vice_academic", "student_affairs_coordinator"), "admin"
    ),
    **dict.fromkeys(
        ("coordinator", "e_projects_coordinator", "activities_coordinator"), "coordinator"
    ),
    **dict.fromkeys(
        (
            "social_worker",
            "psychologist",
            "academic_advisor",
            "speech_therapist",
            "occupational_therapist",
            "support_companion",
        ),
        "support",
    ),
}


def group_of(role_name: str | None) -> str | None:
    """مفتاحُ مجموعة الدور، أو None لمن لا استبانةَ له (طالب، وليّ أمر، دورٌ غير معروف)."""
    return _BY_ROLE.get(role_name or "")
