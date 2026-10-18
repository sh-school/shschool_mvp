"""منطقُ فحص البيئة المحلّيّة بمحاكاة مخرجات docker لا بتشغيله (W-20261017-017)."""

import importlib.util
import pathlib
import sys

_spec = importlib.util.spec_from_file_location(
    "env_health", pathlib.Path(__file__).resolve().parents[1] / "scripts" / "env_health.py"
)
eh = importlib.util.module_from_spec(_spec)
sys.modules["env_health"] = eh
_spec.loader.exec_module(eh)

PS_OK = (
    "shschool-dev-db\tUp 3 hours (healthy)\t0.0.0.0:5433->5432/tcp, [::]:5433->5432/tcp\n"
    "schoolos-main-preview-a-web-1\tUp 2 minutes (healthy)\t0.0.0.0:8500->8000/tcp, [::]:8500->8000/tcp\n"
    "schoolos-main-preview-a-worker-1\tUp 2 minutes\t\n"
)


def fake_run(ps: str, role: str = "OK", calls: list | None = None):
    def run(cmd):
        if calls is not None:
            calls.append(cmd)
        if cmd[:2] == ["docker", "ps"]:
            return 0, ps
        if cmd[:2] == ["docker", "exec"]:
            return 0, role + "\n"
        return 0, ""

    return run


def probe_up(url):
    return True, "HTTP 200"


def probe_down(url):
    return False, "URLError"


def problems(report):
    return [f.problem for f in report.findings]


def test_everything_healthy():
    r = eh.collect(fake_run(PS_OK), probe_up)
    assert r.findings == []
    assert eh.render(r).count("✔") == 1


def test_stopped_container_detected():
    ps = PS_OK.replace("Up 2 minutes (healthy)", "Exited (1) 5 minutes ago")
    r = eh.collect(fake_run(ps), probe_up)
    assert any("متوقّفة" in p for p in problems(r))


def test_unhealthy_container_detected():
    ps = PS_OK.replace("Up 2 minutes (healthy)", "Up 58 minutes (unhealthy)")
    r = eh.collect(fake_run(ps), probe_up)
    assert any("unhealthy" in p for p in problems(r))


def test_restarting_container_detected():
    ps = PS_OK.replace("Up 2 minutes (healthy)", "Restarting (1) 4 seconds ago")
    r = eh.collect(fake_run(ps), probe_up)
    assert any("إعادةِ تشغيلٍ" in p for p in problems(r))


def test_db_port_not_forwarded_detected():
    ps = PS_OK.replace("0.0.0.0:5433->5432/tcp, [::]:5433->5432/tcp", "5432/tcp")
    r = eh.collect(fake_run(ps), probe_up)
    assert any("5433" in p for p in problems(r))


def test_db_container_missing_detected():
    ps = "\n".join(line for line in PS_OK.splitlines() if not line.startswith("shschool-dev-db"))
    r = eh.collect(fake_run(ps), probe_up)
    assert any("قاعدة البيانات غير موجودة" in p for p in problems(r))


def test_health_down_detected_with_port():
    r = eh.collect(fake_run(PS_OK), probe_down)
    assert any(f.where.endswith(":8500") and "/health/" in f.problem for f in r.findings)


def test_role_auth_failure_detected_and_never_prints_secret():
    r = eh.collect(fake_run(PS_OK, role="AUTH"), probe_up)
    assert any("كلمةُ shschool_app" in p for p in problems(r))
    text = eh.render(r)
    assert "password=" not in text.lower() and "APP_DB_PASSWORD=" not in text


def test_role_unknown_output_is_other_not_leaked():
    assert eh.classify_role_output("FATAL: password authentication failed for user x") == "OTHER"
    assert eh.classify_role_output("") == "OTHER"
    assert eh.classify_role_output("noise\nNODB") == "NODB"


def test_docker_unreachable_reported_without_restarting_it():
    def run(cmd):
        return 1, "error"

    r = eh.collect(run, probe_up)
    assert len(r.findings) == 1 and "Docker Desktop" in r.findings[0].problem


def test_fix_restarts_named_session_containers_only():
    calls: list = []
    out = eh.fix(["schoolos-x-web-1", "shschool-dev-db", "postgres"], fake_run("", calls=calls))
    restarted = [c[-1] for c in calls if c[:2] == ["docker", "restart"]]
    assert restarted == ["schoolos-x-web-1"]
    assert sum("رفضتُ" in line for line in out) == 2


def test_default_mode_never_runs_state_changing_commands():
    calls: list = []
    eh.collect(fake_run(PS_OK, calls=calls), probe_up)
    assert not [
        c for c in calls if c[:2] in (["docker", "restart"], ["docker", "stop"], ["docker", "rm"])
    ]


def test_main_exit_codes(capsys):
    assert eh.main(["--fix", "postgres"], run=fake_run("")) == 0
    assert "رفضتُ" in capsys.readouterr().out
