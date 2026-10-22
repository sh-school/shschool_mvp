"""[COMMAND-CENTER] كشفُ الدمج المتعطّل (W-20261022-011): طلبٌ CLEAN عالقٌ أكثرَ من ساعة يُنذر، ودمجٌ تلقائيٌّ غيرُ مفعَّلٍ يُكشف.

GitHub مُحاكًى بالكامل (`github.fetch`)؛ والتنبيهُ إشعارُ جرسٍ لا حالةُ لوحةٍ، ولا مسَّ بالدفتر.
"""

import pytest
from django.core.cache import cache

from command_center import collectors, contract
from command_center.collectors import flow_merge_stall as stall
from command_center.collectors import github, queue
from notifications.models import InAppNotification

pytestmark = pytest.mark.django_db

NOW = 1_800_000_000.0
HOUR = 3600.0


@pytest.fixture(autouse=True)
def _live(settings):
    settings.QCC_NOTIFY_ENABLED = True
    cache.clear()
    yield
    cache.clear()


def _github(monkeypatch, pulls, *, down=False):
    """pulls: {رقم: (draft, armed, عمرٌ بالساعات، mergeable_state)}."""

    def fetch(path, reduce):
        if down:
            return None
        if path == queue.OPEN_PATH:
            return {
                "rows": [
                    [n, "ab12cd34", draft, armed, NOW - age * HOUR]
                    for n, (draft, armed, age, _s) in pulls.items()
                ]
            }
        number = int(path.split("/")[1])
        return {"state": pulls[number][3]}

    monkeypatch.setattr(github, "fetch", fetch)


def _bell(user):
    return list(InAppNotification.objects.filter(user=user))


def test_classify_needs_clean_and_more_than_an_hour():
    assert stall.classify(1, "clean", True, 2.0) == "stalled"
    assert stall.classify(1, "clean", False, 2.0) == "unarmed"
    assert stall.classify(1, "clean", True, 0.5) is None
    assert stall.classify(1, "clean", True, 1.0) is None
    assert stall.classify(1, "blocked", True, 9.0) is None
    assert stall.classify(1, "clean", True, None) is None


def test_scan_separates_stalled_from_unarmed_and_skips_drafts(monkeypatch):
    _github(
        monkeypatch,
        {
            10: (False, True, 3.0, "clean"),
            11: (False, False, 5.0, "clean"),
            12: (True, False, 9.0, "clean"),
            13: (False, False, 9.0, "dirty"),
            14: (False, True, 0.2, "clean"),
        },
    )
    assert stall.scan(NOW) == {"stalled": [10], "unarmed": [11]}


def test_a_stuck_clean_pr_sends_one_urgent_bell(monkeypatch, developer_user):
    _github(monkeypatch, {10: (False, True, 3.0, "clean")})
    assert stall.collect(NOW) == ["fired"]
    bell = _bell(developer_user)
    assert len(bell) == 1 and bell[0].priority == "urgent"
    assert "#10" in bell[0].body


def test_unarmed_pr_is_reported_as_a_false_tick_candidate(monkeypatch, developer_user):
    _github(monkeypatch, {11: (False, False, 2.0, "clean")})
    assert stall.collect(NOW) == ["fired"]
    assert "كاذب" in _bell(developer_user)[0].body


def test_same_stall_is_not_repeated_before_six_hours(monkeypatch, developer_user):
    _github(monkeypatch, {10: (False, True, 3.0, "clean")})
    assert stall.collect(NOW) == ["fired"]
    assert stall.collect(NOW + 3600) == []
    assert len(_bell(developer_user)) == 1


def test_it_renotifies_after_six_hours_and_when_the_set_changes(monkeypatch, developer_user):
    _github(monkeypatch, {10: (False, True, 3.0, "clean")})
    stall.collect(NOW)
    assert stall.collect(NOW + 6 * HOUR + 1) == ["renotified"]
    _github(monkeypatch, {10: (False, True, 3.0, "clean"), 11: (False, False, 2.0, "clean")})
    assert stall.collect(NOW + 6 * HOUR + 60) == ["fired"]


def test_clearing_resets_so_a_new_stall_alerts_again(monkeypatch, developer_user):
    _github(monkeypatch, {10: (False, True, 3.0, "clean")})
    stall.collect(NOW)
    _github(monkeypatch, {})
    assert stall.collect(NOW + 600) == []
    _github(monkeypatch, {10: (False, True, 3.0, "clean")})
    assert stall.collect(NOW + 1200) == ["fired"]


def test_a_github_outage_neither_alerts_nor_clears(monkeypatch, developer_user):
    _github(monkeypatch, {10: (False, True, 3.0, "clean")})
    stall.collect(NOW)
    _github(monkeypatch, {}, down=True)
    assert stall.collect(NOW + 600) == []
    assert cache.get(stall.STATE_KEY)


def test_kill_switch_silences_it(monkeypatch, developer_user, settings):
    settings.QCC_NOTIFY_ENABLED = False
    _github(monkeypatch, {10: (False, True, 3.0, "clean")})
    assert stall.collect(NOW) == []
    assert _bell(developer_user) == []


def test_safe_collect_never_raises(monkeypatch):
    def boom(now=None):
        raise RuntimeError("down")

    monkeypatch.setattr(stall, "collect", boom)
    assert stall.safe_collect() == []


def test_remote_run_triggers_the_check_but_local_run_does_not(monkeypatch):
    calls = []
    monkeypatch.setattr(stall, "safe_collect", lambda: calls.append(1) or [])
    collectors.run({})
    assert calls == []
    monkeypatch.setattr(collectors, "REMOTE", {"queue": lambda: None})
    collectors.run(collectors.REMOTE)
    assert calls == [1]


def test_it_writes_no_panel_state(monkeypatch):
    _github(monkeypatch, {10: (False, True, 3.0, "clean")})
    stall.collect(NOW)
    assert stall.PANEL not in {p.key for p in contract.PANELS}
