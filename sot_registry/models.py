"""سجلُّ مصدر الحقيقة (W-20261015-007، المواصفة W-20261015-006).

ثمانيةُ جداول: المصدر والحكم والموضوع والعتبة والإحلال وربطُ الكود والمراجعات (إلحاقٌ فقط) والتعارض (لا يُحذف).

الثوابتُ بالبنية لا بالعرف:
- الحذفُ ناعمٌ دائمًا: `delete()` يرفع `ProtectedDeletionError` على كلّ جدول، والإخفاءُ بـ`soft_delete` في `services`.
- `Revision` إلحاقٌ فقط: لا تعديلَ لسطرٍ موجود ولا حذف.
- الحكمُ لا يظهر لغير الإدارة إلا «نافذٌ» (`Provision.objects.visible()`).
- لا مفتاحَ أجنبيّ إلى المستخدم: الفاعلُ نصٌّ قصير (الدور + المعرّف) كي لا يدخل السجلُّ في دائرة المحو.
"""

from typing import Any

from django.db import models
from django.utils import timezone


class ProtectedDeletionError(Exception):
    """محاولةُ حذفٍ نهائيّ — ممنوعةٌ بقرار المالك؛ الحذفُ النهائيُّ لأمر إدارةٍ مسجَّل وحده."""


class _NoHardDelete(models.Model):
    class Meta:
        abstract = True

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ProtectedDeletionError("الحذفُ النهائيّ ممنوع؛ استعمل الحذف الناعم.")


class _SoftDeletable(_NoHardDelete):
    is_deleted = models.BooleanField(default=False, db_index=True, verbose_name="محذوفٌ ناعمًا")
    deleted_at = models.DateTimeField(null=True, blank=True, verbose_name="وقتُ الحذف الناعم")
    delete_reason = models.CharField(max_length=200, blank=True, verbose_name="سببُ الحذف الناعم")

    class Meta:
        abstract = True


class Source(_SoftDeletable):
    KINDS = [
        ("MIN", "وزاريّ"),
        ("LAW", "قانون"),
        ("OWN-D", "قرارُ المالك"),
        ("SCH", "مدرسيّ"),
    ]
    code = models.CharField(max_length=40, unique=True, verbose_name="رمز المصدر")
    kind = models.CharField(max_length=5, choices=KINDS, verbose_name="النوع")
    title = models.CharField(max_length=200, verbose_name="العنوان")
    issuer = models.CharField(max_length=120, blank=True, verbose_name="الجهةُ المُصدِرة")
    doc_number = models.CharField(max_length=60, blank=True, verbose_name="رقمُ الوثيقة")
    school_year = models.CharField(max_length=9, blank=True, verbose_name="العامُ الدراسيّ")
    original_sha256 = models.CharField(max_length=64, blank=True, verbose_name="بصمةُ الأصل")
    expected_count = models.PositiveIntegerField(default=0, verbose_name="عددُ الأحكام المتوقَّع")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "مصدر"
        verbose_name_plural = "المصادر"
        ordering = ("code",)

    def __str__(self) -> str:
        return f"{self.code} — {self.title}"


class Topic(_SoftDeletable):
    code = models.CharField(max_length=40, unique=True, verbose_name="رمز الموضوع")
    name = models.CharField(max_length=120, verbose_name="الموضوع")
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="children",
        verbose_name="الموضوع الأعلى",
    )

    class Meta:
        verbose_name = "موضوع"
        verbose_name_plural = "المواضيع"
        ordering = ("code",)

    def __str__(self) -> str:
        return self.name


class ProvisionQuerySet(models.QuerySet):
    def alive(self) -> "ProvisionQuerySet":
        return self.filter(is_deleted=False)

    def visible(self) -> "ProvisionQuerySet":
        """ما يراه غيرُ الإدارة: النافذُ وغيرُ المحذوف فقط."""
        return self.filter(is_deleted=False, status=Provision.EFFECTIVE)


class Provision(_SoftDeletable):
    DRAFT, UNVERIFIED, IN_REVIEW, EFFECTIVE, REVOKED = (
        "draft",
        "unverified",
        "in_review",
        "effective",
        "revoked",
    )
    STATUSES = [
        (DRAFT, "مسوّدة"),
        (UNVERIFIED, "غير مدقَّق"),
        (IN_REVIEW, "قيد المراجعة"),
        (EFFECTIVE, "نافذ"),
        (REVOKED, "ملغى"),
    ]
    pid = models.CharField(max_length=60, unique=True, verbose_name="معرّف الحكم (ثابت)")
    source = models.ForeignKey(
        Source, on_delete=models.PROTECT, related_name="provisions", verbose_name="المصدر"
    )
    topic = models.ForeignKey(
        Topic,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="provisions",
        verbose_name="الموضوع",
    )
    article = models.CharField(max_length=60, verbose_name="المادة أو البند")
    printed_page = models.PositiveSmallIntegerField(verbose_name="رقمُ الصفحة المطبوع")
    file_page = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="رقمُ صفحة الملف"
    )
    verbatim = models.TextField(verbose_name="النصُّ الحرفيّ")
    explanation = models.TextField(blank=True, verbose_name="الشرح")
    rank = models.PositiveSmallIntegerField(default=0, verbose_name="الرتبة")
    status = models.CharField(
        max_length=12, choices=STATUSES, default=UNVERIFIED, db_index=True, verbose_name="الحالة"
    )
    loaded_by = models.CharField(max_length=80, blank=True, verbose_name="حمّله")
    reviewed_by = models.CharField(max_length=80, blank=True, verbose_name="راجعه (بشريّ)")
    reviewed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقتُ المراجعة")

    objects = ProvisionQuerySet.as_manager()

    class Meta:
        verbose_name = "حكم"
        verbose_name_plural = "الأحكام"
        ordering = ("source", "rank", "pid")

    def __str__(self) -> str:
        return f"{self.pid} ({self.article})"

    @property
    def is_protected(self) -> bool:
        """حكمٌ له ربطُ كودٍ أو تعارضٌ مفتوح لا يُحذف حتى ولو ناعمًا."""
        return (
            self.code_links.exists()
            or Conflict.objects.filter(
                models.Q(provision_a=self) | models.Q(provision_b=self), status=Conflict.OPEN
            ).exists()
        )


class Threshold(_SoftDeletable):
    provision = models.ForeignKey(
        Provision, on_delete=models.PROTECT, related_name="thresholds", verbose_name="الحكم"
    )
    key = models.CharField(max_length=60, verbose_name="المفتاح")
    comparator = models.CharField(
        max_length=2,
        choices=[(">=", "≥"), ("<=", "≤"), ("==", "="), (">", ">"), ("<", "<")],
        default=">=",
        verbose_name="المقارنة",
    )
    value = models.DecimalField(max_digits=10, decimal_places=2, verbose_name="القيمة")
    unit = models.CharField(max_length=30, blank=True, verbose_name="الوحدة")

    class Meta:
        verbose_name = "عتبة"
        verbose_name_plural = "العتبات"
        ordering = ("provision", "key")

    def __str__(self) -> str:
        return f"{self.provision.pid}: {self.key} {self.comparator} {self.value}"


class Supersession(_SoftDeletable):
    old = models.ForeignKey(
        Provision,
        on_delete=models.PROTECT,
        related_name="superseded_by_links",
        verbose_name="الحكم القديم",
    )
    new = models.ForeignKey(
        Provision,
        on_delete=models.PROTECT,
        related_name="supersedes_links",
        verbose_name="الحكم الجديد",
    )
    effective_date = models.DateField(null=True, blank=True, verbose_name="تاريخ السريان")
    note = models.CharField(max_length=200, blank=True, verbose_name="ملاحظة")

    class Meta:
        verbose_name = "إحلال"
        verbose_name_plural = "الإحلالات"

    def __str__(self) -> str:
        return f"{self.old.pid} ← {self.new.pid}"


class CodeLink(_NoHardDelete):
    """ربطُ حكمٍ بثابتٍ مرمَّزٍ في الكود (بلا تعديله): حكمٌ له ربطٌ لا يُحذف."""

    provision = models.ForeignKey(
        Provision, on_delete=models.PROTECT, related_name="code_links", verbose_name="الحكم"
    )
    code_path = models.CharField(max_length=200, verbose_name="مسارُ الملف")
    symbol = models.CharField(max_length=120, blank=True, verbose_name="الرمز (ثابت أو دالّة)")
    note = models.CharField(max_length=200, blank=True, verbose_name="ملاحظة")

    class Meta:
        verbose_name = "ربطُ كود"
        verbose_name_plural = "روابطُ الكود"
        unique_together = ("provision", "code_path", "symbol")

    def __str__(self) -> str:
        return f"{self.provision.pid} → {self.code_path}:{self.symbol}"


class Revision(_NoHardDelete):
    """سجلُّ تغييرٍ إلحاقيّ: لا يُعدَّل سطرٌ بعد كتابته ولا يُحذف."""

    LOAD, EDIT, STATUS, SOFT_DELETE, RESTORE = "load", "edit", "status", "soft_delete", "restore"
    ACTIONS = [
        (LOAD, "تحميل"),
        (EDIT, "تعديل"),
        (STATUS, "تغييرُ حالة"),
        (SOFT_DELETE, "حذفٌ ناعم"),
        (RESTORE, "استرجاع"),
    ]
    provision = models.ForeignKey(
        Provision, on_delete=models.PROTECT, related_name="revisions", verbose_name="الحكم"
    )
    action = models.CharField(max_length=12, choices=ACTIONS, verbose_name="الإجراء")
    before = models.JSONField(default=dict, blank=True, verbose_name="قبل")
    after = models.JSONField(default=dict, blank=True, verbose_name="بعد")
    actor = models.CharField(max_length=80, verbose_name="الفاعل")
    at = models.DateTimeField(default=timezone.now, editable=False, verbose_name="الوقت")

    class Meta:
        verbose_name = "مراجعة"
        verbose_name_plural = "المراجعات (إلحاقٌ فقط)"
        ordering = ("-at", "-id")

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk:
            raise ProtectedDeletionError("سجلُّ المراجعات إلحاقٌ فقط؛ لا تعديل.")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.provision.pid}: {self.action}"


class Conflict(_NoHardDelete):
    OPEN, RESOLVED = "open", "resolved"
    provision_a = models.ForeignKey(
        Provision, on_delete=models.PROTECT, related_name="conflicts_a", verbose_name="الحكم الأول"
    )
    provision_b = models.ForeignKey(
        Provision,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="conflicts_b",
        verbose_name="الحكم الثاني",
    )
    description = models.TextField(verbose_name="وصفُ التعارض")
    status = models.CharField(
        max_length=8,
        choices=[(OPEN, "مفتوح"), (RESOLVED, "محسوم")],
        default=OPEN,
        verbose_name="الحالة",
    )
    resolution = models.TextField(blank=True, verbose_name="الحسم")

    class Meta:
        verbose_name = "تعارض"
        verbose_name_plural = "التعارضات"

    def __str__(self) -> str:
        return f"{self.provision_a.pid}: {self.get_status_display()}"
