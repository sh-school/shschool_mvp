# ══════════════════════════════════════════════════════════════════════
# core/models/permission_audit.py
# PermissionAuditLog — سجل تغييرات الصلاحيات (v6 Architecture Upgrade)
# من غيّر ماذا ومتى — Audit Trail كامل
# ══════════════════════════════════════════════════════════════════════

from django.core.exceptions import PermissionDenied
from django.db import models

from .school import School, _uuid
from .user import CustomUser


class PermissionAuditLog(models.Model):
    """
    سجل كل تغيير في الصلاحيات والأدوار والأقسام.

    Immutable — لا يمكن تعديله أو حذفه بعد الإنشاء.
    يُسجّل تلقائياً عند: تعيين/إزالة دور، تغيير قسم، تعيين منسق،
    تعطيل/تفعيل حساب، تعيين بديل، موافقة/رفض تبديل.
    """

    ACTIONS = [
        ("role_assigned", "تعيين دور"),
        ("role_removed", "إزالة دور"),
        ("dept_changed", "تغيير القسم"),
        ("dept_head_set", "تعيين منسق"),
        ("dept_head_removed", "إزالة منسق"),
        ("account_disabled", "تعطيل حساب"),
        ("account_enabled", "تفعيل حساب"),
        ("substitute_assigned", "تعيين بديل"),
        ("swap_approved", "موافقة تبديل"),
        ("swap_rejected", "رفض تبديل"),
        ("compensatory_approved", "موافقة تعويض"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="permission_audit_logs",
        verbose_name="المدرسة",
    )
    actor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="perm_audit_actions",
        verbose_name="المنفّذ",
        help_text="من نفّذ التغيير",
    )
    target = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="perm_audit_targets",
        verbose_name="المستهدف",
        help_text="على من تم التغيير",
    )
    action = models.CharField(
        max_length=30,
        choices=ACTIONS,
        verbose_name="نوع الإجراء",
    )
    details = models.JSONField(
        default=dict,
        blank=True,
        verbose_name="تفاصيل",
        help_text='مثال: {"old_dept": "الرياضيات", "new_dept": "العلوم"}',
    )
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name="عنوان IP",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        verbose_name="وقت التنفيذ",
    )

    class Meta:
        verbose_name = "سجل تغيير صلاحيات"
        verbose_name_plural = "سجلات تغيير الصلاحيات"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "-created_at"]),
            models.Index(fields=["actor", "-created_at"]),
            models.Index(fields=["target", "-created_at"]),
            models.Index(fields=["action"]),
        ]

    def __str__(self):
        actor_name = self.actor.full_name if self.actor else "النظام"
        target_name = self.target.full_name if self.target else "—"
        return (
            f"{actor_name} → {self.get_action_display()} → {target_name} "
            f"| {self.created_at:%Y-%m-%d %H:%M}"
        )

    # ── Immutable — لا تعديل ولا حذف ────────────────────────────────

    def save(self, *args, **kwargs):
        if self.pk and PermissionAuditLog.objects.filter(pk=self.pk).exists():
            raise PermissionDenied("سجلات تغيير الصلاحيات غير قابلة للتعديل (Immutable).")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("سجلات تغيير الصلاحيات غير قابلة للحذف (Immutable).")

    # ── Class Method — تسجيل سريع ────────────────────────────────────

    @classmethod
    def log(cls, *, actor, target, action, school=None, details=None, request=None):
        """
        تسجيل تغيير صلاحيات بسرعة.

        Usage:
            PermissionAuditLog.log(
                actor=request.user,
                target=some_user,
                action="role_assigned",
                details={"role": "coordinator", "dept": "math"},
                request=request,
            )
        """
        ip = None
        if request:
            ip = request.META.get("REMOTE_ADDR")
            if not school and hasattr(request, "user") and hasattr(request.user, "get_school"):
                school = request.user.get_school()

        return cls.objects.create(
            school=school,
            actor=actor,
            target=target,
            action=action,
            details=details or {},
            ip_address=ip,
        )
