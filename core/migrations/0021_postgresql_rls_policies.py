"""
Migration: PostgreSQL Row-Level Security (RLS) — طبقة دفاع إضافية
═══════════════════════════════════════════════════════════════════
يُضيف سياسات RLS على مستوى قاعدة البيانات كحماية عميقة (defense-in-depth)
لمنع تسرب البيانات بين المدارس حتى لو أُخطئ في فلترة الـ ORM.
"""

from django.db import migrations


def _rls_enable_sql(table_name, extra_condition=""):
    """توليد SQL شرطي لتفعيل RLS على جدول."""
    using_clause = (
        "current_setting(''app.current_school_id'', true) IS NULL "
        "OR current_setting(''app.current_school_id'', true) = '''' "
        f"OR school_id = current_setting(''app.current_school_id'', true)::uuid"
    )
    if extra_condition:
        using_clause += f" {extra_condition}"

    return f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = '{table_name}' AND table_schema = 'public') THEN
            EXECUTE 'ALTER TABLE {table_name} ENABLE ROW LEVEL SECURITY';
            -- FORCE RLS لا يُطبق على المالك (Django DB user) — defense-in-depth فقط للأدوار الأخرى
            EXECUTE 'DROP POLICY IF EXISTS school_isolation ON {table_name}';
            EXECUTE '
                CREATE POLICY school_isolation ON {table_name}
                    USING ({using_clause})';
        END IF;
    END $$;
    """


def _rls_disable_sql(table_name):
    """توليد SQL شرطي لإلغاء RLS على جدول."""
    return f"""
    DO $$
    BEGIN
        IF EXISTS (SELECT 1 FROM information_schema.tables
                   WHERE table_name = '{table_name}' AND table_schema = 'public') THEN
            EXECUTE 'DROP POLICY IF EXISTS school_isolation ON {table_name}';
            EXECUTE 'ALTER TABLE {table_name} DISABLE ROW LEVEL SECURITY';
        END IF;
    END $$;
    """


# الجداول المحمية
TABLES = [
    "clinic_clinicvisit",
    "behavior_behaviorinfraction",
    "transport_schoolbus",
    "library_librarybook",
    "core_classgroup",
    "notifications_inappnotification",
]

# core_auditlog — يحتاج شرط إضافي (school_id IS NULL مسموح)
AUDIT_TABLE = "core_auditlog"


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_populate_national_id_hmac_encrypted"),
        # cross-app dependencies لضمان وجود الجداول
        ("clinic", "0001_initial"),
        ("behavior", "0001_initial"),
        ("transport", "0001_initial"),
        ("library", "0001_initial"),
        ("notifications", "0001_initial"),
    ]

    FORWARD_SQL = (
        # دالة مساعدة
        """
        CREATE OR REPLACE FUNCTION current_school_id()
        RETURNS uuid
        LANGUAGE sql STABLE
        AS $$
            SELECT NULLIF(current_setting('app.current_school_id', true), '')::uuid;
        $$;
        """
        # RLS على الجداول العادية
        + "".join(_rls_enable_sql(t) for t in TABLES)
        # RLS على AuditLog (مع شرط NULL)
        + _rls_enable_sql(AUDIT_TABLE, "OR school_id IS NULL")
    )

    REVERSE_SQL = (
        "".join(_rls_disable_sql(t) for t in TABLES)
        + _rls_disable_sql(AUDIT_TABLE)
        + "DROP FUNCTION IF EXISTS current_school_id();"
    )

    operations = [
        migrations.RunSQL(
            sql=FORWARD_SQL,
            reverse_sql=REVERSE_SQL,
        ),
    ]
