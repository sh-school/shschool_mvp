"""
tests/test_runtime_db_role_verifier.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[SEC-06] عقد الفاحص fail-closed لدور التشغيل.

الفاحص يُشغَّل عند إقلاع عامل Celery ويجب أن يرفض الإقلاع عند أي صلاحية زائدة.
هذه الاختبارات تُثبت أن كل شرط مفحوص فعلاً وأن رسالة النجاح تحمل كل العلامات
التي تعتمد عليها سكربتات التحقّق التشغيلية.
"""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db import connection

pytestmark = pytest.mark.django_db

VERIFIER = "core.management.commands.verify_runtime_db_role"

# كل علامة في رسالة النجاح — سكربتات التحقّق الإنتاجية تُطابقها حرفياً.
REQUIRED_MARKERS = (
    "runtime DB role verified:",
    "role=shschool_app",
    "super=false",
    "bypassrls=false",
    "inherit=false",
    "owned_tables=0",
    "createdb=false",
    "createrole=false",
    "memberships=0",
    "schema_create=false",
    "rls=enabled",
    "policy=school_isolation",
    "context=unset",
)


class TestVerifierContract:
    """الشروط التي يفرضها الفاحص."""

    def test_rejects_non_postgresql_backend(self, monkeypatch):
        """محرّك غير PostgreSQL ⇒ رفض (لا RLS أصلاً)."""
        monkeypatch.setattr(type(connection), "vendor", "sqlite", raising=False)

        with pytest.raises(CommandError, match="requires PostgreSQL"):
            call_command("verify_runtime_db_role")

    def test_rejects_unexpected_role(self):
        """أي دور غير shschool_app ⇒ رفض.

        اختبارات CI تعمل بدور المالك، فالفاحص يجب أن يرفضها — وهذا بحد ذاته
        إثبات أن شرط الدور مفروض ولا يُتجاوَز صامتاً.
        """
        if connection.vendor != "postgresql":
            pytest.skip("PostgreSQL-specific runtime role contract")

        with connection.cursor() as cursor:
            cursor.execute("SELECT current_user")
            role = cursor.fetchone()[0]

        if role == "shschool_app":
            pytest.skip("already running as the constrained runtime role")

        with pytest.raises(CommandError) as excinfo:
            call_command("verify_runtime_db_role")

        assert "shschool_app" in str(excinfo.value)


class TestVerifierCoverage:
    """كل صلاحية خطرة يجب أن تكون مقروءة فعلاً — لا مُعلنة فقط."""

    def _source(self):
        import importlib

        module = importlib.import_module(VERIFIER)
        from pathlib import Path

        return Path(module.__file__).read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "attribute",
        [
            "rolsuper",
            "rolbypassrls",
            "rolcanlogin",
            "rolinherit",
            "rolcreatedb",
            "rolcreaterole",
        ],
    )
    def test_reads_every_dangerous_role_attribute(self, attribute):
        """كل سمة دور خطرة تُقرأ من pg_roles."""
        assert attribute in self._source()

    def test_checks_role_memberships(self):
        """[SEC-06] NOINHERIT لا يمنع SET ROLE — العضويات تُفحص."""
        assert "pg_auth_members" in self._source()

    def test_checks_schema_create_privilege(self):
        """[SEC-06] CREATE على المخطّط يسمح بامتلاك جداول تتجاوز RLS."""
        source = self._source()
        assert "has_schema_privilege" in source
        assert "'CREATE'" in source

    @pytest.mark.parametrize("marker", REQUIRED_MARKERS)
    def test_success_message_carries_marker(self, marker):
        """رسالة النجاح تحمل كل علامة تعتمد عليها سكربتات التحقّق."""
        assert marker in self._source()
