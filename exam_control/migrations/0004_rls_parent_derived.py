"""Isolate the six exam-control tables through `ExamSession`.

None of them carries a `school_id`, so migration 0037's reconcile loop could not
see any of them. All six resolve to the same owner: the room, the supervisor,
the schedule and the incident hold `session` directly; the envelope and the
grade sheet reach it through `schedule`.

Four of these tables hold more than one tenant-bearing relation, and that is
where a naive policy leaks. A schedule holds both a session and a room; a
supervisor and an incident may hold a room as well; an incident may also point
at a behaviour infraction. Checking only the session would let a row pair this
school's session with another school's room. Foreign keys do not close that gap
— PostgreSQL runs referential integrity checks outside row-level security, so a
key can legitimately reference a row the writer is not allowed to see.

So `USING` establishes ownership and `WITH CHECK` additionally requires every
other tenant-bearing relation on the row to resolve to the same school. Nullable
relations are admitted when absent rather than treated as violations.
"""

from django.db import migrations

CURRENT = "public.app_rls_school()"


def _session_owned(column):
    """The referenced ExamSession belongs to the current school."""
    return f"""
    EXISTS (
        SELECT 1
        FROM public.exam_control_examsession AS s
        WHERE s.id = {column}
          AND s.school_id = {CURRENT}
    )
    """


def _room_owned(column):
    """The referenced room's session belongs to the current school."""
    return f"""
    EXISTS (
        SELECT 1
        FROM public.exam_control_examroom AS r
        JOIN public.exam_control_examsession AS rs ON rs.id = r.session_id
        WHERE r.id = {column}
          AND rs.school_id = {CURRENT}
    )
    """


def _schedule_owned(column):
    """The referenced schedule's session belongs to the current school."""
    return f"""
    EXISTS (
        SELECT 1
        FROM public.exam_control_examschedule AS sch
        JOIN public.exam_control_examsession AS ss ON ss.id = sch.session_id
        WHERE sch.id = {column}
          AND ss.school_id = {CURRENT}
    )
    """


def _infraction_owned(column):
    """The referenced behaviour infraction belongs to the current school."""
    return f"""
    EXISTS (
        SELECT 1
        FROM public.core_behaviorinfraction AS bi
        WHERE bi.id = {column}
          AND bi.school_id = {CURRENT}
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


# ── exam_control_examroom — one relation ─────────────────────────────────────
ROOM = "exam_control_examroom"
ROOM_PREDICATE = _session_owned(f"{ROOM}.session_id")

# ── exam_control_examschedule — session + room (both NOT NULL) ───────────────
SCHEDULE = "exam_control_examschedule"
SCHEDULE_USING = _session_owned(f"{SCHEDULE}.session_id")
SCHEDULE_CHECK = f"{SCHEDULE_USING} AND {_room_owned(f'{SCHEDULE}.room_id')}"

# ── exam_control_examsupervisor — session + optional room ────────────────────
SUPERVISOR = "exam_control_examsupervisor"
SUPERVISOR_USING = _session_owned(f"{SUPERVISOR}.session_id")
SUPERVISOR_CHECK = (
    f"{SUPERVISOR_USING} AND ("
    f"{SUPERVISOR}.room_id IS NULL OR {_room_owned(f'{SUPERVISOR}.room_id')})"
)

# ── exam_control_examincident — session + optional room + optional link ──────
INCIDENT = "exam_control_examincident"
INCIDENT_USING = _session_owned(f"{INCIDENT}.session_id")
INCIDENT_CHECK = (
    f"{INCIDENT_USING}"
    f" AND ({INCIDENT}.room_id IS NULL OR {_room_owned(f'{INCIDENT}.room_id')})"
    f" AND ({INCIDENT}.behavior_link_id IS NULL"
    f" OR {_infraction_owned(f'{INCIDENT}.behavior_link_id')})"
)

# ── exam_control_examenvelope — schedule only ────────────────────────────────
ENVELOPE = "exam_control_examenvelope"
ENVELOPE_PREDICATE = _schedule_owned(f"{ENVELOPE}.schedule_id")

# ── exam_control_examgradesheet — schedule only ──────────────────────────────
GRADESHEET = "exam_control_examgradesheet"
GRADESHEET_PREDICATE = _schedule_owned(f"{GRADESHEET}.schedule_id")


class Migration(migrations.Migration):
    dependencies = [
        ("exam_control", "0003_alter_examsupervisor_unique_together_and_more"),
        ("behavior", "0014_rls_parent_derived"),
        ("core", "0037_rls_tenant_identity_from_db_role"),
    ]

    operations = [
        migrations.RunSQL(
            sql=_enable(ROOM, ROOM_PREDICATE, ROOM_PREDICATE),
            reverse_sql=_disable(ROOM),
        ),
        migrations.RunSQL(
            sql=_enable(SCHEDULE, SCHEDULE_USING, SCHEDULE_CHECK),
            reverse_sql=_disable(SCHEDULE),
        ),
        migrations.RunSQL(
            sql=_enable(SUPERVISOR, SUPERVISOR_USING, SUPERVISOR_CHECK),
            reverse_sql=_disable(SUPERVISOR),
        ),
        migrations.RunSQL(
            sql=_enable(INCIDENT, INCIDENT_USING, INCIDENT_CHECK),
            reverse_sql=_disable(INCIDENT),
        ),
        migrations.RunSQL(
            sql=_enable(ENVELOPE, ENVELOPE_PREDICATE, ENVELOPE_PREDICATE),
            reverse_sql=_disable(ENVELOPE),
        ),
        migrations.RunSQL(
            sql=_enable(GRADESHEET, GRADESHEET_PREDICATE, GRADESHEET_PREDICATE),
            reverse_sql=_disable(GRADESHEET),
        ),
    ]
