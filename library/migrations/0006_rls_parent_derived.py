"""Isolate borrowings and the activity-participants join table.

`core_bookborrowing` derives its school from the borrowed book.

`core_libraryactivity_participants` is the table Django creates for
`LibraryActivity.participants`. It appears in no ordinary model inventory —
`apps.get_models()` omits auto-created through models — which is precisely why
it went unnoticed: it holds tenant associations, carries two foreign keys and no
`school_id`, and nothing in the reconcile loop could ever have reached it.

Only the activity side is policed. The other side is `core_customuser`, and a
person's tenancy is a many-to-many through `core_membership`, so requiring it
would either widen the predicate or wrongly exclude a legitimate participant.
The association is owned by the activity, and the activity is owned by a school.
"""

from django.db import migrations

CURRENT = "public.app_rls_school()"

BORROWING = "core_bookborrowing"
BORROWING_PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.core_librarybook AS book
    WHERE book.id = {BORROWING}.book_id
      AND book.school_id = {CURRENT}
)
"""

PARTICIPANTS = "core_libraryactivity_participants"
PARTICIPANTS_PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.core_libraryactivity AS activity
    WHERE activity.id = {PARTICIPANTS}.libraryactivity_id
      AND activity.school_id = {CURRENT}
)
"""


def _enable(table, predicate):
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{table};

CREATE POLICY school_isolation ON public.{table}
    USING ({predicate})
    WITH CHECK ({predicate});
"""


def _disable(table):
    return f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""


class Migration(migrations.Migration):
    dependencies = [
        ("library", "0005_alter_librarybook_digital_file"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_enable(BORROWING, BORROWING_PREDICATE),
            reverse_sql=_disable(BORROWING),
        ),
        migrations.RunSQL(
            sql=_enable(PARTICIPANTS, PARTICIPANTS_PREDICATE),
            reverse_sql=_disable(PARTICIPANTS),
        ),
    ]
