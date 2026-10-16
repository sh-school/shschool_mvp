"""[التشغيل] طلبُ التثبيت يُنفَّذ في watch لا في عملية الطالب (متابعة W-20261016-011، أمرُ المالك 2026-10-16).

العطب: `pin` كان يبني الخانةَ في عملية الطالب فتقتلها مهلةُ أداته، فتبقى الخانةُ نصفَ مبنيّةٍ والقفلُ بصاحبٍ ميّتٍ
ولا شيءَ في `status` يقول إنّ تثبيتاً بدأ. الآن: `pin` يكتب `pin_request` ويرجع، وwatch ينفّذه، و`pin_in_progress` يُنظَّف
إن مات صاحبُه، و`status` ينبّه على الإقلاع الطويل وغيابِ نبض watch.

لا docker حقيقيّ: دوالُّ السكربت تُستدعى بـ`source` في مستودعٍ مؤقّت و`docker` وهميٌّ على PATH (كـ`test_preview_dead_lock.py`).
"""

from __future__ import annotations

import shutil
import time

import pytest

from tests.test_preview_integration import SCRIPT, Sandbox, _git_version, _write

pytestmark = [
    pytest.mark.skipif(shutil.which("bash") is None, reason="لا bash في هذه البيئة"),
    pytest.mark.skipif(_git_version() < (2, 38), reason="merge-tree --write-tree يلزمه git 2.38"),
]

LIVE = {"PREVIEW_DRY_RUN": "0"}
SEP = "\t"


@pytest.fixture(scope="module")
def box(tmp_path_factory) -> Sandbox:
    return Sandbox(tmp_path_factory.mktemp("pinrequest"))


@pytest.fixture()
def clean(box):
    if box.state.exists():
        shutil.rmtree(box.state)
    yield
    if box.state.exists():
        shutil.rmtree(box.state)


def _state(box, name, text):
    box.state.mkdir(parents=True, exist_ok=True)
    (box.state / name).write_bytes(text.encode("utf-8"))


def _read(box, name):
    f = box.state / name
    return f.read_text(encoding="utf-8") if f.exists() else None


def _fake_docker(box, log):
    path = box.fakebin / "docker"
    _write(path, f'#!/usr/bin/env bash\necho "$*" >> "{log.as_posix()}"\nexit 0\n')
    path.chmod(0o755)


# deploy_pin وهميٌّ يسجّل نداءَه (البناءُ الحقيقيّ يلزمه docker حقيقيّ)
STUB = 'deploy_pin() { echo "DEPLOY $1 $2" >> "$(state_dir)/deploys"; return 0; }\n'
# عمليّةٌ انتهت: pid لا يُشغَّل بعد الآن
DEAD = "dead=$(bash -c 'echo $$')\n"


def _req(tree="/x/w1", mins="20", force="0", ts=None, retried="0"):
    return SEP.join([tree, mins, force, str(ts or int(time.time())), retried])


def _progress_cmd(pid_expr: str, tree: str, retried: str) -> str:
    rec = f'"{pid_expr}\\t1\\t{tree}\\t20\\t0\\t{retried}"'
    return f'printf "%b" {rec} > "$(state_dir)/pin_in_progress"\n'


# ── pin يسجّل ولا يبني ──────────────────────────────────────────


def test_pin_command_writes_a_request_and_never_builds(box, clean):
    log = box.base / "docker_pin.log"
    log.unlink(missing_ok=True)
    _fake_docker(box, log)
    _write(box.wt / "merged" / "manage.py", "# stub\n")
    start = time.time()
    tree = (box.wt / "merged").as_posix()
    body = STUB + 'SELF_ROOT="' + box.repo.as_posix() + '"\n' + "cmd_pin " + tree + " 20"
    result = box.bash(body, **LIVE)
    assert result.returncode == 0, result.stderr
    assert time.time() - start < 30
    assert _read(box, "deploys") is None  # لم يُستدعَ deploy_pin
    assert not log.exists() or "compose" not in log.read_text(encoding="utf-8")
    fields = (_read(box, "pin_request") or "").split(SEP)
    assert (
        fields[0].endswith("merged") and fields[1] == "20" and fields[2] == "0" and fields[4] == "0"
    )
    assert "سُجّل طلبُ تثبيت" in result.stdout


def test_deploy_pin_is_called_only_by_the_executor_and_the_queue_promoter():
    text = SCRIPT.read_text(encoding="utf-8")
    pin = text[text.index("cmd_pin() {") : text.index("cmd_release() {")]
    assert "deploy_pin" not in pin
    callers = [
        ln
        for ln in text.splitlines()
        if "deploy_pin " in ln and not ln.lstrip().startswith("#") and "deploy_pin() {" not in ln
    ]
    assert len(callers) == 2, callers  # run_pin_request وpromote_queue


def test_the_sync_cycle_stamps_the_heartbeat_before_taking_the_lock():
    text = SCRIPT.read_text(encoding="utf-8")
    body = text[text.index("cmd_sync() {") : text.index("cmd_watch() {")]
    assert body.index('sset watch_hb "$(now)"') < body.index("acquire_lock")
    assert body.index("acquire_lock") < body.index("run_pin_request")


# ── التنفيذ في watch ────────────────────────────────────────────


def test_the_executor_deploys_once_and_clears_the_request_and_progress(box, clean):
    tree = box.wt / "merged"
    _write(tree / "manage.py", "# stub\n")
    _state(box, "pin_request", _req(tree=tree.as_posix(), mins="15"))
    result = box.bash(f"{STUB}run_pin_request", **LIVE)
    assert result.returncode == 0, result.stderr
    assert (_read(box, "deploys") or "").count("DEPLOY") == 1
    assert "merged 15" in _read(box, "deploys")
    assert _read(box, "pin_request") is None and _read(box, "pin_in_progress") is None


def test_progress_is_recorded_while_the_build_runs(box, clean):
    tree = box.wt / "merged"
    _write(tree / "manage.py", "# stub\n")
    _state(box, "pin_request", _req(tree=tree.as_posix()))
    stub = 'deploy_pin() { cp "$(state_dir)/pin_in_progress" "$(state_dir)/seen"; return 0; }\n'
    box.bash(f"{stub}run_pin_request", **LIVE)
    seen = (_read(box, "seen") or "").split(SEP)
    assert len(seen) == 6 and seen[0].isdigit() and seen[2].endswith("merged") and seen[5] == "0"
    assert _read(box, "pin_in_progress") is None


def test_no_request_means_the_executor_does_nothing(box, clean):
    result = box.bash(f"{STUB}run_pin_request", **LIVE)
    assert result.returncode == 0 and _read(box, "deploys") is None


def test_a_request_while_another_tree_holds_a_live_pin_goes_to_the_queue(box, clean):
    tree = box.wt / "merged"
    _write(tree / "manage.py", "# stub\n")
    _state(box, "mode", "pin")
    _state(box, "pin_tree", "/x/other")
    _state(box, "pin_until", str(int(time.time()) + 600))
    _state(box, "pin_request", _req(tree=tree.as_posix()))
    box.bash(f"{STUB}run_pin_request", **LIVE)
    assert _read(box, "deploys") is None
    assert "merged" in (_read(box, "pin_queue") or "")


# ── التعافي من إقلاعٍ مات صاحبُه ────────────────────────────────


def test_a_dead_progress_clears_only_the_empty_slot_and_retries_once(box, clean):
    log = box.base / "docker_rec.log"
    log.unlink(missing_ok=True)
    _fake_docker(box, log)
    tree = box.wt / "merged"
    _write(tree / "manage.py", "# stub\n")
    _state(box, "slot", "a")
    body = DEAD + _progress_cmd("$dead", tree.as_posix(), "0") + "recover_pin_in_progress\n"
    result = box.bash(body, **LIVE)
    assert result.returncode == 0, result.stderr
    calls = log.read_text(encoding="utf-8").splitlines()
    downs = [c for c in calls if " down " in f" {c} "]
    assert len(downs) == 1 and downs[0].split()[2].endswith("-b"), calls  # الفارغةُ b وحدَها؛ a تخدم
    assert _read(box, "pin_in_progress") is None
    assert (_read(box, "pin_request") or "").split(SEP)[4] == "1"


def test_a_second_death_gives_up_and_records_the_error(box, clean):
    log = box.base / "docker_rec2.log"
    log.unlink(missing_ok=True)
    _fake_docker(box, log)
    tree = box.wt / "merged"
    _write(tree / "manage.py", "# stub\n")
    _state(box, "slot", "b")
    body = DEAD + _progress_cmd("$dead", tree.as_posix(), "1") + "recover_pin_in_progress\n"
    box.bash(body, **LIVE)
    assert _read(box, "pin_request") is None and _read(box, "pin_in_progress") is None
    assert "مات مرّتين" in (_read(box, "last_error") or "")
    downs = [c for c in log.read_text(encoding="utf-8").splitlines() if " down " in f" {c} "]
    assert len(downs) == 1 and downs[0].split()[2].endswith("-a")


def test_a_live_owner_progress_is_left_alone(box, clean):
    _state(box, "slot", "a")
    body = (
        "sleep 30 &\nalive=$!\n"
        + _progress_cmd("$alive", "/x/w1", "0")
        + "recover_pin_in_progress\n"
        + 'kill "$alive" 2>/dev/null\n'
    )
    box.bash(body, **LIVE)
    assert _read(box, "pin_in_progress") is not None and _read(box, "pin_request") is None


# ── status ──────────────────────────────────────────────────────


def _status(box, **state):
    for k, v in state.items():
        _state(box, k, v)
    return box.bash("pin_start_status", **LIVE)


def test_status_shows_a_build_in_progress_without_alert_when_young(box, clean):
    now = int(time.time())
    r = _status(
        box,
        pin_in_progress=SEP.join(["1", str(now - 120), "/x/w1", "20", "0", "0"]),
        watch_hb=str(now),
    )
    assert "قيدَ الإقلاع" in r.stdout and "w1" in r.stdout and "تنبيه" not in r.stderr


def test_status_alerts_when_a_build_exceeds_ten_minutes(box, clean):
    now = int(time.time())
    r = _status(
        box,
        pin_in_progress=SEP.join(["1", str(now - 11 * 60), "/x/w1", "20", "0", "0"]),
        watch_hb=str(now),
    )
    assert "طال أكثر من 10 دقائق" in r.stderr


def test_status_shows_a_waiting_request_and_alerts_when_it_is_old(box, clean):
    now = int(time.time())
    r = _status(box, pin_request=_req(tree="/x/w2", ts=now - 12 * 60), watch_hb=str(now))
    assert "طلبٌ ينتظر watch" in r.stdout and "w2" in r.stdout and "لم يُنفَّذ" in r.stderr


def test_status_alerts_when_the_watch_heartbeat_is_stale(box, clean):
    r = _status(box, watch_hb=str(int(time.time()) - 16 * 60))
    assert "لا نبضَ لـwatch" in r.stderr


def test_status_alerts_when_no_heartbeat_was_ever_recorded(box, clean):
    r = box.bash("pin_start_status", **LIVE)
    assert "لم يُسجَّل نبضٌ" in r.stderr


def test_status_is_quiet_with_a_fresh_heartbeat_and_nothing_pending(box, clean):
    r = _status(box, watch_hb=str(int(time.time()) - 60))
    assert r.stderr.strip() == "" and "تثبيت:" not in r.stdout
