import json
from pathlib import Path

import pytest
from django.core.management.base import CommandError

from core.management.commands import verify_runtime_db_role as runtime_role

ROOT = Path(__file__).resolve().parents[1]


class FakeCursor:
    def __init__(self, rows):
        self._rows = iter(rows)

    def execute(self, *args, **kwargs):
        return None

    def fetchone(self):
        return next(self._rows)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class FakeConnection:
    def __init__(self, rows, vendor="postgresql"):
        self.vendor = vendor
        self._rows = rows

    def cursor(self):
        return FakeCursor(self._rows)


def runtime_rows(
    *,
    role="shschool_app",
    superuser=False,
    bypass_rls=False,
    can_login=True,
    inherit=False,
    context=None,
    rls_enabled=True,
    policy_count=1,
    owned_public_tables=0,
):
    return [
        (role,),
        (
            superuser,
            bypass_rls,
            can_login,
            inherit,
        ),
        (context,),
        (rls_enabled,),
        (policy_count,),
        (owned_public_tables,),
    ]


def run_verifier(monkeypatch, **overrides):
    rows = runtime_rows(**overrides)
    monkeypatch.setattr(
        runtime_role,
        "connection",
        FakeConnection(rows),
    )
    runtime_role.Command().handle()


def test_runtime_role_accepts_safe_rls_worker(monkeypatch):
    run_verifier(monkeypatch)


def test_runtime_role_rejects_non_postgresql(monkeypatch):
    monkeypatch.setattr(
        runtime_role,
        "connection",
        FakeConnection([], vendor="sqlite"),
    )

    with pytest.raises(CommandError) as exc:
        runtime_role.Command().handle()

    assert "requires PostgreSQL" in str(exc.value)


def test_runtime_role_rejects_wrong_database_role(monkeypatch):
    with pytest.raises(CommandError) as exc:
        run_verifier(monkeypatch, role="postgres")

    assert "Unsafe runtime DB role" in str(exc.value)


def test_runtime_role_rejects_superuser(monkeypatch):
    with pytest.raises(CommandError) as exc:
        run_verifier(monkeypatch, superuser=True)

    assert "superuser=true" in str(exc.value)


def test_runtime_role_rejects_bypassrls(monkeypatch):
    with pytest.raises(CommandError) as exc:
        run_verifier(monkeypatch, bypass_rls=True)

    assert "bypassrls=true" in str(exc.value)


def test_runtime_role_rejects_non_login_role(monkeypatch):
    with pytest.raises(CommandError) as exc:
        run_verifier(monkeypatch, can_login=False)

    assert "cannot login" in str(exc.value)


def test_runtime_role_rejects_inheriting_role(monkeypatch):
    with pytest.raises(CommandError) as exc:
        run_verifier(
            monkeypatch,
            inherit=True,
        )

    assert "inherit=true" in str(exc.value)


def test_runtime_role_rejects_missing_table_rls(monkeypatch):
    with pytest.raises(CommandError) as exc:
        run_verifier(monkeypatch, rls_enabled=False)

    assert "RLS is not enabled" in str(exc.value)


@pytest.mark.parametrize("policy_count", [0, 2])
def test_runtime_role_requires_exactly_one_canonical_policy(
    monkeypatch,
    policy_count,
):
    with pytest.raises(CommandError) as exc:
        run_verifier(monkeypatch, policy_count=policy_count)

    assert "Expected exactly one" in str(exc.value)


def test_runtime_role_rejects_owned_public_tables(monkeypatch):
    with pytest.raises(CommandError) as exc:
        run_verifier(
            monkeypatch,
            owned_public_tables=1,
        )

    assert "owns public tables" in str(exc.value)


def test_runtime_role_rejects_inherited_tenant_context(monkeypatch):
    with pytest.raises(CommandError) as exc:
        run_verifier(
            monkeypatch,
            context="00000000-0000-0000-0000-000000000001",
        )

    assert "inherited a non-empty tenant RLS context" in str(exc.value)


def test_worker_script_is_fail_closed_and_not_a_web_release_process():
    script = (ROOT / "scripts" / "railway-worker.sh").read_text(encoding="utf-8")

    required = (
        "REDIS_URL is required for the Celery worker.",
        "APP_DB_PASSWORD is required for the Celery worker.",
        "unset DATABASE_URL",
        "export DB_USER=shschool_app",
        'export DB_PASSWORD="$APP_DB_PASSWORD"',
        "python manage.py verify_runtime_db_role",
        "exec celery -A shschool worker",
    )

    for fragment in required:
        assert fragment in script

    forbidden = (
        "python manage.py migrate",
        "collectstatic",
        "daphne",
        "provision_rls_role",
    )

    for fragment in forbidden:
        assert fragment not in script

    # Creating a worker must not activate async producers in the web app.
    assert "CELERY_ASYNC_ENABLED" not in script


def test_worker_railway_config_is_worker_only():
    config = json.loads((ROOT / "railway.worker.json").read_text(encoding="utf-8"))

    assert config["build"]["builder"] == "DOCKERFILE"
    assert config["build"]["dockerfilePath"] == "Dockerfile"

    deploy = config["deploy"]

    assert deploy["startCommand"] == "bash scripts/railway-worker.sh"
    assert deploy["restartPolicyType"] == "ON_FAILURE"
    assert deploy["restartPolicyMaxRetries"] == 3

    # A Celery worker has no HTTP health endpoint.
    assert "healthcheckPath" not in deploy
