"""
core/role_inheritance.py — وراثة الأدوار التلقائية (v6).

نُقلت من `core/permissions.py` (W-20261010-012) لأنّ ذلك الملف بلغ سقف سقّاطة الحجم؛ والمنطقُ كما هو.
تبقى `ROLE_INHERITS` و`expand_roles` مستورَدتين من `core.permissions` لمن يعتمد عليهما.
"""

ROLE_INHERITS = {
    # child → parent (يرث كل صلاحياته الأكاديمية)
    "coordinator": "teacher",  # المنسق يرث المعلم
    "ese_teacher": "teacher",  # معلم ESE يرث المعلم
    "vice_academic": "coordinator",  # النائب الأكاديمي يرث المنسق
    "vice_admin": "admin_supervisor",  # النائب الإداري يرث المشرف الإداري
    "principal": "vice_academic",  # المدير يرث النائب الأكاديمي
    # v7 — مساعدون يرثون من أساتذتهم
    "teacher_assistant": "teacher",  # مساعد المعلم يرث المعلم (جدول + حضور)
    "ese_assistant": "ese_teacher",  # مساعد ESE يرث معلم ESE
    "activities_coordinator": "coordinator",  # منسق أنشطة يرث المنسق
    "e_projects_coordinator": "teacher",  # منسّق المشاريع الإلكترونية معلّمٌ بنصابٍ مخفَّض
    "transport_officer": "bus_supervisor",  # مسؤول نقل يرث مشرف النقل
}


def expand_roles(roles: set, *, not_inherited_by: frozenset | set = frozenset()) -> set:
    """
    يوسّع مجموعة أدوار لتشمل كل دور يرث منها.

    مثال:
        expand_roles({"teacher"})
        → {"teacher", "ese_teacher", "coordinator", "vice_academic", "principal"}

    ملاحظة: تُستخدم فقط للصلاحيات ذات الطبيعة الوراثية (الأكاديمية).
    الصلاحيات المتخصصة (nurse, librarian...) تبقى صريحة.
    """
    expanded = set(roles)
    blocked = set(not_inherited_by) - expanded  # W-20261010-012: تُذكر صراحةً أو لا تُورَّث
    changed = True
    while changed:
        changed = False
        for child, parent in ROLE_INHERITS.items():
            if parent in expanded and child not in expanded and child not in blocked:
                expanded.add(child)
                changed = True
    return expanded
