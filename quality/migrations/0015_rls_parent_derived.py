"""Isolate the seven quality tables that hold no `school_id` of their own.

Every one of them is tenant data reached through a parent that does carry the
school: an axis through its template, a score through its evaluation, a target
through its domain, an indicator through its target's domain, and both the
evidence and the status log through their procedure.

`quality_observationscore` is the one that mattered most to find. It holds the
rating and the recommendation for each criterion of a classroom observation —
the substance of a teacher's appraisal. Its parent `quality_classroomobservation`
carries the school and was covered; the content itself was not.

It is also the one table here with two tenant-bearing relations, so its
`WITH CHECK` does more than repeat `USING`: the observation must belong to the
current school *and* the criterion must belong to the same school as the
observation. Without that second clause a row could score this school's
observation against another school's criterion, and the foreign keys would raise
no objection — PostgreSQL runs referential integrity outside row-level security.
"""

from django.db import migrations

CURRENT = "public.app_rls_school()"


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


def _owned_by(parent_table, alias, local_column):
    return f"""
    EXISTS (
        SELECT 1
        FROM public.{parent_table} AS {alias}
        WHERE {alias}.id = {local_column}
          AND {alias}.school_id = {CURRENT}
    )
    """


# ── single-parent tables ─────────────────────────────────────────────────────
AXIS = "quality_evaluationaxis"
AXIS_PREDICATE = _owned_by(
    "quality_roleevaluationtemplate", "template", f"{AXIS}.template_id"
)

SCORE = "quality_evaluationscore"
SCORE_PREDICATE = _owned_by(
    "quality_employeeevaluation", "evaluation", f"{SCORE}.evaluation_id"
)

TARGET = "quality_operationaltarget"
TARGET_PREDICATE = _owned_by(
    "quality_operationaldomain", "domain", f"{TARGET}.domain_id"
)

EVIDENCE = "quality_procedureevidence"
EVIDENCE_PREDICATE = _owned_by(
    "quality_operationalprocedure", "procedure", f"{EVIDENCE}.procedure_id"
)

STATUS_LOG = "quality_procedurestatuslog"
STATUS_LOG_PREDICATE = _owned_by(
    "quality_operationalprocedure", "procedure", f"{STATUS_LOG}.procedure_id"
)

# ── two hops: indicator -> target -> domain ──────────────────────────────────
INDICATOR = "quality_operationalindicator"
INDICATOR_PREDICATE = f"""
EXISTS (
    SELECT 1
    FROM public.quality_operationaltarget AS target
    JOIN public.quality_operationaldomain AS domain ON domain.id = target.domain_id
    WHERE target.id = {INDICATOR}.target_id
      AND domain.school_id = {CURRENT}
)
"""

# ── two tenant relations: observation + criterion ────────────────────────────
OBS_SCORE = "quality_observationscore"
OBS_SCORE_USING = f"""
EXISTS (
    SELECT 1
    FROM public.quality_classroomobservation AS o
    WHERE o.id = {OBS_SCORE}.observation_id
      AND o.school_id = {CURRENT}
)
"""
OBS_SCORE_CHECK = f"""
EXISTS (
    SELECT 1
    FROM public.quality_classroomobservation AS o
    JOIN public.quality_observationcriterion AS c
      ON c.id = {OBS_SCORE}.criterion_id
    WHERE o.id = {OBS_SCORE}.observation_id
      AND o.school_id = {CURRENT}
      AND c.school_id = o.school_id
)
"""


class Migration(migrations.Migration):
    dependencies = [
        ("quality", "0014_classroomobservation_kind"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_enable(AXIS, AXIS_PREDICATE, AXIS_PREDICATE),
            reverse_sql=_disable(AXIS),
        ),
        migrations.RunSQL(
            sql=_enable(SCORE, SCORE_PREDICATE, SCORE_PREDICATE),
            reverse_sql=_disable(SCORE),
        ),
        migrations.RunSQL(
            sql=_enable(TARGET, TARGET_PREDICATE, TARGET_PREDICATE),
            reverse_sql=_disable(TARGET),
        ),
        migrations.RunSQL(
            sql=_enable(INDICATOR, INDICATOR_PREDICATE, INDICATOR_PREDICATE),
            reverse_sql=_disable(INDICATOR),
        ),
        migrations.RunSQL(
            sql=_enable(EVIDENCE, EVIDENCE_PREDICATE, EVIDENCE_PREDICATE),
            reverse_sql=_disable(EVIDENCE),
        ),
        migrations.RunSQL(
            sql=_enable(STATUS_LOG, STATUS_LOG_PREDICATE, STATUS_LOG_PREDICATE),
            reverse_sql=_disable(STATUS_LOG),
        ),
        migrations.RunSQL(
            sql=_enable(OBS_SCORE, OBS_SCORE_USING, OBS_SCORE_CHECK),
            reverse_sql=_disable(OBS_SCORE),
        ),
    ]
