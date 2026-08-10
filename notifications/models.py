"""
notifications/models.py
نظام الإشعارات — بريد إلكتروني + SMS
"""

import uuid

from django.db import models
from django.utils import timezone

from core.models import CustomUser, School
from core.models._crypto import decrypt_field, encrypt_field


def _uuid():
    return uuid.uuid4()


class DeadLetterMessage(models.Model):
    """[P0-8] رسائل إشعار فشلت نهائياً بعد استنفاد المحاولات — بدل ضياعها بصمت.

    [P2-B3] وحدة هذا الجدول **تسليم** لا مهمة: محاولة إيصال إشعار واحد إلى
    مستلم واحد عبر قناة واحدة، استنفدت محاولاتها القابلة للإعادة. مهمة واحدة قد
    تحمل عدة تسليمات — بريد ينجح وSMS يفشل لنفس الشخص — فجعل المهمة هي الوحدة
    كان يعني إعادة إرسال ما نجح وإنتاج إشعارات مكرّرة.

    [P2-B1] المدرسة عمود حقيقي لا مفتاح داخل JSON. سياسات RLS تعمل على الأعمدة
    ولا تقرأ داخل JSONField، فجدول يخزّن school_id في الـpayload يبقى خارج العزل
    مهما بلغت تغطية بقيّة الجداول — وأي شاشة تُبنى فوقه تعرض كل المدارس.

    [P2-B2] الـpayload بيانات **تشخيصية** لا نسخة من الرسالة: لا بريد ولا هاتف
    ولا نصّ. وهي **لا تكفي لإعادة الإرسال** في كل الحالات — `send_email_task`
    تقبل student_id=None مع notif_type="custom"، فرسالة إلى عنوان خارجي لا يبقى
    منها ما يستعيد المستلم. إعادة الإرسال محجوبة حتى يُصمَّم مرجع أو snapshot
    مشفّر؛ والبديل — تخزين البريد والهاتف والنصّ خاماً — يُنشئ مستودع PII جديداً.
    """

    KIND = [
        ("email", "بريد"),
        ("sms", "SMS"),
        ("push", "Push"),
        ("whatsapp", "WhatsApp"),
    ]
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="dead_letter_messages",
        verbose_name="المدرسة",
    )
    # [B4-0] الرابط إلى التسليم — خامد حتى يوجد كاتب.
    #
    # `null=True` للصفوف السابقة للخطّ لا لصفوف جديدة بلا تسليم: اشتراط وجوده
    # على الكتابة الجديدة قرارٌ يأتي مع الكاتب، لا في بنية لا تكتب شيئاً.
    #
    # و`PROTECT` لأن هذا الجدول **دليل**: صفٌّ فيه يقول إن تسليماً استنفد
    # محاولاته. حذف التسليم لا يجوز أن يمحو شهادة فشله، والصفّ يبقى منسوباً
    # لمدرسته على أي حال لأنه يحمل `school_id` خاصاً به.
    delivery = models.OneToOneField(
        "NotificationDelivery",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="dead_letter",
        verbose_name="التسليم",
    )
    kind = models.CharField(max_length=10, choices=KIND)
    payload = models.JSONField(default=dict)
    error = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "رسالة فاشلة (DLQ)"
        verbose_name_plural = "رسائل فاشلة (DLQ)"
        ordering = ["-created_at"]
        indexes = [
            # school أولاً: كل استعلام يمرّ بمُسند RLS على school_id.
            models.Index(fields=["school", "resolved", "created_at"], name="notif_dlq_school_idx"),
        ]

    def __str__(self):
        return f"{self.kind} — {'محلولة' if self.resolved else 'معلّقة'}"


class NotificationLog(models.Model):
    """سجلّ محاولة تسليم واحدة على قناة خارجية.

    الاسم يقول "أُرسل" والدورة تقول غير ذلك: الصفّ يُنشأ بحالة `pending` **قبل**
    نداء المزوّد ثم يُحسم إلى `sent` أو `failed`. هذه دورة حياة محاولة لا سجلّ
    إرسال، وإعادة Celery تستدعي الخدمة من جديد فتُنشئ صفّاً لكل محاولة.

    وقد كانت هذه الدورة قائمة في البريد وSMS وحدهما: WhatsApp كان يكتب بعد نجاح
    الإرسال فقط — فلا أثر لمحاولة فشلت — وPush لم يكن يكتب شيئاً إطلاقاً.

    `in_app` ليست هنا عمداً: `InAppNotification` هي الكيان المُرسَل نفسه
    والمخزَّن في القاعدة، لا تسليماً خارجياً له مزوّد وإعادة محاولة.
    """

    CHANNEL = [
        ("email", "بريد إلكتروني"),
        ("sms", "SMS"),
        ("whatsapp", "WhatsApp"),
        ("push", "Push"),
    ]
    TYPE = [
        ("absence_alert", "تنبيه غياب"),
        ("fail_alert", "تنبيه رسوب"),
        ("grade_report", "تقرير درجات"),
        ("custom", "رسالة مخصصة"),
    ]
    STATUS = [
        ("sent", "أُرسل"),
        ("failed", "فشل"),
        ("pending", "معلّق"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="notification_logs")
    # [B4-0] الرابط إلى التسليم — خامد حتى يوجد كاتب.
    #
    # `null=True` معناه "سابق للخطّ"، وهو وصف صادق للصفوف القائمة. ولا backfill:
    # اختلاق واقعة إطلاق لم نشهدها هو النمط نفسه الذي نطارده.
    #
    # و`PROTECT` لأن هذا الصفّ **دليل** على محاولة جرت. حذف التسليم يجب ألّا
    # يمحو تاريخ ما حدث؛ والصفّ يبقى ضمن حدّ مدرسته لأنه يحمل `school_id` خاصاً.
    delivery = models.ForeignKey(
        "NotificationDelivery",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="attempts",
        verbose_name="التسليم",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_logs",
        verbose_name="الطالب",
    )
    recipient = models.CharField(max_length=200, verbose_name="المستلم (email/رقم)")
    channel = models.CharField(max_length=10, choices=CHANNEL, default="email")
    notif_type = models.CharField(max_length=20, choices=TYPE, default="custom")
    subject = models.CharField(max_length=300, blank=True, verbose_name="الموضوع")
    body = models.TextField(verbose_name="نص الرسالة")
    status = models.CharField(max_length=10, choices=STATUS, default="pending", db_index=True)
    error_msg = models.TextField(blank=True)
    sent_at = models.DateTimeField(auto_now_add=True, db_index=True)
    sent_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_notifications",
    )

    class Meta:
        verbose_name = "إشعار مُرسل"
        verbose_name_plural = "سجل الإشعارات"
        ordering = ["-sent_at"]
        indexes = [models.Index(fields=["school", "notif_type", "status"])]

    def __str__(self):
        return f"{self.get_notif_type_display()} → {self.recipient} ({self.get_status_display()})"


class NotificationSettings(models.Model):
    """إعدادات الإشعارات لكل مدرسة"""

    school = models.OneToOneField(School, on_delete=models.CASCADE, related_name="notif_settings")

    # البريد الإلكتروني
    email_enabled = models.BooleanField(default=True)
    absence_threshold = models.IntegerField(default=3, verbose_name="حد الغياب (حصص)")
    absence_email_enabled = models.BooleanField(default=True)
    fail_email_enabled = models.BooleanField(default=True)
    from_name = models.CharField(max_length=100, default="إدارة المدرسة")
    reply_to = models.EmailField(blank=True)

    # SMS (Twilio أو أي مزود)
    sms_enabled = models.BooleanField(default=False)
    sms_provider = models.CharField(
        max_length=20, default="twilio", choices=[("twilio", "Twilio"), ("local", "محلي")]
    )
    sms_from_number = models.CharField(max_length=20, blank=True)
    # ── VULN-003 Fix: Fernet encryption for Twilio credentials (CWE-312) ──
    _twilio_account_sid = models.TextField(blank=True, default="", db_column="twilio_account_sid")
    _twilio_auth_token = models.TextField(blank=True, default="", db_column="twilio_auth_token")

    @property
    def twilio_account_sid(self):
        return decrypt_field(self._twilio_account_sid) or self._twilio_account_sid

    @twilio_account_sid.setter
    def twilio_account_sid(self, value):
        self._twilio_account_sid = encrypt_field(value) if value else ""

    @property
    def twilio_auth_token(self):
        return decrypt_field(self._twilio_auth_token) or self._twilio_auth_token

    @twilio_auth_token.setter
    def twilio_auth_token(self, value):
        self._twilio_auth_token = encrypt_field(value) if value else ""

    # نصوص الرسائل (قابلة للتخصيص)
    absence_email_subject = models.CharField(
        max_length=200, default="تنبيه: غياب متكرر للطالب {student_name}"
    )
    fail_email_subject = models.CharField(
        max_length=200, default="إشعار: نتيجة الطالب {student_name}"
    )

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "إعدادات الإشعارات"
        verbose_name_plural = "إعدادات الإشعارات"

    def __str__(self):
        return f"إعدادات إشعارات — {self.school.name}"


# ════════════════════════════════════════════════════════════════════
# ✅ PushSubscription — v5 (VAPID Push Notifications)
# ════════════════════════════════════════════════════════════════════


class PushSubscription(models.Model):
    """
    اشتراك Push للمتصفح — يُخزَّن عند تسجيل ولي الأمر
    endpoint + keys تأتي من browser.pushManager.subscribe()
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="push_subscriptions"
    )
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="push_subscriptions")
    # بيانات الاشتراك من المتصفح
    endpoint = models.TextField(unique=True, verbose_name="Push Endpoint")
    p256dh = models.TextField(verbose_name="p256dh key")
    # ── HIGH-003 Fix: Fernet encryption for push auth secret ──
    _auth = models.TextField(verbose_name="auth secret (encrypted)", db_column="auth", default="")

    @property
    def auth(self):
        return decrypt_field(self._auth) or self._auth

    @auth.setter
    def auth(self, value):
        self._auth = encrypt_field(value) if value else ""

    # معلومات الجهاز
    user_agent = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    last_used = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "اشتراك Push"
        verbose_name_plural = "اشتراكات Push"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user.full_name} — {self.endpoint[:60]}..."

    def to_dict(self):
        """تنسيق pywebpush"""
        return {
            "endpoint": self.endpoint,
            "keys": {
                "p256dh": self.p256dh,
                "auth": self.auth,
            },
        }


# ════════════════════════════════════════════════════════════════════
# ✅ v6: إشعارات المنصة الداخلية (In-App Notifications)
# ════════════════════════════════════════════════════════════════════


class InAppNotificationManager(models.Manager):
    """Manager لاستعلامات الإشعارات الداخلية"""

    def unread_for_user(self, user):
        return self.filter(user=user, is_read=False).order_by("-created_at")

    def unread_count(self, user):
        return self.filter(user=user, is_read=False).count()

    def mark_all_read(self, user):
        return self.filter(user=user, is_read=False).update(is_read=True, read_at=timezone.now())

    def for_user(self, user, limit=50):
        return self.filter(user=user).order_by("-created_at")[:limit]


class InAppNotification(models.Model):
    """
    إشعار داخل المنصة — يظهر في الجرس (Navbar)
    مجاني، فوري، لا يحتاج إعدادات من المستخدم
    """

    EVENT_TYPES = [
        ("behavior", "مخالفة سلوكية"),
        ("absence", "غياب متكرر"),
        ("grade", "درجات جديدة"),
        ("fail", "نتيجة رسوب"),
        ("clinic", "زيارة عيادة"),
        ("sent_home", "إرسال للمنزل"),
        ("meeting", "اجتماع أولياء أمور"),
        ("parent_summon", "استدعاء ولي أمر"),
        ("plan_update", "تحديث الخطة التشغيلية"),
        ("plan_deadline", "اقتراب موعد نهائي"),
        ("plan_overdue", "تأخر إجراء"),
        ("review_cycle", "دورة مراجعة ذاتية"),
        # ── إشعارات التبديل والتعويض ──
        ("swap_request", "طلب تبديل حصة"),
        ("swap_response", "رد على طلب تبديل"),
        ("swap_approved", "موافقة على تبديل"),
        ("compensatory", "حصة تعويضية"),
        ("general", "إشعار عام"),
    ]
    PRIORITY = [
        ("low", "منخفض"),
        ("medium", "متوسط"),
        ("high", "عالي"),
        ("urgent", "عاجل"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    user = models.ForeignKey(
        CustomUser, on_delete=models.CASCADE, related_name="in_app_notifications"
    )
    school = models.ForeignKey(
        School, on_delete=models.CASCADE, related_name="in_app_notifications"
    )
    title = models.CharField(max_length=300, verbose_name="العنوان")
    body = models.TextField(verbose_name="النص", blank=True)
    event_type = models.CharField(
        max_length=20, choices=EVENT_TYPES, default="general", db_index=True
    )
    priority = models.CharField(max_length=10, choices=PRIORITY, default="medium")
    # ربط بالكائن المصدر (اختياري)
    related_object_id = models.CharField(
        max_length=100, blank=True, verbose_name="معرّف الكائن المرتبط"
    )
    related_url = models.CharField(max_length=500, blank=True, verbose_name="رابط مباشر")
    # حالة القراءة
    is_read = models.BooleanField(default=False, db_index=True)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    objects = InAppNotificationManager()

    class Meta:
        verbose_name = "إشعار داخلي"
        verbose_name_plural = "الإشعارات الداخلية"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "is_read", "-created_at"]),
            models.Index(fields=["school", "event_type"]),
        ]

    def __str__(self):
        status = "مقروء" if self.is_read else "جديد"
        return f"{self.title} → {self.user.full_name} ({status})"

    def mark_read(self):
        if not self.is_read:
            self.is_read = True
            self.read_at = timezone.now()
            self.save(update_fields=["is_read", "read_at"])


# ════════════════════════════════════════════════════════════════════
# ✅ v6: تفضيلات الإشعارات لكل مستخدم
# ════════════════════════════════════════════════════════════════════


class UserNotificationPreference(models.Model):
    """
    تفضيلات قنوات الإشعارات — يتحكم المستخدم بأي قناة يريد
    """

    user = models.OneToOneField(
        CustomUser, on_delete=models.CASCADE, related_name="notification_preferences"
    )

    # تفعيل القنوات
    in_app_enabled = models.BooleanField(default=True, verbose_name="إشعارات المنصة")
    push_enabled = models.BooleanField(default=True, verbose_name="Push Notifications")
    whatsapp_enabled = models.BooleanField(default=False, verbose_name="WhatsApp")
    email_enabled = models.BooleanField(default=True, verbose_name="البريد الإلكتروني")
    sms_enabled = models.BooleanField(default=False, verbose_name="SMS")

    # تفضيلات حسب نوع الحدث (JSON: {"behavior": ["in_app","email"], "absence": ["in_app","whatsapp","email"]})
    # فارغ = استخدام الإعدادات الافتراضية
    event_channels = models.JSONField(default=dict, blank=True, verbose_name="قنوات حسب نوع الحدث")

    # ساعات الهدوء — لا ترسل إشعارات خارجية في هذه الفترة
    quiet_hours_start = models.TimeField(null=True, blank=True, verbose_name="بداية ساعات الهدوء")
    quiet_hours_end = models.TimeField(null=True, blank=True, verbose_name="نهاية ساعات الهدوء")

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "تفضيلات إشعارات"
        verbose_name_plural = "تفضيلات الإشعارات"

    def __str__(self):
        return f"تفضيلات — {self.user.full_name}"

    def get_channels_for_event(self, event_type):
        """
        يُرجع قائمة القنوات المفعّلة لهذا النوع من الأحداث.
        يتحقق أولاً من event_channels المخصص، ثم الإعدادات العامة.
        """
        # تفضيل مخصص لهذا الحدث
        if event_type in self.event_channels:
            return self.event_channels[event_type]

        # الإعدادات العامة
        channels = []
        if self.in_app_enabled:
            channels.append("in_app")
        if self.push_enabled:
            channels.append("push")
        if self.whatsapp_enabled:
            channels.append("whatsapp")
        if self.email_enabled:
            channels.append("email")
        if self.sms_enabled:
            channels.append("sms")
        return channels

    def is_quiet_hours(self):
        """هل الوقت الحالي ضمن ساعات الهدوء؟"""
        if not self.quiet_hours_start or not self.quiet_hours_end:
            return False
        from django.utils import timezone as tz

        now = tz.localtime().time()
        if self.quiet_hours_start <= self.quiet_hours_end:
            return self.quiet_hours_start <= now <= self.quiet_hours_end
        else:  # يعبر منتصف الليل
            return now >= self.quiet_hours_start or now <= self.quiet_hours_end


# ════════════════════════════════════════════════════════════════════
# [B4-0] البنية الخامدة — Dispatch / Delivery
# ════════════════════════════════════════════════════════════════════
#
# لا كاتب لهذين الجدولين بعد، ولا راية تُشغّلهما. هذه الدفعة تُنشئ البنية
# وتُثبت قيودها فقط؛ توصيل المسار الحالي إليها يأتي لاحقاً.


class NotificationDispatch(models.Model):
    """واقعة إطلاق إشعار واحدة — لا وحدة تسليم.

    الـdispatch هو "حدث وقع فأردنا إخبار أحد به": مخالفة سُجّلت، إجراء اقترب
    موعده. وهو فريد بحكم إنشائه لا بقيد: تذكير الغد لنفس الإجراء واقعة جديدة
    مقصودة، لا تكراراً لواقعة الأمس.

    ولهذا `related_object_id` سياق لا هوية. مُعرّف كائن الأعمال يُجيب عن
    "بمَ يتعلّق هذا؟" ولا يُجيب عن "أهذه الواقعة نفسها؟" — والخلط بينهما كان
    سيمنع تذكيرين مشروعين لنفس الإجراء في يومين.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="notification_dispatches",
        verbose_name="المدرسة",
    )
    event_type = models.CharField(max_length=40, db_index=True, verbose_name="نوع الحدث")
    related_object_id = models.CharField(
        max_length=64, blank=True, verbose_name="كائن الأعمال (سياق)"
    )
    related_url = models.CharField(max_length=500, blank=True, verbose_name="الرابط")
    sent_by = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="notification_dispatches",
        verbose_name="أطلقها",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "واقعة إشعار"
        verbose_name_plural = "وقائع الإشعار"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "event_type", "created_at"], name="notif_dispatch_idx"),
        ]
        constraints = [
            # هدف المفتاح المركّب في NotificationDelivery. بدونه لا يمكن لقاعدة
            # البيانات أن تفرض أن الابن يحمل مدرسة أبيه.
            models.UniqueConstraint(fields=["id", "school"], name="uniq_dispatch_id_school"),
        ]

    def __str__(self):
        return f"{self.event_type} — {self.created_at:%Y-%m-%d %H:%M}"


class NotificationDelivery(models.Model):
    """محاولة إيصال واقعة إلى مستلم واحد عبر قناة واحدة.

    هذه هي وحدة الفشل التي استقرّ عليها P2-B3، والهوية التي تجعل إعادة الإرسال
    قابلة للتمييز عن إرسال جديد: `(dispatch, recipient, channel)`.

    والهوية ليست ضماناً بأن الرسالة تُسلَّم مرّة واحدة. القيد يمنع **تسليمين**
    لنفس الثلاثية، ولا يمنع محاولتين على تسليم واحد تبلغان المزوّد كلتاهما —
    فالالتزام عندنا وعند المزوّد ليسا ذرّة واحدة. الضمان `at-least-once`.

    `school` مكرَّر عمداً هنا خلافاً لقاعدة الاشتقاق من الأب التي اعتمدناها في
    الجداول العشرين: هذا الجدول يُستعلَم بالمدرسة مباشرةً في شاشات التشغيل،
    وتكراره يجعل سياسة العزل مُسنَداً محلياً بلا استعلام فرعي. والانحراف عن
    الأب مستحيل لأن المفتاح المركّب يفرض التطابق في قاعدة البيانات نفسها.

    `in_app` ليست قناة هنا: `InAppNotification` هي الكيان المُرسَل والمخزَّن،
    لا تسليماً خارجياً له مزوّد وإعادة محاولة وطابور فشل.
    """

    CHANNEL = [
        ("email", "بريد إلكتروني"),
        ("sms", "SMS"),
        ("whatsapp", "WhatsApp"),
        ("push", "Push"),
    ]

    #: [B4-0] الحالات كما أُقرّت في تصميم B4-B، بلا `unknown_outcome`.
    #: تلك تصير حقيقة قابلة للتسجيل حين يدخل الاستئجار وآلة الحالات في B4-3؛
    #: إضافتها قبل وجود انتقال يُنتجها تخلق دلالة لا يكتبها شيء.
    STATUS = [
        ("pending", "معلّق"),
        ("in_progress", "قيد التنفيذ"),
        ("sent", "سُلّم"),
        ("retry_wait", "بانتظار إعادة المحاولة"),
        ("dead_lettered", "استنفد المحاولات"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    dispatch = models.ForeignKey(
        NotificationDispatch,
        on_delete=models.CASCADE,
        related_name="deliveries",
        verbose_name="الواقعة",
    )
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="notification_deliveries",
        verbose_name="المدرسة",
    )
    recipient = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name="notification_deliveries",
        verbose_name="المستلم",
    )
    channel = models.CharField(max_length=10, choices=CHANNEL, verbose_name="القناة")
    status = models.CharField(
        max_length=15, choices=STATUS, default="pending", db_index=True, verbose_name="الحالة"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "تسليم إشعار"
        verbose_name_plural = "تسليمات الإشعار"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["school", "status", "created_at"], name="notif_delivery_idx"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["dispatch", "recipient", "channel"],
                name="uniq_delivery_dispatch_recipient_channel",
            ),
            # هدف المفتاح المركّب في NotificationLog وDeadLetterMessage.
            models.UniqueConstraint(fields=["id", "school"], name="uniq_delivery_id_school"),
        ]

    def __str__(self):
        return f"{self.channel} → {self.recipient_id} ({self.status})"
