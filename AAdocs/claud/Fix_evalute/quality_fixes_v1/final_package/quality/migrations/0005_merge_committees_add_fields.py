"""
quality/migrations/0005_merge_committees_add_fields.py

الإصلاح #2: دمج اللجنتين + إضافة حقول جديدة
- إضافة committee_type لـ QualityCommitteeMember
- إضافة can_execute / can_review / can_report على مستوى الفرد
- ترحيل بيانات OperationalPlanExecutorCommittee → QualityCommitteeMember
- حذف نموذج OperationalPlanExecutorCommittee
- إضافة deadline لـ OperationalProcedure
- إضافة reviewed_by / reviewed_at / review_note
- تحديث STATUS لإضافة "Pending Review"
"""
from django.db import migrations, models
import django.db.models.deletion
import uuid


def migrate_executor_committee_to_members(apps, schema_editor):
    """
    ترحيل بيانات OperationalPlanExecutorCommittee إلى QualityCommitteeMember
    كل عضو في M2M يُحوَّل إلى سجل منفصل بـ committee_type = "executor"
    """
    OldCommittee = apps.get_model("quality", "OperationalPlanExecutorCommittee")
    NewMember    = apps.get_model("quality", "QualityCommitteeMember")

    for committee in OldCommittee.objects.all():
        for user in committee.members.all():
            # تجنّب التكرار إذا كان المستخدم موجوداً بالفعل
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
    """عكس الترحيل — حذف أعضاء اللجنة التنفيذية المُرحَّلين"""
    NewMember = apps.get_model("quality", "QualityCommitteeMember")
    NewMember.objects.filter(committee_type="executor").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("quality", "0004_operationalplanexecutorcommittee"),
    ]

    operations = [
        # ── 1. إضافة committee_type ──────────────────────────────
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

        # ── 2. صلاحيات على مستوى الفرد ──────────────────────────
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

        # ── 3. تحديث unique_together → constraint ────────────────
        migrations.AlterUniqueTogether(
            name="qualitycommitteemember",
            unique_together=set(),
        ),
        migrations.AddConstraint(
            model_name="qualitycommitteemember",
            constraint=models.UniqueConstraint(
                fields=["school", "academic_year", "user", "committee_type"],
                name="unique_member_per_committee_year",
            ),
        ),

        # ── 4. ترحيل بيانات اللجنة التنفيذية ────────────────────
        migrations.RunPython(
            migrate_executor_committee_to_members,
            reverse_migrate,
        ),

        # ── 5. حذف نموذج OperationalPlanExecutorCommittee ────────
        migrations.DeleteModel(
            name="OperationalPlanExecutorCommittee",
        ),

        # ── 6. إضافة deadline لـ OperationalProcedure ────────────
        migrations.AddField(
            model_name="operationalprocedure",
            name="deadline",
            field=models.DateField(
                blank=True, null=True, verbose_name="الموعد النهائي"
            ),
        ),

        # ── 7. Approval Workflow fields ───────────────────────────
        migrations.AddField(
            model_name="operationalprocedure",
            name="reviewed_by",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="reviewed_procedures",
                to="core.customuser",
                verbose_name="المراجع",
            ),
        ),
        migrations.AddField(
            model_name="operationalprocedure",
            name="reviewed_at",
            field=models.DateTimeField(
                blank=True, null=True, verbose_name="تاريخ المراجعة"
            ),
        ),
        migrations.AddField(
            model_name="operationalprocedure",
            name="review_note",
            field=models.TextField(blank=True, verbose_name="ملاحظة المراجعة"),
        ),

        # ── 8. إضافة deadline index ───────────────────────────────
        migrations.AddIndex(
            model_name="operationalprocedure",
            index=models.Index(fields=["deadline"], name="quality_ope_deadlin_idx"),
        ),
    ]
