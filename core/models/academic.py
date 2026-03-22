from django.db import models
from django.utils import timezone
from .school import School, _uuid
from .user import CustomUser


class ClassGroup(models.Model):
    GRADES = [
        ("G7",  "الصف السابع"),
        ("G8",  "الصف الثامن"),
        ("G9",  "الصف التاسع"),
        ("G10", "الصف العاشر"),
        ("G11", "الصف الحادي عشر"),
        ("G12", "الصف الثاني عشر"),
    ]
    LEVELS = [("prep", "إعدادي"), ("sec", "ثانوي")]

    id            = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school        = models.ForeignKey(School, on_delete=models.CASCADE, related_name="class_groups")
    grade         = models.CharField(max_length=3, choices=GRADES)
    section       = models.CharField(max_length=10, verbose_name="الشعبة")
    level_type    = models.CharField(max_length=4, choices=LEVELS, default="prep")
    academic_year = models.CharField(max_length=9, default="2025-2026")
    supervisor    = models.ForeignKey(
        CustomUser, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="supervised_classes",
    )
    is_active     = models.BooleanField(default=True)

    class Meta:
        verbose_name        = "فصل دراسي"
        verbose_name_plural = "الفصول الدراسية"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "grade", "section", "academic_year"],
                name="unique_class_per_year",
            )
        ]
        indexes = [models.Index(fields=["school", "grade", "academic_year"])]

    def __str__(self):
        return f"{self.get_grade_display()} / {self.section} ({self.academic_year})"


class StudentEnrollment(models.Model):
    id          = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student     = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="enrollments")
    class_group = models.ForeignKey(ClassGroup, on_delete=models.CASCADE, related_name="enrollments")
    is_active   = models.BooleanField(default=True)
    enrolled_at = models.DateField(default=timezone.now)

    class Meta:
        verbose_name = "تسجيل طالب"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "class_group"],
                condition=models.Q(is_active=True),
                name="unique_active_enrollment",
            )
        ]

    def __str__(self):
        return f"{self.student.full_name} → {self.class_group}"


class ParentStudentLink(models.Model):
    RELATIONSHIP = [
        ("father",   "الأب"),
        ("mother",   "الأم"),
        ("guardian", "الوصي"),
        ("other",    "أخرى"),
    ]

    id           = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school       = models.ForeignKey(School, on_delete=models.CASCADE, related_name="parent_links")
    parent       = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE,
        related_name="children_links", verbose_name="ولي الأمر",
    )
    student      = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE,
        related_name="parent_links", verbose_name="الطالب",
    )
    relationship        = models.CharField(max_length=20, choices=RELATIONSHIP, default="father",
                                           verbose_name="صلة القرابة")
    is_primary          = models.BooleanField(default=True, verbose_name="ولي الأمر الأساسي")
    can_view_grades     = models.BooleanField(default=True, verbose_name="يرى الدرجات")
    can_view_attendance = models.BooleanField(default=True, verbose_name="يرى الغياب")
    created_at          = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name        = "ربط ولي أمر"
        verbose_name_plural = "ربط أولياء الأمور"
        ordering            = ["student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student", "school"],
                name="unique_parent_student_school",
            )
        ]

    def __str__(self):
        return (
            f"{self.parent.full_name} ← {self.student.full_name} "
            f"({self.get_relationship_display()})"
        )
