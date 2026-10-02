"""[COMMAND-CENTER] لوحةُ «مزامنةُ الخارطة» (MAE-11): طلباتٌ دُمجت ولم يُذكر رقمُها في أيّ بندٍ — أرقامٌ فقط في اللوحة، والقائمةُ بالأمر."""

import io
import time

import pytest
from django.core.cache import cache
from django.core.management import call_command

from command_center import collectors, contract
from command_center.collectors import github, sync
from command_center.management.commands import roadmap_unsynced
from roadmap.models import RoadmapItem

pytestmark = pytest.mark.django_db

NOW = 1_799_312_400.0
HOUR = 3600


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _panel():
    return next(p for p in contract.read_panels() if p["key"] == "sync")


def _iso(hours_before_now):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - hours_before_now * HOUR))


def _pull(number, hours_ago, login="dev", kind="User", merged=True, **extra):
    return {
        "number": number,
        "merged_at": _iso(hours_ago) if merged else None,
        "user": {"login": login, "type": kind},
        **extra,
    }


def _item(code, **fields):
    return RoadmapItem.objects.create(code=code, lane="ops", title=code, **fields)


def _fetch(payload):
    return lambda path, reduce: reduce(payload)


def test_the_panel_is_registered_and_collected_remotely():
    assert "sync" in collectors.REMOTE
    assert any(p.key == "sync" for p in contract.PANELS)


def test_the_reducer_keeps_numbers_and_times_only_and_skips_bots_and_unmerged():
    payload = [
        _pull(10, 5, title="سرٌّ لا يُخزَّن", body="نصّ"),
        _pull(11, 5, login="dependabot[bot]", kind="Bot"),
        _pull(12, 5, merged=False),
        _pull(13, 7, login="x[bot]", kind="User"),
        "تالف",
    ]
    summary = sync.reduce_merged(payload)
    assert [n for n, _ in summary["prs"]] == [10]
    assert "سرّ" not in str(summary)
    assert sync.reduce_merged({"message": "x"}) is None
    assert sync.reduce_merged([_pull(n, 1) for n in range(100, 200)])["full"] is True


def test_numbers_are_read_from_pr_note_and_ref_with_word_boundaries():
    _item("A-1", pr="#732")
    _item("A-2", note="أُغلق بـ#737 و(#742)، وليس #5 ولا a#99999999")
    _item("A-3", ref="طلب #800")
    known = sync.synced_numbers()
    assert {732, 737, 742, 800} <= known
    assert 5 not in known


def test_the_queue_is_ordered_oldest_first_and_excludes_known():
    prs = [[3, NOW - HOUR], [1, NOW - 9 * HOUR], [2, NOW - 4 * HOUR]]
    assert sync.unsynced(prs, {2}) == [(1, NOW - 9 * HOUR), (3, NOW - HOUR)]


def test_everything_synced_is_green(monkeypatch):
    _item("A-1", pr="#10, #11")
    monkeypatch.setattr(github, "fetch", _fetch([_pull(10, 50), _pull(11, 5)]))
    sync.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.OK and panel["gauge"] == 100
    assert panel["headline"] == "كلُّ المدموج مذكورٌ في الخارطة"


def test_a_fresh_unsynced_pull_is_within_grace_and_green(monkeypatch):
    monkeypatch.setattr(github, "fetch", _fetch([_pull(10, 3)]))
    sync.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.OK
    assert {"label": "مدموجٌ لم يُزامَن", "value": "1"} in panel["metrics"]
    assert {"label": "متأخّرٌ فوق 36 س", "value": "0"} in panel["metrics"]


def test_an_old_unsynced_pull_turns_the_panel_amber_never_red(monkeypatch):
    _item("A-1", pr="#11")
    monkeypatch.setattr(github, "fetch", _fetch([_pull(10, 40), _pull(11, 5), _pull(12, 2)]))
    sync.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.WARN
    assert panel["headline"] == "2 طلباً دُمج ولم يُزامَن"
    assert {"label": "متأخّرٌ فوق 36 س", "value": "1"} in panel["metrics"]
    assert {"label": "أقدمُ غيرِ مُزامَن", "value": "منذ 40 س"} in panel["metrics"]
    assert panel["gauge"] == pytest.approx(100 / 3, abs=1)


def test_no_pull_number_or_text_reaches_the_panel(monkeypatch):
    monkeypatch.setattr(github, "fetch", _fetch([_pull(98765, 50, title="سرّ", body="نص")]))
    sync.collect(NOW)
    shown = str(_panel())
    assert "98765" not in shown and "سرّ" not in shown


def test_a_failed_fetch_keeps_the_last_state_and_flags_the_panel(monkeypatch):
    monkeypatch.setattr(github, "fetch", lambda path, reduce: None)
    sync.collect(NOW)
    assert _panel()["ok"] is False


def test_the_command_lists_the_numbers_for_the_roadmap_session(monkeypatch):
    _item("A-1", pr="#11")
    monkeypatch.setattr(github, "fetch", _fetch([_pull(10, 40), _pull(11, 5), _pull(12, 2)]))
    monkeypatch.setattr(roadmap_unsynced.Command, "now", lambda self: NOW)
    out = io.StringIO()
    call_command("roadmap_unsynced", stdout=out)
    text = out.getvalue()
    assert "#10" in text and "#12" in text and "#11" not in text
    assert "متأخّر" in text and "ضمن المهلة" in text
    assert text.index("#10") < text.index("#12")  # الأقدمُ أوّلاً


def test_the_command_says_so_when_everything_is_synced(monkeypatch):
    _item("A-1", pr="#10")
    monkeypatch.setattr(github, "fetch", _fetch([_pull(10, 40)]))
    out = io.StringIO()
    call_command("roadmap_unsynced", stdout=out)
    assert "كلُّ المدموج مذكورٌ" in out.getvalue()
