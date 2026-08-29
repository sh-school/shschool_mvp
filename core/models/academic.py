from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.academic_calendar import default_academic_year

from .school import School, _uuid
from .user import CustomUser


class AcademicYear(models.Model):
    """
    العام الدراسي — يُستخدم لتحديد السنة الأكاديمية النشطة لكل مدرسة.

    UniqueConstraint يمنع وجود أكثر من عام دراسي حالي لنفس المدرسة.
    """

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="academic_years",
        verbose_name="المدرسة",
    )
    name = models.CharField(
        max_length=9,
        verbose_name="العام الدراسي",
        help_text="مثال: 2025-2026",
    )
    start_date = models.DateField(verbose_name="تاريخ البداية")
    end_date = models.DateField(verbose_name="تاريخ النهاية")
    is_current = models.BooleanField(default=False, verbose_name="العام الحالي")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")

    class Meta:
        verbose_name = "عام دراسي"
        verbose_name_plural = "الأعوام الدراسية"
        ordering = ["-start_date"]
        constraints = [
            models.UniqueConstraint(
                fields=["school", "name"],
                name="unique_academic_year_per_school",
            ),
            models.UniqueConstraint(
                fields=["school"],
                condition=models.Q(is_current=True),
                name="unique_current_academic_year_per_school",
            ),
        ]

    def __str__(self):
        current = " ✓" if self.is_current else ""
        return f"{self.name}{current} — {self.school.name}"


class ClassGroup(models.Model):
    GRADES = [
        ("G7", "الصف السابع"),
        ("G8", "الصف الثامن"),
        ("G9", "الصف التاسع"),
        ("G10", "الصف العاشر"),
        ("G11", "الصف الحادي عشر"),
        ("G12", "الصف الثاني عشر"),
    ]
    LEVELS = [("prep", "إعدادي"), ("sec", "ثانوي")]

    #: مسارات المرحلة الثانوية في مدارس قطر. يختارها الطالب بعد نجاحه في
    #: العاشر، فتبدأ من الحادي عشر — والصفوف دونها بلا مسار.
    TRACKS = [
        ("science", "علمي"),
        ("humanities", "آداب وإنسانيات"),
        ("technology", "تكنولوجي"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="class_groups")
    grade = models.CharField(max_length=3, choices=GRADES)
    section = models.CharField(max_length=10, verbose_name="الشعبة")
    level_type = models.CharField(max_length=4, choices=LEVELS, default="prep")
    #: فارغٌ في الإعدادي وفي العاشر — والشعبة الثانوية بلا مسار حالةٌ مشروعة
    #: حتى تُحدَّد. ولا يُقيَّد بالصف في قاعدة البيانات: القيد في
    #: كي يُخبر المُدخِل بالخطأ بدل أن يرفضه المحرّك بلا بيان.
    track = models.CharField(max_length=12, choices=TRACKS, blank=True, verbose_name="المسار")
    academic_year = models.CharField(max_length=9, default=default_academic_year)
    supervisor = models.ForeignKey(
        CustomUser,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="supervised_classes",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        # «الفصل الدراسي» مصطلحُ الوزارة للمدّة الزمنية (الأول/الثاني)، وهو
        # اسم `Semester`. وهذا النموذج يحمل `grade` و`section` معاً — أي
        # الشعبة داخل الصف — فكانت التسميتان متطابقتين في لوحة الإدارة
        # وتقودان إلى شيئين لا صلة بينهما.
        verbose_name = "شعبة دراسية"
        verbose_name_plural = "الشُّعب الدراسية"
        constraints = [
            models.UniqueConstraint(
                fields=["school", "grade", "section", "academic_year"],
                name="unique_class_per_year",
            )
        ]
        indexes = [models.Index(fields=["school", "grade", "academic_year"])]

    def clean(self):
        """المسار للثانوي وحده — ومن أخطأ يُخبَر لا يُرفض بلا بيان."""
        super().clean()
        if self.track and self.level_type != "sec":
            raise ValidationError({"track": "المسار للمرحلة الثانوية وحدها."})

    def __str__(self):
        track = f" — {self.get_track_display()}" if self.track else ""
        return f"{self.get_grade_display()} / {self.section}{track} ({self.academic_year})"


class StudentEnrollment(models.Model):
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    student = models.ForeignKey(CustomUser, on_delete=models.CASCADE, related_name="enrollments")
    class_group = models.ForeignKey(
        ClassGroup, on_delete=models.CASCADE, related_name="enrollments"
    )
    is_active = models.BooleanField(default=True)
    enrolled_at = models.DateField(default=timezone.now)

    class Meta:
        verbose_name = "تسجيل طالب"
        constraints = [
            models.UniqueConstraint(
                fields=["student", "class_group"],
                condition=models.Q(is_active=True),
                name="unique_active_enrollment",
            )
        ]
        indexes = [
            models.Index(fields=["class_group", "is_active"], name="idx_enrollment_class_active"),
            models.Index(fields=["student", "is_active"], name="idx_enrollment_student_active"),
        ]

    def __str__(self):
        return f"{self.student.full_name} → {self.class_group}"


class ParentStudentLink(models.Model):
    RELATIONSHIP = [
        ("father", "الأب"),
        ("mother", "الأم"),
        ("guardian", "الوصي"),
        ("other", "أخرى"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(School, on_delete=models.CASCADE, related_name="parent_links")
    parent = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="children_links",
        verbose_name="ولي الأمر",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="parent_links",
        verbose_name="الطالب",
    )
    relationship = models.CharField(
        max_length=20, choices=RELATIONSHIP, default="father", verbose_name="صلة القرابة"
    )
    is_primary = models.BooleanField(default=True, verbose_name="ولي الأمر الأساسي")
    can_view_grades = models.BooleanField(default=True, verbose_name="يرى الدرجات")
    can_view_attendance = models.BooleanField(default=True, verbose_name="يرى الغياب")
    can_view_behavior = models.BooleanField(default=True, verbose_name="يرى السلوك")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "ربط ولي أمر"
        verbose_name_plural = "ربط أولياء الأمور"
        ordering = ["student__full_name"]
        constraints = [
            models.UniqueConstraint(
                fields=["parent", "student", "school"],
                name="unique_parent_student_school",
            )
        ]

    def __str__(self):
        return (
            f"{self.parent.full_name} ← {self.student.full_name} "
            f"({self.get_relationship_display()})"
        )


class Semester(models.Model):
    """الفصل الدراسي — حدودُه تواريخُ تقويم الوزارة، لا رايةٌ يُبدّلها أحد.

    «الفصل الحالي» يُشتقّ من التاريخ (`AcademicCalendar.current`)، فلا يوجد
    `is_current` هنا عمداً: رايةٌ كهذه تُنسى، فتُسجَّل درجاتٌ في الفصل الخطأ
    ولا شيء يكشف ذلك.

    والفصلان متلاصقان بلا فجوة — إجازة منتصف العام تُلحق بالفصل المنتهي —
    كي لا يأتي يومٌ بلا فصلٍ فتضطرّ كل شاشة إلى اختراع سلوكٍ لتلك الحالة.
    """

    CODES = [
        ("S1", "الفصل الدراسي الأول"),
        ("S2", "الفصل الدراسي الثاني"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="semesters",
        verbose_name="العام الدراسي",
    )
    code = models.CharField(max_length=2, choices=CODES, verbose_name="الفصل")
    start_date = models.DateField(verbose_name="تاريخ البداية")
    end_date = models.DateField(verbose_name="تاريخ النهاية")
    max_grade = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        verbose_name="الدرجة القصوى",
        help_text="٤٠ للفصل الأول و٦٠ للثاني — وزن الفصل بياناتٌ لا ثابتٌ في الشيفرة",
    )

    class Meta:
        verbose_name = "فصل دراسي"
        verbose_name_plural = "الفصول الدراسية"
        ordering = ["academic_year", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["academic_year", "code"],
                name="unique_semester_code_per_year",
            ),
            models.CheckConstraint(
                condition=models.Q(end_date__gt=models.F("start_date")),
                name="semester_ends_after_it_starts",
            ),
        ]

    def __str__(self):
        return f"{self.get_code_display()} — {self.academic_year.name}"

    def covers(self, day):
        return self.start_date <= day <= self.end_date


class CalendarEvent(models.Model):
    """حدثٌ في تقويم الوزارة — اختبارٌ أو إجازةٌ أو بدء دوام.

    ثلاثة حقول تفصله عن «تاريخٍ ونصّ»، وكلٌّ منها فرضه التقويم نفسه:

      `grade_scope`   نوافذ الاختبارات تختلف: الصفوف ١–٩ · ١٠–١١ · ١٢
      `audience`      الموظفون يبدأون قبل الطلبة بأسبوع
      `academic_year` اختبارات الدور الثاني لعامٍ تقع في تقويم العام التالي،
                      فالحدث ينتمي إلى عامٍ قد لا يكون عام تاريخه
    """

    TYPES = [
        ("staff_start", "بدء دوام الموظفين"),
        ("students_start", "بدء دوام الطلبة"),
        ("midterm_exam", "اختبارات منتصف الفصل"),
        ("final_exam", "اختبارات نهاية الفصل"),
        ("makeup_exam", "ملحق الاختبارات"),
        ("second_round", "اختبارات الدور الثاني"),
        ("break", "إجازة"),
        ("resume", "استئناف الدوام"),
    ]

    GRADE_SCOPES = [
        ("all", "جميع الصفوف"),
        ("g1_9", "الصفوف ١–٩"),
        ("g10_11", "الصفّان ١٠–١١"),
        ("g12", "الصف ١٢"),
    ]

    AUDIENCES = [
        ("both", "الجميع"),
        ("staff", "الموظفون"),
        ("students", "الطلبة"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    academic_year = models.ForeignKey(
        AcademicYear,
        on_delete=models.CASCADE,
        related_name="calendar_events",
        verbose_name="العام الدراسي",
    )
    semester = models.ForeignKey(
        Semester,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="calendar_events",
        verbose_name="الفصل",
    )
    event_type = models.CharField(max_length=20, choices=TYPES, verbose_name="النوع")
    name = models.CharField(max_length=200, verbose_name="البيان")
    start_date = models.DateField(verbose_name="من")
    end_date = models.DateField(verbose_name="إلى")
    grade_scope = models.CharField(
        max_length=10, choices=GRADE_SCOPES, default="all", verbose_name="نطاق الصفوف"
    )
    audience = models.CharField(
        max_length=10, choices=AUDIENCES, default="both", verbose_name="الجمهور"
    )

    class Meta:
        verbose_name = "حدث تقويم"
        verbose_name_plural = "أحداث التقويم"
        ordering = ["start_date", "event_type"]
        indexes = [models.Index(fields=["academic_year", "start_date"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(end_date__gte=models.F("start_date")),
                name="calendar_event_ends_after_it_starts",
            ),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_date} → {self.end_date})"
