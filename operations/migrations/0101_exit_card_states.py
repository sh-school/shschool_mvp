"""إدارةُ الأجنحة 2/4: حالاتُ بطاقة الخروج ومُهَلُ الوجهات وعدّادُ تأخّر العودة.

حقولٌ قابلةٌ للفراغ على `ClassExit` (فلا إعادةَ كتابةٍ للصفوف القائمة)، وعمودٌ بقيمةٍ افتراضيّةٍ على
`DailyExitTally`، وجدولُ `ExitDestinationGrace`. كلُّها إضافةٌ: التراجعُ يحذفها بلا فقدِ بياناتٍ سابقة.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0087_wing_assignment"),
        ("operations", "0100_exitpermit_encrypt_caller"),
    ]

    operations = [
        migrations.AddField(
            model_name="classexit",
            name="routed_at",
            field=models.DateTimeField(
                blank=True, db_index=True, null=True, verbose_name="وقتُ الوصول إلى الوجهة"
            ),
        ),
        migrations.AddField(
            model_name="classexit",
            name="routed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="class_exits_routed",
                to=settings.AUTH_USER_MODEL,
                verbose_name="حدّد الوجهة",
            ),
        ),
        migrations.AddField(
            model_name="classexit",
            name="returned_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="class_exits_returned",
                to=settings.AUTH_USER_MODEL,
                verbose_name="سجّل العودة",
            ),
        ),
        migrations.AddField(
            model_name="classexit",
            name="returned_by_role",
            field=models.CharField(
                blank=True,
                choices=[
                    ("teacher", "المعلّم"),
                    ("wing_supervisor", "مشرف الجناح"),
                    ("field_supervisor", "المشرف الميداني"),
                    ("clinic", "العيادة"),
                    ("system", "النظام"),
                ],
                max_length=20,
                verbose_name="دورُ من سجّل العودة",
            ),
        ),
        migrations.AddField(
            model_name="classexit",
            name="allowed_minutes",
            field=models.PositiveSmallIntegerField(
                blank=True,
                help_text="لقطةٌ من مهلة الوجهة لحظةَ الوصول؛ فتغييرُ الإعداد بعدها لا يمسّ ما سبق. فارغةٌ = وجهةٌ بلا مهلة.",
                null=True,
                verbose_name="المهلة المسموحة (دقائق)",
            ),
        ),
        migrations.AddField(
            model_name="classexit",
            name="late_return_seconds",
            field=models.PositiveIntegerField(
                blank=True,
                help_text="ما بعد المهلة عند العودة بنقرة؛ فارغٌ لمن لا مهلةَ له أو أُغلق بالجرس (مجهول لا تأخّر).",
                null=True,
                verbose_name="تأخّرُ العودة (ثوانٍ)",
            ),
        ),
        migrations.AddField(
            model_name="classexit",
            name="alert_stage",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="مرحلةُ التنبيه"),
        ),
        migrations.AddField(
            model_name="classexit",
            name="followup_reason",
            field=models.TextField(blank=True, verbose_name="سببُ التحويل إلى متابعة"),
        ),
        migrations.AddField(
            model_name="classexit",
            name="followup_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="وقتُ التحويل إلى متابعة"
            ),
        ),
        migrations.AddField(
            model_name="dailyexittally",
            name="late_return_seconds",
            field=models.PositiveIntegerField(
                default=0,
                help_text="يُعاد حسابُه من `ClassExit.late_return_seconds` ولا يُزاد؛ ولا يدخل `late_minutes` في الحضور.",
                verbose_name="مجموعُ تأخّر العودة (ثوانٍ)",
            ),
        ),
        migrations.CreateModel(
            name="ExitDestinationGrace",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4, editable=False, primary_key=True, serialize=False
                    ),
                ),
                ("destination", models.CharField(max_length=10, verbose_name="الوجهة")),
                ("minutes", models.PositiveSmallIntegerField(verbose_name="المهلة (دقائق)")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="آخرُ تحديث")),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exit_graces",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
            ],
            options={
                "verbose_name": "مهلةُ وجهةِ خروج",
                "verbose_name_plural": "مُهَلُ وجهات الخروج",
                "constraints": [
                    models.UniqueConstraint(
                        fields=("school", "destination"), name="uniq_exit_grace_school_destination"
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("minutes__gte", 1)), name="exit_grace_minutes_positive"
                    ),
                ],
            },
        ),
    ]
