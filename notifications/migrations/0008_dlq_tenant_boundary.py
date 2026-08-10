"""Bring the dead-letter queue inside the tenant boundary.

`DeadLetterMessage` stored the school inside its JSON payload. RLS policies are
column predicates and cannot read into a JSONField, so migration 0037's
reconcile loop — which selects tables carrying a `school_id` column — never saw
this table. Measured in production before this change:

    HAS_SCHOOL_ID_COLUMN = 0
    RLS_ENABLED          = False
    POLICY_COUNT         = 0

Every other school-scoped table is isolated; this one was not, and any operator
screen built over it would have listed every school's failed messages.

Adding the column is not enough on its own. Migration 0037 has already run and
will not run again, so the policy has to be created here explicitly rather than
left to a reconcile that is in the past.

The backfill fails closed. A row whose payload carries no usable school cannot
be attributed, and guessing one would file another tenant's failure under the
wrong school. Production holds zero rows, but this migration does not assume
that — a development database, or a row written between now and deploy, must
behave the same way.
"""

import django.db.models.deletion
from django.db import migrations, models

TABLE = "notifications_deadlettermessage"

ENABLE_RLS_SQL = f"""
ALTER TABLE public.{TABLE} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{TABLE};

CREATE POLICY school_isolation ON public.{TABLE}
    USING (school_id = public.app_rls_school())
    WITH CHECK (school_id = public.app_rls_school());
"""

DISABLE_RLS_SQL = f"""
DROP POLICY IF EXISTS school_isolation ON public.{TABLE};
ALTER TABLE public.{TABLE} DISABLE ROW LEVEL SECURITY;
"""


def backfill_school(apps, schema_editor):
    """Attribute historical rows from payload['school_id'], or refuse to migrate."""
    DeadLetterMessage = apps.get_model("notifications", "DeadLetterMessage")
    School = apps.get_model("core", "School")

    known = set(School.objects.values_list("id", flat=True))
    unattributable = []

    for row in DeadLetterMessage.objects.filter(school__isnull=True).iterator():
        raw = (row.payload or {}).get("school_id")

        if not raw:
            unattributable.append((row.pk, "payload has no school_id"))
            continue

        try:
            import uuid as _uuid

            candidate = _uuid.UUID(str(raw))
        except (TypeError, ValueError):
            unattributable.append((row.pk, "school_id is not a UUID"))
            continue

        if candidate not in known:
            unattributable.append((row.pk, "school_id matches no school"))
            continue

        row.school_id = candidate
        row.save(update_fields=["school"])

    if unattributable:
        listed = "; ".join(f"{pk}: {why}" for pk, why in unattributable[:10])
        raise RuntimeError(
            f"{len(unattributable)} dead-letter rows cannot be attributed to a "
            f"school and would land under the wrong tenant. Resolve or delete "
            f"them, then re-run. First offenders — {listed}"
        )


def unbackfill(apps, schema_editor):
    """Reverse leaves the column populated; dropping it is the AddField's job."""


class Migration(migrations.Migration):
    dependencies = [
        ("notifications", "0007_deadlettermessage"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.AddField(
            model_name="deadlettermessage",
            name="school",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="dead_letter_messages",
                to="core.school",
                verbose_name="المدرسة",
            ),
        ),
        migrations.RunPython(backfill_school, unbackfill),
        migrations.AlterField(
            model_name="deadlettermessage",
            name="school",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="dead_letter_messages",
                to="core.school",
                verbose_name="المدرسة",
            ),
        ),
        migrations.RemoveIndex(
            model_name="deadlettermessage",
            name="notif_dlq_resolved_idx",
        ),
        migrations.AddIndex(
            model_name="deadlettermessage",
            index=models.Index(
                fields=["school", "resolved", "created_at"],
                name="notif_dlq_school_idx",
            ),
        ),
        migrations.RunSQL(sql=ENABLE_RLS_SQL, reverse_sql=DISABLE_RLS_SQL),
    ]
