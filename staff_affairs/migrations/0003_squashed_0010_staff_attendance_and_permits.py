"""مخطَّط حضور الموظّفين والأذونات (نماذج 02 و03 والتكليف) — هجرةٌ واحدةٌ مضغوطة.

كانت ثماني هجراتٍ (0003…0010) تراكمت في فرع wave3-g قبل أن تصل main، وفيها إعادةُ
تسميةٍ وحذفُ عمودٍ وفهارسُ على جداولَ أنشأتها هي نفسُها ولم تُنشر قطّ. فلا إنتاجَ
ولا main يعرفها: الجداولُ تُنشأ هنا بصورتها النهائيّة، وعزلُ الصفّ (RLS) في الهجرة
نفسها، فلا تفحصها بوّابةُ التوسيع/التقليص على أنّها حذفٌ فعليّ.

قاعدةٌ طُبّقت عليها الهجراتُ القديمةُ (جلسةٌ شقيقةٌ) لا تُسجَّل هذه مطبَّقةً بصمتٍ — فالمخطّطُ
هنا أوسعُ منها: أوّلُ عمليّةٍ تُزيل أثرَها إن كانت جداولُها فارغة (``_clear_orphan``)، وتتوقّف
بلا حذفٍ إن وُجدت بيانات، فتُنشأ الجداولُ بصورتها النهائيّة.
"""

import uuid

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

#: هجراتٌ حُذفت من الفرع قبل وصوله إلى main وقد طُبّقت في قواعد جلساتٍ شقيقة (لم تصل إلى
#: main ولا إلى الإنتاج): 0003_wave3g (644e2880) بمفتاح BigAutoField، وثمانٍ 0003…0010 بمخطّطٍ
#: أقدم من هذا. وكلُّها أنشأت الجداولَ نفسَها، فبقاؤها يُسقط ``migrate`` بـ«already exists» — أو
#: يترك مخطّطاً قديماً بلا الجديد.
ORPHAN_MIGRATIONS = (
    "0003_wave3g_staff_attendance_permits",
    "0003_staff_attendance_and_permits",
    "0004_rls_staff_attendance_and_permits",
    "0005_staff_attendance_absence_excuse_early_leave",
    "0006_permit_two_boxes_exceptions_delegation",
    "0007_rls_attendance_exceptions_and_delegations",
    "0008_permit_paper_order_and_coverage_deadline",
    "0009_principal_delegation_kept_on_revoke",
    "0010_staff_attendance_absence_disputed",
)
ORPHAN_TABLES = (
    "staff_affairs_permitrequest",
    "staff_affairs_staffattendance",
    "staff_affairs_attendanceexception",
    "staff_affairs_principaldelegation",
)


def clear_orphan(connection, name=ORPHAN_MIGRATIONS[0], tables=ORPHAN_TABLES):
    """يُزيل أثرَ هجرةٍ يتيمة قبل إنشاء الجداول — وإلّا سقط migrate بـ«already exists».

    لا يفعل شيئاً ما لم يُسجَّل اسمُها في ``django_migrations``. ولا يحذف جدولاً فيه
    صفّ: يتوقّف ويسمّي العلاج (نسخُ القاعدة من جديد بـ``scripts/session-db.sh``)، فلا
    تُفقد بياناتٌ بصمت.
    """
    quote = connection.ops.quote_name
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT 1 FROM django_migrations WHERE app = %s AND name = %s",
            ["staff_affairs", name],
        )
        if cursor.fetchone() is None:
            return
        present = [t for t in tables if t in connection.introspection.table_names(cursor)]
        for table in present:
            cursor.execute(f"SELECT EXISTS (SELECT 1 FROM {quote(table)})")
            if cursor.fetchone()[0]:
                raise RuntimeError(
                    f"الهجرةُ اليتيمة staff_affairs.{name} تركت {table} وفيه بيانات — لا يُحذف "
                    "آليّاً. انسخ قاعدةَ الجلسة من جديد: bash scripts/session-db.sh"
                )
        for table in present:
            cursor.execute(f"DROP TABLE {quote(table)} CASCADE")
        cursor.execute(
            "DELETE FROM django_migrations WHERE app = %s AND name = %s",
            ["staff_affairs", name],
        )


def _clear_orphan(apps, schema_editor):
    for name in ORPHAN_MIGRATIONS:
        clear_orphan(schema_editor.connection, name)


CURRENT = "public.app_rls_school()"
RLS_TABLES = (
    "staff_affairs_staffattendance",
    "staff_affairs_permitrequest",
    "staff_affairs_attendanceexception",
    "staff_affairs_staffassignment",
)


def _enable(table: str) -> str:
    predicate = f"{table}.school_id = {CURRENT}"
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{table};

CREATE POLICY school_isolation ON public.{table}
    USING ({predicate})
    WITH CHECK ({predicate});
"""


def _disable(table: str) -> str:
    return f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0037_rls_tenant_identity_from_db_role"),
        ("staff_affairs", "0002_alter_leavebalance_academic_year_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.RunPython(_clear_orphan, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="leavebalance",
            name="leave_type",
            field=models.CharField(
                choices=[
                    ("annual", "إجازة سنوية"),
                    ("sick", "إجازة مرضية"),
                    ("emergency", "إجازة عارضة"),
                    ("unpaid", "إجازة بدون راتب"),
                    ("maternity", "إجازة أمومة"),
                    ("hajj", "إجازة حج"),
                    ("marriage", "إجازة زواج"),
                    ("iddah", "إجازة عدّة"),
                    ("bereavement", "إجازة عزاء"),
                    ("training", "إجازة تدريب"),
                    ("official", "مهمة رسمية"),
                    ("study", "إجازة دراسية"),
                    ("child_care", "رعاية طفل"),
                    ("work_injury", "إصابة عمل"),
                    ("patient_companion", "مرافقة مريض"),
                    ("other", "أخرى"),
                ],
                max_length=20,
                verbose_name="نوع الإجازة",
            ),
        ),
        migrations.AlterField(
            model_name="leaverequest",
            name="leave_type",
            field=models.CharField(
                choices=[
                    ("annual", "إجازة سنوية"),
                    ("sick", "إجازة مرضية"),
                    ("emergency", "إجازة عارضة"),
                    ("unpaid", "إجازة بدون راتب"),
                    ("maternity", "إجازة أمومة"),
                    ("hajj", "إجازة حج"),
                    ("marriage", "إجازة زواج"),
                    ("iddah", "إجازة عدّة"),
                    ("bereavement", "إجازة عزاء"),
                    ("training", "إجازة تدريب"),
                    ("official", "مهمة رسمية"),
                    ("study", "إجازة دراسية"),
                    ("child_care", "رعاية طفل"),
                    ("work_injury", "إصابة عمل"),
                    ("patient_companion", "مرافقة مريض"),
                    ("other", "أخرى"),
                ],
                max_length=20,
                verbose_name="نوع الإجازة",
            ),
        ),
        migrations.CreateModel(
            name="AttendanceException",
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
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل"),
                ),
                (
                    "exception_type",
                    models.CharField(
                        choices=[
                            ("late_arrival", "تأخير صباحي"),
                            ("early_departure", "خروج مبكر"),
                        ],
                        max_length=20,
                        verbose_name="نوع الاستثناء",
                    ),
                ),
                ("start_date", models.DateField(verbose_name="من تاريخ")),
                ("end_date", models.DateField(verbose_name="إلى تاريخ")),
                ("boundary_time", models.TimeField(verbose_name="الساعة")),
                (
                    "content",
                    models.CharField(max_length=1000, verbose_name="محتوى الطلب"),
                ),
                (
                    "evidence",
                    models.CharField(blank=True, max_length=300, verbose_name="وصف المرفق"),
                ),
                (
                    "evidence_file",
                    models.FileField(
                        blank=True,
                        null=True,
                        upload_to="attendance_exceptions/%Y/%m/",
                        verbose_name="المرفق (ما يثبت الحاجة)",
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "قيد الانتظار"),
                            ("approved", "معتمد"),
                            ("rejected", "مرفوض"),
                        ],
                        default="pending",
                        max_length=10,
                        verbose_name="الحالة",
                    ),
                ),
                (
                    "feedback",
                    models.CharField(blank=True, max_length=500, verbose_name="التغذية الراجعة"),
                ),
                (
                    "reviewed_at",
                    models.DateTimeField(
                        blank=True, null=True, verbose_name="تاريخ التغذية الراجعة"
                    ),
                ),
                (
                    "decided_on_behalf",
                    models.BooleanField(default=False, verbose_name="قُرّر بالإنابة"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشأه",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_attendance_exceptions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="قرّره",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_attendance_exceptions",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "staff",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="attendance_exceptions",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="الموظف",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="عدّله",
                    ),
                ),
            ],
            options={
                "verbose_name": "استثناء حضور (نموذج 03)",
                "verbose_name_plural": "استثناءات الحضور (نموذج 03)",
                "ordering": ["-start_date", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["school", "staff", "status", "start_date"],
                        name="staff_affai_school__384f77_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("end_date__gte", models.F("start_date"))),
                        name="attendance_exception_dates_ordered",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="PermitRequest",
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
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل"),
                ),
                (
                    "permit_type",
                    models.CharField(
                        choices=[
                            ("late_arrival", "تأخير صباحي"),
                            ("during_day", "استئذان أثناء الدوام"),
                            ("early_departure", "خروج مبكر"),
                        ],
                        max_length=20,
                        verbose_name="نوع الطلب",
                    ),
                ),
                ("date", models.DateField(verbose_name="التاريخ")),
                ("start_time", models.TimeField(verbose_name="من الساعة")),
                ("end_time", models.TimeField(verbose_name="إلى الساعة")),
                (
                    "duration_minutes",
                    models.PositiveSmallIntegerField(verbose_name="المدة بالدقائق"),
                ),
                ("reason", models.CharField(max_length=500, verbose_name="سبب الطلب")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "قيد الانتظار"),
                            ("approved", "معتمد"),
                            ("rejected", "مرفوض"),
                            ("cancelled", "ملغى"),
                            ("expired", "منتهٍ"),
                        ],
                        default="pending",
                        max_length=10,
                        verbose_name="الحالة",
                    ),
                ),
                (
                    "stage",
                    models.CharField(
                        choices=[
                            ("secretary", "السكرتارية"),
                            ("coordinator", "منسّق المادّة"),
                            ("supervisor", "المسؤول المباشر والنائب المسؤول"),
                            ("principal", "مدير المدرسة"),
                            ("external", "اعتماد خارجي"),
                            ("closed", "مغلق"),
                        ],
                        default="secretary",
                        max_length=12,
                        verbose_name="المرحلة",
                    ),
                ),
                (
                    "deputy_role",
                    models.CharField(blank=True, max_length=30, verbose_name="دور النائب المسؤول"),
                ),
                (
                    "coordinator_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="وقت توقيع المنسّق"),
                ),
                (
                    "supervisor_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="وقت موافقة المسؤول"),
                ),
                (
                    "deputy_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="وقت موافقة النائب"),
                ),
                (
                    "secretary_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="توقيت تسجيل الرصيد"),
                ),
                (
                    "recorded_balance_minutes",
                    models.PositiveSmallIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="رصيد الساعات المسجّل (دقائق)",
                    ),
                ),
                (
                    "reviewed_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="تاريخ المراجعة"),
                ),
                (
                    "rejection_reason",
                    models.CharField(blank=True, max_length=300, verbose_name="سبب الرفض"),
                ),
                (
                    "rejected_stage",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("secretary", "السكرتارية"),
                            ("coordinator", "منسّق المادّة"),
                            ("supervisor", "المسؤول المباشر والنائب المسؤول"),
                            ("principal", "مدير المدرسة"),
                            ("external", "اعتماد خارجي"),
                            ("closed", "مغلق"),
                        ],
                        max_length=12,
                        verbose_name="مرحلة الرفض",
                    ),
                ),
                (
                    "over_limit",
                    models.BooleanField(default=False, verbose_name="يجاوز الحدّ"),
                ),
                (
                    "written_approval_ref",
                    models.CharField(
                        blank=True,
                        max_length=300,
                        verbose_name="مرجع الموافقة الكتابية",
                    ),
                ),
                (
                    "external_reference",
                    models.CharField(
                        blank=True,
                        max_length=300,
                        verbose_name="مرجع اعتماد رئيس المدير",
                    ),
                ),
                (
                    "notified_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="وقت إخطار الموظف"),
                ),
                (
                    "decided_on_behalf",
                    models.BooleanField(default=False, verbose_name="قُرّر بالإنابة"),
                ),
                (
                    "coordinator",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="coordinated_permit_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="منسّق المادّة",
                    ),
                ),
                (
                    "coordinator_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="coordinator_signed_permit_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="وقّعه من المنسّقين",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشأه",
                    ),
                ),
                (
                    "deputy_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="deputy_permit_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="النائب المسؤول",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="reviewed_permit_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="اعتمده",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_permit_requests",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "secretary_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="recorded_permit_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="موظف السكرتارية",
                    ),
                ),
                (
                    "staff",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="permit_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="الموظف",
                    ),
                ),
                (
                    "supervisor_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="supervised_permit_requests",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المسؤول المباشر",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="عدّله",
                    ),
                ),
            ],
            options={
                "verbose_name": "طلب إذن",
                "verbose_name_plural": "طلبات الأذونات",
                "ordering": ["-date", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["school", "staff", "date"],
                        name="staff_affai_school__034335_idx",
                    ),
                    models.Index(
                        fields=["school", "status", "stage"],
                        name="staff_affai_school__50637d_idx",
                    ),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        condition=models.Q(("status", "approved")),
                        fields=("school", "staff", "date"),
                        name="one_approved_permit_per_day",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(("end_time__gt", models.F("start_time"))),
                        name="permit_end_after_start",
                    ),
                    models.CheckConstraint(
                        condition=models.Q(
                            ("duration_minutes__gt", 0), ("duration_minutes__lte", 420)
                        ),
                        name="permit_duration_within_workday",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="StaffAssignment",
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
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل"),
                ),
                (
                    "acting_role",
                    models.CharField(
                        choices=[
                            ("principal", "مدير المدرسة"),
                            ("vice_admin", "نائب المدير للشؤون الإدارية وشؤون الطلاب"),
                            ("vice_academic", "نائب المدير للشؤون الأكاديمية"),
                        ],
                        max_length=20,
                        verbose_name="الوظيفة المكلَّف بأعبائها",
                    ),
                ),
                ("start_date", models.DateField(verbose_name="من تاريخ")),
                ("end_date", models.DateField(verbose_name="إلى تاريخ")),
                (
                    "reason",
                    models.CharField(max_length=300, verbose_name="سبب التكليف"),
                ),
                (
                    "reference",
                    models.CharField(blank=True, max_length=200, verbose_name="مرجع القرار"),
                ),
                (
                    "revoked_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="رُفع في"),
                ),
                (
                    "assigned_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments_given",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المكلِّف",
                    ),
                ),
                (
                    "assignee",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="assignments_received",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="المكلَّف",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشأه",
                    ),
                ),
                (
                    "revoked_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="assignments_revoked",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="رفعه",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_assignments",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="عدّله",
                    ),
                ),
            ],
            options={
                "verbose_name": "تكليف",
                "verbose_name_plural": "التكليفات",
                "ordering": ["-start_date", "-created_at"],
                "indexes": [
                    models.Index(
                        fields=["school", "acting_role", "start_date", "end_date"],
                        name="staff_affai_school__f37d8e_idx",
                    )
                ],
                "constraints": [
                    models.CheckConstraint(
                        condition=models.Q(("end_date__gte", models.F("start_date"))),
                        name="assignment_end_after_start",
                    )
                ],
            },
        ),
        migrations.CreateModel(
            name="StaffAttendance",
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
                    "created_at",
                    models.DateTimeField(auto_now_add=True, verbose_name="تاريخ الإنشاء"),
                ),
                (
                    "updated_at",
                    models.DateTimeField(auto_now=True, verbose_name="تاريخ التعديل"),
                ),
                ("date", models.DateField(verbose_name="التاريخ")),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("present", "حاضر"),
                            ("late", "متأخّر"),
                            ("absent", "غائب"),
                            ("permitted", "مستأذن"),
                        ],
                        max_length=10,
                        verbose_name="الحالة",
                    ),
                ),
                (
                    "check_in",
                    models.TimeField(blank=True, null=True, verbose_name="وقت الحضور"),
                ),
                (
                    "check_out",
                    models.TimeField(blank=True, null=True, verbose_name="وقت الانصراف"),
                ),
                (
                    "late_minutes",
                    models.PositiveSmallIntegerField(default=0, verbose_name="دقائق التأخّر"),
                ),
                (
                    "permit_minutes",
                    models.PositiveSmallIntegerField(default=0, verbose_name="دقائق الإذن المعتمد"),
                ),
                (
                    "early_leave_minutes",
                    models.PositiveSmallIntegerField(
                        default=0, verbose_name="دقائق الانصراف المبكر بلا إذن"
                    ),
                ),
                (
                    "absence_type",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("casual", "عارضة"),
                            ("unpaid", "بدون راتب"),
                            ("sick", "مرضية"),
                            ("official_mission", "مهمة رسمية"),
                            ("experience_exchange", "تبادل خبرات"),
                            ("external_training", "تدريب خارجي"),
                            ("bereavement", "عزاء"),
                            ("marriage", "زواج"),
                            ("hajj", "حج"),
                            ("maternity", "وضع"),
                            ("iddah", "عدّة شرعية"),
                            ("patient_companion", "مرافقة مريض"),
                            ("work_injury", "إصابة عمل"),
                        ],
                        max_length=20,
                        verbose_name="نوع الغياب",
                    ),
                ),
                (
                    "accepted_excuse",
                    models.CharField(
                        blank=True,
                        max_length=300,
                        verbose_name="العذر المقبول (البند 2.4)",
                    ),
                ),
                (
                    "excuse_accepted_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="وقت قبول العذر"),
                ),
                (
                    "excuse_on_behalf",
                    models.BooleanField(default=False, verbose_name="قُبل العذر بالإنابة"),
                ),
                (
                    "covered_at",
                    models.DateTimeField(blank=True, null=True, verbose_name="وقت تغطية الغياب"),
                ),
                (
                    "notes",
                    models.CharField(blank=True, max_length=300, verbose_name="ملاحظات"),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_created",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="أنشأه",
                    ),
                ),
                (
                    "excuse_accepted_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="accepted_staff_excuses",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="قبِل العذر",
                    ),
                ),
                (
                    "school",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_attendance_records",
                        to="core.school",
                        verbose_name="المدرسة",
                    ),
                ),
                (
                    "staff",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="staff_attendance_records",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="الموظف",
                    ),
                ),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="%(app_label)s_%(class)s_updated",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="عدّله",
                    ),
                ),
            ],
            options={
                "verbose_name": "حضور موظف",
                "verbose_name_plural": "حضور الموظفين",
                "ordering": ["-date"],
                "indexes": [
                    models.Index(
                        fields=["school", "date", "status"],
                        name="staff_affai_school__0e4009_idx",
                    )
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("school", "staff", "date"),
                        name="unique_staff_attendance_day",
                    )
                ],
            },
        ),
    ] + [migrations.RunSQL(sql=_enable(table), reverse_sql=_disable(table)) for table in RLS_TABLES]
