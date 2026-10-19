"""سقفُ خوادم الجلسات بـdocker وهمي (W-20261016-009): ثلاثةٌ حيّة ترفض الرابع، الخاملُ يُطفأ، النشطُ يبقى، والمعاينةُ لا تُمَسّ."""

import importlib.util
import pathlib

import pytest

_spec = importlib.util.spec_from_file_location(
    "session_cap", pathlib.Path(__file__).parent.parent / "scripts" / "session_cap.py"
)
sc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sc)

QUIET = "GET /health/ 200\n"
BUSY = "GET /health/ 200\nGET /schedule/ 200\n"


def web(n):
    return f"schoolos-s{n}-web-1"


class FakeDocker:
    """يحاكي docker: أسماءٌ حيّة وسجلاتٌ؛ stop يُسقط المشروعَ من الحيّة ويُسجَّل."""

    def __init__(self, names, logs):
        self.names, self.logs, self.stopped = list(names), logs, []

    def __call__(self, args):
        if args[:3] == ["docker", "ps", "--format"]:
            return "\n".join(self.names)
        if args[:2] == ["docker", "logs"]:
            return self.logs.get(args[-1], "")
        if args[:3] == ["docker", "ps", "-q"]:
            proj = args[-1].rsplit("=", 1)[1]
            return f"{proj}-web-1 {proj}-worker-1"
        if args[:2] == ["docker", "stop"]:
            self.stopped.append(args[2:])
            self.names = [n for n in self.names if n not in args[2:]]
            return "ok"
        return None


def test_three_live_all_busy_refuses_fourth():
    fake = FakeDocker([web(1), web(2), web(3)], {web(i): BUSY for i in (1, 2, 3)})
    code, msg = sc.check("schoolos-s4", fake)
    assert code == 1 and "السقف" in msg and fake.stopped == []


def test_two_live_allows_third():
    assert sc.check("schoolos-s3", FakeDocker([web(1), web(2)], {}))[0] == 0


def test_own_restart_not_counted():
    fake = FakeDocker([web(1), web(2), web(3)], {web(i): BUSY for i in (1, 2, 3)})
    assert sc.check("schoolos-s1", fake)[0] == 0


def test_idle_stopped_busy_untouched_and_start_allowed():
    fake = FakeDocker([web(1), web(2), web(3)], {web(1): QUIET, web(2): BUSY, web(3): BUSY})
    code, _ = sc.check("schoolos-s4", fake)
    assert code == 0 and len(fake.stopped) == 1
    assert "schoolos-s1-web-1" in fake.stopped[0]
    assert all("s2" not in a and "s3" not in a for a in fake.stopped[0])


def test_main_preview_and_dev_never_counted_or_touched():
    names = ["schoolos-main-preview-a-web-1", "shschool-dev-db", web(1)]
    assert sc.live_sessions("\n".join(names)) == ["schoolos-s1"]
    fake = FakeDocker(names, {"schoolos-main-preview-a-web-1": QUIET})
    assert sc.reap(["schoolos-main-preview-a"], fake) == []
    assert fake.stopped == []


def test_dry_run_stops_nothing():
    fake = FakeDocker([web(1)], {web(1): QUIET})
    assert sc.reap(["schoolos-s1"], fake, dry_run=True) == ["schoolos-s1"]
    assert fake.stopped == []


def test_docker_missing_is_unmeasured_and_allows():
    code, msg = sc.check("schoolos-s1", lambda _a: None)
    assert code == 0 and "غير مقيس" in msg


def test_only_whitelisted_subcommands():
    for bad in (["docker", "rm", "-f", "x"], ["docker", "system", "prune"], ["rm", "-rf", "/"]):
        with pytest.raises(PermissionError):
            sc.run(bad)
