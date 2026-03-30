"""
operations/migrations/0011_temporary_permission_audit_log.py

إنشاء نموذجَي TemporaryPermission و PermissionAuditLog
لدعم نقل الصلاحيات المؤقتة خلال حصص الأشغال والتبديل والتعويض.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("operations", "0010_staffevaluation"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="TemporaryPermission",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "permission_type",
                    models.CharField(
                        choices=[
                            ("ATTENDANCE", "تسجيل الحضور والغياب"),
                            ("BEHAVIOR", "تسجيل السلوك"),
                            ("ATTENDANCE_BEHAVIOR", "الحضور + السلوك"),
                        ],
                        default="ATTENDANCE_BEHAVIOR",
                        max_length=30,
                        verbose_name="نوع الصلاحية",
                    ),
                ),
                (
                    "source_type",
                    models.CharField(
                        choices=[
                            ("assignment", "حصة أشغال"),
                            ("swap", "تبديل حصص"),
                            ("compensatory", "حصة تعويضية"),
                        ],
                        max_length=15,
                        verbose_name="مصدر الصلاحية",
                    ),
                ),
                (
                    "valid_from",
                    models.DateTimeField(db_index=True, verbose_name="بداية الصلاحية"),
                ),
                (
                    "valid_until",
                    models.DateTimeField(db_index=True, verbose_name="نهاية الصلاحية"),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("active", "نشطة"),
                            ("expired", "منتهية"),
                            ("revoked", "ملغاة يدوياً"),
                        ],
                        db_index=True,
                        default="active",
                        max_length=10,
                        verbose_name="الحالة",
                    ),
                ),
                (
                    "revoked_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="وقت الإلغاء"),
                ),
                ("notes", models.TextField(blank=True, verbose_name="ملاحظات")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "class_group",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="temporary_permissions",
                        to="core.classgroup",
                        verbose_name="الشعبة المستهدفة",
                    ),
                ),
                (
                    "compensatory",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="temp_permissions",
                        to="operations.compensatorysession",
                        verbose_name="الحصة التعويضية",
                    ),
                ),
                (
                    "granted_by",
                    models.ForeignKey(
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="granted_temp_permissions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="مانح الصلاحية",
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="revoked_temp_permissions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="مُلغي الصلاحية",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="temporary_permissions",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "session",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="temp_permissions",
                        to="operations.session",
                        verbose_name="الحصة المرتبطة",
                    ),
                ),
                (
                    "swap",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="temp_permissions",
                        to="operations.teacherswap",
                        verbose_name="طلب التبديل",
                    ),
                ),
                (
                    "teacher",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="temporary_permissions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المعلم المستفيد",
                    ),
                ),
            ],
            options={
                "verbose_name": "صلاحية مؤقتة",
                "verbose_name_plural": "الصلاحيات المؤقتة",
                "ordering": ["-valid_from"],
            },
        ),
        migrations.AddIndex(
            model_name="temporarypermission",
            index=models.Index(fields=["school", "status"], name="idx_tempperm_school_status"),
        ),
        migrations.AddIndex(
            model_name="temporarypermission",
            index=models.Index(fields=["teacher", "status"], name="idx_tempperm_teacher_status"),
        ),
        migrations.AddIndex(
            model_name="temporarypermission",
            index=models.Index(
                fields=["class_group", "status"], name="idx_tempperm_class_status"
            ),
        ),
        migrations.AddIndex(
            model_name="temporarypermission",
            index=models.Index(
                fields=["valid_until", "status"], name="idx_tempperm_expiry_status"
            ),
        ),
        migrations.CreateModel(
            name="PermissionAuditLog",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "action",
                    models.CharField(
                        choices=[
                            ("granted", "مُمنوحة"),
                            ("auto_revoked", "ملغاة تلقائياً"),
                            ("manual_revoked", "ملغاة يدوياً"),
                            ("extended", "ممتدة"),
                        ],
                        max_length=20,
                        verbose_name="الإجراء",
                    ),
                ),
                ("performed_at", models.DateTimeField(auto_now_add=True, verbose_name="وقت التنفيذ")),
                ("notes", models.TextField(blank=True, verbose_name="ملاحظات")),
                (
                    "performed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="permission_audit_actions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="مُنفِّذ الإجراء",
                    ),
                ),
                (
                    "temp_permission",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="audit_logs",
                        to="operations.temporarypermission",
                        verbose_name="الصلاحية المؤقتة",
                    ),
                ),
            ],
            options={
                "verbose_name": "سجل مراجعة صلاحية",
                "verbose_name_plural": "سجلات مراجعة الصلاحيات",
                "ordering": ["-performed_at"],
            },
        ),
    ]
