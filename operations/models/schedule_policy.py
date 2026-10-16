"""سياسةُ تخفيف التلاصق للمدرسة — قرارُ المالك D-382م (W-20261011-007).

كانت تخفيفاتُ الجدول الحيّ (HC5 إلى سقف تتابعٍ 2، ومنعُ السادسة والسابعة معاً، ومنعُ الثلاثيّات بالرقم) في ملفٍّ
خارج المستودع، فيصير زرُّ التوليد صارماً (INFEASIBLE في ثوانٍ) وتبقى القاعدةُ التي وُلّد بها الجدولُ الحيُّ غيرَ
ظاهرةٍ ولا مدقَّقة. فصارت إعداداً مدرسيّاً في القاعدة يقرؤه المولّدُ والمُقيِّمُ وفحصُ الجدوى من مصدرٍ واحد.
"""

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.models import CustomUser, School

from .common import _uuid

#: سقفُ التتابع المخفَّف الذي يعرفه المولّدُ والمُقيِّم: حصّتان متتاليتان لا ثلاث (HC5 → run_cap_2).
RELAXED_RUN_CAP = 2


class ScheduleRelaxationPolicy(models.Model):
    """تخفيفاتُ التوليد المعلَنة لمدرسة — صفٌّ واحد للمدرسة، وغيابُه يعني القيمَ الافتراضيّةَ أدناه (انظر `school_policy`).

    القيمُ الافتراضيّةُ هي قاعدةُ الجدول الحيّ نفسُها، فمدرسةٌ لم يُحفظ لها صفٌّ تُولَّد بها. وكلُّ تعديلٍ في الأدمن
    يُسجَّل قبل/بعد (`AuditLog`). لا معرّفاتِ معلّمين هنا: «للجميع» عَلَمٌ لا قائمة، فلا يتقادم بدخول معلّمٍ جديد.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.OneToOneField(
        School,
        on_delete=models.CASCADE,
        related_name="schedule_relaxation_policy",
        verbose_name="المدرسة",
    )
    relax_touch_for_all = models.BooleanField(
        default=True,
        verbose_name="تخفيف التلاصق (HC5) للجميع",
        help_text="يُرفع منعُ تلاصق الحصص عن كلّ المعلّمين إلى سقف التتابع أدناه؛ وإطفاؤه يعيد «لا تلاصق» صارماً",
    )
    touch_run_cap = models.PositiveSmallIntegerField(
        default=RELAXED_RUN_CAP,
        validators=[MinValueValidator(RELAXED_RUN_CAP), MaxValueValidator(RELAXED_RUN_CAP)],
        verbose_name="سقف التتابع بعد التخفيف",
        help_text="حصّتان متتاليتان لا ثلاث — القيمةُ الوحيدة التي يعرفها المُقيِّم (run_cap_2)",
    )
    no_6_7 = models.BooleanField(
        default=True,
        verbose_name="لا السادسة والسابعة معاً",
        help_text="قيدٌ صلبٌ: لا يقف المعلّمُ الحصّتين السادسة والسابعة في اليوم الواحد",
    )
    triples_by_number = models.BooleanField(
        default=True,
        verbose_name="لا ثلاثُ حصصٍ بأرقامٍ متتالية",
        help_text="تُمنع ثلاثُ حصصٍ متتاليةٍ بالرقم ولو فصلت فسحةٌ بينها",
    )
    decision_ref = models.CharField(
        max_length=60,
        blank=True,
        default="D-382م",
        verbose_name="مرجعُ القرار",
        help_text="رقمُ قرار المالك الذي تستند إليه هذه التخفيفات",
    )
    updated_at = models.DateTimeField(auto_now=True, null=True, verbose_name="تاريخ التعديل")
    updated_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        verbose_name="عدّله",
    )

    class Meta:
        verbose_name = "سياسة تخفيف التلاصق"
        verbose_name_plural = "سياسات تخفيف التلاصق"

    def __str__(self) -> str:
        return f"تخفيفات التوليد — {self.school_id}"

    def as_spec(self) -> dict[str, object]:
        """الصيغةُ التي يفهمها `options_from_relaxations` (المفاتيحُ نفسُها كملفّ `--relaxations`)."""
        spec: dict[str, object] = {
            "no_6_7": self.no_6_7,
            "triples_by_number": self.triples_by_number,
        }
        if self.relax_touch_for_all:
            spec["touch_relaxed_all"] = True
            spec["run_cap"] = self.touch_run_cap
        return spec
