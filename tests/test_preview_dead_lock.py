"""[التشغيل] قفلُ المعاينة الميّت وتثبيتٌ منتهٍ لا يُفكّ وانتقالُ الخانة (W-20261016-011، أمرُ المالك 2026-10-16).

العطب: كان قفلُ `preview.sh` يبقى 20 دقيقةً بعد موت صاحبه فتتخطّى كلُّ دورة watch عملَها، فلا يُفكّ تثبيتٌ انتهى (قيس: 717 دقيقةً والطابورُ 11 شجرة)،
وبقايا حاويات الخانة الفارغة تحجز منفذَها فيسقط البناءُ بـ«port is already allocated» وتبقى المعاينةُ على نسخةٍ قديمة.

لا docker حقيقيّ ولا 8500: دوالُّ السكربت تُستدعى بـ`source` في مستودعٍ مؤقّت (كـ`test_preview_cadence.py`)، و`docker` وهميٌّ على PATH.
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


@pytest.fixture(scope="module")
def box(tmp_path_factory) -> Sandbox:
    return Sandbox(tmp_path_factory.mktemp("deadlock"))


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


# ── القفل ──────────────────────────────────────────────────────


def test_a_lock_whose_owner_died_is_broken_at_once(box, clean):
    """القفلُ جديدٌ (ثوانٍ) لكنّ صاحبه ميّت: يُكسر في الدورة نفسِها لا بعد 20 دقيقة."""
    body = (
        'mkdir -p "$(state_dir)/lock"\n'
        "dead=$(bash -c 'echo $$')\n"  # عمليّةٌ انتهت
        'printf "%s" "$dead" > "$(state_dir)/lock/pid"\n'
        "acquire_lock && echo got\n"
    )
    result = box.bash(body, **LIVE)
    assert result.stdout.strip() == "got", result.stderr


def test_a_lock_whose_owner_is_alive_is_never_broken_however_old(box, clean):
    body = (
        'mkdir -p "$(state_dir)/lock"\n'
        "sleep 30 &\n"
        "alive=$!\n"
        'printf "%s" "$alive" > "$(state_dir)/lock/pid"\n'
        'touch -d "3 hours ago" "$(state_dir)/lock"\n'
        "if acquire_lock; then echo got; else echo held; fi\n"
        'kill "$alive" 2>/dev/null\n'
    )
    result = box.bash(body, **LIVE)
    assert result.stdout.strip() == "held", result.stderr


def test_a_legacy_lock_without_pid_keeps_the_twenty_minute_rule(box, clean):
    fresh = box.bash(
        'mkdir -p "$(state_dir)/lock"\nif acquire_lock; then echo got; else echo held; fi', **LIVE
    )
    assert fresh.stdout.strip() == "held", fresh.stderr
    stale = box.bash(
        'touch -d "30 minutes ago" "$(state_dir)/lock"\nif acquire_lock; then echo got; else echo held; fi',
        **LIVE,
    )
    assert stale.stdout.strip() == "got", stale.stderr


def test_a_taken_lock_records_the_owner_pid_and_is_released_at_exit(box, clean):
    inside = box.bash('acquire_lock\ncat "$(state_dir)/lock/pid"; echo; echo "$$"', **LIVE)
    pid, me = inside.stdout.split()
    assert pid == me
    assert not (box.state / "lock").exists()


# ── تثبيتٌ منتهٍ لا يُفكّ ────────────────────────────────────────


def test_an_expired_pin_unreleased_for_fifteen_minutes_raises_the_flag_once(box, clean):
    now = int(time.time())
    _state(box, "mode", "pin")
    _state(box, "pin_tree", "D:/x/w015-grid-live")
    _state(box, "pin_until", str(now - 16 * 60))
    result = box.bash(
        'pin_overdue_check\npin_overdue_check\ncat "$(state_dir)/pin_overdue"', **LIVE
    )
    assert result.returncode == 0, result.stderr
    ts, tree, minutes = result.stdout.split()
    assert tree == "w015-grid-live" and int(minutes) >= 16 and int(ts) >= now
    assert result.stderr.count("انتهى منذ") == 1  # مرّةً واحدةً لا في كلّ دورة


def test_a_pin_expired_for_less_than_fifteen_minutes_raises_nothing(box, clean):
    _state(box, "mode", "pin")
    _state(box, "pin_until", str(int(time.time()) - 5 * 60))
    box.bash("pin_overdue_check", **LIVE)
    assert not (box.state / "pin_overdue").exists()


def test_a_live_pin_never_raises_the_flag(box, clean):
    _state(box, "mode", "pin")
    _state(box, "pin_until", str(int(time.time()) + 20 * 60))
    box.bash("pin_overdue_check", **LIVE)
    assert not (box.state / "pin_overdue").exists()


def test_following_main_raises_nothing_even_with_a_stale_pin_until(box, clean):
    _state(box, "mode", "follow")
    _state(box, "pin_until", str(int(time.time()) - 3600))
    box.bash("pin_overdue_check", **LIVE)
    assert not (box.state / "pin_overdue").exists()


def test_status_names_the_overdue_pin(box, clean):
    _state(box, "pin_overdue", f"{int(time.time())} w015-grid-live 17")
    result = box.bash("sget pin_overdue | awk '{print $2}'", **LIVE)
    assert result.stdout.strip() == "w015-grid-live"


# ── انتقالُ الخانة: «port is already allocated» ───────────────────


def _fake_docker(box, script: str):
    path = box.fakebin / "docker"
    _write(path, "#!/usr/bin/env bash\n" + script)
    path.chmod(0o755)


def test_a_port_conflict_on_the_empty_slot_is_retried_once_after_clearing_it(box, clean):
    log = box.base / "docker_calls.log"
    log.unlink(missing_ok=True)
    _fake_docker(
        box,
        f'echo "$*" >> "{log.as_posix()}"\n'
        'case "$*" in\n'
        '  *" up "*)\n'
        f'    n=$(grep -c " up " "{log.as_posix()}")\n'
        '    if [ "$n" = 1 ]; then echo "Bind for 127.0.0.1:8510 failed: port is already allocated"; exit 1; fi\n'
        "    exit 0 ;;\n"
        "esac\n"
        "exit 0\n",
    )
    result = box.bash('SLOT_PROJECT=schoolos-x-a\nslot_up "$PREVIEW_DIR" 8510\necho rc=$?', **LIVE)
    calls = log.read_text(encoding="utf-8")
    assert "rc=0" in result.stdout, result.stderr
    assert calls.count(" up ") == 2, calls
    assert calls.count(" down ") >= 1, calls  # أُزيلت بقايا الخانة بين المحاولتين


def test_any_other_compose_failure_is_not_retried(box, clean):
    log = box.base / "docker_calls2.log"
    log.unlink(missing_ok=True)
    _fake_docker(
        box,
        f'echo "$*" >> "{log.as_posix()}"\n'
        'case "$*" in *" up "*) echo "build failed: boom"; exit 1 ;; esac\n'
        "exit 0\n",
    )
    result = box.bash('SLOT_PROJECT=schoolos-x-a\nslot_up "$PREVIEW_DIR" 8510\necho rc=$?', **LIVE)
    assert "rc=1" in result.stdout, result.stderr
    assert log.read_text(encoding="utf-8").count(" up ") == 1


def test_slot_cleanup_targets_only_the_slot_project():
    """التنظيفُ قبل بناء الخانة وبعد تعارض المنفذ على `$SLOT_PROJECT` وحده؛ لا الواجهةُ `$FRONT` ولا الخانةُ القائمة."""
    text = SCRIPT.read_text(encoding="utf-8")
    start = text.index("slot_up() {")
    body = text[start : text.index("bluegreen_up() {")]
    assert body.count('docker compose -p "$SLOT_PROJECT" down') == 1
    assert "$FRONT" not in body and '"$PROJECT"' not in body
