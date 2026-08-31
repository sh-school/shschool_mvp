"""
مركز معلومات الطلبة — نموذج الملاحظة على الطالب.

لم يكن في المنصّة قبل اليوم نموذجٌ لملاحظةٍ تُكتب على طالب: السلوكُ مخالفةٌ
لها إجراء، والزيارةُ الصفّيّة على المعلّم لا الطالب، وملاحظةُ الدرجة سطرٌ
داخل التقييم. وهذا النموذجُ يسدّ ذلك الفراغ لخمس جهاتٍ تكتب عن الطالب:
معلّموه، والأخصائيّ الاجتماعيّ، والأخصائيّ النفسيّ، والممرّض، ومنسّق شؤون
الطلاب.

والنصُّ مشفَّرٌ عند السكون بـ`EncryptedTextField` — لا بمساعِدَي `get_`/`set_`
اليدويَّين: ملاحظةُ الأخصائيّ النفسيّ عن قاصرٍ أشدُّ حساسيّةً ممّا يُترك
لانضباط من يكتب الكود بعدنا.
"""

from django.db import models

from core.academic_calendar import default_academic_year
from core.fields import EncryptedTextField
from core.models import CustomUser, School
from core.models.base import AuditedModel

#: جهاتُ الكتابة الخمس. القيمةُ مفتاحٌ ثابتٌ في العناوين والصلاحيات معاً،
#: فلا تُغيَّر بعد النشر إلّا بهجرة.
NOTE_CATEGORIES = [
    ("teacher", "ملاحظات المعلمين"),
    ("social_worker", "ملاحظات الأخصائي الاجتماعي"),
    ("psychologist", "ملاحظات الأخصائي النفسي"),
    ("nurse", "ملاحظات الممرض"),
    ("student_affairs", "ملاحظات منسق شؤون الطلاب"),
]

#: ما يُسجَّل الوصولُ إليه في سجلّ التدقيق: ملاحظاتُ الأخصائيَّين وحدهما.
#: (PDPPL م.19 — بيانةٌ ذاتُ طبيعةٍ خاصّةٍ عن قاصر.)
SENSITIVE_CATEGORIES = ("social_worker", "psychologist")


class StudentNote(AuditedModel):
    """ملاحظةٌ مكتوبةٌ على طالبٍ من إحدى الجهات الخمس."""

    school = models.ForeignKey(
        School,
        on_delete=models.CASCADE,
        related_name="student_notes",
        verbose_name="المدرسة",
    )
    student = models.ForeignKey(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="info_notes",
        verbose_name="الطالب",
    )
    category = models.CharField(
        max_length=20,
        choices=NOTE_CATEGORIES,
        db_index=True,
        verbose_name="الجهة",
    )
    title = models.CharField(max_length=160, verbose_name="العنوان")
    body = EncryptedTextField(verbose_name="نصّ الملاحظة")
    occurred_on = models.DateField(verbose_name="التاريخ")
    academic_year = models.CharField(max_length=9, default=default_academic_year)

    class Meta(AuditedModel.Meta):
        verbose_name = "ملاحظة على طالب"
        verbose_name_plural = "الملاحظات على الطلاب"
        ordering = ["-occurred_on", "-created_at"]
        indexes = [
            models.Index(fields=["school", "student", "academic_year"]),
            models.Index(fields=["school", "category", "academic_year"]),
        ]

    def __str__(self):
        return f"{self.get_category_display()} — {self.student.full_name} — {self.occurred_on}"

    @property
    def is_sensitive(self):
        return self.category in SENSITIVE_CATEGORIES
