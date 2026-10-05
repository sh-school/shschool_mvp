"""[W-20261004-018] عزلُ ملخّص الخروج اليوميّ بين المدارس (RLS، بياناتُ قاصرين) — حكمُ 0104 P1.

الجدولُ `operations_dailyexittally` يحمل `school_id` وسياسةَ `school_isolation` بالصيغة المعتمَدة بعد `core/0037` (هجرة operations/0069):
هويّةُ المستأجِر من **دور الاتصال** لا من متغيّر جلسة. والاختبارُ بدورٍ غيرِ متميّزٍ مربوطٍ بمدرسةٍ (RLS لا يُخضع superuser).
"""

import datetime as dt
from contextlib import contextmanager

import pytest
from django.db import DatabaseError, connection, transaction

from operations.models import DailyExitTally
from tests.conftest import SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

PROBE_ROLE = "w018_tally_probe"
TABLE = "operations_dailyexittally"
DAY = dt.date(2026, 9, 13)


@contextmanager
def _as_tenant(school_id):
    """دورٌ غيرُ متميّزٍ مربوطٌ بمدرسة (يُحوَّل إليه) — كاختبار سجلّ الرصد (`test_attendance_ledger_hardening`)."""
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
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE ON public.{TABLE} TO {PROBE_ROLE}")
        for table in ("operations_classexit", "operations_session"):
            cursor.execute(f"GRANT SELECT ON public.{table} TO {PROBE_ROLE}")
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


def _tally(school, student):
    return DailyExitTally.objects.create(
        school=school, student=student, date=DAY, exit_count=1, total_seconds=300
    )


def test_a_school_sees_only_its_own_daily_tallies():
    a, b = SchoolFactory(), SchoolFactory()
    kid_a, kid_b = UserFactory(), UserFactory()
    _tally(a, kid_a)
    _tally(b, kid_b)
    with _as_tenant(b.pk), connection.cursor() as cursor:
        cursor.execute(f"SELECT school_id FROM public.{TABLE}")
        seen = {str(row[0]) for row in cursor.fetchall()}
    assert seen == {str(b.pk)}  # مدرسةُ «ب» لا ترى صفَّ «أ»


def test_writing_a_row_for_another_school_is_refused_by_with_check():
    a, b = SchoolFactory(), SchoolFactory()
    kid = UserFactory()
    with _as_tenant(b.pk):
        with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                f"""
                INSERT INTO public.{TABLE} (id, school_id, student_id, date, exit_count, total_seconds, by_destination, updated_at)
                VALUES (gen_random_uuid(), %s, %s, %s, 1, 1, '{{}}'::jsonb, now())
                """,
                [str(a.pk), str(kid.pk), DAY],
            )


def test_the_table_has_the_canonical_policy():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity FROM pg_class WHERE oid = 'public.operations_dailyexittally'::regclass"
        )
        assert cursor.fetchone()[0] is True
        cursor.execute(
            "SELECT policyname FROM pg_policies WHERE tablename = 'operations_dailyexittally'"
        )
        assert [row[0] for row in cursor.fetchall()] == ["school_isolation"]


def test_refresh_tally_writes_under_the_tenant_role_of_its_own_school():
    """حكمُ 0104: كتابةُ الخدمة (refresh_tally) تنجح بدور المدرسة نفسِها بعد تفعيل RLS ولا تتعطّل صامتةً؛ ومدرسةٌ أخرى لا تكتب لغيرها."""
    from operations.class_exit import refresh_tally

    school = SchoolFactory()
    kid = UserFactory()
    # الصفُّ المصدر (ClassExit) يُكتب بدور المالك العاديّ؛ ثمّ يُعاد حسابُ الملخّص بدور المدرسة
    DailyExitTally.objects.filter(student=kid).delete()
    with _as_tenant(school.pk):
        tally = refresh_tally(school, kid, DAY)
    assert (tally.school_id, tally.exit_count) == (school.pk, 0)
    other = SchoolFactory()
    with _as_tenant(other.pk):
        with pytest.raises(DatabaseError), transaction.atomic():
            refresh_tally(school, kid, DAY)  # سطرُ مدرسةٍ أخرى لا يُكتب بدورٍ غير دورها
