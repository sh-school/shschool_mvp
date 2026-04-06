from django.db import models
from django.utils import timezone

from .school import School, _uuid
from .user import CustomUser

# Lazy import to avoid circular dependency — Department imports CustomUser
# Department FK is referenced as string "department.Department" below


# ══════════════════════════════════════════════════════════════════════
# Role — الأدوار الوظيفية حسب الهيكل التنظيمي الرسمي
# المرجع: قرار مجلس الوزراء 32/2019 + نظام الرخص المهنية (قطر)
# ══════════════════════════════════════════════════════════════════════

# ── تصنيف المستويات الإدارية (Tiers) ────────────────────────────────
# المرجع: قرار مجلس الوزراء 32/2019 + تعديل 23/2025 + إعلانات وزارة التعليم 2022-2026
TIER_1_LEADERSHIP = {"principal"}
TIER_2_DEPUTIES = {"vice_admin", "vice_academic"}
TIER_3_SUPERVISORS = {"coordinator", "admin_supervisor", "activities_coordinator"}
TIER_4_STAFF = {
    # الكادر التدريسي
    "teacher",
    "ese_teacher",
    "teacher_assistant",
    "ese_assistant",
    # الدعم الأكاديمي والطلابي
    "social_worker",
    "psychologist",
    "academic_advisor",
    "speech_therapist",
    "occupational_therapist",
    # الخدمات المساندة
    "nurse",
    "librarian",
    "it_technician",
    "bus_supervisor",
    "transport_officer",
    # الإداريون
    "admin",
    "secretary",
    "receptionist",
}
TIER_5_BENEFICIARIES = {"student", "parent"}
TIER_SYSTEM = {"platform_developer"}

# أدوار لها صلاحية إدارية شاملة
ADMIN_ROLES = TIER_1_LEADERSHIP | TIER_2_DEPUTIES
# القيادة (T1 + T2)
LEADERSHIP = TIER_1_LEADERSHIP | TIER_2_DEPUTIES
# أدوار الطاقم الأكاديمي
ACADEMIC_ROLES = {
    "principal",
    "vice_academic",
    "coordinator",
    "teacher",
    "ese_teacher",
    "teacher_assistant",
    "ese_assistant",
    "activities_coordinator",
}
# أدوار الطاقم بالكامل (بدون طلاب وأولياء أمور)
ALL_STAFF_ROLES = TIER_1_LEADERSHIP | TIER_2_DEPUTIES | TIER_3_SUPERVISORS | TIER_4_STAFF


class Role(models.Model):
    ROLES = [
        # T1 — القيادة العليا
        ("principal", "مدير المدرسة"),
        # T2 — نواب المدير
        ("vice_admin", "النائب الإداري"),
        ("vice_academic", "النائب الأكاديمي"),
        # T3 — المنسقون والإشراف
        ("coordinator", "منسق أكاديمي"),
        ("admin_supervisor", "مشرف إداري"),
        ("activities_coordinator", "منسق الأنشطة المدرسية"),  # قرار 32/2019 — جديد v7
        # T4 — الكادر التدريسي
        ("teacher", "معلم"),
        ("ese_teacher", "معلم تربية خاصة"),
        ("teacher_assistant", "مساعد المعلم"),  # نص صريح قرار 32/2019 — جديد v7
        ("ese_assistant", "مساعد معلم تربية خاصة"),  # نص صريح قرار 32/2019 — جديد v7
        # T4 — الدعم الأكاديمي والطلابي
        ("social_worker", "أخصائي اجتماعي"),
        ("psychologist", "أخصائي نفسي"),
        ("academic_advisor", "مرشد أكاديمي"),
        ("speech_therapist", "أخصائي النطق"),  # إعلان رسمي وزارة التعليم — جديد v7
        ("occupational_therapist", "أخصائي العلاج الوظائفي"),  # إعلان رسمي وزارة التعليم — جديد v7
        # T4 — الخدمات المساندة
        ("nurse", "ممرض"),
        ("librarian", "أمين مصادر التعلم"),
        ("it_technician", "فني تقنية معلومات"),
        ("bus_supervisor", "مشرف نقل مدرسي"),
        ("transport_officer", "مسؤول النقل"),  # إدارة النقل — مختلف عن مشرف الحافلة — جديد v7
        # T4 — الإداريون
        ("admin", "إداري"),
        ("secretary", "سكرتير المدرسة"),
        ("receptionist", "موظف استقبال"),  # جديد v7
        # T4-legacy — التوافق الخلفي
        ("specialist", "أخصائي (قديم)"),
        # T5 — المستفيدون
        ("student", "طالب"),
        ("parent", "ولي أمر"),
        # System
        ("platform_developer", "مطور المنصة"),
    ]
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=30, choices=ROLES)

    class Meta:
        verbose_name = "دور"
        verbose_name_plural = "الأدوار"
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_role_per_school")
        ]

    def __str__(self):
        return f"{self.get_name_display()} — {self.school.code}"

    @property
    def tier(self):
        """يُعيد رقم المستوى الإداري (1-5) أو 0 للنظام."""
        name = self.name
        if name in TIER_1_LEADERSHIP:
            return 1
        if name in TIER_2_DEPUTIES:
            return 2
        if name in TIER_3_SUPERVISORS:
            return 3
        if name in TIER_4_STAFF or name == "specialist":
            return 4
        if name in TIER_5_BENEFICIARIES:
            return 5
        return 0  # platform_developer أو غير معروف

    @property
    def is_staff_role(self):
        """أي موظف في المدرسة (ليس طالباً أو ولي أمر)."""
        return self.name in ALL_STAFF_ROLES or self.name == "specialist"


# ══════════════════════════════════════════════════════════════════════
# Membership — عضوية المستخدم في المدرسة مع الدور والقسم
# ══════════════════════════════════════════════════════════════════════


class Membership(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="memberships")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    is_active = models.BooleanField(default=True)
    joined_at = models.DateField(default=timezone.now)

    # ── القسم/التخصص — FK إلى Department model ──────────────────
    department_obj = models.ForeignKey(
        "core.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memberships",
        verbose_name="القسم الأكاديمي",
        help_text="القسم من جدول الأقسام — يحل محل حقل department النصي",
    )

    class Meta:
        verbose_name = "عضوية"
        verbose_name_plural = "العضويات"
        indexes = [
            models.Index(fields=["school", "role"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school", "role"],
                condition=models.Q(is_active=True),
                name="unique_active_membership",
            )
        ]

    @property
    def department_name(self):
        """يُعيد اسم القسم من FK."""
        if self.department_obj_id:
            return self.department_obj.name
        return ""

    def __str__(self):
        dept = f" [{self.department_name}]" if self.department_name else ""
        return f"{self.user.full_name} | {self.role}{dept} | {self.school.code}"
