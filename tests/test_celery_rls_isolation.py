"""P2 guard tests for Celery/PostgreSQL RLS context isolation."""

import ast
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest
from django.db import DatabaseError

from core.celery_tasks import RLSIsolatedTask, TenantRLSTask, school_rls_scope
from core.rls import reset_rls_context


def test_worker_task_resets_rls_before_and_after_execution(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "core.celery_tasks.reset_rls_context",
        lambda: calls.append("reset"),
    )

    class ProbeTask(RLSIsolatedTask):
        name = "tests.rls_probe_success"

        @property
        def request(self):
            return SimpleNamespace(is_eager=False)

        def run(self):
            calls.append("run")
            return "ok"

    assert ProbeTask()() == "ok"
    assert calls == ["reset", "run", "reset"]


def test_worker_task_resets_rls_after_failure(monkeypatch):
    calls = []

    monkeypatch.setattr(
        "core.celery_tasks.reset_rls_context",
        lambda: calls.append("reset"),
    )

    class FailingTask(RLSIsolatedTask):
        name = "tests.rls_probe_failure"

        @property
        def request(self):
            return SimpleNamespace(is_eager=False)

        def run(self):
            calls.append("run")
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        FailingTask()()

    assert calls == ["reset", "run", "reset"]


def test_eager_task_uses_scoped_empty_context_and_restores_caller(monkeypatch):
    calls = []

    @contextmanager
    def fake_rls_context(value):
        calls.append(f"enter:{value}")
        try:
            yield
        finally:
            calls.append(f"exit:{value}")

    monkeypatch.setattr(
        "core.celery_tasks.rls_context",
        fake_rls_context,
    )
    monkeypatch.setattr(
        "core.celery_tasks.reset_rls_context",
        lambda: calls.append("unexpected-reset"),
    )

    class EagerProbeTask(RLSIsolatedTask):
        name = "tests.rls_probe_eager"

        @property
        def request(self):
            return SimpleNamespace(is_eager=True)

        def run(self):
            calls.append("run")
            return "ok"

    assert EagerProbeTask()() == "ok"
    assert calls == ["enter:", "run", "exit:"]


def test_eager_task_restores_caller_context_after_failure(monkeypatch):
    calls = []

    @contextmanager
    def fake_rls_context(value):
        calls.append(f"enter:{value}")
        try:
            yield
        finally:
            calls.append(f"exit:{value}")

    monkeypatch.setattr(
        "core.celery_tasks.rls_context",
        fake_rls_context,
    )

    class EagerFailingTask(RLSIsolatedTask):
        name = "tests.rls_probe_eager_failure"

        @property
        def request(self):
            return SimpleNamespace(is_eager=True)

        def run(self):
            calls.append("run")
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        EagerFailingTask()()

    assert calls == ["enter:", "run", "exit:"]


def test_reset_rls_context_sets_fail_closed_empty_value(monkeypatch):
    applied = []

    monkeypatch.setattr(
        "core.rls._apply_rls_context",
        lambda value: applied.append(value),
    )

    reset_rls_context()

    assert applied == [""]


def test_reset_rls_context_closes_connection_on_database_error(monkeypatch):
    closed = []

    def fail(_value):
        raise DatabaseError("set_config failed")

    monkeypatch.setattr("core.rls._apply_rls_context", fail)
    monkeypatch.setattr(
        "core.rls.connection.close",
        lambda: closed.append(True),
    )

    with pytest.raises(DatabaseError, match="set_config failed"):
        reset_rls_context()

    assert closed == [True]


def test_celery_app_uses_rls_isolated_task_base():
    from shschool.celery import app

    assert issubclass(app.Task, RLSIsolatedTask)


ROOT = Path(__file__).resolve().parents[1]
VALID_SCHOOL_ID = "00000000-0000-0000-0000-000000000001"


def test_tenant_worker_enters_school_context_between_resets(
    monkeypatch,
):
    events = []

    @contextmanager
    def fake_rls_context(value):
        events.append(("enter", value))
        try:
            yield
        finally:
            events.append(("exit", value))

    monkeypatch.setattr(
        "core.celery_tasks.rls_context",
        fake_rls_context,
    )
    monkeypatch.setattr(
        "core.celery_tasks.reset_rls_context",
        lambda: events.append(("reset", None)),
    )

    class TenantProbe(TenantRLSTask):
        name = "tests.tenant_worker_probe"

        @property
        def request(self):
            return SimpleNamespace(is_eager=False)

        def run(self, school_id):
            events.append(("run", school_id))
            return "ok"

    assert TenantProbe()(school_id=VALID_SCHOOL_ID) == "ok"

    assert events == [
        ("reset", None),
        ("enter", VALID_SCHOOL_ID),
        ("run", VALID_SCHOOL_ID),
        ("exit", VALID_SCHOOL_ID),
        ("reset", None),
    ]


def test_tenant_eager_nests_school_inside_fail_closed_scope(
    monkeypatch,
):
    events = []

    @contextmanager
    def fake_rls_context(value):
        events.append(("enter", value))
        try:
            yield
        finally:
            events.append(("exit", value))

    monkeypatch.setattr(
        "core.celery_tasks.rls_context",
        fake_rls_context,
    )
    monkeypatch.setattr(
        "core.celery_tasks.reset_rls_context",
        lambda: events.append(("unexpected_reset", None)),
    )

    class TenantProbe(TenantRLSTask):
        name = "tests.tenant_eager_probe"

        @property
        def request(self):
            return SimpleNamespace(is_eager=True)

        def run(self, school_id):
            events.append(("run", school_id))
            return "ok"

    assert TenantProbe()(school_id=VALID_SCHOOL_ID) == "ok"

    assert events == [
        ("enter", ""),
        ("enter", VALID_SCHOOL_ID),
        ("run", VALID_SCHOOL_ID),
        ("exit", VALID_SCHOOL_ID),
        ("exit", ""),
    ]


def test_tenant_task_rejects_missing_school_id(monkeypatch):
    events = []

    @contextmanager
    def fake_rls_context(value):
        events.append(("enter", value))
        try:
            yield
        finally:
            events.append(("exit", value))

    monkeypatch.setattr(
        "core.celery_tasks.rls_context",
        fake_rls_context,
    )

    class TenantProbe(TenantRLSTask):
        name = "tests.tenant_missing_school"

        @property
        def request(self):
            return SimpleNamespace(is_eager=True)

        def run(self, school_id=None):
            raise AssertionError("run must not execute")

    with pytest.raises(
        ValueError,
        match="requires school_id",
    ):
        TenantProbe()()

    assert events == [
        ("enter", ""),
        ("exit", ""),
    ]


def test_tenant_task_rejects_privileged_wildcard(monkeypatch):
    events = []

    @contextmanager
    def fake_rls_context(value):
        events.append(("enter", value))
        try:
            yield
        finally:
            events.append(("exit", value))

    monkeypatch.setattr(
        "core.celery_tasks.rls_context",
        fake_rls_context,
    )

    class TenantProbe(TenantRLSTask):
        name = "tests.tenant_wildcard"

        @property
        def request(self):
            return SimpleNamespace(is_eager=True)

        def run(self, school_id=None):
            raise AssertionError("run must not execute")

    with pytest.raises(
        ValueError,
        match="valid school UUID",
    ):
        TenantProbe()(school_id="*")

    assert events == [
        ("enter", ""),
        ("exit", ""),
    ]


def _function_map(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name: node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
    }


def _shared_task_decorator(function):
    for decorator in function.decorator_list:
        if (
            isinstance(decorator, ast.Call)
            and isinstance(decorator.func, ast.Name)
            and decorator.func.id == "shared_task"
        ):
            return decorator

    raise AssertionError(f"{function.name} has no @shared_task decorator")


def test_all_tenant_notification_tasks_require_tenant_base_and_school_id():
    path = ROOT / "notifications" / "tasks.py"
    functions = _function_map(path)

    expected = {
        "send_email_task",
        "send_sms_task",
        "notify_absence_task",
        "notify_fail_task",
        "notify_behavior_task",
        "send_push_task",
        "send_push_to_school_task",
        "hub_send_notification_task",
    }

    for function_name in expected:
        function = functions[function_name]

        arg_names = {arg.arg for arg in (list(function.args.args) + list(function.args.kwonlyargs))}

        assert "school_id" in arg_names, function_name

        decorator = _shared_task_decorator(function)

        bases = [keyword for keyword in decorator.keywords if keyword.arg == "base"]

        assert len(bases) == 1, function_name
        value = bases[0].value

        assert isinstance(value, ast.Name), function_name
        assert value.id == "TenantRLSTask", function_name


def test_all_notify_behavior_call_sites_propagate_school_id():
    path = ROOT / "behavior" / "views.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    calls = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func

        if (
            isinstance(func, ast.Attribute)
            and func.attr == "delay"
            and isinstance(func.value, ast.Name)
            and func.value.id == "notify_behavior_task"
        ):
            calls.append(node)

    assert len(calls) == 2

    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords if keyword.arg}

        assert "school_id" in keywords


def test_every_nested_push_task_call_propagates_school_id():
    path = ROOT / "notifications" / "tasks.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))

    calls = []

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        func = node.func

        if (
            isinstance(func, ast.Attribute)
            and func.attr == "delay"
            and isinstance(func.value, ast.Name)
            and func.value.id == "send_push_task"
        ):
            calls.append(node)

    assert len(calls) == 3

    for call in calls:
        keywords = {keyword.arg for keyword in call.keywords if keyword.arg}

        assert "school_id" in keywords


def test_push_subscription_lookup_is_explicitly_school_scoped():
    path = ROOT / "notifications" / "tasks.py"
    functions = _function_map(path)
    function = functions["send_push_task"]

    filters = []

    for node in ast.walk(function):
        if not isinstance(node, ast.Call):
            continue

        func = node.func

        if (
            isinstance(func, ast.Attribute)
            and func.attr == "filter"
            and isinstance(func.value, ast.Attribute)
            and func.value.attr == "objects"
            and isinstance(func.value.value, ast.Name)
            and func.value.value.id == "PushSubscription"
        ):
            filters.append(node)

    assert filters

    keywords = {keyword.arg for keyword in filters[0].keywords if keyword.arg}

    assert "user_id" in keywords
    assert "school_id" in keywords
    assert "is_active" in keywords


def test_school_rls_scope_enters_canonical_context(monkeypatch):
    events = []

    @contextmanager
    def fake_rls_context(value):
        events.append(("enter", value))
        try:
            yield
        finally:
            events.append(("exit", value))

    monkeypatch.setattr(
        "core.celery_tasks.rls_context",
        fake_rls_context,
    )

    with school_rls_scope(VALID_SCHOOL_ID) as canonical:
        events.append(("body", canonical))

    assert events == [
        ("enter", VALID_SCHOOL_ID),
        ("body", VALID_SCHOOL_ID),
        ("exit", VALID_SCHOOL_ID),
    ]


def test_school_rls_scope_rejects_invalid_and_wildcard():
    with pytest.raises(
        ValueError,
        match="valid school UUID",
    ):
        with school_rls_scope("*"):
            raise AssertionError("must not enter wildcard scope")

    with pytest.raises(
        ValueError,
        match="valid school UUID",
    ):
        with school_rls_scope("not-a-uuid"):
            raise AssertionError("must not enter invalid scope")


def test_all_multi_school_tasks_enter_per_school_scope():
    expected = {
        "operations/tasks.py": {
            "revoke_expired_temp_permissions",
            "generate_daily_sessions_task",
            "check_license_expiry_task",
        },
        "behavior/tasks.py": {
            "weekly_risk_check",
        },
        "analytics/tasks.py": {
            "send_monthly_kpi_report",
        },
        "notifications/tasks.py": {
            "send_pending_absence_alerts_task",
            "check_breach_deadlines_task",
        },
    }

    for relative_path, function_names in expected.items():
        path = ROOT / relative_path
        functions = _function_map(path)

        for function_name in function_names:
            function = functions[function_name]

            school_scopes = [
                node
                for node in ast.walk(function)
                if isinstance(node, ast.With)
                and any(
                    isinstance(item.context_expr, ast.Call)
                    and isinstance(
                        item.context_expr.func,
                        ast.Name,
                    )
                    and item.context_expr.func.id == "school_rls_scope"
                    for item in node.items
                )
            ]

            assert school_scopes, (
                relative_path,
                function_name,
            )


def test_multi_school_task_sources_never_request_wildcard():
    paths = [
        ROOT / "operations" / "tasks.py",
        ROOT / "behavior" / "tasks.py",
        ROOT / "analytics" / "tasks.py",
        ROOT / "notifications" / "tasks.py",
    ]

    for path in paths:
        source = path.read_text(encoding="utf-8")

        assert 'rls_context("*")' not in source
        assert "rls_context('*')" not in source
        assert 'school_rls_scope("*")' not in source
        assert "school_rls_scope('*')" not in source


def test_all_current_beat_targets_are_in_multi_school_scope_set():
    celery_source = (ROOT / "shschool" / "celery.py").read_text(encoding="utf-8")

    beat_targets = {
        "notifications.send_pending_absence_alerts_all_schools",
        "notifications.check_breach_deadlines",
        "analytics.send_monthly_kpi_report",
        "operations.generate_daily_sessions",
        "operations.revoke_expired_temp_permissions",
        "behavior.weekly_risk_check",
    }

    for target in beat_targets:
        assert f'"task": "{target}"' in celery_source


def _function_source(relative_path, function_name):
    path = ROOT / relative_path
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)

    function = next(
        node
        for node in tree.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
        and node.name == function_name
    )

    lines = source.splitlines()
    return "\n".join(lines[function.lineno - 1 : function.end_lineno])


def test_compliance_and_expiry_tasks_do_not_skip_inactive_schools():
    breach_source = _function_source(
        "notifications/tasks.py",
        "check_breach_deadlines_task",
    )
    revoke_source = _function_source(
        "operations/tasks.py",
        "revoke_expired_temp_permissions",
    )

    for source in (
        breach_source,
        revoke_source,
    ):
        assert "School.objects.all()" in source
        assert "School.objects.filter(is_active=True)" not in source

    # Preserve the pre-RLS task return contract.
    assert '"checked_at"' not in breach_source


def test_license_expiry_preserves_first_active_membership_contract():
    source = _function_source(
        "operations/tasks.py",
        "check_license_expiry_task",
    )

    assert "School.objects.filter(is_active=True)" not in source
    assert "School.objects.all()" not in source
    assert "for school in " not in source

    assert "Membership.objects.filter(" in source
    assert "user=user" in source
    assert "is_active=True" in source
    assert ".first()" in source
    assert "with school_rls_scope(school.id):" in source

    assert source.index("membership =") < source.index("with school_rls_scope")
