"""[W-20261010-032] عزلُ تفضيلات الخانات بين المدارس (RLS) بصيغة `operations/0069` — الهويّةُ من دور الاتصال."""

from contextlib import contextmanager

import pytest
from django.db import DatabaseError, connection, transaction

from operations.models import TeacherPeriodPreference
from tests.conftest import SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

PROBE_ROLE = "w032_period_pref_probe"
TABLE = "operations_teacherperiodpreference"


@contextmanager
def _as_tenant(school_id):
    if connection.vendor != "postgresql":
        pytest.skip("عقدُ RLS خاصٌّ بـPostgreSQL")
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            DO $$
            BEGIN
                CREATE ROLE {PROBE_ROLE} NOSUPERUSER NOBYPASSRLS NOINHERIT;
            EXCEPTION WHEN duplicate_object THEN
                NULL;
            END $$;
            """
        )
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {PROBE_ROLE}")
        cursor.execute(f"GRANT SELECT ON public.app_rls_role_school TO {PROBE_ROLE}")
        cursor.execute(f"GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA public TO {PROBE_ROLE}")
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{TABLE} TO {PROBE_ROLE}")
        cursor.execute(
            """
            INSERT INTO public.app_rls_role_school (db_role, school_id)
            VALUES (session_user, %s)
            ON CONFLICT (db_role) DO UPDATE SET school_id = EXCLUDED.school_id
            """,
            [str(school_id)],
        )
        cursor.execute(f"SET ROLE {PROBE_ROLE}")
    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


def _row(school, teacher):
    return TeacherPeriodPreference.objects.create(
        teacher=teacher,
        school=school,
        academic_year="2026-2027",
        day_of_week=0,
        period_number=1,
        preference="prefer",
    )


def test_a_school_sees_only_its_own_period_preferences():
    a, b = SchoolFactory(), SchoolFactory()
    _row(a, UserFactory())
    _row(b, UserFactory())
    with _as_tenant(b.pk), connection.cursor() as cursor:
        cursor.execute(f"SELECT school_id FROM public.{TABLE}")
        seen = {str(row[0]) for row in cursor.fetchall()}
    assert seen == {str(b.pk)}


def test_writing_a_row_for_another_school_is_refused_by_with_check():
    a, b = SchoolFactory(), SchoolFactory()
    teacher = UserFactory()
    with _as_tenant(b.pk):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO public.{TABLE}
                    (id, school_id, teacher_id, academic_year, day_of_week, period_number, preference, created_at, updated_at)
                VALUES (gen_random_uuid(), %s, %s, '2026-2027', 0, 1, 'prefer', now(), now())
                """,
                [str(a.pk), str(teacher.pk)],
            )


def test_the_table_has_the_canonical_policy():
    with connection.cursor() as cursor:
        cursor.execute(
            f"SELECT relrowsecurity FROM pg_class WHERE oid = 'public.{TABLE}'::regclass"
        )
        assert cursor.fetchone()[0] is True
        cursor.execute("SELECT policyname FROM pg_policies WHERE tablename = %s", [TABLE])
        assert [row[0] for row in cursor.fetchall()] == ["school_isolation"]
