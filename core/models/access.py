from django.db import models
from django.utils import timezone

from .school import School, _uuid
from .user import CustomUser


class Role(models.Model):
    ROLES = [
        ("principal", "مدير المدرسة"),
        ("vice_admin", "النائب الإداري"),
        ("vice_academic", "النائب الأكاديمي"),
        ("coordinator", "منسق"),
        ("teacher", "معلم"),
        ("specialist", "أخصائي"),
        ("nurse", "ممرض/ة"),
        ("librarian", "أمين مكتبة"),
        ("bus_supervisor", "مشرف باص"),
        ("admin", "إداري"),
        ("student", "طالب"),
        ("parent", "ولي أمر"),
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


class Membership(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="memberships")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    is_active = models.BooleanField(default=True)
    joined_at = models.DateField(default=timezone.now)

    class Meta:
        verbose_name = "عضوية"
        verbose_name_plural = "العضويات"
        indexes = [models.Index(fields=["school", "role"])]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school", "role"],
                condition=models.Q(is_active=True),
                name="unique_active_membership",
            )
        ]

    def __str__(self):
        return f"{self.user.full_name} | {self.role} | {self.school.code}"
