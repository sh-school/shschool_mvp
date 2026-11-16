"""إذنُ خروج الطالب من المدرسة — استمارةٌ تُطبع للحارس وسجلٌّ بها (W-20261005-010).

(W-20261116-003) الورقةُ تُصدَر وتُطبع مباشرةً بلا اعتماد في المنصّة ويوقّعها بالقلم النائبُ الإداريّ؛
وحضورُ الوليّ ليس شرطاً: `guardian_method` حضورٌ أو اتّصال، و`approved` القديمةُ تبقى مقروءة.
(سابقاً: الإذنُ يُطلب ثمّ يُعتمد، ولا يعتمد بلا تسجيل حضور وليّ الأمر.) **لا تُحفظ نسخةُ بطاقة الوليّ ولا رقمُها**
(قرارُ المالك 2026-10-05): يُسجَّل حضورُه منطقيّاً فقط. وعددُ الحصص المكتملة يُحفظ لحظةَ الطلب للتحذير
دون تغيير الحضور (ربطُ الأثر بالحضور لاحقاً مع D-201م).
"""

from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField
from core.models import ClassGroup, CustomUser, School

from .common import _uuid


class ExitPermit(models.Model):
    REASONS = [
        ("medical", "موعد طبّي"),
        ("family", "ظرف عائلي"),
        ("official", "مراجعة جهة رسمية"),
        ("other", "سبب آخر"),
    ]
    #: `issued` الحالةُ الجديدة؛ و`requested`/`approved` قديمتان تبقيان مقروءتين.
    STATUSES = [("issued", "صادرة"), ("requested", "مطلوب"), ("approved", "معتمَد")]
    #: طريقةُ موافقة وليّ الأمر: حضر ببطاقته (بلا حفظ صورةٍ ولا رقم) أو اتّصالٌ هاتفيّ.
    GUARDIAN_METHODS = [("present", "حضر ببطاقته"), ("phone", "اتّصال هاتفيّ")]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School, on_delete=models.PROTECT, related_name="exit_permits", verbose_name="المدرسة"
    )
    student = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="exit_permits", verbose_name="الطالب"
    )
    class_group = models.ForeignKey(
        ClassGroup,
        on_delete=models.PROTECT,
        related_name="exit_permits",
        verbose_name="الشعبة",
    )
    #: تسلسلُ الإذن داخل المدرسة (يُحسب بالخدمة تحت قفل صفّ المدرسة).
    sequence = models.PositiveIntegerField(verbose_name="التسلسل")
    reason = models.CharField(max_length=12, choices=REASONS, verbose_name="السبب")
    note = models.CharField(max_length=200, blank=True, verbose_name="تفصيل العذر")
    exit_at = models.DateTimeField(default=timezone.now, verbose_name="وقت الخروج")
    completed_periods = models.PositiveSmallIntegerField(
        default=0, verbose_name="الحصص المكتملة عند الطلب"
    )
    guardian_present = models.BooleanField(default=False, verbose_name="حضر وليّ الأمر ببطاقته")
    #: فارغةٌ في الصفوف القديمة (حضورُها في `guardian_present`).
    guardian_method = models.CharField(
        max_length=8,
        choices=GUARDIAN_METHODS,
        blank=True,
        default="",
        db_default="",
        verbose_name="طريقة موافقة وليّ الأمر",
    )
    #: رقمُ الاتّصال مشفَّر؛ ولا يدخل AuditLog إلا مقنَّعاً، ويُمحى بمحو الطالب (الصفُّ كلُّه).
    call_phone = EncryptedTextField(
        blank=True, default="", db_default="", verbose_name="رقم الاتّصال"
    )
    call_phone_registered = models.BooleanField(
        default=True, db_default=True, verbose_name="الرقمُ مسجَّلٌ لوليّ الأمر"
    )
    caller_name = models.CharField(
        max_length=150, blank=True, default="", db_default="", verbose_name="اسم المتصل"
    )
    caller_relation = models.CharField(
        max_length=40, blank=True, default="", db_default="", verbose_name="صلة المتصل"
    )
    status = models.CharField(
        max_length=10, choices=STATUSES, default="issued", verbose_name="الحالة"
    )
    requested_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="exit_permits_requested",
        verbose_name="من طلب",
    )
    approved_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="exit_permits_approved",
        verbose_name="من اعتمد",
    )
    approved_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الاعتماد")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="أُنشئ")

    class Meta:
        verbose_name = "إذن خروج طالب"
        verbose_name_plural = "أذونات خروج الطلاب"
        ordering = ["-exit_at"]
        constraints = [
            models.UniqueConstraint(fields=["school", "sequence"], name="op_exitpermit_seq_uniq"),
        ]
        indexes = [models.Index(fields=["school", "exit_at"], name="op_exitpermit_day_idx")]

    def __str__(self) -> str:
        return f"إذن خروج {self.sequence} — {self.get_status_display()}"
