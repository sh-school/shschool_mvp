"""سجلُّ رصد المعلّم المضافُ إليه ولا يُمحى — إدخالٌ مبدئيّ، وقرارُ اعتمادٍ أو رفض (W-20261002-020).

## لِمَ جدولان ولا حقلُ اعتمادٍ على `StudentAttendance`

`StudentAttendance` سجلٌّ **واحدٌ** لكلّ (حصّة، طالب) بقيدٍ فريد، وكلُّ قارئٍ للحضور (عتباتُ الغياب،
الإخطارات، التقارير، التصديرات) يفترض ذلك ويقرأ المعتمَدَ. فأن يُكتب فيه ما لم يُعتمد بعدُ يجعل كلَّ
قارئٍ يحسبه، وأن يصير التصحيحُ «صفّاً جديداً» فيه يُسقط القيدَ ويُعيد كتابةَ القرّاء كلِّهم في طلبٍ واحد
على سندِ خصمٍ وتأديب (قرارُ 0101 وحكمُ 0105، 2026-10-02).

فالسجلُّ الذي لا يُمحى جدولان **مضافان فقط**:

- `AttendanceEntry` — ما أدخله المعلّمُ الفعليّ، بنسخٍ متعاقبةٍ (`supersedes`): تصحيحُ إدخالٍ صفٌّ جديدٌ
  بسببٍ، لا تعديل.
- `AttendanceDecision` — قرارُ الاعتماد أو الرفض، **صفٌّ واحدٌ لكلّ إدخال** (قيدٌ فريد، فالاعتمادُ
  المزدوجُ المتزامن واحد)، بدليله وقتَ القرار (الجناحُ والتغطيةُ والحامل) فلا يُعاد حسابُه لاحقاً.

وتبقى `StudentAttendance` الرصدَ **المعتمَدَ الفعّال**: لا يُكتب إليها إلّا عند الاعتماد (أو فوراً في
التربية الخاصّة). فيرى كلُّ قارئٍ المعتمَدَ وحدَه دون أن يُمسّ.

«بانتظار الاعتماد» = إدخالٌ بلا قرار؛ و«مستبدَل» = له إدخالٌ لاحقٌ يشير إليه — كلاهما **مشتقٌّ** لا حقلٌ يُحدَّث.

## عدمُ القابليّة للتعديل

على ثلاث طبقات: هنا (`save` لا يقبل إلّا الإنشاء، و`delete` والتعديلُ الجماعيُّ مرفوضان)، وفي القاعدة (مشغّلُ
`BEFORE UPDATE OR DELETE` في هجرة 0062، على غرار `core/0014` لـAuditLog)، وفي الأدمن (قراءةٌ فقط).
والاستثناءُ الوحيد محوُ طالبٍ (PDPPL م.18): `erase_attendance_ledger` في
[`attendance_entries`](../attendance_entries.py) يضبط علَماً محلّيّاً في المعاملة يسمح بالحذف وحدَه — وهو
مفتاحٌ لا إذن، فحارسٌ معماريٌّ يمنع ظهورَ اسمه خارج موضعه.
"""

from typing import Any, NoReturn

from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models import Q
from django.utils import timezone

from core.models import CustomUser, School

from .attendance import Session
from .common import _uuid

#: اسمُ علَم المحو المحلّيّ في المعاملة — يقرؤه المشغّلُ في القاعدة. لا يُضبط إلّا من `erase_attendance_ledger`.
ERASURE_FLAG = "app.attendance_erasure"


class AppendOnlyQuerySet(models.QuerySet):
    """يمنع التعديلَ والحذفَ الجماعيَّ — السجلُّ يُضاف إليه ولا يُمحى."""

    def update(self, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("سجلُّ الرصد مضافٌ-إليه فقط: لا تعديل.")

    def bulk_update(self, objs: Any, fields: Any, batch_size: int | None = None) -> NoReturn:
        raise PermissionDenied("سجلُّ الرصد مضافٌ-إليه فقط: لا تعديل.")

    def delete(self) -> NoReturn:
        raise PermissionDenied("سجلُّ الرصد مضافٌ-إليه فقط: لا حذف.")

    def _erase(self) -> int:
        """الحذفُ الوحيد المشروع — يستدعيه `erase_attendance_ledger` وحدَه بعد ضبط علَم المحو.

        حذفٌ خامٌّ بلا جامعِ تتابعٍ: `PROTECT` على `supersedes` وعلى القرارات يمنع جامعَ Django حتى لو حُذف
        الطرفان معاً، والقاعدةُ تتحقّق من قيودها (مؤجَّلةً) بعد العبارة.
        """
        count: int = self._raw_delete(self.db)  # type: ignore[attr-defined]  # واجهةٌ خاصّةٌ ثابتةٌ في Django بلا تلميح
        return count


class AppendOnlyModel(models.Model):
    objects = AppendOnlyQuerySet.as_manager()

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self._state.adding:
            raise PermissionDenied("سجلُّ الرصد مضافٌ-إليه فقط: لا تعديل.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> NoReturn:
        raise PermissionDenied("سجلُّ الرصد مضافٌ-إليه فقط: لا حذف.")


class AttendanceEntry(AppendOnlyModel):
    """ما أدخله المعلّمُ الفعليّ لطالبٍ في حصّته — مبدئيٌّ حتى يُقرَّر فيه."""

    STATUS = [
        ("present", "حاضر"),
        ("absent", "غائب"),
        ("late", "متأخّر"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="attendance_entries",
        verbose_name="المدرسة",
    )
    session = models.ForeignKey(
        Session,
        on_delete=models.PROTECT,
        related_name="attendance_entries",
        verbose_name="الحصّة",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="attendance_entries",
        verbose_name="الطالب",
    )
    status = models.CharField(max_length=10, choices=STATUS, verbose_name="الحالة")
    tardiness_minutes = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="دقائق التأخّر"
    )
    #: من الخادم وحدَه — لا من الطلب.
    entered_by = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="attendance_entries_made",
        verbose_name="أدخله",
    )
    entered_at = models.DateTimeField(default=timezone.now, verbose_name="وقتُ الإدخال")
    #: النسخةُ التي يصحّحها هذا الإدخال. `OneToOne` فلا فرعان لصفٍّ واحد (M4-أ).
    supersedes = models.OneToOneField(
        "self",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="superseded_by",
        verbose_name="يصحّح",
    )
    correction_reason = models.TextField(blank=True, verbose_name="سببُ التصحيح")
    #: مصدرُ الإدخال: فارغٌ لرصدٍ مرصودٍ بالمسار القائم، `grid` لخليّةٍ كتبها كاتبٌ في جدول الشعبة، و`grid_default` لـ«حاضرٍ افتراضيّ» كتبه الحفظُ
    #: لخليّةٍ فارغةٍ في عمودٍ بدأت حصّتُه (W-20261006-005، قرارُ المالك D-240م): يظهر في الشاشة والتصدير مختلفاً عن «حاضرٍ مرصود».
    #: `db_default` فتُدرج نسخةُ الكود القديمةُ أثناء النشر المتدحرج بلا الحقل (توسيعٌ ثمّ تقليص).
    origin = models.CharField(
        max_length=16, blank=True, default="", db_default="", verbose_name="مصدرُ الإدخال"
    )

    class Meta:
        verbose_name = "إدخالُ رصدٍ مبدئيّ"
        verbose_name_plural = "إدخالاتُ الرصد المبدئيّ"
        ordering = ["entered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "student"],
                condition=Q(supersedes__isnull=True),
                name="unique_root_attendance_entry",
            ),
            models.CheckConstraint(  # type: ignore[call-arg]  # `condition` (Django 5.1+) غيرُ معروفٍ لـdjango-stubs 5.0
                condition=Q(supersedes__isnull=True) | ~Q(correction_reason=""),
                name="attendance_entry_correction_has_reason",
            ),
        ]
        indexes = [models.Index(fields=["session", "student"], name="idx_attentry_session_student")]

    def __str__(self) -> str:
        return f"{self.session_id} · {self.student_id} · {self.status}"


class AttendanceDecision(AppendOnlyModel):
    """قرارُ حاملِ الجناح (أو القيادةِ حين لا حامل) في إدخالٍ — صفٌّ واحدٌ لكلّ إدخال."""

    DECISIONS = [("approved", "اعتماد"), ("rejected", "رفض")]
    BASES = [
        ("wing_holder", "حاملُ جناح الشعبة"),
        ("leadership_no_holder", "القيادةُ — لا حاملَ للجناح"),
        ("leadership_holder_is_teacher", "القيادةُ — حاملُ الجناح هو معلّمُ الحصّة"),
        ("leadership_holder_inactive", "القيادةُ — حاملُ الجناح بلا عضويّةٍ نشطة"),
        ("school_wide", "حاصرُ الغياب العامّ — اعتمادٌ ثانٍ بجانب الحامل"),
        ("supervisor_record", "كُتب رصدُ مشرفٍ فوق الإدخال"),
        ("special_ed_self", "التربيةُ الخاصّة — اعتمادٌ ذاتيٌّ بالتصميم"),
        ("wing_holder_self", "حاملُ الجناح — اعتمادُ ما كتبه بنفسه (جدولُ الشعبة)"),
        ("direct_entry", "رصدٌ نهائيٌّ مباشر — جناحٌ بلا اعتماد (جدولُ الشعبة)"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="attendance_decisions",
        verbose_name="المدرسة",
    )
    entry = models.OneToOneField(
        AttendanceEntry,
        on_delete=models.PROTECT,
        related_name="decision",
        verbose_name="الإدخال",
    )
    decision = models.CharField(max_length=10, choices=DECISIONS, verbose_name="القرار")
    decided_by = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="attendance_decisions_made",
        verbose_name="قرّره",
    )
    decided_at = models.DateTimeField(default=timezone.now, verbose_name="وقتُ القرار")
    basis = models.CharField(max_length=40, choices=BASES, verbose_name="أساسُ الصلاحيّة")
    #: دليلُ الصلاحيّة وقتَ القرار (الجناحُ والتغطيةُ والحامل) — يُحفظ فلا يُعاد حسابُه بعد تغيّر التغطية.
    evidence = models.JSONField(default=dict, blank=True, verbose_name="الدليل")
    reason = models.TextField(blank=True, verbose_name="السبب")

    class Meta:
        verbose_name = "قرارُ رصد"
        verbose_name_plural = "قراراتُ الرصد"
        ordering = ["decided_at"]
        constraints = [
            models.CheckConstraint(  # type: ignore[call-arg]  # `condition` (Django 5.1+) غيرُ معروفٍ لـdjango-stubs 5.0
                condition=Q(decision="approved") | ~Q(reason=""),
                name="attendance_decision_rejection_has_reason",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.entry_id} · {self.decision}"
