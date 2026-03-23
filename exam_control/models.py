"""
exam_control/models.py  ·  SchoolOS v5
وحدة كنترول الاختبارات — مبنية على دليل SOP من Ct.zip (10 محاور)
"""

from django.conf import settings

import uuid

from django.db import models


def _uuid():
    return uuid.uuid4()


class ExamSession(models.Model):
    """دورة اختبار (نصف سنة / نهاية سنة / مُكمِّل)"""

    SESSION_TYPES = [("mid", "منتصف الفصل"), ("final", "نهاية الفصل"), ("makeup", "الدور الثاني")]
    STATUS = [("planned", "مُخطَّطة"), ("active", "جارية"), ("completed", "منتهية")]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    school = models.ForeignKey(
        "core.School", on_delete=models.CASCADE, related_name="exam_sessions"
    )
    name = models.CharField(max_length=200, verbose_name="اسم دورة الاختبار")
    session_type = models.CharField(max_length=10, choices=SESSION_TYPES, default="final")
    academic_year = models.CharField(max_length=20, default=settings.CURRENT_ACADEMIC_YEAR)
    start_date = models.DateField()
    end_date = models.DateField()
    status = models.CharField(max_length=15, choices=STATUS, default="planned")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(
        "core.CustomUser",
        null=True,
        on_delete=models.SET_NULL,
        related_name="created_exam_sessions",
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
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="rooms")
    name = models.CharField(max_length=100, verbose_name="اسم القاعة / الرقم")
    capacity = models.PositiveSmallIntegerField(default=30)
    floor = models.CharField(max_length=20, blank=True)
    notes = models.TextField(blank=True)

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
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="supervisors")
    room = models.ForeignKey(
        ExamRoom, null=True, blank=True, on_delete=models.SET_NULL, related_name="supervisors"
    )
    staff = models.ForeignKey(
        "core.CustomUser", on_delete=models.CASCADE, related_name="exam_roles"
    )
    role = models.CharField(max_length=15, choices=ROLES, default="supervisor")
    assigned_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "مشرف كنترول"
        verbose_name_plural = "مشرفو الكنترول"
        unique_together = [("session", "staff")]

    def __str__(self):
        return f"{self.staff.full_name} — {self.get_role_display()}"


class ExamSchedule(models.Model):
    """جدول الاختبارات اليومي — توزيع المواد على القاعات"""

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="schedules")
    room = models.ForeignKey(ExamRoom, on_delete=models.CASCADE, related_name="schedules")
    subject = models.CharField(max_length=100)
    grade_level = models.CharField(max_length=20)
    exam_date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    students_count = models.PositiveSmallIntegerField(default=0)

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
    session = models.ForeignKey(ExamSession, on_delete=models.CASCADE, related_name="incidents")
    room = models.ForeignKey(
        ExamRoom, null=True, blank=True, on_delete=models.SET_NULL, related_name="incidents"
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
    )
    incident_type = models.CharField(max_length=15, choices=TYPES, default="other")
    severity = models.PositiveSmallIntegerField(choices=SEVERITY, default=1)
    description = models.TextField(verbose_name="وصف الحادث التفصيلي")  # القسم ب
    injuries = models.TextField(blank=True, verbose_name="الإصابات والأضرار")  # القسم ج
    action_taken = models.TextField(blank=True, verbose_name="الإجراء الفوري")  # القسم د
    attachments = models.TextField(blank=True, verbose_name="المرفقات/الشهود")  # القسم هـ
    recommendations = models.TextField(blank=True, verbose_name="التوصيات")  # القسم و
    status = models.CharField(max_length=10, choices=STATUS, default="open")
    incident_time = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)
    # ربط بسلوك الطالب إن اقتضى
    behavior_link = models.ForeignKey(
        "behavior.BehaviorInfraction",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exam_incidents",
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
    schedule = models.ForeignKey(ExamSchedule, on_delete=models.CASCADE, related_name="envelopes")
    action = models.CharField(max_length=15, choices=ACTIONS)
    done_by = models.ForeignKey("core.CustomUser", null=True, on_delete=models.SET_NULL)
    witness = models.ForeignKey(
        "core.CustomUser",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="witnessed_envelopes",
    )
    copies = models.PositiveSmallIntegerField(default=0, verbose_name="عدد النسخ")
    notes = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "محضر مظروف"
        verbose_name_plural = "محاضر المظاريف"
        ordering = ["timestamp"]


class ExamGradeSheet(models.Model):
    """ورقة الرصد والتصحيح — المحور 6–8–9"""

    STATUS = [("pending", "في انتظار الرصد"), ("graded", "مُصحَّحة"), ("submitted", "مُسلَّمة")]

    id = models.UUIDField(primary_key=True, default=_uuid, editable=False)
    schedule = models.ForeignKey(
        ExamSchedule, on_delete=models.CASCADE, related_name="grade_sheets"
    )
    grader = models.ForeignKey(
        "core.CustomUser", null=True, on_delete=models.SET_NULL, related_name="grade_sheets"
    )
    papers_count = models.PositiveSmallIntegerField(default=0, verbose_name="عدد الأوراق المستلمة")
    status = models.CharField(max_length=12, choices=STATUS, default="pending")
    submitted_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "ورقة رصد"
        verbose_name_plural = "أوراق الرصد"

    def __str__(self):
        return f"رصد: {self.schedule} — {self.get_status_display()}"
