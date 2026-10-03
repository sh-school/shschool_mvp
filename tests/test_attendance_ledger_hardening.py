"""[LEGAL] تصليبُ سجلّ رصد المعلّم: المحوُ لا يفشل صامتاً تحت RLS، والسباقُ لا يصير 500، والصلاحيّاتُ لا تتّسع (W-20261002-020، شروطُ 0105).

- **المحو تحت RLS:** هويّةُ المستأجِر تأتي من **دور القاعدة** (`app_rls_school()` يقرأ `session_user`، `core/0037`) لا من
  سياقٍ يضبطه التطبيق. فدورُ مدرسة «ب» الذي يحذف صفوفَ مدرسة «أ» يرى **صفراً** ويرجع عدّادٌ 0 دون خطأ، ويُقال «تمّ
  المحو» والصفوفُ باقية — إخفاقٌ في حقّ المحو (PDPPL م.18). فالدالّةُ ترفض ألّا يطابق مستأجرُ الدور مدرسةَ الطلب،
  وتتحقّق بعد الحذف أنّه لم يبقَ شيءٌ، وإلّا تُلغى المعاملةُ كلُّها.
- **سباقُ الكتابة:** اعتمادٌ يجد الصفَّ غائباً ثمّ يسبقه مشرفٌ بكتابته فيصطدم القيدُ الفريد — يصير `EntryConflictError` لا 500.
- **الصلاحيّات:** دورُ التطبيق لا يملك `TRUNCATE` (مشغّلُ الصفّ لا يمنعه) — فحصٌ ساكنٌ على ملفّ التزويد وآخرُ تشغيليّ.
- **الوقت:** أيُّ view لا يمرّر `now` من الطلب إلى `submit_entry`/`decide_entry` (معاملُ اختبارٍ لا مدخلُ مستخدم).
"""

import ast
import pathlib
import re
from contextlib import contextmanager

import pytest
from django.db import connection

from operations.attendance_entries import (
    EntryConflictError,
    EntryError,
    decide_entry,
    erase_attendance_ledger,
    submit_entry,
)
from operations.models import AttendanceDecision, AttendanceEntry, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at
from tests.conftest import SchoolFactory

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parent.parent
LEDGER_TABLES = ("operations_attendanceentry", "operations_attendancedecision")
PROBE_ROLE = "w020_ledger_probe"
NOW = at(7, 30)


def _skip_unless_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("عقدُ RLS خاصٌّ بـPostgreSQL")


@contextmanager
def _as_tenant(school_id):
    """دورٌ غيرُ متميّزٍ مربوطٌ بمدرسة (يُحوَّل إليه) — RLS لا يُخضع superuser ولا BYPASSRLS، فبلا هذا تمرّ الاختباراتُ عبثاً."""
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
        cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {PROBE_ROLE}")
        for table in LEDGER_TABLES:
            cursor.execute(f"GRANT SELECT, DELETE ON public.{table} TO {PROBE_ROLE}")
        cursor.execute(f"GRANT SELECT, INSERT ON public.core_auditlog TO {PROBE_ROLE}")
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


def _ledger_for(kid, session, teacher, holder):
    entry = submit_entry(teacher, session, kid, "absent", now=NOW)
    decide_entry(holder, entry, approve=True)
    return entry


# ══════════════════════════════════════════════════════════════════
# المحو تحت RLS
# ══════════════════════════════════════════════════════════════════


def test_erasure_works_when_the_role_tenant_matches_the_request_school(
    school, session, teacher, holder, kid
):
    _skip_unless_postgres()
    _ledger_for(kid, session, teacher, holder)
    with _as_tenant(school.pk):
        counts = erase_attendance_ledger(kid, school=school)
    assert counts == {"decisions": 1, "entries": 1}
    assert not AttendanceEntry.objects.filter(student=kid).exists()


def test_erasure_refuses_loudly_when_the_role_tenant_is_another_school(
    school, session, teacher, holder, kid
):
    """دورُ مدرسةٍ أخرى يرى صفراً: لا «تمّ المحو» الكاذب — استثناءٌ يُلغي المعاملةَ وتبقى الصفوف."""
    _skip_unless_postgres()
    _ledger_for(kid, session, teacher, holder)
    other = SchoolFactory()
    with _as_tenant(other.pk), pytest.raises(EntryError) as caught:
        erase_attendance_ledger(kid, school=school)
    assert caught.value.code == "erasure_wrong_tenant"
    assert AttendanceEntry.objects.filter(student=kid).count() == 1
    assert AttendanceDecision.objects.filter(entry__student=kid).count() == 1


def test_erasure_flag_is_closed_even_when_it_refuses(school, session, teacher, holder, kid):
    """الفشلُ لا يترك العلَمَ مفتوحاً للباقي في المعاملة."""
    _skip_unless_postgres()
    _ledger_for(kid, session, teacher, holder)
    other = SchoolFactory()
    with _as_tenant(other.pk), pytest.raises(EntryError):
        erase_attendance_ledger(kid, school=school)
    with connection.cursor() as cursor:
        cursor.execute("SELECT COALESCE(current_setting('app.attendance_erasure', true), '')")
        assert cursor.fetchone()[0] in ("", "off")


def test_the_ledger_tables_carry_a_school_isolation_policy(school):
    _skip_unless_postgres()
    with connection.cursor() as cursor:
        for table in LEDGER_TABLES:
            cursor.execute(
                "SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(%s)",
                [f"public.{table}"],
            )
            assert cursor.fetchone()[0] is True, table
            cursor.execute(
                "SELECT count(*) FROM pg_policies WHERE tablename = %s AND policyname = 'school_isolation'",
                [table],
            )
            assert cursor.fetchone()[0] == 1, table


def test_the_ledger_rows_of_another_school_are_invisible_to_a_tenant_role(
    school, session, teacher, holder, kid
):
    """RLS يمنع فعلاً: دورُ مدرسةٍ أخرى لا يرى إدخالاتِ هذه."""
    _skip_unless_postgres()
    _ledger_for(kid, session, teacher, holder)
    other = SchoolFactory()
    with _as_tenant(other.pk):
        assert AttendanceEntry.objects.count() == 0
    with _as_tenant(school.pk):
        assert AttendanceEntry.objects.count() == 1


# ══════════════════════════════════════════════════════════════════
# سباقُ الكتابة في الرصد المعتمَد
# ══════════════════════════════════════════════════════════════════


def test_a_supervisor_row_that_wins_the_race_becomes_a_conflict_not_a_500(
    monkeypatch, session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=NOW)
    StudentAttendance.objects.create(
        session=session,
        student=kid,
        school=session.school,
        status="present",
        source="supervisor",
        marked_by=holder,
    )
    # الاعتمادُ لا يجد الصفَّ عند القفل (سبقه المشرفُ بعده) فيصطدم بالقيد الفريد عند الإنشاء.
    monkeypatch.setattr(
        StudentAttendance.objects,
        "select_for_update",
        lambda **kw: StudentAttendance.objects.none(),
    )
    with pytest.raises(EntryConflictError):
        decide_entry(holder, entry, approve=True)
    assert not AttendanceDecision.objects.exists()
    assert StudentAttendance.objects.get(session=session, student=kid).source == "supervisor"


# ══════════════════════════════════════════════════════════════════
# الصلاحيّات: لا TRUNCATE
# ══════════════════════════════════════════════════════════════════


def test_the_provisioning_script_never_grants_truncate_or_all():
    """مشغّلُ الصفّ لا يمنع TRUNCATE — فلا يُمنح دورُ التطبيق صلاحيّتَه ولا ALL."""
    sql = (ROOT / "scripts" / "provision_rls_app_role.sql").read_text(encoding="utf-8")
    grants = [
        line
        for line in sql.splitlines()
        if re.match(r"\s*GRANT\b", line, re.IGNORECASE) and "shschool_app" in line
    ]
    assert grants, "لم أجد منحاً لدور التطبيق — تغيّر الملفّ؟ حدِّث الاختبار"
    for line in grants:
        assert not re.search(r"\bTRUNCATE\b", line, re.IGNORECASE), line
        assert not re.search(r"\bALL\s+PRIVILEGES\b", line, re.IGNORECASE), line
        assert not re.search(
            r"\bGRANT\s+ALL\s+ON\s+(?!ALL\s+(TABLES|SEQUENCES|FUNCTIONS))", line, re.IGNORECASE
        ), line


def test_the_runtime_role_cannot_truncate_the_ledger_when_it_exists():
    _skip_unless_postgres()
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'shschool_app'")
        if cursor.fetchone() is None:
            pytest.skip("دورُ التطبيق shschool_app غيرُ موجودٍ في هذه القاعدة")
        for table in LEDGER_TABLES:
            cursor.execute(
                "SELECT has_table_privilege('shschool_app', %s, 'TRUNCATE')", [f"public.{table}"]
            )
            assert cursor.fetchone()[0] is False, table


# ══════════════════════════════════════════════════════════════════
# الوقت: لا يُمرَّر من الطلب
# ══════════════════════════════════════════════════════════════════


def _calls_with_request_now():
    offenders = []
    skip = {"tests", "migrations", "node_modules", ".venv", "venv", ".claude", "staticfiles"}
    for path in ROOT.rglob("*.py"):
        rel = path.relative_to(ROOT)
        if set(rel.parts) & skip or path.name.startswith("test_") or path.name == "conftest.py":
            continue
        text = path.read_text(encoding="utf-8")
        if "submit_entry" not in text and "decide_entry" not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if not isinstance(node, ast.Call):
                continue
            name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
            if name not in {"submit_entry", "decide_entry"}:
                continue
            for keyword in node.keywords:
                if keyword.arg == "now" and "request" in ast.unparse(keyword.value):
                    offenders.append(f"{rel.as_posix()}:{node.lineno}")
    return offenders


def test_no_view_passes_the_time_from_the_request():
    assert _calls_with_request_now() == []
