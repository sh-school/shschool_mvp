"""
core/models/capability_grant.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
منحُ قدرةٍ مفوَّضةٍ باسم مستخدم — «مُشغِّل الجدول» أوّلَها (التذكرة SOS-20260924-1CFE، الجزء أ).

القدراتُ في `core/capabilities.py` تُقرأ عادةً من الدور. وبعضُها يُفوَّض لشخصٍ بعينه بلا تغيير دوره — كمعلّمَين
يتولّيان مسؤوليّةَ الجدول العامّ فيُسنَدان ويولّدان بلا أن يصيرا منسّقَين ولا نائبَين. فهذا الجدولُ يحفظ **من يحمل ماذا
الآن**: صفٌّ لكلّ منحٍ، يُسحَب ولا يُحذف (يبقى أثرُ من منح ولمن ومتى ولِمَ، وسحبُه بسببه).

ولا يُكتب فيه رقمٌ وظيفيٌّ ولا اسم: المنحُ لأشخاصٍ بأعيانهم يجري وقتَ التشغيل (`grant_capability`)، والمستودعُ عامّ.
والكتابةُ فيه بـ`core/capability_grants.py` وحدَه (يفحص من يمنح، ويشترط السبب، ويدقّق) — لا من لوحة الإدارة مباشرةً.
"""

from django.conf import settings
from django.db import models
from django.db.models import Q

from .base import SchoolScopedModel

#: القدراتُ القابلةُ للتفويض باسم مستخدم ← اسمُها المعروض. إضافةُ قدرةٍ إلى هنا قرارٌ يُراجَع: كلُّ قدرةٍ مفوَّضةٍ
#: تُعرَّف في السجلّ بـ`grant=` (يقرأ هذا الجدول) — راجع `core/capabilities.py`.
DELEGABLE_CAPABILITIES = {
    "schedule.operator": "مُشغِّل الجدول",
}


class CapabilityGrant(SchoolScopedModel):
    """منحُ قدرةٍ مفوَّضةٍ لمستخدمٍ في مدرسة — فعّالٌ ما لم يُسحَب."""

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="capability_grants",
        verbose_name="حاملُ القدرة",
    )
    capability = models.CharField(
        max_length=60,
        choices=list(DELEGABLE_CAPABILITIES.items()),
        db_index=True,
        verbose_name="القدرة",
    )
    reason = models.TextField(verbose_name="سببُ المنح")
    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        related_name="capability_grants_given",
        verbose_name="مانحُها",
    )
    revoked_at = models.DateTimeField(
        null=True, blank=True, db_index=True, verbose_name="وقتُ السحب"
    )
    revoked_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="capability_grants_revoked",
        verbose_name="ساحبُها",
    )
    revoke_reason = models.TextField(blank=True, verbose_name="سببُ السحب")

    class Meta(SchoolScopedModel.Meta):
        verbose_name = "منحُ قدرةٍ مفوَّضة"
        verbose_name_plural = "منحُ القدرات المفوَّضة"
        constraints = [
            # منحٌ فعّالٌ واحدٌ لكلّ (مدرسة، مستخدم، قدرة) — والمسحوبُ يتعدّد أثراً.
            models.UniqueConstraint(
                fields=["school", "user", "capability"],
                condition=Q(revoked_at__isnull=True),
                name="uniq_active_capability_grant",
            ),
            models.CheckConstraint(condition=~Q(reason=""), name="capability_grant_has_a_reason"),
            # سحبٌ بلا سبب لا يُقبل: وقتٌ وسحبٌ وساحبٌ وسببٌ معاً أو لا شيء.
            models.CheckConstraint(
                condition=Q(revoked_at__isnull=True, revoke_reason="")
                | (Q(revoked_at__isnull=False) & ~Q(revoke_reason="")),
                name="capability_grant_revocation_has_a_reason",
            ),
        ]
        indexes = [
            models.Index(fields=["school", "capability", "revoked_at"]),
            models.Index(fields=["user", "capability", "revoked_at"]),
        ]

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def __str__(self) -> str:
        state = "فعّال" if self.is_active else "مسحوب"
        return f"{DELEGABLE_CAPABILITIES.get(self.capability, self.capability)} — {state}"
