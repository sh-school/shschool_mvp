"""
core/mixins.py
Mixins مشتركة لجميع نماذج SchoolOS
"""

from django.conf import settings
from django.db import models
from django.utils import timezone


class TimestampMixin(models.Model):
    """Mixin يضيف حقول created_at و updated_at تلقائياً"""

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="آخر تحديث")

    class Meta:
        abstract = True


class SoftDeleteQuerySet(models.QuerySet):
    """QuerySet يُخفي السجلات المحذوفة تلقائياً"""

    def delete(self):
        """حذف ناعم — يضبط is_deleted=True بدلاً من الحذف الفعلي"""
        return self.update(is_deleted=True, deleted_at=timezone.now())

    def hard_delete(self):
        """حذف فعلي — استخدم بحذر"""
        return super().delete()

    def alive(self):
        """السجلات النشطة فقط"""
        return self.filter(is_deleted=False)

    def dead(self):
        """السجلات المحذوفة فقط"""
        return self.filter(is_deleted=True)


class SoftDeleteManager(models.Manager):
    """Manager يُرجع السجلات النشطة فقط افتراضياً"""

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).alive()


class SoftDeleteMixin(models.Model):
    """
    Mixin للحذف الناعم — لا يحذف السجلات فعلياً

    الاستخدام:
        class MyModel(SoftDeleteMixin):
            name = models.CharField(...)

        # objects يُرجع النشطة فقط
        MyModel.objects.all()      # is_deleted=False فقط
        # all_objects يشمل المحذوفة
        MyModel.all_objects.all()  # الكل
        # حذف ناعم
        instance.soft_delete(user=request.user)
        # استعادة
        instance.restore()
    """

    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="محذوف")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الحذف")
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="%(class)s_deleted",
        verbose_name="حُذف بواسطة",
    )

    objects = SoftDeleteManager()
    all_objects = models.Manager()

    class Meta:
        abstract = True

    def soft_delete(self, user=None):
        """حذف ناعم مع تسجيل المستخدم"""
        self.is_deleted = True
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])

    def restore(self):
        """استعادة سجل محذوف"""
        self.is_deleted = False
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["is_deleted", "deleted_at", "deleted_by"])
