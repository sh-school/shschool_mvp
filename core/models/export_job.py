"""
core/models/export_job.py
━━━━━━━━━━━━━━━━━━━━━━━━━
صفُّ تصديرٍ خلفيّ — توليدُ PDF/Excel الثقيل خارج دورة الطلب (P4-6).

كان توليدُ الجدول PDF/Excel يتمّ متزامناً داخل الطلب (WeasyPrint بطيءٌ بما
يكفي ليُذكر صراحةً في `operations/schedule_paper.py`)، مخالفاً معيار
المشروع (>300ms → Background Job). فصار الطلبُ يُنشئ هذا الصفّ ويُرجع فوراً،
والعاملُ يملأه، وصفحةُ متابعةٍ تُنزّل الناتج حين يجهز.

المحتوى يُحذف دورياً (`operations.purge_expired_export_jobs`) بعد ٢٤ ساعة —
لا يتراكم في القاعدة كالملفات الدائمة في `StoredFile`.
"""

from django.conf import settings
from django.db import models

from .base import SchoolScopedModel


class ExportJob(SchoolScopedModel):
    STATUS = [
        ("pending", "قيد الانتظار"),
        ("running", "جارٍ التحضير"),
        ("done", "جاهز"),
        ("failed", "فشل"),
    ]

    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="export_jobs",
        verbose_name="طلبه",
    )
    #: معرِّفٌ ثابتٌ لنوع التصدير — يطابق قِيَم `log_export(kind=...)`.
    kind = models.CharField(max_length=50, db_index=True, verbose_name="النوع")
    #: مدخلاتُ الطلب الأصليّة (query string) — يُعاد بناء نفس السياق منها في العامل.
    query_string = models.TextField(blank=True, verbose_name="معاملات الطلب")
    status = models.CharField(
        max_length=10, choices=STATUS, default="pending", db_index=True, verbose_name="الحالة"
    )
    content = models.BinaryField(null=True, blank=True, verbose_name="المحتوى")
    content_type = models.CharField(max_length=100, blank=True, verbose_name="نوع المحتوى")
    filename = models.CharField(max_length=255, blank=True, verbose_name="اسم الملف")
    error_message = models.CharField(max_length=2000, blank=True, verbose_name="رسالة الخطأ")
    finished_at = models.DateTimeField(null=True, blank=True, verbose_name="وقت الانتهاء")

    class Meta(SchoolScopedModel.Meta):
        verbose_name = "صفّ تصدير"
        verbose_name_plural = "صفوف التصدير"
        indexes = [
            models.Index(fields=["school", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]

    def __str__(self):
        return f"{self.kind} — {self.get_status_display()} ({self.id})"
