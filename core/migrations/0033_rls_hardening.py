"""
Migration 0033 — تقوية Row-Level Security (إصلاح المخاطر #1/#2/#3)
═══════════════════════════════════════════════════════════════════
يستبدل طبقة RLS المعطوبة في 0021 بطبقة فعّالة:

  #1  العزل يُطبَّق فعلياً لأن Django يتصل بدور تطبيق غير-superuser/غير-bypassrls
      (shschool_app). المالك (shschool_user) يبقى للترحيل/التعبئة ويتجاوز RLS
      بلا FORCE — لذا لا حاجة لـ FORCE.
  #2  السياسة fail-CLOSED: غياب سياق المدرسة ⇒ لا صفوف (بدل "كل الصفوف").
  #3  تغطية صحيحة وكاملة: كل جدول فيه عمود school_id (54 جدولاً) بأسمائه
      الحقيقية — بدل 6 أسماء أغلبها خاطئ في 0021.

التجاوز المنضبط: عند ضبط app.current_school_id = '*' (يفعله الـ middleware
للـ superuser فقط) تُرى كل المدارس. core_auditlog يسمح بـ school_id IS NULL.
جداول الهوية/الإقلاع (core_membership, core_role) مُستثناة — يحتاجها حلّ
مدرسة المستخدم قبل ضبط السياق.
"""

from django.db import migrations

# ── كل جدول فيه عمود school_id (مصدر الحقيقة: information_schema) ──────────
PROTECTED_TABLES = [
    "assessments_annualsubjectresult",
    "assessments_assessment",
    "assessments_assessmentpackage",
    "assessments_studentassessmentgrade",
    "assessments_studentsubjectresult",
    "assessments_subjectclasssetup",
    "core_academicyear",
    "core_auditlog",
    "core_behaviorinfraction",
    "core_breachreport",
    "core_classgroup",
    "core_clinicvisit",
    "core_consentrecord",
    "core_department",
    "core_erasurerequest",
    "core_libraryactivity",
    "core_librarybook",
    "core_parentstudentlink",
    "core_permissionauditlog",
    "core_schoolbus",
    "exam_control_examsession",
    "notifications_inappnotification",
    "notifications_notificationlog",
    "notifications_notificationsettings",
    "notifications_pushsubscription",
    "operations_absencealert",
    "operations_compensatorysession",
    "operations_freeslotregistry",
    "operations_schedulegeneration",
    "operations_scheduleslot",
    "operations_session",
    "operations_staffevaluation",
    "operations_studentattendance",
    "operations_subject",
    "operations_subjectclassassignment",
    "operations_substituteassignment",
    "operations_teacherabsence",
    "operations_teacherexemption",
    "operations_teacherpreference",
    "operations_teacherswap",
    "operations_temporarypermission",
    "operations_timeslotconfig",
    "quality_employeeevaluation",
    "quality_evaluationcycle",
    "quality_executormapping",
    "quality_operationaldomain",
    "quality_operationalprocedure",
    "quality_qualitycommitteemember",
    "quality_roleevaluationtemplate",
    "staff_affairs_leavebalance",
    "staff_affairs_leaverequest",
    "staging_importlog",
    "student_affairs_studentactivity",
    "student_affairs_studenttransfer",
]

# جدول واحد يسمح بـ school_id IS NULL (سجلّات تدقيق على مستوى النظام)
NULL_OK_TABLES = {"core_auditlog"}

# دوال مساعدة آمنة (تتجنّب خطأ تحويل '*'::uuid)
HELPERS_SQL = """
CREATE OR REPLACE FUNCTION app_rls_bypass() RETURNS boolean
    LANGUAGE sql STABLE AS $$
    SELECT current_setting('app.current_school_id', true) = '*';
$$;

CREATE OR REPLACE FUNCTION app_rls_school() RETURNS uuid
    LANGUAGE sql STABLE AS $$
    SELECT CASE
        WHEN coalesce(current_setting('app.current_school_id', true), '') IN ('', '*')
            THEN NULL
        ELSE current_setting('app.current_school_id', true)::uuid
    END;
$$;
"""

DROP_HELPERS_SQL = """
DROP FUNCTION IF EXISTS app_rls_bypass();
DROP FUNCTION IF EXISTS app_rls_school();
"""


def _enable_sql(table):
    null_clause = " OR school_id IS NULL" if table in NULL_OK_TABLES else ""
    predicate = f"(app_rls_bypass() OR school_id = app_rls_school(){null_clause})"
    return f"""
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = '{table}' AND table_schema = 'public') THEN
            EXECUTE 'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY';
            EXECUTE 'DROP POLICY IF EXISTS school_isolation ON {table}';
            EXECUTE 'CREATE POLICY school_isolation ON {table}
                        USING {predicate} WITH CHECK {predicate}';
        END IF;
    END $$;
    """


def _disable_sql(table):
    return f"""
    DO $$ BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = '{table}' AND table_schema = 'public') THEN
            EXECUTE 'DROP POLICY IF EXISTS school_isolation ON {table}';
            EXECUTE 'ALTER TABLE {table} DISABLE ROW LEVEL SECURITY';
        END IF;
    END $$;
    """


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_add_nationality_to_user"),
        ("assessments", "0001_initial"),
        ("operations", "0001_initial"),
        ("quality", "0001_initial"),
        ("staff_affairs", "0001_initial"),
        ("student_affairs", "0001_initial"),
        ("staging", "0001_initial"),
        ("exam_control", "0001_initial"),
        ("notifications", "0001_initial"),
    ]

    FORWARD_SQL = HELPERS_SQL + "".join(_enable_sql(t) for t in PROTECTED_TABLES)
    REVERSE_SQL = "".join(_disable_sql(t) for t in PROTECTED_TABLES) + DROP_HELPERS_SQL

    operations = [
        migrations.RunSQL(sql=FORWARD_SQL, reverse_sql=REVERSE_SQL),
    ]
