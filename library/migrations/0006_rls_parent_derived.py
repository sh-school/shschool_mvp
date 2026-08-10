"""Isolate borrowings and the activity-participants join table.

`core_bookborrowing` derives its school from the borrowed book.

`core_libraryactivity_participants` is the table Django creates for
`LibraryActivity.participants`. It appears in no ordinary model inventory —
`apps.get_models()` omits auto-created through models — which is precisely why
it went unnoticed: it holds tenant associations, carries two foreign keys and no
`school_id`, and nothing in the reconcile loop could ever have reached it.

Both references are policed on write. A library activity belongs to one school
and its participants are that school's people; nothing in the model suggests a
guest from elsewhere, and reading it as though it did would make the table the
one place in the platform where a person from another school may be recorded
against a school's own activity. If such a case ever arises it should be an
explicit decision with an explicit relation, not a gap left by a policy that
checked one side.

The participant side has no `school_id` to check — `core_customuser` carries
none, since a person's tenancy is a many-to-many through `core_membership` — so
the predicate asks that table: the user must hold a membership in the current
school. A person belonging to two schools may be listed in each.

`USING` covers the activity alone, on purpose: an existing participation must
stay readable and removable after a membership ends. `WITH CHECK` is where the
second reference is enforced, because it governs what may be written.
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
PARTICIPANTS_USING = f"""
EXISTS (
    SELECT 1
    FROM public.core_libraryactivity AS activity
    WHERE activity.id = {PARTICIPANTS}.libraryactivity_id
      AND activity.school_id = {CURRENT}
)
"""
PARTICIPANTS_CHECK = f"""
{PARTICIPANTS_USING}
AND EXISTS (
    SELECT 1
    FROM public.core_membership AS m
    WHERE m.user_id = {PARTICIPANTS}.customuser_id
      AND m.school_id = {CURRENT}
)
"""


def _enable(table, using, check):
    return f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{table};

CREATE POLICY school_isolation ON public.{table}
    USING ({using})
    WITH CHECK ({check});
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
            sql=_enable(BORROWING, BORROWING_PREDICATE, BORROWING_PREDICATE),
            reverse_sql=_disable(BORROWING),
        ),
        migrations.RunSQL(
            sql=_enable(PARTICIPANTS, PARTICIPANTS_USING, PARTICIPANTS_CHECK),
            reverse_sql=_disable(PARTICIPANTS),
        ),
    ]
