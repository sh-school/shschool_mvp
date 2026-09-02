from django.db import models
from django.utils import timezone

from .school import School, _uuid
from .user import CustomUser

# Lazy import to avoid circular dependency — Department imports CustomUser
# Department FK is referenced as string "department.Department" below


# ══════════════════════════════════════════════════════════════════════
# Role — الأدوار الوظيفية حسب الهيكل التنظيمي الرسمي
# المرجع: قرار مجلس الوزراء 32/2019 + نظام الرخص المهنية (قطر)
# ══════════════════════════════════════════════════════════════════════

# ── تصنيف المستويات الإدارية (Tiers) ────────────────────────────────
# المرجع: قرار مجلس الوزراء 32/2019 + تعديل 23/2025 + إعلانات وزارة التعليم 2022-2026
TIER_1_LEADERSHIP = {"principal"}
TIER_2_DEPUTIES = {"vice_admin", "vice_academic"}
TIER_3_SUPERVISORS = {"coordinator", "admin_supervisor", "activities_coordinator"}
TIER_4_STAFF = {
    # الكادر التدريسي
    "teacher",
    "ese_teacher",
    "teacher_assistant",
    "ese_assistant",
    # الدعم الأكاديمي والطلابي
    "social_worker",
    "psychologist",
    "academic_advisor",
    "speech_therapist",
    "occupational_therapist",
    # الخدمات المساندة
    "nurse",
    "librarian",
    "it_technician",
    "bus_supervisor",
    "transport_officer",
    # الإداريون
    "admin",
    "secretary",
    "receptionist",
}
TIER_5_BENEFICIARIES = {"student", "parent"}
TIER_SYSTEM = {"platform_developer"}

# أدوار لها صلاحية إدارية شاملة
ADMIN_ROLES = TIER_1_LEADERSHIP | TIER_2_DEPUTIES
# القيادة (T1 + T2)
LEADERSHIP = TIER_1_LEADERSHIP | TIER_2_DEPUTIES
# أدوار الطاقم الأكاديمي
ACADEMIC_ROLES = {
    "principal",
    "vice_academic",
    "coordinator",
    "teacher",
    "ese_teacher",
    "teacher_assistant",
    "ese_assistant",
    "activities_coordinator",
}
# مَن يحمل نصاباً في توزيعات المواد على الشُّعب.
#
# المنسّقُ يدرّس بنصابٍ مخفَّض — اثنا عشرَ منسّقاً حملوا ستّين حصّةً في
# 2026-2027 بعضويّة `coordinator` وحدها، فأخفتهم قائمةٌ تقبل `teacher`
# حرفيّاً وعرضت صفوفَهم «بلا معلّم». والحدُّ هنا قرارٌ (2026-09-02):
# معلّمٌ ومنسّق، لا معلّمُ التربية الخاصّة ولا منسّقُ الأنشطة.
TEACHING_ROLES = {"teacher", "coordinator"}
# مَن يجوز تفريغُه من الجدول — كادرُ الجدولة وحدَه.
#
# وكانت الشاشةُ تعرض هذه الأدوارَ بينما `TeacherExemptionForm.clean_teacher`
# يقبل أيَّ منسوبٍ في المدرسة: طالباً أو وليَّ أمرٍ أو موظّفاً غيرَ مُجدول،
# لمن بدّل الحقلَ في الطلب. فالقائمةُ المعروضةُ والحدُّ المفروضُ من مصدرٍ
# واحدٍ الآن، فلا يفترقان بمرور الوقت.
EXEMPTABLE_ROLES = {"teacher", "coordinator", "ese_teacher", "activities_coordinator"}
# أدوار الطاقم بالكامل (بدون طلاب وأولياء أمور)
#
# ومعها `TIER_SYSTEM`: كان `platform_developer` خارجها، فيُردّ عن لوحة
# التحكّم نفسها برسالة «ليس لديك صلاحية الوصول — دورك: platform_developer».
# ولم يظهر ذلك لأنّ حساب المطوّر `superuser` و`role_required` يُمرّره —
# فالدور معطَّلٌ في ذاته، ويعمل بصفةٍ أخرى.
ALL_STAFF_ROLES = (
    TIER_1_LEADERSHIP | TIER_2_DEPUTIES | TIER_3_SUPERVISORS | TIER_4_STAFF | TIER_SYSTEM
)


class Role(models.Model):
    ROLES = [
        # T1 — القيادة العليا
        ("principal", "مدير المدرسة"),
        # T2 — نواب المدير
        ("vice_admin", "النائب الإداري"),
        ("vice_academic", "النائب الأكاديمي"),
        # T3 — المنسقون والإشراف
        ("coordinator", "منسق أكاديمي"),
        ("admin_supervisor", "مشرف إداري"),
        ("activities_coordinator", "منسق الأنشطة المدرسية"),  # قرار 32/2019 — جديد v7
        # T4 — الكادر التدريسي
        ("teacher", "معلم"),
        ("ese_teacher", "معلم تربية خاصة"),
        ("teacher_assistant", "مساعد المعلم"),  # نص صريح قرار 32/2019 — جديد v7
        ("ese_assistant", "مساعد معلم تربية خاصة"),  # نص صريح قرار 32/2019 — جديد v7
        # T4 — الدعم الأكاديمي والطلابي
        ("social_worker", "أخصائي اجتماعي"),
        ("psychologist", "أخصائي نفسي"),
        ("academic_advisor", "مرشد أكاديمي"),
        ("speech_therapist", "أخصائي النطق"),  # إعلان رسمي وزارة التعليم — جديد v7
        ("occupational_therapist", "أخصائي العلاج الوظائفي"),  # إعلان رسمي وزارة التعليم — جديد v7
        # T4 — الخدمات المساندة
        ("nurse", "ممرض"),
        ("librarian", "أمين مصادر التعلم"),
        ("it_technician", "فني تقنية معلومات"),
        ("bus_supervisor", "مشرف نقل مدرسي"),
        ("transport_officer", "مسؤول النقل"),  # إدارة النقل — مختلف عن مشرف الحافلة — جديد v7
        # T4 — الإداريون
        ("admin", "إداري"),
        ("secretary", "سكرتير المدرسة"),
        ("receptionist", "موظف استقبال"),  # جديد v7
        # T4-legacy — التوافق الخلفي
        ("specialist", "أخصائي (قديم)"),
        # T5 — المستفيدون
        ("student", "طالب"),
        ("parent", "ولي أمر"),
        # System
        ("platform_developer", "مطور المنصة"),
    ]
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="roles")
    name = models.CharField(max_length=30, choices=ROLES)

    class Meta:
        verbose_name = "دور"
        verbose_name_plural = "الأدوار"
        constraints = [
            models.UniqueConstraint(fields=["school", "name"], name="unique_role_per_school")
        ]

    def __str__(self):
        return f"{self.get_name_display()} — {self.school.code}"

    @property
    def tier(self):
        """يُعيد رقم المستوى الإداري (1-5) أو 0 للنظام."""
        name = self.name
        if name in TIER_1_LEADERSHIP:
            return 1
        if name in TIER_2_DEPUTIES:
            return 2
        if name in TIER_3_SUPERVISORS:
            return 3
        if name in TIER_4_STAFF or name == "specialist":
            return 4
        if name in TIER_5_BENEFICIARIES:
            return 5
        return 0  # platform_developer أو غير معروف

    @property
    def is_staff_role(self):
        """أي موظف في المدرسة (ليس طالباً أو ولي أمر)."""
        return self.name in ALL_STAFF_ROLES or self.name == "specialist"


# ══════════════════════════════════════════════════════════════════════
# Membership — عضوية المستخدم في المدرسة مع الدور والقسم
# ══════════════════════════════════════════════════════════════════════


def _as_date(value):
    """يقبل `date` و`datetime` معاً — فالافتراضُ القديم كان يُخزّن لحظة."""
    return value.date() if hasattr(value, "date") else value


#: أسبابُ مغادرة الكادر — والنقلُ أشيعُها في المدارس الحكوميّة.
DEPARTURE_REASONS = [
    ("transfer", "نقلٌ إلى مدرسةٍ أخرى"),
    ("end_of_service", "انتهاءُ خدمة"),
    ("resignation", "استقالة"),
    ("retirement", "تقاعد"),
    ("other", "أخرى"),
]


class MembershipQuerySet(models.QuerySet):
    """العضويّةُ مدّةٌ لا حالة — فالسؤالُ عنها يحتاج تاريخاً."""

    def current(self):
        """من هو في الكادر الآن."""
        return self.active_on(timezone.localdate())

    def active_on(self, on):
        """من كان في الكادر في يومٍ بعينه — ولو غادر بعده.

        وهذا ما يجعل تاريخَ العام الماضي مقروءاً: معلّمٌ نُقل هذا الصيفَ له
        خمسٌ وعشرون حصّةً في جدول 2025-2026، ولا يجوز أن تُقطع عن صاحبها.
        """
        return self.filter(joined_at__lte=on).filter(
            models.Q(left_at__isnull=True) | models.Q(left_at__gt=on)
        )

    def departed(self):
        return self.filter(left_at__isnull=False)


class Membership(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    user = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="memberships")
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="memberships")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="memberships")
    is_active = models.BooleanField(default=True)
    #: `timezone.now` تُرجع لحظةً لا يوماً، فيحمل الكائنُ غيرَ المحفوظ
    #: `datetime` في حقلِ `date` — وتنكسر أيُّ مقارنةٍ قبل أوّل حفظ.
    joined_at = models.DateField(default=timezone.localdate)

    # ── المغادرة: تاريخٌ لا محو ───────────────────────────────────
    #
    # كان `joined_at` بلا نظير، فمن نُقل لا يُقال عنه إلّا «غيرُ نشط» — وذلك
    # يمحو السؤالَ لا يجيبه: أكان في كادر العام الماضي؟ نعم. أهو في كادر هذا
    # العام؟ لا. وبوليانٌ واحدٌ لا يحمل الجوابين.
    #
    # و`is_active` يُطفأ مع التاريخ، فتصير مئةُ استعلامٍ قائمةٍ تسأل عن
    # النشطين صحيحةً بلا تعديلِ سطرٍ فيها.
    left_at = models.DateField(null=True, blank=True, verbose_name="تاريخ المغادرة")
    departure_reason = models.CharField(
        max_length=16, choices=DEPARTURE_REASONS, blank=True, verbose_name="سبب المغادرة"
    )
    departure_reference = models.CharField(
        max_length=200, blank=True, verbose_name="مرجع قرار المغادرة"
    )
    departure_note = models.CharField(max_length=200, blank=True, verbose_name="ملاحظة")

    objects = MembershipQuerySet.as_manager()

    # ── القسم/التخصص — FK إلى Department model ──────────────────
    department_obj = models.ForeignKey(
        "core.Department",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="memberships",
        verbose_name="القسم الأكاديمي",
        help_text="القسم من جدول الأقسام — يحل محل حقل department النصي",
    )

    class Meta:
        verbose_name = "عضوية"
        verbose_name_plural = "العضويات"
        indexes = [
            models.Index(fields=["school", "role"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "school", "role"],
                condition=models.Q(is_active=True),
                name="unique_active_membership",
            )
        ]

    def record_departure(self, *, on, reason, reference, note=""):
        """يُسجّل مغادرةَ الكادر — تاريخاً وسبباً ومرجعاً، ثمّ يُطفئ العضويّة.

        والمرجعُ لازمٌ كما لزم في التفريغ وفي خطّة النصاب: نقلُ معلّمٍ قرارٌ
        إداريٌّ، ورقمٌ بلا مرجعٍ لا يُراجَع.
        """
        from django.core.exceptions import ValidationError

        if not (reference or "").strip():
            raise ValidationError({"departure_reference": "مغادرةُ الكادر قرارٌ — ومرجعُه لازم."})
        if on < _as_date(self.joined_at):
            raise ValidationError({"left_at": "المغادرةُ قبل الالتحاق — تاريخٌ لا يستقيم."})

        self.left_at = on
        self.departure_reason = reason
        self.departure_reference = reference
        self.departure_note = note
        self.is_active = False
        self.save(
            update_fields=[
                "left_at",
                "departure_reason",
                "departure_reference",
                "departure_note",
                "is_active",
            ]
        )
        return self

    def was_member_on(self, on) -> bool:
        """أكان في الكادر في هذا اليوم؟ — ويومُ المغادرة أوّلُ أيّام الغياب."""
        if on < _as_date(self.joined_at):
            return False
        return self.left_at is None or on < self.left_at

    @property
    def department_name(self):
        """يُعيد اسم القسم من FK."""
        if self.department_obj_id:
            return self.department_obj.name
        return ""

    def __str__(self):
        dept = f" [{self.department_name}]" if self.department_name else ""
        return f"{self.user.full_name} | {self.role}{dept} | {self.school.code}"
