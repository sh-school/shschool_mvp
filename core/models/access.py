from django.db import models
from django.utils import timezone

from .school import School, _uuid
from .user import CustomUser


# ══════════════════════════════════════════════════════════════════════
# Role — الأدوار الوظيفية حسب الهيكل التنظيمي الرسمي
# المرجع: قرار مجلس الوزراء 32/2019 + نظام الرخص المهنية (قطر)
# ══════════════════════════════════════════════════════════════════════

# ── تصنيف المستويات الإدارية (Tiers) ────────────────────────────────
TIER_1_LEADERSHIP = {"principal"}
TIER_2_DEPUTIES = {"vice_admin", "vice_academic"}
TIER_3_SUPERVISORS = {"coordinator", "admin_supervisor"}
TIER_4_STAFF = {
    "teacher", "social_worker", "psychologist", "academic_advisor",
    "ese_teacher", "nurse", "librarian", "it_technician",
    "bus_supervisor", "admin", "secretary",
}
TIER_5_BENEFICIARIES = {"student", "parent"}
TIER_SYSTEM = {"platform_developer"}

# أدوار لها صلاحية إدارية شاملة
ADMIN_ROLES = TIER_1_LEADERSHIP | TIER_2_DEPUTIES
# القيادة (T1 + T2)
LEADERSHIP = TIER_1_LEADERSHIP | TIER_2_DEPUTIES
# أدوار الطاقم الأكاديمي
ACADEMIC_ROLES = {"principal", "vice_academic", "coordinator", "teacher", "ese_teacher"}
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
        # T4 — المعلمون والموظفون
        ("teacher", "معلم"),
        ("social_worker", "أخصائي اجتماعي"),
        ("psychologist", "أخصائي نفسي"),
        ("academic_advisor", "مرشد أكاديمي"),
        ("ese_teacher", "معلم تربية خاصة"),
        ("nurse", "ممرض/ة"),
        ("librarian", "أمين مصادر التعلم"),
        ("it_technician", "فني تقنية معلومات"),
        ("bus_supervisor", "مشرف نقل مدرسي"),
        ("admin", "إداري"),
        ("secretary", "سكرتير المدرسة"),
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
        return 0

    @property
    def is_staff_role(self):
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

    # ── القسم/التخصص — مهم للمنسقين والمعلمين ────────────────────
    department = models.CharField(
        max_length=60,
        blank=True,
        default="",
        verbose_name="القسم / التخصص",
        help_text="مثال: رياضيات، علوم، لغة عربية — يُستخدم لتقييد صلاحيات المنسق بتخصصه",
        db_index=True,
    )

    class Meta:
        verbose_name = "عضوية"
        verbose_name_plural = "العضويات"
        indexes = [
            models.Index(fields=["school", "role"]),
            models.Index(fields=["department"], condition=models.Q(is_active=True), name="idx_active_dept"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school", "role"],
                condition=models.Q(is_active=True),
                name="unique_active_membership",
            )
        ]

    def __str__(self):
        dept = f" [{self.department}]" if self.department else ""
        return f"{self.user.full_name} | {self.role}{dept} | {self.school.code}"
