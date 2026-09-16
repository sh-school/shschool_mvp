"""مراحلُ نموذج 02 بترتيب الورقة، والإخطارُ والإنابةُ والعذرُ ومرفقُ نموذج 03.

``docs/compliance/staff_attendance_spec.md``:

* م-18ب — حالة «منتهٍ» للاستئذان والخروج المبكر إذا بدأت نافذتُه ولم يُعتمد.
* م-19 — ترتيبُ المربّعات: السكرتارية أوّلاً، ثمّ المسؤول المباشر والنائب المسؤول خطوةً
  واحدة (فتسقط مرحلةُ «deputy»، ز-8)، ثمّ مربّع المدير؛ و``notified_at`` للإخطار.
* م-21 — لا مرحلةَ لمنسّق القسم، فيسقط ``line_manager``.
* م-7 — من قبِل العذرَ ومتى، ووسمُ القبول بالإنابة.
* م-25 وم-30 — وسمُ القرار بالإنابة في الإذن والاستثناء.
* م-31 — مرفقُ نموذج 03 ملفٌّ، والوصفُ النصّيُّ اختياريّ.
* م-35 — ``covered_at`` لوسم التغطية بعد المهلة.
"""

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _to_paper_order(apps, schema_editor):
    """المعلَّقُ في مربّع المسؤول يعود إلى أوّل الورقة، و«deputy» تصير خطوةَ المسؤول."""
    PermitRequest = apps.get_model("staff_affairs", "PermitRequest")
    PermitRequest.objects.filter(status="pending", stage__in=("supervisor", "deputy")).update(
        stage="secretary"
    )
    PermitRequest.objects.filter(stage="deputy").update(stage="supervisor")
    PermitRequest.objects.filter(rejected_stage="deputy").update(rejected_stage="supervisor")


def _back(apps, schema_editor):
    PermitRequest = apps.get_model("staff_affairs", "PermitRequest")
    PermitRequest.objects.filter(status="pending", stage="secretary").update(stage="supervisor")


STAGES = [
    ("secretary", "السكرتارية"),
    ("supervisor", "المسؤول المباشر والنائب المسؤول"),
    ("principal", "مدير المدرسة"),
    ("external", "اعتماد خارجي"),
    ("closed", "مغلق"),
]

STATUS = [
    ("pending", "قيد الانتظار"),
    ("approved", "معتمد"),
    ("rejected", "مرفوض"),
    ("cancelled", "ملغى"),
    ("expired", "منتهٍ"),
]


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("staff_affairs", "0007_rls_attendance_exceptions_and_delegations"),
    ]

    operations = [
        migrations.RemoveField(model_name="permitrequest", name="line_manager"),
        migrations.AddField(
            model_name="permitrequest",
            name="notified_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت إخطار الموظف"),
        ),
        migrations.AddField(
            model_name="permitrequest",
            name="decided_on_behalf",
            field=models.BooleanField(default=False, verbose_name="قُرّر بالإنابة"),
        ),
        migrations.AddField(
            model_name="staffattendance",
            name="covered_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت تغطية الغياب"),
        ),
        migrations.AddField(
            model_name="staffattendance",
            name="excuse_accepted_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="accepted_staff_excuses",
                to=settings.AUTH_USER_MODEL,
                verbose_name="قبِل العذر",
            ),
        ),
        migrations.AddField(
            model_name="staffattendance",
            name="excuse_accepted_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="وقت قبول العذر"),
        ),
        migrations.AddField(
            model_name="staffattendance",
            name="excuse_on_behalf",
            field=models.BooleanField(default=False, verbose_name="قُبل العذر بالإنابة"),
        ),
        migrations.AddField(
            model_name="attendanceexception",
            name="evidence_file",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="attendance_exceptions/%Y/%m/",
                verbose_name="المرفق (ما يثبت الحاجة)",
            ),
        ),
        migrations.AddField(
            model_name="attendanceexception",
            name="decided_on_behalf",
            field=models.BooleanField(default=False, verbose_name="قُرّر بالإنابة"),
        ),
        migrations.AlterField(
            model_name="attendanceexception",
            name="evidence",
            field=models.CharField(blank=True, max_length=300, verbose_name="وصف المرفق"),
        ),
        migrations.AlterField(
            model_name="permitrequest",
            name="status",
            field=models.CharField(
                choices=STATUS, default="pending", max_length=10, verbose_name="الحالة"
            ),
        ),
        # البيانات قبل تضييق الخيارات: «deputy» تصير «supervisor».
        migrations.RunPython(_to_paper_order, _back),
        migrations.AlterField(
            model_name="permitrequest",
            name="stage",
            field=models.CharField(
                choices=STAGES, default="secretary", max_length=10, verbose_name="المرحلة"
            ),
        ),
        migrations.AlterField(
            model_name="permitrequest",
            name="rejected_stage",
            field=models.CharField(
                blank=True, choices=STAGES, max_length=10, verbose_name="مرحلة الرفض"
            ),
        ),
    ]
