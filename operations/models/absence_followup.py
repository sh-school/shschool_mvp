"""سجلّا «متابعة الغياب» الرسميّان — اتّصالُ وليّ الأمر، والإجراءُ الإداريّ (W-20261013-011).

كانت متابعةُ المدير للغياب ورقيّةً. والسجلُّ هنا رسميٌّ في القاعدة: **مضافٌ إليه فقط** (`AppendOnlyModel`)،
فلا يُعدَّل سجلٌّ ولا يُحذف؛ وتصحيحُ سجلٍّ يكون **سجلاً جديداً** يشير إلى السابق بـ`corrects`، فيبقى
الأثرُ كاملاً لمن راجع. و«الحالُ الراهنة» لطالبٍ في يومٍ هي آخرُ سجلٍّ لم يُستبدَل بلاحق — مشتقّةٌ لا حقلٌ يُحدَّث.

**ما لا يُخزَّن هنا:** رقمُ وليّ الأمر ولا اسمُه ولا اسمُ الأمّ (قرارُ المالك D-431م): الرقمُ يُقرأ من
`ParentStudentLink` وقتَ العرض، وشاشةُ المتابعة لا تعرض اسماً أبداً. والتغذية الراجعة من وليّ الأمر نصٌّ حرٌّ قد يحمل ما
يحمل، فهي `EncryptedTextField` (PII) لا يقرؤها إلّا حاملُ قدرتها.
"""

from django.db import models
from django.utils import timezone

from core.fields import EncryptedTextField
from core.models import CustomUser, School

from .attendance import AbsenceExcuse
from .attendance_ledger import AppendOnlyModel
from .common import _uuid

#: حالةُ المتابعة لعمودَي «المتابعة» (W-20261014-018، قولُ المالك): تُدخَل وتُعرض للمدير والنائب الإداريّ
#: ومنسّق شؤون الطلاب وحدَهم (`operations.absence_followup_followup`).
FOLLOWUP_STATUSES = [
    ("done", "تمّ"),
    ("partial", "تمّ جزئياً"),
    ("not_done", "لم يتمّ"),
    ("not_followed", "لم تتمّ المتابعة"),
]


class AbsenceContactLog(AppendOnlyModel):
    """اتّصالٌ هاتفيٌّ بوليّ أمر طالبٍ عن يومِ غيابٍ بعينه — ومعه تغذيتُه الراجعة."""

    #: الستّةُ الأولى هي ما تعرضه الشاشةُ للتسجيل (قولُ المالك، بلاغ 6E42، حرفاً بحرف)؛ والأربعةُ بعدها قيمٌ
    #: سابقةٌ تبقى مقروءةً في السجلّات القديمة ولا تُعرض للتسجيل (توسيعٌ لا حذف — P4-1).
    OUTCOMES = [
        ("no_excuse", "غياب بدون عذر"),
        ("medical", "غياب بعذر طبي"),
        ("int_expel", "مفصول داخليًّا"),
        ("ext_expel", "مفصول خارجيًّا"),
        ("no_reply", "ولي الأمر لم يرد"),
        ("other", "أخرى"),
        ("answered", "ردّ"),
        ("no_answer", "لم يردّ"),
        ("will_excuse", "سيُحضر عذراً"),
        ("wrong_number", "الرقمُ غيرُ صحيح"),
    ]
    OFFERED_OUTCOMES = OUTCOMES[:6]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="absence_contact_logs",
        verbose_name="المدرسة",
    )
    #: يصير `NULL` بالمحو (PDPPL م.18 — «أثرٌ مجهَّلٌ» لا حذف، قرارُ المالك): يبقى الصفُّ للإحصاء بلا هويّة.
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="absence_contact_logs",
        verbose_name="الطالب",
    )
    absence_date = models.DateField(verbose_name="يومُ الغياب")
    contacted_at = models.DateTimeField(default=timezone.now, verbose_name="وقتُ الاتّصال")
    contacted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="absence_contacts_made",
        verbose_name="من اتّصل",
    )
    outcome = models.CharField(max_length=12, choices=OUTCOMES, verbose_name="النتيجة")
    #: حالةُ المتابعة — فارغةٌ في السجلّات القديمة ولغير الثلاثة (توسيعٌ لا حذف).
    status = models.CharField(
        max_length=14,
        choices=FOLLOWUP_STATUSES,
        blank=True,
        default="",
        verbose_name="حالةُ التواصل",
    )
    #: التغذية الراجعة من وليّ الأمر نصٌّ حرٌّ مشفَّر (PII) — لا يظهر إلّا لحاملي قدرة قراءته، وفتحُه يُدقَّق بلا نصّه.
    feedback = EncryptedTextField(
        blank=True, default="", verbose_name="التغذية الراجعة من وليّ الأمر"
    )
    #: التصحيحُ سجلٌّ جديدٌ يشير إلى ما صحّحه؛ والسابقُ يبقى كما كُتب.
    corrects = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrected_by",
        verbose_name="يصحّح سجلاً سابقاً",
    )

    class Meta:
        verbose_name = "اتّصالٌ بوليّ أمر عن غياب"
        verbose_name_plural = "اتّصالاتُ أولياء الأمور عن الغياب"
        ordering = ["-contacted_at"]
        indexes = [
            models.Index(fields=["school", "absence_date"], name="op_acl_school_day_idx"),
            models.Index(fields=["student", "absence_date"], name="op_acl_student_day_idx"),
        ]

    def __str__(self) -> str:
        return f"اتّصال {self.absence_date:%Y-%m-%d} — {self.get_outcome_display()}"


class AbsenceActionLog(AppendOnlyModel):
    """إجراءٌ إداريٌّ لغيابِ طالبٍ — تمّ، أو لم يتمّ، أو استُلمت إجازتُه المرضيّة."""

    #: `written_notice` يبقى مخزَّناً كما هو ويتبدّل اسمُه المعروض «تعهد خطي» (قولُ المالك) — فلا سجلَّ يُعدَّل.
    KINDS = [
        ("guardian_summon", "استدعاءُ وليّ الأمر"),
        ("written_notice", "تعهد خطي"),
        ("refer_coordinator", "تحويل لمنسق شؤون الطلاب"),
        ("refer_social", "تحويل للأخصائي الاجتماعي"),
        ("other", "أخرى"),
    ]
    STATUSES = [
        ("done", "تمّ"),
        ("not_done", "لم يتمّ"),
        ("sick_leave_received", "استلامُ إجازة مرضيّة"),
        ("partial", "تمّ جزئياً"),
        ("not_followed", "لم تتمّ المتابعة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.PROTECT,
        related_name="absence_action_logs",
        verbose_name="المدرسة",
    )
    #: يصير `NULL` بالمحو (PDPPL م.18 — «أثرٌ مجهَّلٌ» لا حذف، قرارُ المالك): يبقى الصفُّ للإحصاء بلا هويّة.
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="absence_action_logs",
        verbose_name="الطالب",
    )
    absence_date = models.DateField(verbose_name="يومُ الغياب")
    action_kind = models.CharField(
        max_length=20, choices=KINDS, default="other", verbose_name="نوعُ الإجراء"
    )
    status = models.CharField(max_length=20, choices=STATUSES, verbose_name="الحالة")
    note = models.CharField(max_length=200, blank=True, verbose_name="ملاحظة")
    #: استلامُ الإجازة المرضيّة يرتبط بالعذر القائم إن وُجد — لا نسخةً منه.
    excuse = models.ForeignKey(
        AbsenceExcuse,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="followup_actions",
        verbose_name="العذرُ المرتبط",
    )
    acted_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        related_name="absence_actions_made",
        verbose_name="من نفّذ",
    )
    acted_at = models.DateTimeField(default=timezone.now, verbose_name="وقتُ التنفيذ")
    #: وقتُ ومسجِّلُ «متابعة الإجراء» (W-20261017-024): يُملآن حين يسجّل أحدُ الثلاثة حالةَ المتابعة؛
    #: فارغان قبلَ المتابعة وفي السجلّات القديمة (توسيعٌ لا حذف).
    followed_at = models.DateTimeField(null=True, blank=True, verbose_name="وقتُ المتابعة")
    followed_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="absence_actions_followed",
        verbose_name="من تابع",
    )
    corrects = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="corrected_by",
        verbose_name="يصحّح سجلاً سابقاً",
    )

    class Meta:
        verbose_name = "إجراءٌ إداريٌّ عن غياب"
        verbose_name_plural = "الإجراءاتُ الإداريّةُ عن الغياب"
        ordering = ["-acted_at"]
        indexes = [
            models.Index(fields=["school", "absence_date"], name="op_aal_school_day_idx"),
            models.Index(fields=["student", "absence_date"], name="op_aal_student_day_idx"),
        ]

    def __str__(self) -> str:
        return f"إجراء {self.absence_date:%Y-%m-%d} — {self.get_status_display()}"
