"""لقطاتُ تقارير الغياب الدوريّة — إحصاءٌ ثابتٌ مختومٌ بوقت توليده (W-20261020-005 الخطوة 5).

التقريرُ لقطةٌ **لا تُعاد قراءتُها من الحضور الحيّ**: ما كُتب فيها يومَ توليدها يبقى كما كُتب، ولو صُحّح الحضورُ بعدها.
وإعادةُ الحساب (زرُّ «أعد الحساب الآن»، ومهلةُ الإجازات المتأخّرة يومان — D-271م) **لقطةٌ جديدةٌ بنسخةٍ أعلى** لا تعديلٌ للقديمة،
فيبقى الأرشيفُ كاملاً لمن راجع. فالجدولُ مضافٌ إليه فقط (`AppendOnlyModel`).

المحتوى أعدادٌ ونسبٌ مجمَّعةٌ (مدرسة ← مرحلة ← جناح ← شعبة) بلا اسمِ طالبٍ ولا رقمٍ شخصيّ.
"""

from django.db import models
from django.utils import timezone

from core.models import CustomUser, School

from .attendance_ledger import AppendOnlyModel
from .common import _uuid


class AbsenceReportSnapshot(AppendOnlyModel):
    KINDS = [
        ("daily", "يومي"),
        ("weekly", "أسبوعي"),
        ("monthly", "شهري"),
        ("quarterly", "ربع سنوي"),
    ]
    #: نطاقُ الصفوف لا يُملأ إلّا في الربع سنوي: تقريرٌ لكلّ نطاقٍ بنهاية اختباراته (قرارُ المالك 2026-10-20).
    SCOPES = [
        ("", "كلّ المدرسة"),
        ("g1_9", "الصفوف ١–٩"),
        ("g10_11", "الصفّان ١٠–١١"),
        ("g12", "الصف ١٢"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="absence_report_snapshots",
        verbose_name="المدرسة",
    )
    kind = models.CharField(max_length=10, choices=KINDS, verbose_name="النوع")
    grade_scope = models.CharField(
        max_length=10, choices=SCOPES, blank=True, default="", verbose_name="نطاق الصفوف"
    )
    period_start = models.DateField(verbose_name="من")
    period_end = models.DateField(verbose_name="إلى")
    #: 1 للتوليد الأوّل، ويزيد بكلّ إعادة حساب؛ الأحدثُ هو المعروض والأقدمُ يبقى في الأرشيف.
    revision = models.PositiveSmallIntegerField(default=1, verbose_name="النسخة")
    generated_at = models.DateTimeField(default=timezone.now, verbose_name="وقتُ التوليد")
    #: فارغٌ = ولّده المجدوِل؛ وإلّا فمن ضغط «أعد الحساب الآن».
    generated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="absence_reports_generated",
        verbose_name="من ولّده",
    )
    school_days = models.PositiveSmallIntegerField(default=0, verbose_name="أيامُ الدراسة المحسوبة")
    payload = models.JSONField(default=dict, verbose_name="الإحصاء")

    class Meta:
        verbose_name = "لقطة تقرير غياب"
        verbose_name_plural = "لقطاتُ تقارير الغياب"
        ordering = ["-period_end", "kind", "grade_scope", "-revision"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "kind", "grade_scope", "period_start", "period_end", "revision"],
                name="op_absrep_unique_revision",
            )
        ]
        indexes = [
            models.Index(fields=["school", "kind", "-period_end"], name="op_absrep_lookup_idx")
        ]

    def __str__(self) -> str:
        return f"{self.get_kind_display()} {self.period_start:%Y-%m-%d}…{self.period_end:%Y-%m-%d} (نسخة {self.revision})"
