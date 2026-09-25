"""الأذوناتُ المؤقّتة وسجلُّ تدقيقها."""

from django.db import models

from core.models import ClassGroup, CustomUser, School

from .attendance import Session
from .common import _uuid
from .substitution import CompensatorySession, TeacherSwap

# ═════════════════════════════════════════════════════════════════════
# الصلاحيات المؤقتة — نقل صلاحيات الحضور والسلوك خلال الحصة
# المرجع: قرار وزارة التعليم 32/2019 + تعديل 23/2025
# يُستخدم في: حصص الأشغال، التبديل بين المعلمين، حصص التعويض
# ═════════════════════════════════════════════════════════════════════


class TemporaryPermission(models.Model):
    """
    صلاحية مؤقتة تُمنح لمعلم على صف معين خلال حصة محددة.

    تُنشأ تلقائياً عند:
    - موافقة منسق على حصة أشغال (assignment)
    - تنفيذ تبديل حصتين (swap)
    - اعتماد حصة تعويضية (compensatory)

    تُلغى تلقائياً عبر Celery Beat كل دقيقة (revoke_expired_temp_permissions).
    """

    PERM_TYPE = [
        ("ATTENDANCE", "تسجيل الحضور والغياب"),
        ("BEHAVIOR", "تسجيل السلوك"),
        ("ATTENDANCE_BEHAVIOR", "الحضور + السلوك"),
    ]

    SOURCE_TYPE = [
        ("assignment", "حصة أشغال"),
        ("swap", "تبديل حصص"),
        ("compensatory", "حصة تعويضية"),
    ]

    STATUS = [
        ("active", "نشطة"),
        ("expired", "منتهية"),
        ("revoked", "ملغاة يدوياً"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)

    # ── الأطراف ────────────────────────────────────────────────────
    teacher = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="temporary_permissions",
        verbose_name="المعلم المستفيد",
    )
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.CASCADE,
        related_name="temporary_permissions",
        verbose_name="الشعبة المستهدفة",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="temporary_permissions",
        verbose_name="المدرسة",
    )

    # ── الحصة المرتبطة (اختياري — قد تكون عبر Session أو ScheduleSlot) ──
    session = models.ForeignKey(
        Session,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="temp_permissions",
        verbose_name="الحصة المرتبطة",
    )

    # ── نوع الصلاحية والمصدر ────────────────────────────────────────
    permission_type = models.CharField(
        max_length=30,
        choices=PERM_TYPE,
        default="ATTENDANCE_BEHAVIOR",
        verbose_name="نوع الصلاحية",
    )
    source_type = models.CharField(
        max_length=15,
        choices=SOURCE_TYPE,
        verbose_name="مصدر الصلاحية",
    )

    # ── المصادر الاختيارية ──────────────────────────────────────────
    swap = models.ForeignKey(
        TeacherSwap,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="temp_permissions",
        verbose_name="طلب التبديل",
    )
    compensatory = models.ForeignKey(
        CompensatorySession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="temp_permissions",
        verbose_name="الحصة التعويضية",
    )

    # ── الصلاحية الممنوحة من ────────────────────────────────────────
    granted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="granted_temp_permissions",
        verbose_name="مانح الصلاحية",
    )

    # ── النطاق الزمني ───────────────────────────────────────────────
    valid_from = models.DateTimeField(verbose_name="بداية الصلاحية", db_index=True)
    valid_until = models.DateTimeField(verbose_name="نهاية الصلاحية", db_index=True)

    status = models.CharField(
        max_length=10,
        choices=STATUS,
        default="active",
        db_index=True,
        verbose_name="الحالة",
    )

    revoked_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الإلغاء")
    revoked_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="revoked_temp_permissions",
        verbose_name="مُلغي الصلاحية",
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "صلاحية مؤقتة"
        verbose_name_plural = "الصلاحيات المؤقتة"
        ordering = ["-valid_from"]
        indexes = [
            models.Index(fields=["school", "status"]),
            models.Index(fields=["teacher", "status"]),
            models.Index(fields=["class_group", "status"]),
            models.Index(fields=["valid_until", "status"]),
        ]

    def __str__(self):
        return (
            f"صلاحية مؤقتة: {self.teacher.full_name} على {self.class_group} "
            f"| {self.get_permission_type_display()} "
            f"| {self.valid_from.strftime('%H:%M')}–{self.valid_until.strftime('%H:%M')} "
            f"| {self.get_status_display()}"
        )

    @property
    def is_active_now(self):
        """هل الصلاحية نشطة الآن؟"""
        from django.utils import timezone

        now = timezone.now()
        return self.status == "active" and self.valid_from <= now <= self.valid_until


class PermissionAuditLog(models.Model):
    """
    سجل مراجعة لكل منح/إلغاء صلاحية مؤقتة.
    يُستخدم للتتبع والمراجعة والامتثال.
    """

    ACTION = [
        ("granted", "مُمنوحة"),
        ("auto_revoked", "ملغاة تلقائياً"),
        ("manual_revoked", "ملغاة يدوياً"),
        ("extended", "ممتدة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    temp_permission = models.ForeignKey(
        TemporaryPermission,
        on_delete=models.CASCADE,
        related_name="audit_logs",
        verbose_name="الصلاحية المؤقتة",
    )
    action = models.CharField(max_length=20, choices=ACTION, verbose_name="الإجراء")
    performed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="permission_audit_actions",
        verbose_name="مُنفِّذ الإجراء",
    )
    performed_at = models.DateTimeField(auto_now_add=True, verbose_name="وقت التنفيذ")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "سجل مراجعة صلاحية"
        verbose_name_plural = "سجلات مراجعة الصلاحيات"
        ordering = ["-performed_at"]

    def __str__(self):
        return (
            f"[{self.get_action_display()}] {self.temp_permission} "
            f"@ {self.performed_at.strftime('%Y-%m-%d %H:%M')}"
        )
