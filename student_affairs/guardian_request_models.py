"""
student_affairs/guardian_request_models.py — طلبات الأولياء وشكاواهم والخطّ الساخن وإفادات الطلاب
(W-20261001-019؛ كتالوج النماذج 07ج: 01 و02 و05 و06 و08).

سجلٌّ واحدٌ بحقل النوع لا خمسة جداول: مسارُها واحدٌ — تحويلٌ للموظّف المختصّ ثمّ تغذيةٌ راجعة ثمّ
تأكيدُ التواصل مع وليّ الأمر ثمّ إغلاق. ولكلّ انتقالٍ منفِّذٌ وتاريخٌ في `GuardianRequestEvent`.
لا رقمَ شخصيّاً لوليّ الأمر هنا (الحدُّ الأدنى من البيانات)؛ والجوّالاتُ مشفَّرةٌ في أعمدتها.
"""

from django.db import models

from core.academic_calendar import default_academic_year
from core.models.base import AuditedModel
from core.models.crypto import decrypt_field, encrypt_field
from core.models.school import School
from core.models.user import CustomUser


def _encrypted(value: str) -> str:
    return str(encrypt_field(value)) if value else ""


def _decrypted(value: str) -> str:
    return str(decrypt_field(value) or "") if value else ""


class GuardianRequest(AuditedModel):
    """طلبُ وليّ أمرٍ أو شكواه أو تغييرُ رقم تواصله أو مكالمةُ خطٍّ ساخن أو إفادةُ طالب."""

    KIND_REQUEST = "request"
    KIND_COMPLAINT = "complaint"
    KIND_CONTACT_CHANGE = "contact_change"
    KIND_HOTLINE = "hotline"
    KIND_STATEMENT = "statement"
    KIND_CHOICES = [
        (KIND_REQUEST, "طلب ولي أمر"),
        (KIND_COMPLAINT, "شكوى ولي أمر"),
        (KIND_CONTACT_CHANGE, "طلب تغيير رقم التواصل"),
        (KIND_HOTLINE, "استمارة الخط الساخن"),
        (KIND_STATEMENT, "إفادة طالب"),
    ]
    #: النماذجُ ذاتُ مسار «تحويلٌ ← تغذيةٌ راجعة ← تأكيد التواصل» (01 و02 و08).
    FOLLOW_UP_KINDS = (KIND_REQUEST, KIND_COMPLAINT, KIND_STATEMENT)

    STAGE_SUBMITTED = "submitted"
    STAGE_REFERRED = "referred"
    STAGE_FEEDBACK = "feedback"
    STAGE_CONTACT_CONFIRMED = "contact_confirmed"
    STAGE_CLOSED = "closed"
    STAGE_REJECTED = "rejected"
    STAGE_CHOICES = [
        (STAGE_SUBMITTED, "مقدَّم"),
        (STAGE_REFERRED, "محوَّل"),
        (STAGE_FEEDBACK, "مردود بتغذية راجعة"),
        (STAGE_CONTACT_CONFIRMED, "تواصل مؤكَّد"),
        (STAGE_CLOSED, "مغلق"),
        (STAGE_REJECTED, "مرفوض"),
    ]

    CONTACT_DONE = "done"
    CONTACT_NOT_DONE = "not_done"
    CONTACT_CHOICES = [(CONTACT_DONE, "تم"), (CONTACT_NOT_DONE, "لم يتم")]

    CAPACITY_GUARDIAN = "guardian"
    CAPACITY_OTHER = "other"
    CAPACITY_CHOICES = [(CAPACITY_GUARDIAN, "ولي أمر"), (CAPACITY_OTHER, "غير ذلك")]

    DIRECT_ACADEMIC = "vice_academic"
    DIRECT_ADMIN = "vice_admin"
    DIRECT_OTHER = "other"
    DIRECT_CHOICES = [
        (DIRECT_ACADEMIC, "النائب الأكاديمي"),
        (DIRECT_ADMIN, "النائب الإداري"),
        (DIRECT_OTHER, "غير ذلك"),
    ]

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="guardian_requests",
        verbose_name="المدرسة",
    )
    kind = models.CharField(
        max_length=15, choices=KIND_CHOICES, db_index=True, verbose_name="النوع"
    )
    stage = models.CharField(
        max_length=20,
        choices=STAGE_CHOICES,
        default=STAGE_SUBMITTED,
        db_index=True,
        verbose_name="المرحلة",
    )
    academic_year = models.CharField(
        max_length=9, default=default_academic_year, verbose_name="العام الدراسي"
    )
    student = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guardian_requests",
        verbose_name="الطالب",
    )
    #: الخطُّ الساخن يذكر طلاباً عدّة بنصٍّ حرّ (الاسم، الشعبة، الصف) بلا ربطٍ بسجلّاتهم.
    related_students_text = models.CharField(
        max_length=500, blank=True, verbose_name="الطلاب ذوو العلاقة (نصّ)"
    )
    guardian_name = models.CharField(max_length=200, blank=True, verbose_name="اسم الوليّ / المتّصل")
    request_date = models.DateField(verbose_name="تاريخ الطلب")
    body = models.TextField(
        max_length=3000, blank=True, verbose_name="الطلب / الشكوى / الإفادة / أسباب الاتصال"
    )
    contact_phone_encrypted = models.TextField(
        blank=True, default="", verbose_name="رقم التواصل (مشفّر)"
    )

    # ── التحويل للموظّف المختصّ ──
    referred_to = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guardian_requests_referred",
        verbose_name="الموظف المختص",
    )
    referred_at = models.DateField(null=True, blank=True, verbose_name="تاريخ التحويل")

    # ── التغذية الراجعة ──
    feedback_text = models.TextField(max_length=3000, blank=True, verbose_name="التغذية الراجعة")
    feedback_at = models.DateField(null=True, blank=True, verbose_name="تاريخ التغذية الراجعة")
    feedback_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guardian_requests_feedback",
        verbose_name="موقّع التغذية الراجعة",
    )

    # ── تأكيد التواصل مع وليّ الأمر ──
    contact_status = models.CharField(
        max_length=8, choices=CONTACT_CHOICES, blank=True, verbose_name="التواصل مع ولي الأمر"
    )
    contact_at = models.DateField(null=True, blank=True, verbose_name="تاريخ التواصل")

    closed_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإغلاق")

    # ── طلب تغيير رقم التواصل (05) ──
    current_phone_encrypted = models.TextField(
        blank=True, default="", verbose_name="الرقم الحالي (مشفّر)"
    )
    new_phone_encrypted = models.TextField(
        blank=True, default="", verbose_name="الرقم الجديد (مشفّر)"
    )
    verified_by = models.ForeignKey(
        CustomUser,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="guardian_requests_verified",
        verbose_name="دقّقه (النائب الإداري)",
    )
    verified_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ التدقيق")
    applied_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ تطبيق الرقم")

    # ── الخطّ الساخن (06) ──
    call_reference = models.CharField(
        max_length=60, blank=True, verbose_name="الرقم المرجعي للاتصال"
    )
    call_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الاتصال")
    caller_capacity = models.CharField(
        max_length=10, choices=CAPACITY_CHOICES, blank=True, verbose_name="صفة المتصل"
    )
    caller_capacity_note = models.CharField(max_length=200, blank=True, verbose_name="توضيح الصفة")
    directed_to = models.CharField(
        max_length=15, choices=DIRECT_CHOICES, blank=True, verbose_name="الموجَّه إليه"
    )
    directed_note = models.CharField(max_length=200, blank=True, verbose_name="توضيح الجهة")
    receiver_name = models.CharField(max_length=200, blank=True, verbose_name="متلقّي الاتصال")

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلب وليّ أمر"
        verbose_name_plural = "طلبات الأولياء وشكاواهم"
        indexes = [
            models.Index(fields=["school", "kind", "stage"]),
            models.Index(fields=["school", "academic_year"]),
        ]

    def __str__(self):
        # بلا اسمٍ شخصيّ: يظهر في سجلّ التدقيق وقائمة الأدمن.
        return f"{self.get_kind_display()} {str(self.pk)[:8]}"

    # ── الجوّالات: مشفَّرةٌ في العمود، وتُقرأ بهذه الخصائص وحدَها ──
    @property
    def contact_phone(self) -> str:
        return _decrypted(self.contact_phone_encrypted)

    @contact_phone.setter
    def contact_phone(self, value: str) -> None:
        self.contact_phone_encrypted = _encrypted(value)

    @property
    def current_phone(self) -> str:
        return _decrypted(self.current_phone_encrypted)

    @current_phone.setter
    def current_phone(self, value: str) -> None:
        self.current_phone_encrypted = _encrypted(value)

    @property
    def new_phone(self) -> str:
        return _decrypted(self.new_phone_encrypted)

    @new_phone.setter
    def new_phone(self, value: str) -> None:
        self.new_phone_encrypted = _encrypted(value)

    @property
    def follows_feedback_path(self) -> bool:
        return self.kind in self.FOLLOW_UP_KINDS

    @property
    def stage_tone(self) -> str:
        """لونُ شارة المرحلة في القوائم (فئة `status-<tone>`)."""
        return {
            self.STAGE_SUBMITTED: "warning",
            self.STAGE_REJECTED: "danger",
            self.STAGE_CONTACT_CONFIRMED: "success",
            self.STAGE_CLOSED: "success",
        }.get(self.stage, "info")


class GuardianRequestEvent(models.Model):
    """أثرُ كلّ انتقالٍ في مسار الطلب: المرحلةُ ومنفِّذُها وتاريخُها — بلا اسمٍ ولا رقمٍ شخصيّ."""

    request = models.ForeignKey(
        GuardianRequest, on_delete=models.CASCADE, related_name="events", verbose_name="الطلب"
    )
    stage = models.CharField(max_length=20, verbose_name="المرحلة")
    actor = models.ForeignKey(
        CustomUser,
        null=True,
        on_delete=models.SET_NULL,
        related_name="guardian_request_events",
        verbose_name="المنفّذ",
    )
    at = models.DateTimeField(auto_now_add=True, verbose_name="التاريخ")
    note = models.CharField(max_length=300, blank=True, verbose_name="ملاحظة")

    class Meta:
        ordering = ["at", "id"]
        verbose_name = "حدث في مسار طلب"
        verbose_name_plural = "أحداث مسارات الطلبات"

    @property
    def stage_label(self) -> str:
        return dict(GuardianRequest.STAGE_CHOICES).get(self.stage, self.stage)

    def __str__(self):
        return f"{self.stage} {self.at:%Y-%m-%d}"
