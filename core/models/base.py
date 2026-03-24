"""
core/models/base.py
━━━━━━━━━━━━━━━━━━
Abstract base models لتوحيد الأنماط المشتركة عبر المنصة.

الاستخدام:
    from core.models.base import TimeStampedModel, SoftDeleteModel, SchoolScopedModel

    class MyModel(SchoolScopedModel):
        name = models.CharField(max_length=100)
        # يرث تلقائياً: id (UUID), school (FK), created_at, updated_at

    class MyDeletableModel(SoftDeleteModel):
        # يرث: id (UUID), created_at, updated_at, is_deleted, deleted_at
        # manager يستبعد المحذوف تلقائياً: MyDeletableModel.objects.all()
        # للوصول للكل: MyDeletableModel.all_objects.all()
"""

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimeStampedModel(models.Model):
    """
    Abstract base — يوفر UUID PK + حقول المراجعة الزمنية.

    الحقول:
        id          — UUID primary key (auto-generated)
        created_at  — تاريخ الإنشاء (تلقائي)
        updated_at  — تاريخ آخر تعديل (تلقائي)
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل")

    class Meta:
        abstract = True
        ordering = ["-created_at"]


class AuditedModel(TimeStampedModel):
    """
    Abstract — يُضيف created_by و updated_by لتتبع المستخدم.

    الحقول الإضافية:
        created_by  — المستخدم الذي أنشأ السجل
        updated_by  — المستخدم الذي عدّل السجل آخر مرة
    """

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_created",
        verbose_name="أنشأه",
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(app_label)s_%(class)s_updated",
        verbose_name="عدّله",
    )

    class Meta(TimeStampedModel.Meta):
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet يستبعد السجلات المحذوفة soft-deleted تلقائياً."""

    def delete(self):
        """Soft delete — يُعلّم السجلات بدلاً من حذفها فعلياً."""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """حذف فعلي من قاعدة البيانات — استخدم بحذر."""
        return super().delete()

    def alive(self):
        """السجلات النشطة فقط (غير المحذوفة)."""
        return self.filter(is_deleted=False)

    def dead(self):
        """السجلات المحذوفة فقط."""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Manager يستبعد المحذوف تلقائياً."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class AllObjectsManager(models.Manager):
    """Manager يُعيد كل السجلات بما فيها المحذوفة."""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db)


class SoftDeleteModel(TimeStampedModel):
    """
    Abstract — يُضيف نمط الحذف الناعم (Soft Delete).

    الحقول الإضافية:
        is_deleted  — علامة الحذف
        deleted_at  — تاريخ الحذف

    Managers:
        objects     — يستبعد المحذوف تلقائياً
        all_objects — يشمل كل السجلات

    الاستخدام:
        obj.delete()        → soft delete
        obj.hard_delete()   → حذف فعلي
        obj.restore()       → استرجاع
        Model.objects.all() → النشطة فقط
        Model.all_objects.all() → الكل
    """

    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="محذوف")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الحذف")

    objects = SoftDeleteManager()
    all_objects = AllObjectsManager()

    class Meta(TimeStampedModel.Meta):
        abstract = True

    def delete(self, using=None, keep_parents=False):
        """Soft delete — يُعلّم السجل بدلاً من حذفه."""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])

    def hard_delete(self, using=None, keep_parents=False):
        """حذف فعلي من قاعدة البيانات."""
        super().delete(using=using, keep_parents=keep_parents)

    def restore(self):
        """استرجاع سجل محذوف."""
        self.is_deleted = False
        self.deleted_at = None
        self.save(update_fields=["is_deleted", "deleted_at", "updated_at"])


class SchoolScopedModel(TimeStampedModel):
    """
    Abstract — نموذج مرتبط بمدرسة (Multi-Tenancy).

    الحقول الإضافية:
        school — FK للمدرسة (CASCADE)
    """

    school = models.ForeignKey(
        "core.School",
        on_delete=models.CASCADE,
        related_name="%(app_label)s_%(class)s_set",
        verbose_name="المدرسة",
    )

    class Meta(TimeStampedModel.Meta):
        abstract = True
