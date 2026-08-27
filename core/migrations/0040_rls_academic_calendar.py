"""Isolate the academic calendar through its academic year.

`Semester` and `CalendarEvent` both hang off `AcademicYear`, which carries the
school. Neither carries `school_id` of its own — deliberately: a duplicate
column would be a second copy of a fact the parent already states, and a second
chance to disagree with it.

`CalendarEvent.semester_id` is not part of the predicate. It is nullable and it
resolves to the same year, so adding it would widen nothing and could only
disagree with `academic_year_id`.
"""

from django.db import migrations

TABLES = ("core_semester", "core_calendarevent")


def _predicate(table: str) -> str:
    return f"""
EXISTS (
    SELECT 1
    FROM public.core_academicyear AS parent
    WHERE parent.id = {table}.academic_year_id
      AND parent.school_id = public.app_rls_school()
)
"""


ENABLE_SQL = "\n".join(
    f"""
ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS school_isolation ON public.{table};

CREATE POLICY school_isolation ON public.{table}
    USING ({_predicate(table)})
    WITH CHECK ({_predicate(table)});
"""
    for table in TABLES
)

DISABLE_SQL = "\n".join(
    f"""
DROP POLICY IF EXISTS school_isolation ON public.{table};
ALTER TABLE public.{table} DISABLE ROW LEVEL SECURITY;
"""
    for table in TABLES
)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0039_academic_calendar"),
    ]

    operations = [
        migrations.RunSQL(sql=ENABLE_SQL, reverse_sql=DISABLE_SQL),
    ]
