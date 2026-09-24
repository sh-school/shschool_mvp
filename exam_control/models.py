"""
exam_control/models.py  ·  SchoolOS v5
وحدة كنترول الاختبارات — مبنية على دليل SOP من Ct.zip (10 محاور)
"""

import uuid

from django.db import models

from core.academic_calendar import default_academic_year


def _uuid():
    return uuid.uuid4()


class ExamSession(models.Model):
    """دورة اختبار (نصف سنة / نهاية سنة / مُكمِّل)"""

    SESSION_TYPES = [("mid", "منتصف الفصل"), ("final", "نهاية الفصل"), ("makeup", "الدور الثاني")]
    STATUS = [("planned", "مُخطَّطة"), ("active", "جارية"), ("completed", "منتهية")]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        "core.School",
        on_delete=models.CASCADE,
        related_name="exam_sessions",
        verbose_name="المدرسة",
    )
    name = models.CharField(max_length=200, verbose_name="اسم دورة الاختبار")
    session_type = models.CharField(
        max_length=10, choices=SESSION_TYPES, default="final", verbose_name="نوع الدورة"
    )
    academic_year = models.CharField(
        max_length=20, default=default_academic_year, verbose_name="العام الدراسي"
    )
    start_date = models.DateField(verbose_name="تاريخ البداية")
    end_date = models.DateField(verbose_name="تاريخ النهاية")
    status = models.CharField(
        max_length=15, choices=STATUS, default="planned", verbose_name="الحالة"
    )
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء")
    created_by = models.ForeignKey(
        "core.CustomUser",
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_exam_sessions",
        verbose_name="أنشأه",
    )

    class Meta:
        verbose_name = "دورة اختبار"
        verbose_name_plural = "دورات الاختبارات"
        ordering = ["-start_date"]

    def __str__(self):
        return f"{self.name} ({self.academic_year})"


class ExamRoom(models.Model):
    """قاعة الاختبار — المنطقة الآمنة (المحور 2)"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    session = models.ForeignKey(
        ExamSession, on_delete=models.CASCADE, related_name="rooms", verbose_name="دورة الاختبارات"
    )
    name = models.CharField(max_length=100, verbose_name="اسم القاعة / الرقم")
    capacity = models.PositiveSmallIntegerField(default=30, verbose_name="السعة")
    floor = models.CharField(max_length=20, blank=True, verbose_name="الطابق")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "قاعة اختبار"
        verbose_name_plural = "قاعات الاختبار"
        ordering = ["name"]

    def __str__(self):
        return f"قاعة {self.name} — {self.session.name}"


class ExamSupervisor(models.Model):
    """تشكيل الكنترول — المحور 1"""

    ROLES = [
        ("head", "رئيس الكنترول"),
        ("deputy", "نائب الرئيس"),
        ("secretary", "أمين السر"),
        ("print", "مسؤول الطباعة"),
        ("safe", "مسؤول الخزائن"),
        ("delivery", "مسؤول التسليم"),
        ("grading", "مسؤول الرصد"),
        ("audit", "مسؤول التدقيق"),
        ("supervisor", "مشرف قاعة"),
        ("observer", "مراقب"),
    ]
    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name="supervisors",
        verbose_name="دورة الاختبارات",
    )
    room = models.ForeignKey(
        ExamRoom,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="supervisors",
        verbose_name="اللجنة",
    )
    staff = models.ForeignKey(
        "core.CustomUser",
        on_delete=models.CASCADE,
        related_name="exam_roles",
        verbose_name="الموظّف",
    )
    role = models.CharField(
        max_length=15, choices=ROLES, default="supervisor", verbose_name="المهمّة"
    )
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name="تاريخ التكليف")

    class Meta:
        verbose_name = "مشرف كنترول"
        verbose_name_plural = "مشرفو الكنترول"
        constraints = [
            models.UniqueConstraint(
                fields=["session", "staff"],
                name="unique_exam_supervisor",
            ),
        ]

    def __str__(self):
        return f"{self.staff.full_name} — {self.get_role_display()}"


class ExamSchedule(models.Model):
    """جدول الاختبارات اليومي — توزيع المواد على القاعات"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name="schedules",
        verbose_name="دورة الاختبارات",
    )
    room = models.ForeignKey(
        ExamRoom, on_delete=models.CASCADE, related_name="schedules", verbose_name="اللجنة"
    )
    subject = models.CharField(max_length=100, verbose_name="المادّة")
    grade_level = models.CharField(max_length=20, verbose_name="الصف")
    exam_date = models.DateField(verbose_name="تاريخ الاختبار")
    start_time = models.TimeField(verbose_name="وقت البداية")
    end_time = models.TimeField(verbose_name="وقت النهاية")
    students_count = models.PositiveSmallIntegerField(default=0, verbose_name="عدد الطلبة")

    class Meta:
        verbose_name = "جدول اختبار"
        verbose_name_plural = "جداول الاختبارات"
        ordering = ["exam_date", "start_time"]

    def __str__(self):
        return f"{self.subject} — {self.grade_level} — {self.exam_date}"


class ExamIncident(models.Model):
    """
    حادث أثناء الاختبار — محضر رسمي (المحور 6 + 10 من دليل Ct.zip)
    يرتبط بـ Template_IncidentReport.md الأقسام أ–ز
    """

    TYPES = [
        ("cheating", "غش مؤكد"),
        ("misconduct", "سوء سلوك"),
        ("medical", "حالة طبية"),
        ("technical", "عطل تقني"),
        ("other", "أخرى"),
    ]
    SEVERITY = [(1, "بسيطة"), (2, "متوسطة"), (3, "جسيمة")]
    STATUS = [("open", "مفتوحة"), ("referred", "محالة"), ("resolved", "منتهية")]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    session = models.ForeignKey(
        ExamSession,
        on_delete=models.CASCADE,
        related_name="incidents",
        verbose_name="دورة الاختبارات",
    )
    room = models.ForeignKey(
        ExamRoom,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="incidents",
        verbose_name="اللجنة",
    )
    student = models.ForeignKey(
        "core.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exam_incidents",
        verbose_name="الطالب المعني",
    )
    reported_by = models.ForeignKey(
        "core.CustomUser",
        null=True,
        on_delete=models.SET_NULL,
        related_name="reported_exam_incidents",
        verbose_name="المُبلِّغ",
    )
    incident_type = models.CharField(
        max_length=15, choices=TYPES, default="other", verbose_name="نوع الحادثة"
    )
    severity = models.PositiveSmallIntegerField(choices=SEVERITY, default=1, verbose_name="الخطورة")
    description = models.TextField(verbose_name="وصف الحادث التفصيلي")  # القسم ب
    injuries = models.TextField(blank=True, verbose_name="الإصابات والأضرار")  # القسم ج
    action_taken = models.TextField(blank=True, verbose_name="الإجراء الفوري")  # القسم د
    attachments = models.TextField(blank=True, verbose_name="المرفقات/الشهود")  # القسم هـ
    recommendations = models.TextField(blank=True, verbose_name="التوصيات")  # القسم و
    status = models.CharField(max_length=10, choices=STATUS, default="open", verbose_name="الحالة")
    incident_time = models.DateTimeField(auto_now_add=True, verbose_name="وقت الحادثة")
    resolved_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت المعالجة")
    # ربط بسلوك الطالب إن اقتضى
    behavior_link = models.ForeignKey(
        "behavior.BehaviorInfraction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exam_incidents",
        verbose_name="المخالفة السلوكيّة المرتبطة",
    )

    class Meta:
        verbose_name = "حادث اختبار"
        verbose_name_plural = "حوادث الاختبارات"
        ordering = ["-incident_time"]

    def __str__(self):
        return f"{self.get_incident_type_display()} — {self.session.name}"


class ExamEnvelope(models.Model):
    """
    محضر فتح/إغلاق المظاريف — المحور 3 (استلام الأسئلة)
    المحور 4 (توزيع المظاريف على اللجان)
    """

    ACTIONS = [
        ("received", "استُلمت"),
        ("opened", "فُتحت"),
        ("distributed", "وُزِّعت"),
        ("returned", "أُعيدت"),
    ]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    schedule = models.ForeignKey(
        ExamSchedule,
        on_delete=models.CASCADE,
        related_name="envelopes",
        verbose_name="موعد الاختبار",
    )
    action = models.CharField(max_length=15, choices=ACTIONS, verbose_name="الإجراء على المظروف")
    done_by = models.ForeignKey(
        "core.CustomUser", null=True, on_delete=models.SET_NULL, verbose_name="المنفِّذ"
    )
    witness = models.ForeignKey(
        "core.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="witnessed_envelopes",
        verbose_name="الشاهد",
    )
    copies = models.PositiveSmallIntegerField(default=0, verbose_name="عدد النسخ")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")
    timestamp = models.DateTimeField(auto_now_add=True, verbose_name="الوقت")

    class Meta:
        verbose_name = "محضر مظروف"
        verbose_name_plural = "محاضر المظاريف"
        ordering = ["timestamp"]


class ExamGradeSheet(models.Model):
    """ورقة الرصد والتصحيح — المحور 6–8–9"""

    STATUS = [("pending", "في انتظار الرصد"), ("graded", "مُصحَّحة"), ("submitted", "مُسلَّمة")]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    schedule = models.ForeignKey(
        ExamSchedule,
        on_delete=models.CASCADE,
        related_name="grade_sheets",
        verbose_name="موعد الاختبار",
    )
    grader = models.ForeignKey(
        "core.CustomUser",
        null=True,
        on_delete=models.SET_NULL,
        related_name="grade_sheets",
        verbose_name="المصحّح",
    )
    papers_count = models.PositiveSmallIntegerField(default=0, verbose_name="عدد الأوراق المستلمة")
    status = models.CharField(
        max_length=12, choices=STATUS, default="pending", verbose_name="الحالة"
    )
    submitted_at = models.DateTimeField(null=True, blank=True, verbose_name="تاريخ الإرسال")
    notes = models.TextField(blank=True, verbose_name="ملاحظات")

    class Meta:
        verbose_name = "ورقة رصد"
        verbose_name_plural = "أوراق الرصد"

    def __str__(self):
        return f"رصد: {self.schedule} — {self.get_status_display()}"
