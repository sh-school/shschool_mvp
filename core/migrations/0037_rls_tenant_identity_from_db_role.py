"""Derive tenant identity from the database role, not from a writable GUC.

Until now every `school_isolation` predicate resolved the tenant through
`current_setting('app.current_school_id')` — a placeholder GUC that any
PostgreSQL role may set without privilege. The party the policy constrains was
the same party that declared its identity to the policy, so RLS never was an
independent trust boundary:

    SET app.current_school_id = '*';            -- every tenant at once
    SET app.current_school_id = '<other uuid>'; -- one arbitrary tenant

Measured against the dev schema as the constrained role `shschool_app`: empty
context returned 0 rows, a wrong UUID returned 0 rows, and the target school's
UUID returned every row. One injected statement was enough.

Tenant identity now comes from the connection credentials, which injected SQL
cannot change:

    app_rls_school()  ->  SELECT school_id
                          FROM public.app_rls_role_school
                          WHERE db_role = session_user

`session_user` is deliberate. `current_user` follows `SET ROLE`, so a role with
any membership could hop tenants; `session_user` records the role that
authenticated and only `SET SESSION AUTHORIZATION` changes it, which is
superuser-only and therefore out of reach of the runtime role.

The mapping table is owned by the migration owner and the runtime role gets
SELECT only. That matters because `provision_rls_role` issues a blanket
`GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public`, which
would otherwise let the application rewrite its own identity — the same class of
hole in a new place. The write privileges are revoked here and again after every
provisioning run.

`app_rls_bypass()` becomes a constant false so that any policy still referencing
it in a partially migrated environment cannot bypass either.

The predicate text is unchanged — `school_id = app_rls_school()` — only what the
function reads changes.

This migration is intentionally NOT reversible. Restoring the previous
definitions would reinstate client-controlled tenant authority, and a security
rollback must never reopen the hole it closed.

The mapping table is excluded from the reconcile loop. It *does* carry a
`school_id` column, so the loop would otherwise give it a policy whose predicate
calls `app_rls_school()`, which reads that very table — infinite recursion,
observed as "stack depth limit exceeded" on the first query. Like
core_membership and core_role it is bootstrap infrastructure: it has to be
readable before any tenant scope exists, and it is protected by grants rather
than by RLS.
"""

from django.db import migrations

RUNTIME_ROLE = "shschool_app"

# ══════════════════════════════════════════════════════════════════
# 1. Trusted role -> school mapping, writable only by the owner
# ══════════════════════════════════════════════════════════════════

MAPPING_SQL = f"""
CREATE TABLE IF NOT EXISTS public.app_rls_role_school (
    db_role   name PRIMARY KEY,
    school_id uuid NOT NULL
);

-- No PUBLIC grant: every role would otherwise be able to read the whole
-- role -> school mapping. Only the runtime role needs SELECT, and it is granted
-- that in LOCK_MAPPING_SQL below once the role is known to exist.
REVOKE ALL ON public.app_rls_role_school FROM PUBLIC;

-- Seed the single-tenant deployment so the mapping is live the moment the
-- policies start reading it. Without this the running web process would see
-- zero rows between migrate and provision_rls_role.
INSERT INTO public.app_rls_role_school (db_role, school_id)
SELECT '{RUNTIME_ROLE}', s.id
FROM public.core_school AS s
WHERE (SELECT COUNT(*) FROM public.core_school) = 1
ON CONFLICT (db_role) DO NOTHING;
"""

# ══════════════════════════════════════════════════════════════════
# 2. Helper functions — no GUC anywhere
# ══════════════════════════════════════════════════════════════════

# Both helpers pin search_path and schema-qualify every reference. They are the
# tenant authority for every policy, so name resolution must not depend on the
# caller's search_path: a schema earlier in the path holding a same-named table
# would otherwise decide who sees what.
HELPERS_SQL = """
CREATE OR REPLACE FUNCTION public.app_rls_bypass() RETURNS boolean
    LANGUAGE sql STABLE
    SET search_path = pg_catalog, public
    AS $$
    SELECT false;
$$;

CREATE OR REPLACE FUNCTION public.app_rls_school() RETURNS uuid
    LANGUAGE sql STABLE
    SET search_path = pg_catalog, public
    AS $$
    SELECT school_id
    FROM public.app_rls_role_school
    WHERE db_role = session_user;
$$;
"""

# ══════════════════════════════════════════════════════════════════
# 3. Reconcile every school-scoped policy
# ══════════════════════════════════════════════════════════════════

RECONCILE_SQL = """
DO $$
DECLARE
    target record;
    predicate text;
BEGIN
    FOR target IN
        SELECT DISTINCT columns.table_name
        FROM information_schema.columns AS columns
        JOIN information_schema.tables AS tables
          ON tables.table_schema = columns.table_schema
         AND tables.table_name = columns.table_name
        WHERE columns.table_schema = 'public'
          AND columns.column_name = 'school_id'
          AND tables.table_type = 'BASE TABLE'
          AND columns.table_name NOT IN (
              'core_membership',
              'core_role',
              -- The mapping table carries a school_id column, so the loop would
              -- otherwise put a policy on it whose predicate calls
              -- app_rls_school(), which reads this very table: infinite
              -- recursion, observed as "stack depth limit exceeded" on the
              -- first query. It is bootstrap infrastructure like the two above
              -- and is protected by grants, not by RLS.
              'app_rls_role_school'
          )
        ORDER BY columns.table_name
    LOOP
        IF target.table_name = 'core_auditlog' THEN
            predicate :=
                '(school_id = public.app_rls_school() OR school_id IS NULL)';
        ELSE
            predicate := '(school_id = public.app_rls_school())';
        END IF;

        -- %I.%I: الحلقة تختار جداول public تحديداً، فيجب أن تُعدّل
        -- جداول public تحديداً. اسم غير مؤهَّل يُحلّ عبر search_path وقد يصيب
        -- سكيما أخرى تحمل الاسم نفسه، فتبقى جداول public بلا سياسة.
        EXECUTE format(
            'ALTER TABLE %I.%I ENABLE ROW LEVEL SECURITY',
            'public',
            target.table_name
        );

        EXECUTE format(
            'DROP POLICY IF EXISTS school_isolation ON %I.%I',
            'public',
            target.table_name
        );

        EXECUTE format(
            'CREATE POLICY school_isolation ON %I.%I '
            'USING %s WITH CHECK %s',
            'public',
            target.table_name,
            predicate,
            predicate
        );
    END LOOP;
END $$;
"""

# ══════════════════════════════════════════════════════════════════
# 4. The runtime role must never rewrite its own identity
# ══════════════════════════════════════════════════════════════════

LOCK_MAPPING_SQL = f"""
REVOKE INSERT, UPDATE, DELETE, TRUNCATE
    ON public.app_rls_role_school FROM PUBLIC;

DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '{RUNTIME_ROLE}') THEN
        EXECUTE 'REVOKE INSERT, UPDATE, DELETE, TRUNCATE '
                'ON public.app_rls_role_school FROM {RUNTIME_ROLE}';
        EXECUTE 'GRANT SELECT ON public.app_rls_role_school TO {RUNTIME_ROLE}';
    END IF;
END $$;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0036_reconcile_school_rls"),
    ]

    operations = [
        migrations.RunSQL(
            sql=MAPPING_SQL + HELPERS_SQL + RECONCILE_SQL + LOCK_MAPPING_SQL,
            # Security rollback must not restore client-controlled tenant
            # authority. Unapplying leaves the hardened state in place.
            reverse_sql=migrations.RunSQL.noop,
        ),
    ]
