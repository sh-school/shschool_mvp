"""استبانة تجربة المستخدم للموظفين (W-20261015-002، المواصفة W-20261015-001).

**الخصوصيّة بالبنية:** جدولان لا رابطَ بينهما.
- `SurveyResponse`: الإجابةُ بلا مستخدمٍ ولا رقمٍ وظيفيّ ولا IP ولا وقتٍ دقيق (الأسبوعُ فقط)، ومفتاحُها UUID
  عشوائيّ فلا يكشف ترتيبُ الإدراج من أجاب بعد من.
- `SurveyParticipation`: من تعامل مع الاستبانة وبأيّ حالة، بلا أيّ حقلٍ من الإجابة ولا طابعٍ زمنيّ.
"""

import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models

from core.fields import EncryptedTextField

FREE_TEXT_MAX = 200


class SurveyWave(models.Model):
    name = models.CharField(max_length=80, verbose_name="اسم الموجة")
    is_active = models.BooleanField(default=False, verbose_name="مفتوحة للإجابة")
    snooze_days = models.PositiveSmallIntegerField(default=7, verbose_name="أيامُ التأجيل")

    class Meta:
        verbose_name = "موجة استبانة"
        verbose_name_plural = "موجات الاستبانة"

    def __str__(self) -> str:
        return self.name


class SurveyResponse(models.Model):
    FREQUENCY = [("daily", "يوميًا"), ("several", "عدة مرات"), ("once", "مرة"), ("rarely", "نادرًا")]
    PLACE = [
        ("school_pc", "حاسوب المدرسة"),
        ("own_pc", "حاسوب شخصي"),
        ("phone", "هاتف"),
        ("multiple", "أكثر من واحد"),
    ]
    FAST = [("always", "دائمًا"), ("often", "غالبًا"), ("sometimes", "أحيانًا"), ("rarely", "نادرًا")]
    SCALE = [MinValueValidator(1), MaxValueValidator(5)]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    wave = models.ForeignKey(
        SurveyWave, on_delete=models.CASCADE, related_name="responses", verbose_name="الموجة"
    )
    #: مجموعةُ الصفة من دور الخادم لا من اختيار المجيب (انظر `groups.py`).
    role_group = models.CharField(max_length=12, verbose_name="الصفة")
    #: يومُ الاثنين من أسبوع الإجابة — لا وقتَ أدقّ منه في أيّ جدول.
    week = models.DateField(verbose_name="أسبوع الإجابة")
    usage_frequency = models.CharField(
        max_length=8, choices=FREQUENCY, verbose_name="مرّاتُ الاستخدام"
    )
    usage_place = models.CharField(max_length=10, choices=PLACE, verbose_name="مكانُ الاستخدام")
    sus_easy = models.PositiveSmallIntegerField(validators=SCALE, verbose_name="سهلة الاستخدام")
    sus_slow = models.PositiveSmallIntegerField(validators=SCALE, verbose_name="تحتاج وقتًا طويلًا")
    sus_confident = models.PositiveSmallIntegerField(validators=SCALE, verbose_name="أشعر بالثقة")
    sus_remember = models.PositiveSmallIntegerField(
        validators=SCALE, verbose_name="يصعب تذكّر الخطوات"
    )
    find_fast = models.CharField(
        max_length=9, choices=FAST, verbose_name="أجد ما أحتاجه بنصف دقيقة"
    )
    hardest_task = EncryptedTextField(verbose_name="المهمة الأصعب")
    wish = EncryptedTextField(blank=True, default="", verbose_name="أمنية التغيير")
    #: المراجعةُ البشريّة قبل أن يظهر النصّ للإدارة: 0 لم تُراجَع، 1 مقبولٌ للعرض، 2 مرفوض.
    review = models.PositiveSmallIntegerField(default=0, verbose_name="حالةُ المراجعة")

    class Meta:
        verbose_name = "إجابة استبانة"
        verbose_name_plural = "إجابات الاستبانة"
        indexes = [models.Index(fields=["wave", "role_group"])]

    def __str__(self) -> str:
        return f"إجابة {self.role_group} — {self.week}"


class SurveyParticipation(models.Model):
    PENDING, ANSWERED, SNOOZED, CLOSED = "pending", "answered", "snoozed", "closed"
    STATUSES = [
        (PENDING, "لم يُجب"),
        (ANSWERED, "أجاب"),
        (SNOOZED, "أُجِّل"),
        (CLOSED, "أُغلق نهائيًّا"),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="survey_participations",
        verbose_name="الموظف",
    )
    wave = models.ForeignKey(
        SurveyWave, on_delete=models.CASCADE, related_name="participations", verbose_name="الموجة"
    )
    status = models.CharField(
        max_length=8, choices=STATUSES, default=PENDING, verbose_name="الحالة"
    )
    snooze_until = models.DateField(null=True, blank=True, verbose_name="يعود بعد")

    class Meta:
        verbose_name = "مشاركة في استبانة"
        verbose_name_plural = "المشاركات في الاستبانة"
        constraints = [
            models.UniqueConstraint(fields=["user", "wave"], name="uniq_survey_user_wave")
        ]

    def __str__(self) -> str:
        return f"{self.user_id} — {self.wave_id} — {self.status}"
