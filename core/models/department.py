# ══════════════════════════════════════════════════════════════════════
# core/models/department.py
# Department — القسم الأكاديمي (v6 Architecture Upgrade)
# يحل محل CharField في Membership.department
# ══════════════════════════════════════════════════════════════════════

from django.db import models

from .school import School, _uuid
from .user import CustomUser


class Department(models.Model):
    """
    القسم الأكاديمي — يحل محل CharField الحر في Membership.

    الفوائد:
    - لا أخطاء إملائية (FK validated)
    - head = المنسق (علاقة مباشرة)
    - code = ثابت للبرمجة، name = قابل للتغيير
    - get_teachers() و get_student_ids() — دوال جاهزة
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="departments",
        verbose_name="المدرسة",
    )
    name = models.CharField(
        max_length=60,
        verbose_name="اسم القسم",
        help_text="مثال: الرياضيات، اللغة العربية",
    )
    code = models.CharField(
        max_length=30,
        verbose_name="كود القسم",
        help_text="كود ثابت للبرمجة — مثال: math, arabic, english",
    )
    head = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="headed_departments",
        verbose_name="المنسق (رئيس القسم)",
    )
    is_active = models.BooleanField(default=True, verbose_name="نشط")
    sort_order = models.PositiveIntegerField(default=0, verbose_name="ترتيب العرض")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "قسم أكاديمي"
        verbose_name_plural = "الأقسام الأكاديمية"
        ordering = ["sort_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"],
                name="unique_dept_name_per_school",
            ),
            models.UniqueConstraint(
                fields=["school", "code"],
                name="unique_dept_code_per_school",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "is_active"]),
        ]

    def __str__(self):
        head_name = self.head.full_name if self.head else "بدون منسق"
        return f"{self.name} ({self.code}) — {head_name}"

    # ── Helper Methods ──────────────────────────────────────────────

    def get_teachers(self):
        """كل معلمي القسم (teacher + ese_teacher + coordinator)."""
        return CustomUser.objects.filter(
            memberships__department_obj=self,
            memberships__is_active=True,
            memberships__role__name__in=("teacher", "ese_teacher", "coordinator"),
        ).distinct()

    def get_teacher_ids(self):
        """مجموعة IDs معلمي القسم."""
        return set(self.get_teachers().values_list("id", flat=True))

    def get_student_ids(self):
        """كل طلاب فصول معلمي القسم."""
        from operations.models import ScheduleSlot

        from .academic import StudentEnrollment

        teacher_ids = self.get_teacher_ids()
        if not teacher_ids:
            return set()

        class_ids = ScheduleSlot.objects.filter(
            teacher_id__in=teacher_ids,
            is_active=True,
        ).values_list("class_group_id", flat=True)

        return set(
            StudentEnrollment.objects.filter(
                class_group_id__in=class_ids,
                is_active=True,
            ).values_list("student_id", flat=True)
        )

    def get_member_count(self):
        """عدد أعضاء القسم النشطين."""
        return self.memberships.filter(is_active=True).count()
