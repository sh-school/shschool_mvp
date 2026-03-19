"""
quality/migrations/0005_merge_committees_add_fields.py
الجزء الأول: تغييرات الحقول + ترحيل البيانات فقط
(بدون الـ UniqueConstraint — ينتقل للـ 0006)
"""
from django.db import migrations, models
import django.db.models.deletion


def migrate_executor_committee_to_members(apps, schema_editor):
    OldCommittee = apps.get_model("quality", "OperationalPlanExecutorCommittee")
    NewMember    = apps.get_model("quality", "QualityCommitteeMember")

    for committee in OldCommittee.objects.all():
        for user in committee.members.all():
            if not NewMember.objects.filter(
                school=committee.school,
                academic_year=committee.academic_year,
                user=user,
                committee_type="executor",
            ).exists():
                NewMember.objects.create(
                    school=committee.school,
                    academic_year=committee.academic_year,
                    user=user,
                    job_title=getattr(user, "job_title", "") or "",
                    responsibility="عضو",
                    committee_type="executor",
                    can_execute=committee.can_execute_plan,
                    can_review=committee.can_review_plan,
                    can_report=committee.can_report_progress,
                    is_active=True,
                )


def reverse_migrate(apps, schema_editor):
    NewMember = apps.get_model("quality", "QualityCommitteeMember")
    NewMember.objects.filter(committee_type="executor").delete()


class Migration(migrations.Migration):

    atomic = False

    dependencies = [
        ("quality", "0004_operationalplanexecutorcommittee"),
    ]

    operations = [
        migrations.AddField(
            model_name="qualitycommitteemember",
            name="committee_type",
            field=models.CharField(
                choices=[
                    ("executor", "لجنة منفذي الخطة التشغيلية"),
                    ("review",   "لجنة المراجعة الذاتية"),
                ],
                default="review",
                max_length=10,
                verbose_name="نوع اللجنة",
                db_index=True,
            ),
        ),
        migrations.AddField(
            model_name="qualitycommitteemember",
            name="can_execute",
            field=models.BooleanField(default=True, verbose_name="صلاحية تنفيذ إجراء"),
        ),
        migrations.AddField(
            model_name="qualitycommitteemember",
            name="can_review",
            field=models.BooleanField(default=True, verbose_name="صلاحية مراجعة إجراء"),
        ),
        migrations.AddField(
            model_name="qualitycommitteemember",
            name="can_report",
            field=models.BooleanField(default=True, verbose_name="صلاحية رفع تقرير"),
        ),
        migrations.RunPython(
            migrate_executor_committee_to_members,
            reverse_migrate,
        ),
        migrations.DeleteModel(
            name="OperationalPlanExecutorCommittee",
        ),
        migrations.AddField(
            model_name="operationalprocedure",
            name="deadline",
            field=models.DateField(blank=True, null=True, verbose_name="الموعد النهائي"),
        ),
        migrations.AddField(
            model_name="operationalprocedure",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True, null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_procedures",
                to="core.customuser",
                verbose_name="المراجع",
            ),
        ),
        migrations.AddField(
            model_name="operationalprocedure",
            name="reviewed_at",
            field=models.DateTimeField(blank=True, null=True, verbose_name="تاريخ المراجعة"),
        ),
        migrations.AddField(
            model_name="operationalprocedure",
            name="review_note",
            field=models.TextField(blank=True, verbose_name="ملاحظة المراجعة"),
        ),
    ]
