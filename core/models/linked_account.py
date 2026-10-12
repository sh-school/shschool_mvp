"""ربطُ حساب مطوّر المنصّة بحسابٍ آخر له في المدرسة — بندُ «التبديل إلى حسابٍ مرتبط» (D-305م وD-306م، W-20261009-032).

المالكُ مطوّرٌ ومعلّمٌ معاً بحسابين؛ والربطُ يتيح له أن ينتقل بنقرةٍ إلى حسابه معلّماً ويعود دون خروجٍ ودخول.
ولا رقمَ وظيفيّاً ولا اسمَ في الكود: الصفُّ يُنشأ من لوحة الإدارة وقتَ التشغيل، بإجراء المطوّر نفسِه وبقدرةٍ منفصلة
(`developer.linked_accounts`)، ولا يُستعمل قبل تأكيده بهويّة المطوّر (`confirmed_at`). وكلُّ إنشاءٍ وتعديلٍ وحذفٍ
سطرٌ في `AuditLog` بالطرفين. وقواعدُ الهدف (كادرٌ غيرُ مرتفعٍ، لا ربطَ سلسليّاً) في `core/view_as/linked.py`.
"""

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models

from .school import _uuid


class LinkedAccount(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    developer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="linked_accounts",
        verbose_name="حسابُ المطوّر",
    )
    target = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="linked_from",
        verbose_name="الحسابُ المرتبط",
    )
    is_active = models.BooleanField(default=True, verbose_name="فعّال")
    #: يُملأ عند أوّل تبديلٍ بعد إعادة تأكيد هويّة المطوّر — وقبله لا يُستعمل الربط («بتأكيدٍ لاحق»).
    confirmed_at = models.DateTimeField(null=True, blank=True, verbose_name="أُكِّد في")
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="أنشأه",
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="أُنشئ في")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="عُدِّل في")

    class Meta:
        verbose_name = "حسابٌ مرتبط بالمطوّر"
        verbose_name_plural = "الحساباتُ المرتبطة بالمطوّر"
        constraints = [
            models.UniqueConstraint(
                fields=["developer", "target"], name="unique_linked_account_pair"
            ),
            models.CheckConstraint(
                condition=~models.Q(developer=models.F("target")),
                name="linked_account_not_self",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.developer} ← {self.target}"

    def clean(self) -> None:
        from core.view_as.linked import link_problems

        if self.developer_id is None or self.target_id is None:
            return
        problems = link_problems(self.developer, self.target, exclude_pk=self.pk)
        duplicate = LinkedAccount.objects.filter(
            developer_id=self.developer_id, target_id=self.target_id
        )
        if duplicate.exclude(pk=self.pk).exists():
            problems.append("هذا الربطُ قائمٌ من قبل.")
        if problems:
            raise ValidationError(problems)
