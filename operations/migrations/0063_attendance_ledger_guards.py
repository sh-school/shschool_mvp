"""حرّاسُ سجلّ رصد المعلّم في قاعدة البيانات: عزلُ المدرسة (RLS) وعدمُ القابليّة للتعديل (W-20261002-020).

- **RLS:** سياسةُ `school_isolation` على الجدولين بصيغة `assessments/0016` — الجدولان يحملان `school_id`.
- **مشغّلُ عدم التعديل:** `BEFORE UPDATE OR DELETE` على الصفّ في الجدولين، على غرار `core/0014` لـAuditLog.
  يرفض كلَّ UPDATE دائماً، ويرفض كلَّ DELETE **إلّا** حين يضبط محوُ الطالب (PDPPL م.18) علَماً محلّيّاً في المعاملة
  `app.attendance_erasure = 'on'` — وهو مفتاحٌ لا إذن، يحرسه اختبارٌ معماريٌّ يمنع ظهورَ اسمه خارج موضعه.
- **TRUNCATE:** لا يمنعه مشغّلُ الصفّ، ولا نضيف مشغّلَ عبارةٍ يكسر تنظيفَ قاعدة الاختبار؛ فسحبُ صلاحيّته من
  دور التطبيق في الإنتاج يُدار في إعداد أدوار القاعدة (راجع `scripts/provision_rls_app_role.sql`) ويُختبر هناك.

هجرةُ SQL وحدَها بلا حذفٍ ولا إعادة تسميةٍ — توسيعٌ صرف.
"""

from django.db import migrations

TABLES = ("operations_attendanceentry", "operations_attendancedecision")
PREDICATE = "(school_id = public.app_rls_school())"

RLS_SQL = "\n".join(
    f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;
DROP POLICY IF EXISTS school_isolation ON public.{table};
CREATE POLICY school_isolation ON public.{table}
    USING {PREDICATE}
    WITH CHECK {PREDICATE};
"""
    for table in TABLES
)

RLS_REVERSE_SQL = "\n".join(
    f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""
    for table in TABLES
)

GUARD_SQL = (
    """
CREATE OR REPLACE FUNCTION operations_attendance_ledger_guard()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE'
       AND COALESCE(current_setting('app.attendance_erasure', true), '') = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'attendance ledger is append-only (operation: %)', TG_OP;
END;
$$;
"""
    + "\n".join(
        f"""
DROP TRIGGER IF EXISTS trg_{table}_append_only ON public.{table};
CREATE TRIGGER trg_{table}_append_only
    BEFORE UPDATE OR DELETE ON public.{table}
    FOR EACH ROW EXECUTE FUNCTION operations_attendance_ledger_guard();
"""
        for table in TABLES
    )
)

GUARD_REVERSE_SQL = (
    "\n".join(f"DROP TRIGGER IF EXISTS trg_{table}_append_only ON public.{table};" for table in TABLES)
    + "\nDROP FUNCTION IF EXISTS operations_attendance_ledger_guard();"
)


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0062_attendance_ledger"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(sql=RLS_SQL, reverse_sql=RLS_REVERSE_SQL),
        migrations.RunSQL(sql=GUARD_SQL, reverse_sql=GUARD_REVERSE_SQL),
    ]
