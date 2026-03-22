"""
Migration 0014 — Immutable AuditLog DB trigger (PDPPL م.19)

Adds a PostgreSQL trigger that raises an exception if any DELETE or UPDATE
is attempted on core_auditlog directly at the database level.
This is defence-in-depth on top of the ORM-level PermissionDenied guards.
"""
from django.db import migrations


TRIGGER_SQL = """
CREATE OR REPLACE FUNCTION core_auditlog_immutable()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION 'AuditLog records are immutable — PDPPL م.19 (operation: %)', TG_OP;
END;
$$;

DROP TRIGGER IF EXISTS trg_auditlog_immutable ON core_auditlog;

CREATE TRIGGER trg_auditlog_immutable
    BEFORE DELETE OR UPDATE ON core_auditlog
    FOR EACH ROW EXECUTE FUNCTION core_auditlog_immutable();
"""

DROP_TRIGGER_SQL = """
DROP TRIGGER IF EXISTS trg_auditlog_immutable ON core_auditlog;
DROP FUNCTION IF EXISTS core_auditlog_immutable();
"""


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0013_add_platform_developer_role"),
    ]

    operations = [
        migrations.RunSQL(
            sql=TRIGGER_SQL,
            reverse_sql=DROP_TRIGGER_SQL,
        ),
    ]
