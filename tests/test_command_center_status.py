"""[COMMAND-CENTER] «حالةُ اليوم» للمالك (W-20261002-022): لوحةُ «الطابورُ والنشر» وصفحتُها — أرقامٌ وحالاتٌ بلا عناوين، وقراءةُ cache فقط.

الوصولُ (مجهولٌ/غيرُ مطوّر/GET فقط) تحرسه اختباراتُ `test_command_center.py` على كلّ مسارٍ في urlpatterns تلقائيّاً، فالمسارُ الجديدُ مشمول.
"""

import time

import pytest
from django.core.cache import cache
from django.urls import reverse

from command_center import collectors, contract, status_page
from command_center.collectors import github, queue

pytestmark = pytest.mark.django_db

NOW = 1_799_312_400.0
HOUR = 3600


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _iso(hours_before_now):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(NOW - hours_before_now * HOUR))


def _pull(number, idle_hours=1, draft=False, auto=False, sha="a" * 40, **extra):
    return {
        "number": number,
        "draft": draft,
        "auto_merge": {"enabled_by": "x"} if auto else None,
        "updated_at": _iso(idle_hours),
        "head": {"sha": sha, "ref": "claude/اسمٌ-سرّيّ"},
        "title": "عنوانٌ لا يُخزَّن",
        **extra,
    }


def _fetch(pulls, states=None, checks=None):
    """جلبٌ مزيَّف: قائمةُ الطلبات، ثمّ mergeable_state وفحوصُ كلّ رأس."""
    states, checks = states or {}, checks or {}

    def fake(path, reduce):
        if path == queue.OPEN_PATH:
            return reduce(pulls)
        if path.startswith("pulls/"):
            number = int(path.split("/")[1])
            return reduce({"mergeable_state": states.get(number, "clean")})
        if path.startswith("commits/"):
            sha = path.split("/")[1]
            runs = checks.get(sha, [{"status": "completed", "conclusion": "success"}])
            return reduce({"check_runs": runs})
        raise AssertionError(path)

    return fake


def _panel():
    return next(p for p in contract.read_panels() if p["key"] == "queue")


def test_the_panel_is_registered_as_remote():
    assert "queue" in collectors.REMOTE
    assert any(p.key == "queue" for p in contract.PANELS)


def test_the_reducers_keep_numbers_and_states_only():
    summary = queue.reduce_open(
        [_pull(10, auto=True), _pull(11, draft=True), "تالف", {"number": 12}]
    )
    assert [r[0] for r in summary["rows"]] == [10, 11]
    assert "سرّيّ" not in str(summary) and "عنوان" not in str(summary)
    assert queue.reduce_open({"message": "x"}) is None
    assert queue.reduce_detail({"mergeable_state": "dirty"}) == {"state": "conflict"}
    assert queue.reduce_detail({"mergeable_state": "جديدٌ غريب"}) == {"state": "unknown"}
    assert queue.reduce_checks(
        {
            "check_runs": [
                {"status": "completed", "conclusion": "success"},
                {"status": "completed", "conclusion": "failure"},
                {"status": "in_progress"},
            ]
        }
    ) == {"total": 3, "ok": 1, "bad": 1}


def test_a_clean_queue_is_green(monkeypatch):
    monkeypatch.setattr(github, "fetch", _fetch([_pull(10, auto=True), _pull(11)]))
    queue.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.OK and panel["gauge"] == 100
    assert {"label": "مفتوحةٌ (بلا المسوّدات)", "value": "2"} in panel["metrics"]
    assert {"label": "تعارضات", "value": "0"} in panel["metrics"]


def test_a_fresh_conflict_warns_and_a_stuck_one_turns_red(monkeypatch):
    monkeypatch.setattr(github, "fetch", _fetch([_pull(10, idle_hours=0.5)], states={10: "dirty"}))
    queue.collect(NOW)
    assert _panel()["status"] == contract.WARN  # عابرٌ بعد دمجِ غيره

    monkeypatch.setattr(github, "fetch", _fetch([_pull(10, idle_hours=3)], states={10: "dirty"}))
    queue.collect(NOW)
    panel = _panel()
    assert panel["status"] == contract.BAD  # عالقٌ فوق ساعتَين ⇒ يصل جرسَ المطوّر (alerts.py)
    assert {"label": "تعارضات", "value": "1"} in panel["metrics"]


def test_a_failed_check_on_a_stuck_pull_is_red_and_a_draft_never_alarms(monkeypatch):
    bad = [{"status": "completed", "conclusion": "failure"}]
    monkeypatch.setattr(
        github, "fetch", _fetch([_pull(10, idle_hours=3, sha="b" * 40)], checks={"b" * 40: bad})
    )
    queue.collect(NOW)
    assert _panel()["status"] == contract.BAD

    monkeypatch.setattr(
        github,
        "fetch",
        _fetch(
            [_pull(10, idle_hours=30, draft=True, sha="b" * 40)],
            states={10: "dirty"},
            checks={"b" * 40: bad},
        ),
    )
    queue.collect(NOW)
    assert _panel()["status"] == contract.OK  # مسوّدةٌ عالقةٌ بتعارضٍ لا تُنذر


def test_a_failed_fetch_flags_the_panel_and_keeps_the_last_state(monkeypatch):
    monkeypatch.setattr(github, "fetch", lambda path, reduce: None)
    queue.collect(NOW)
    assert _panel()["ok"] is False


def test_no_title_branch_or_author_reaches_the_cache(monkeypatch):
    monkeypatch.setattr(github, "fetch", _fetch([_pull(10)]))
    queue.collect(NOW)
    stored = str(cache.get(contract.cache_key("queue")))
    assert "سرّيّ" not in stored and "عنوان" not in stored and "claude/" not in stored


def test_the_rows_are_capped_and_invalid_data_is_ignored(monkeypatch):
    monkeypatch.setattr(
        github,
        "fetch",
        _fetch([_pull(n, sha=f"{n:040x}") for n in range(100, 100 + queue.MAX_ROWS + 5)]),
    )
    queue.collect(NOW)
    assert len(status_page.queue_rows()) == queue.MAX_ROWS
    cache.set(contract.cache_key("queue"), {"data": {"rows": "x", "status": {"nested": 1}}})
    assert status_page.queue_rows() == []


def test_the_page_answers_the_owners_four_questions(client_as, developer_user, monkeypatch):
    monkeypatch.setattr(
        github,
        "fetch",
        _fetch([_pull(10, auto=True), _pull(11, idle_hours=3)], states={11: "dirty"}),
    )
    queue.collect(time.time())
    html = client_as(developer_user).get(reverse("command_center:status")).content.decode()
    assert "الطابور — الطلباتُ المفتوحة" in html
    assert "#10" in html and "#11" in html
    assert "تعارضٌ مع main" in html  # الحالةُ نصّاً
    assert "تعارضاتٌ مع main:" in html and "#11" in html
    assert 'http-equiv="refresh"' in html  # تتجدّد وحدَها
    assert "عنوانٌ لا يُخزَّن" not in html and "اسمٌ-سرّيّ" not in html
    assert "https://github.com/sh-school/shschool_mvp/pull/10" in html


def test_an_unknown_panel_is_never_read_as_healthy(client_as, developer_user):
    html = client_as(developer_user).get(reverse("command_center:status")).content.decode()
    assert "لم تُجمَع بعدُ (غيرُ معلوم — لا يعني سليماً)" in html
    assert "لا لوحةَ حمراءَ" in html  # ولا حمراءَ مُدَّعاةً بلا قياس


def test_the_unpublished_commits_are_read_from_the_pulls_panel(client_as, developer_user):
    contract.store(
        "pulls",
        {"status": "ok", "headline": "x", "gauge": 100, "m3_l": "إيداعاتٌ غيرُ منشورة", "m3_v": "3"},
    )
    html = client_as(developer_user).get(reverse("command_center:status")).content.decode()
    assert "3 إيداعاً في main لم يُنشر بعدُ" in html
    contract.store(
        "pulls",
        {"status": "ok", "headline": "x", "gauge": 100, "m3_l": "إيداعاتٌ غيرُ منشورة", "m3_v": "0"},
    )
    html = client_as(developer_user).get(reverse("command_center:status")).content.decode()
    assert "الإنتاجُ على آخر main" in html


def test_a_red_panel_is_listed_by_name(client_as, developer_user):
    contract.store("ci", {"status": "bad", "headline": "x", "gauge": 10})
    html = client_as(developer_user).get(reverse("command_center:status")).content.decode()
    assert "أحمر:" in html and "فحوصُ CI" in html


# ── الروابط: القائمةُ والصفحاتُ المرتبطة (ملاحظة المالك: أين رابطُها في المنيو؟) ──────────────────────────────


def _developer_principal(principal_user):
    from django.contrib.auth.models import Group

    principal_user.groups.add(Group.objects.get_or_create(name="developers")[0])
    return principal_user


def test_the_developer_sees_the_status_link_in_the_menu_next_to_the_center(
    client_as, principal_user
):
    url = reverse("command_center:status")
    html = client_as(_developer_principal(principal_user)).get("/dashboard/").content.decode()
    assert f'href="{url}"' in html
    assert (
        html.index(reverse("command_center:index"))
        < html.index(f'href="{url}"')
        < html.index(reverse("improvement_roadmap"))
    ), "بعد «مركز قيادة الجودة» وقبل «خارطة التجويد» في أدوات المطوّر"
    assert 'aria-label="حالة اليوم' in html


def test_a_non_developer_never_sees_the_status_link(client_as, teacher_user, principal_user):
    url = reverse("command_center:status")
    assert url not in client_as(teacher_user).get("/dashboard/").content.decode()
    assert url not in client_as(principal_user).get("/dashboard/").content.decode()


def test_the_center_page_and_the_status_page_link_to_each_other(client_as, developer_user):
    client = client_as(developer_user)
    center = client.get(reverse("command_center:index")).content.decode()
    status = client.get(reverse("command_center:status")).content.decode()
    assert f'href="{reverse("command_center:status")}"' in center
    assert f'href="{reverse("command_center:index")}"' in status
