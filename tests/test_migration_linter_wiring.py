"""[CI] مدقّق الهجرات موصولٌ فعلاً — لا حارسٌ يُعرَّف ولا يُشغَّل (P4-1).

كانت هجرةٌ تحذف عموداً (2026-09-11: `spread_days_scope`) تُدمج بلا اعتراض، فأسقطت
ثماني صفحاتٍ في كلّ شجرةٍ أخرى — العلاجُ ليس تجنّب الحذف بل بوّابةٌ تسأل عنه أوّلاً.
هذا الاختبار لا يشغّل `manage.py lintmigrations` (يحتاج تاريخ git وقاعدة migrate
كاملة، مسؤوليّةُ وظيفة migration-linter في quality-gate.yml)؛ يثبت أنّ الآلةَ
التي تلك الوظيفةُ تستدعيها فعلاً تُسقط SQL يحذف عموداً — لا تُخمَّن سلوكُها.
"""

import pytest

django_migration_linter = pytest.importorskip("django_migration_linter")

from django_migration_linter.sql_analyser.analyser import analyse_sql_statements  # noqa: E402
from django_migration_linter.sql_analyser.postgresql import PostgresqlAnalyser  # noqa: E402


def _errors(sql_statements: list[str]):
    errors, _ignored, _warnings = analyse_sql_statements(PostgresqlAnalyser, sql_statements)
    return {issue.code for issue in errors}


def test_dropping_a_column_is_an_error():
    sql = ['ALTER TABLE "operations_session" DROP COLUMN "spread_days_scope";']

    assert "DROP_COLUMN" in _errors(sql)


def test_dropping_a_table_is_an_error():
    sql = ['DROP TABLE "operations_stale";']

    assert "DROP_TABLE" in _errors(sql)


def test_renaming_a_column_is_an_error():
    sql = ['ALTER TABLE "core_customuser" RENAME COLUMN "phone" TO "mobile";']

    assert any("RENAME" in code for code in _errors(sql))


def test_adding_a_not_null_column_without_a_default_is_an_error():
    sql = ['ALTER TABLE "core_customuser" ADD COLUMN "middle_name" varchar(50) NOT NULL;']

    assert "NOT_NULL" in _errors(sql)


def test_adding_a_column_with_a_default_is_not_flagged():
    """التوسيع — الخطوة الأولى من Expand/Contract — يمرّ بلا اعتراض."""
    sql = [
        'ALTER TABLE "core_customuser" ADD COLUMN "middle_name" varchar(50) ' "DEFAULT '' NOT NULL;"
    ]

    assert _errors(sql) == set()


def test_the_app_is_registered_only_when_the_package_is_installed():
    """التسجيلُ مشروطٌ (settings/testing.py) — فبيئةٌ بلا الحزمة لا تُكسَر."""
    from django.apps import apps

    assert apps.is_installed("django_migration_linter")
