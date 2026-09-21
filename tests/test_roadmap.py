"""[ROADMAP] خارطةُ تجويد المنصّة — نماذجُ وخدماتٌ وصلاحيّةٌ وتحديثٌ واستيراد.

الصفحةُ لمطوّر المنصّة وحدَه (superuser أو مجموعة developers): غيرُه 403 على الصفحة وعلى كلّ
مسار كتابة، ومجهولٌ يُحوَّل إلى الدخول. والتحديثُ يتحقّق من كلّ قيمة قبل الكتابة ويترك
أثراً في `core_auditlog` بما تغيّر وحدَه. والاستيرادُ idempotent بالرمز.

العيّنةُ هنا مصطنعةٌ صغيرة — اللقطةُ الحقيقيّة لا تُودَع في المستودع (عامّ، وفيها تفاصيلُ أمنيّة).
"""

import json
from copy import deepcopy

import pytest
from django.core.management import CommandError, call_command
from django.test import Client
from django.urls import reverse

from core.models import AuditLog
from roadmap import selectors
from roadmap.import_services import import_snapshot
from roadmap.models import (
    RoadmapChecklistItem,
    RoadmapDecision,
    RoadmapItem,
    RoadmapKpi,
    RoadmapMeta,
    RoadmapRisk,
)
from roadmap.services import (
    RoadmapError,
    page_context,
    set_checklist_done,
    update_decision,
    update_item,
    weighted_progress,
)

pytestmark = pytest.mark.django_db

SNAPSHOT = {
    "items": [
        {
            "id": "T-01", "src": "U", "lane": "sec", "title": "بندٌ أوّل", "status": "doing",
            "progress": 40, "start": "2026-09-21", "end": "2026-10-05", "dateBasis": "مقترَح",
            "effort": 2, "deps": "", "criterion": "معيار", "note": "", "gate": "owner",
            "ref": "الخطّة", "order": 1, "updated": "2026-09-21",
        },
        {
            "id": "T-02", "src": "M", "lane": "mobile", "title": "بندٌ ثانٍ", "status": "todo",
            "progress": 0, "start": None, "end": None, "dateBasis": "", "effort": 0.5, "deps": "T-01",
            "criterion": "", "note": "", "gate": "", "ref": "", "order": 2, "pr": "#12",
        },
        {
            "id": "T-03", "src": "DBT", "lane": "debt", "title": "بندٌ مؤجَّل", "status": "deferred",
            "progress": 0, "start": None, "end": None, "dateBasis": "", "effort": 3, "deps": "",
            "criterion": "", "note": "", "gate": "", "ref": "", "order": 3,
        },
    ],
    "kpis": [
        {
            "code": "K1", "lane": "sec", "name": "مؤشّرٌ رقميّ", "baseline": 10, "current": 5,
            "target": 0, "dir": "down", "unit": "count", "source": "المصدر", "order": 1,
            "history": [{"d": "2026-09-21", "v": 5}], "measuredAt": "2026-09-21", "track": "both",
        },
        {
            "code": "K2", "lane": "mobile", "name": "مؤشّرٌ نصّيّ", "baseline": None, "current": None,
            "target": None, "baselineText": "58%", "targetText": "≤ 5%", "dir": "down",
            "textMode": True, "why": "لم يُقَس بعد", "history": [], "order": 2, "affected": "كلّ البنود",
        },
    ],
    "decisions": [
        {
            "id": "D-1", "src": "U", "title": "قرارٌ مفتوح", "status": "open", "decider": "المالك",
            "due": "مفتوح", "date": "", "blocks": "T-01", "recommendation": "توصية", "order": 1,
        },
        {
            "id": "D-2", "src": "M", "title": "قرارٌ محسوم", "status": "decided", "decider": "المالك",
            "due": "", "date": "2026-09-18", "blocks": "", "recommendation": "", "order": 2,
            "options": "أ أو ب",
        },
    ],
    "risks": [
        {"id": "R1", "src": "الخطّة", "risk": "خطر", "prob": "متوسط", "impact": "مرتفع",
         "mitigation": "تخفيف", "order": 1},
    ],
    "checklist": [
        {"id": "C1", "src": "الجوال", "text": "فحصٌ أوّل", "done": False, "order": 1},
        {"id": "C2", "src": "الجوال", "text": "فحصٌ ثانٍ", "done": True, "order": 2},
    ],
    "meta": {
        "asOf": "2026-09-21", "horizonStart": "2026-09-21", "horizonEnd": "2027-03-31",
        "lanes": [{"key": "sec", "name": "أمن"}, {"key": "mobile", "name": "جوال"}],
        "phases": [{"key": "P0", "name": "تثبيت", "start": "2026-09-21", "end": "2026-09-27", "goal": "هدف"}],
        "milestones": [{"d": "2026-09-25", "name": "نافذة"}],
        "standards": [["الوصولية", "WCAG", "axe", "قائم"]],
        "rules": ["قاعدة"], "limits": "حدود",
    },
}  # fmt: skip


@pytest.fixture
def snapshot():
    return deepcopy(SNAPSHOT)


@pytest.fixture
def seeded(snapshot):
    import_snapshot(snapshot)
    return snapshot


def _post(client, name, code, payload, raw=None):
    body = raw if raw is not None else json.dumps(payload)
    return client.post(reverse(name, args=[code]), data=body, content_type="application/json")


# ── الحساب ────────────────────────────────────────────────────────────────


class TestWeightedProgress:
    def test_empty_is_zero(self):
        assert weighted_progress([]) == 0

    def test_effort_weights_progress(self):
        # (2 × 100 + 1 × 0) / 3 = 66.67 → 67
        assert weighted_progress([("doing", 2, 100), ("doing", 1, 0)]) == 67

    def test_deferred_weighs_nothing(self):
        assert weighted_progress([("doing", 1, 50), ("deferred", 99, 0)]) == 50
        assert weighted_progress([("deferred", 5, 0)]) == 0

    def test_done_counts_as_100_whatever_its_stored_progress(self):
        assert weighted_progress([("done", 1, 0)]) == 100

    def test_zero_or_missing_effort_weighs_one(self):
        assert weighted_progress([("doing", 0, 100), ("doing", 1, 0)]) == 50

    def test_rounds_half_up_like_math_round(self):
        # 25.5 → 26 (لا تقريبَ المصرفيّ 26 → 26 ولا 25.5 → 25 بـ round)
        assert weighted_progress([("doing", 1, 25), ("doing", 1, 26)]) == 26
        assert weighted_progress([("doing", 1, 0), ("doing", 1, 1)]) == 1


# ── النماذج والاستيراد ────────────────────────────────────────────────────


class TestImport:
    def test_first_run_creates_every_row_and_reports_counts(self, snapshot):
        report = import_snapshot(snapshot)

        assert report.created == {
            "items": 3, "kpis": 2, "decisions": 2, "risks": 1, "checklist": 2, "meta": 1,
        }  # fmt: skip
        assert report.updated == {}
        assert RoadmapItem.objects.count() == 3
        assert RoadmapMeta.objects.count() == 1

    def test_second_run_updates_and_never_duplicates(self, snapshot):
        import_snapshot(snapshot)
        report = import_snapshot(snapshot)

        assert report.created == {}
        assert report.updated == {
            "items": 3, "kpis": 2, "decisions": 2, "risks": 1, "checklist": 2, "meta": 1,
        }  # fmt: skip
        counts = [
            m.objects.count()
            for m in (RoadmapItem, RoadmapKpi, RoadmapDecision, RoadmapRisk, RoadmapChecklistItem)
        ]
        assert counts == [3, 2, 2, 1, 2]

    def test_a_changed_snapshot_field_reaches_the_row(self, snapshot):
        import_snapshot(snapshot)
        snapshot["items"][0]["status"] = "done"
        snapshot["items"][0]["progress"] = 100
        import_snapshot(snapshot)

        assert RoadmapItem.objects.get(code="T-01").status == "done"

    def test_fields_map_to_columns_and_odd_keys_go_to_extra(self, seeded):
        item = RoadmapItem.objects.get(code="T-01")
        assert (item.start_date.isoformat(), item.end_date.isoformat()) == (
            "2026-09-21",
            "2026-10-05",
        )
        assert item.effort == 2 and item.gate == "owner" and item.sort_order == 1
        assert RoadmapItem.objects.get(code="T-02").pr == "#12"
        assert RoadmapItem.objects.get(code="T-02").start_date is None

        numeric, textual = RoadmapKpi.objects.get(code="K1"), RoadmapKpi.objects.get(code="K2")
        assert numeric.history == [{"d": "2026-09-21", "v": 5}]
        assert (
            numeric.extra == {"track": "both"} and numeric.measured_at.isoformat() == "2026-09-21"
        )
        assert textual.baseline is None and textual.text_mode and textual.baseline_text == "58%"
        assert textual.extra == {"affected": "كلّ البنود"}

        assert RoadmapDecision.objects.get(code="D-1").decision_date is None
        assert RoadmapDecision.objects.get(code="D-2").decision_date.isoformat() == "2026-09-18"
        assert RoadmapChecklistItem.objects.get(code="C2").done is True
        assert selectors.meta_data()["rules"] == ["قاعدة"]

    def test_a_snapshot_without_pr_does_not_wipe_a_pr_saved_in_the_ui(self, seeded, snapshot):
        RoadmapItem.objects.filter(code="T-01").update(pr="#99")
        import_snapshot(snapshot)  # T-01 بلا مفتاح pr

        assert RoadmapItem.objects.get(code="T-01").pr == "#99"

    def test_import_leaves_an_audit_line_with_counts_not_content(self, snapshot):
        import_snapshot(snapshot)

        entry = AuditLog.objects.get(changes__event="roadmap_snapshot_import")
        assert entry.changes["created"]["items"] == 3
        assert "بندٌ أوّل" not in json.dumps(entry.changes, ensure_ascii=False)

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda s: s["items"][0].update(status="bogus"),
            lambda s: s["items"][0].update(progress=150),
            lambda s: s["items"][0].update(start="2026-99-99"),
            lambda s: s["kpis"][0].update(current="خمسة"),
            lambda s: s["kpis"][0].update(dir="sideways"),
            lambda s: s["decisions"][0].update(status="maybe"),
            lambda s: s["items"].append(dict(s["items"][0])),
            lambda s: s["risks"].append({"risk": "بلا رمز"}),
        ],
    )
    def test_a_bad_snapshot_is_rejected_whole_and_writes_nothing(self, snapshot, mutate):
        mutate(snapshot)

        with pytest.raises(RoadmapError):
            import_snapshot(snapshot)

        assert RoadmapItem.objects.count() == 0 and RoadmapMeta.objects.count() == 0

    def test_a_non_snapshot_is_rejected(self):
        with pytest.raises(RoadmapError):
            import_snapshot({"nothing": []})
        with pytest.raises(RoadmapError):
            import_snapshot([1, 2])


class TestImportCommand:
    def test_reports_created_then_updated(self, tmp_path, snapshot, capsys):
        path = tmp_path / "snap.json"
        path.write_text(json.dumps(snapshot, ensure_ascii=False), encoding="utf-8")

        call_command("import_roadmap_snapshot", str(path))
        first = capsys.readouterr().out
        call_command("import_roadmap_snapshot", str(path))
        second = capsys.readouterr().out

        assert "items: أُنشئ 3 - حُدِّث 0" in first
        assert "items: أُنشئ 0 - حُدِّث 3" in second
        assert RoadmapItem.objects.count() == 3

    def test_missing_file_and_bad_json_are_command_errors(self, tmp_path):
        with pytest.raises(CommandError):
            call_command("import_roadmap_snapshot", str(tmp_path / "absent.json"))
        bad = tmp_path / "bad.json"
        bad.write_text("{not json", encoding="utf-8")
        with pytest.raises(CommandError):
            call_command("import_roadmap_snapshot", str(bad))

    def test_a_rejected_snapshot_is_a_command_error_and_writes_nothing(self, tmp_path, snapshot):
        snapshot["items"][0]["status"] = "bogus"
        path = tmp_path / "snap.json"
        path.write_text(json.dumps(snapshot), encoding="utf-8")

        with pytest.raises(CommandError):
            call_command("import_roadmap_snapshot", str(path))

        assert RoadmapItem.objects.count() == 0


# ── الصلاحيّة ─────────────────────────────────────────────────────────────


class TestAccess:
    def test_the_developer_sees_the_page(self, client_as, developer_user, seeded):
        response = client_as(developer_user).get(reverse("improvement_roadmap"))

        assert response.status_code == 200
        body = response.content.decode()
        assert 'id="rm-data"' in body and 'id="rm-root"' in body
        assert "/static/js/roadmap.js" in body
        assert response.context["item_count"] == 3

    def test_a_superuser_sees_it_too(self, client, school, seeded):
        from tests.conftest import MembershipFactory, RoleFactory, UserFactory

        boss = UserFactory(is_superuser=True)
        MembershipFactory(
            user=boss, school=school, role=RoleFactory(school=school, name="it_technician")
        )
        client.force_login(boss)

        assert client.get(reverse("improvement_roadmap")).status_code == 200

    def test_everyone_else_gets_403_and_a_visitor_is_redirected(
        self, client, teacher_user, principal_user, seeded
    ):
        url = reverse("improvement_roadmap")
        assert client.get(url).status_code == 302
        for user in (teacher_user, principal_user):
            client.force_login(user)
            assert client.get(url).status_code == 403, user

    @pytest.mark.parametrize(
        "name,code",
        [
            ("roadmap_item_update", "T-01"),
            ("roadmap_decision_update", "D-1"),
            ("roadmap_checklist_update", "C1"),
        ],
    )
    def test_writes_are_developer_only_and_change_nothing_otherwise(
        self, client, teacher_user, principal_user, seeded, name, code
    ):
        payload = {"done": True} if name == "roadmap_checklist_update" else {"status": "done"}
        assert _post(client, name, code, payload).status_code == 302
        for user in (teacher_user, principal_user):
            client.force_login(user)
            assert _post(client, name, code, payload).status_code == 403, user

        assert RoadmapItem.objects.get(code="T-01").status == "doing"
        assert RoadmapDecision.objects.get(code="D-1").status == "open"
        assert RoadmapChecklistItem.objects.get(code="C1").done is False

    def test_the_writes_demand_a_csrf_token(self, developer_user, seeded):
        strict = Client(enforce_csrf_checks=True)
        strict.force_login(developer_user)

        response = _post(strict, "roadmap_item_update", "T-01", {"status": "done"})

        assert response.status_code == 403
        assert RoadmapItem.objects.get(code="T-01").status == "doing"

    def test_writes_are_post_only(self, client_as, developer_user, seeded):
        client = client_as(developer_user)
        assert client.get(reverse("roadmap_item_update", args=["T-01"])).status_code == 405


class TestMenu:
    def test_the_link_sits_under_the_identity_guide_for_the_developer_only(
        self, client_as, principal_user, teacher_user
    ):
        # قائمةُ «الإدارة» تُرسم لأدوار القيادة، و«أدوات المطوّر» فيها لمن هو في مجموعة developers
        from django.contrib.auth.models import Group

        principal_user.groups.add(Group.objects.get_or_create(name="developers")[0])
        url = reverse("improvement_roadmap")
        dev_html = client_as(principal_user).get("/dashboard/").content.decode()
        assert f'href="{url}"' in dev_html
        assert dev_html.index(reverse("ui_components")) < dev_html.index(f'href="{url}"')

        teacher_html = client_as(teacher_user).get("/dashboard/").content.decode()
        assert url not in teacher_html


# ── التحديث ───────────────────────────────────────────────────────────────


class TestUpdateItem:
    def test_a_valid_edit_is_saved_returned_stamped_and_audited(
        self, client_as, developer_user, seeded
    ):
        response = _post(
            client_as(developer_user), "roadmap_item_update", "T-01",
            {"status": "doing", "progress": 65, "start": "2026-09-22", "end": "2026-10-08", "pr": "#446", "note": "ملاحظة"},
        )  # fmt: skip

        assert response.status_code == 200
        row = response.json()["row"]
        assert (row["progress"], row["start"], row["end"], row["pr"]) == (
            65,
            "2026-09-22",
            "2026-10-08",
            "#446",
        )
        item = RoadmapItem.objects.get(code="T-01")
        assert item.progress == 65 and item.note == "ملاحظة" and item.updated_by == developer_user
        assert item.date_basis == "محدَّث يدوياً"
        entry = AuditLog.objects.get(changes__event="roadmap_item_update")
        assert entry.object_id == "T-01" and entry.user == developer_user
        assert (
            entry.changes["before"]["progress"] == 40 and entry.changes["after"]["progress"] == 65
        )
        assert "title" not in json.dumps(entry.changes)

    def test_done_forces_100_and_todo_resets_to_0(self, developer_user, seeded):
        assert update_item("T-01", {"status": "done"}, user=developer_user)["progress"] == 100
        assert update_item("T-01", {"status": "todo"}, user=developer_user)["progress"] == 0
        update_item("T-01", {"status": "doing", "progress": 30}, user=developer_user)
        assert update_item("T-01", {"status": "blocked"}, user=developer_user)["progress"] == 30

    def test_done_wins_over_an_explicit_lower_progress(self, developer_user, seeded):
        row = update_item("T-01", {"status": "done", "progress": 20}, user=developer_user)

        assert row["progress"] == 100

    def test_clearing_dates_and_pr_is_allowed(self, developer_user, seeded):
        row = update_item("T-01", {"start": "", "end": None}, user=developer_user)
        assert row["start"] is None and row["end"] is None
        assert "pr" not in update_item("T-02", {"pr": ""}, user=developer_user)

    def test_an_edit_that_changes_nothing_leaves_no_audit_trail(self, developer_user, seeded):
        update_item("T-01", {"status": "doing", "progress": 40}, user=developer_user)

        assert not AuditLog.objects.filter(changes__event="roadmap_item_update").exists()

    @pytest.mark.parametrize(
        "payload,field",
        [
            ({"status": "finished"}, "status"),
            ({"status": None}, "status"),
            ({"progress": 101}, "progress"),
            ({"progress": -1}, "progress"),
            ({"progress": "كثير"}, "progress"),
            ({"progress": True}, "progress"),
            ({"progress": 5.5}, "progress"),
            ({"start": "2026-13-40"}, "start"),
            ({"start": "21/09/2026"}, "start"),
            ({"end": "1999-01-01"}, "end"),
            ({"start": "2026-11-01", "end": "2026-10-01"}, "end"),
            ({"pr": "<script>x</script>"}, "pr"),
            ({"pr": "9" * 65}, "pr"),
            ({"note": "x" * 2001}, "note"),
            ({"title": "لا يُعدَّل"}, "title"),
            ({"status": "done", "lane": "sec"}, "lane"),
        ],
    )
    def test_a_bad_value_is_a_400_naming_the_field_and_saves_nothing(
        self, client_as, developer_user, seeded, payload, field
    ):
        before = RoadmapItem.objects.values().get(code="T-01")

        response = _post(client_as(developer_user), "roadmap_item_update", "T-01", payload)

        assert response.status_code == 400
        assert field in response.json()["fields"]
        after = RoadmapItem.objects.values().get(code="T-01")
        assert {k: v for k, v in after.items() if k != "updated_at"} == {
            k: v for k, v in before.items() if k != "updated_at"
        }
        assert not AuditLog.objects.filter(changes__event="roadmap_item_update").exists()

    @pytest.mark.parametrize("raw", ["{oops", "null", "[]", "{}", "5"])
    def test_a_body_that_is_not_a_json_object_of_edits_is_a_400(
        self, client_as, developer_user, seeded, raw
    ):
        response = _post(client_as(developer_user), "roadmap_item_update", "T-01", None, raw=raw)

        assert response.status_code == 400

    def test_an_oversized_body_is_refused(self, client_as, developer_user, seeded):
        raw = json.dumps({"note": "x" * 9000})

        assert (
            _post(
                client_as(developer_user), "roadmap_item_update", "T-01", None, raw=raw
            ).status_code
            == 400
        )

    def test_an_unknown_code_is_a_404(self, client_as, developer_user, seeded):
        assert (
            _post(
                client_as(developer_user), "roadmap_item_update", "NOPE", {"status": "done"}
            ).status_code
            == 404
        )


class TestUpdateDecisionAndChecklist:
    def test_a_decision_status_and_date_are_saved_and_audited(
        self, client_as, developer_user, seeded
    ):
        response = _post(
            client_as(developer_user), "roadmap_decision_update", "D-1",
            {"status": "decided", "date": "2026-09-22"},
        )  # fmt: skip

        assert response.status_code == 200
        decision = RoadmapDecision.objects.get(code="D-1")
        assert decision.status == "decided" and decision.decision_date.isoformat() == "2026-09-22"
        assert (
            AuditLog.objects.get(changes__event="roadmap_decision_update").changes["after"][
                "status"
            ]
            == "decided"
        )

    @pytest.mark.parametrize(
        "payload",
        [
            {"status": "done"},
            {"date": "غدا"},
            {"title": "x"},
            {"status": "decided", "date": "2026-02-30"},
        ],
    )
    def test_a_bad_decision_edit_is_a_400(self, client_as, developer_user, seeded, payload):
        assert (
            _post(client_as(developer_user), "roadmap_decision_update", "D-1", payload).status_code
            == 400
        )
        assert RoadmapDecision.objects.get(code="D-1").status == "open"

    def test_the_checklist_takes_a_real_boolean_only(self, client_as, developer_user, seeded):
        client = client_as(developer_user)
        assert _post(client, "roadmap_checklist_update", "C1", {"done": True}).status_code == 200
        assert RoadmapChecklistItem.objects.get(code="C1").done is True
        assert AuditLog.objects.filter(changes__event="roadmap_checklist_update").count() == 1

        for bad in ({"done": "true"}, {"done": 1}, {}, {"done": None}):
            assert _post(client, "roadmap_checklist_update", "C1", bad).status_code == 400
        assert _post(client, "roadmap_checklist_update", "NOPE", {"done": True}).status_code == 404

    def test_service_level_not_found_and_type_errors(self, developer_user, seeded):
        with pytest.raises(RoadmapError):
            set_checklist_done("C1", "yes", user=developer_user)
        with pytest.raises(RoadmapError):
            update_decision("D-1", {}, user=developer_user)


# ── سياق الصفحة ───────────────────────────────────────────────────────────


class TestPageContext:
    def test_serialisation_keeps_the_snapshot_keys_the_script_reads(self, seeded):
        data = page_context()["roadmap_data"]

        assert set(data) == {"meta", "items", "kpis", "decisions", "risks", "checklist"}
        item = data["items"][0]
        assert {
            "id",
            "lane",
            "status",
            "progress",
            "start",
            "end",
            "dateBasis",
            "effort",
            "gate",
            "order",
        } <= set(item)
        assert data["items"][1]["pr"] == "#12" and "pr" not in data["items"][0]
        kpis = {k["code"]: k for k in data["kpis"]}
        assert kpis["K1"]["dir"] == "down" and kpis["K1"]["track"] == "both"
        assert kpis["K2"]["baseline"] is None and kpis["K2"]["textMode"] is True
        assert data["decisions"][0]["date"] == "" and data["decisions"][1]["options"] == "أ أو ب"
        assert data["meta"]["lanes"][0]["key"] == "sec"

    def test_the_overall_progress_is_computed_server_side(self, seeded):
        # T-01: جهد 2 وتقدّم 40؛ T-02: جهد 0.5 وتقدّم 0؛ T-03 مؤجَّل ← (80 + 0) / 2.5 = 32
        assert page_context()["overall_progress"] == 32

    def test_an_empty_database_renders_an_empty_page_with_the_import_hint(
        self, client_as, developer_user
    ):
        response = client_as(developer_user).get(reverse("improvement_roadmap"))

        assert response.status_code == 200
        assert "import_roadmap_snapshot" in response.content.decode()


# ── الواجهة: قواعدُ لا تُكسر ──────────────────────────────────────────────


def test_the_script_never_writes_html_from_data_and_uses_no_inline_handlers():
    """كلُّ نصٍّ يدخل الصفحةَ بـtextContent — لا innerHTML ولا eval ولا استمارةً مضمَّنة."""
    import pathlib
    import re

    source = pathlib.Path("static/js/roadmap.js").read_text(encoding="utf-8")

    assert not re.search(
        r"innerHTML|outerHTML|insertAdjacentHTML|document\.write|eval\(|new Function", source
    )
    template = pathlib.Path("templates/roadmap/roadmap.html").read_text(encoding="utf-8")
    assert not re.search(r"\son[a-z]+=|\sstyle=|<script(?![^>]*\bsrc=)(?![^>]*json)", template)


def test_no_roadmap_table_is_school_scoped():
    """وثيقةُ مطوّرٍ عن المنصّة: لا `school` في جداولها، فلا سياسةَ RLS تُطلب منها."""
    from django.apps import apps

    models = list(apps.get_app_config("roadmap").get_models())

    assert len(models) == 6
    assert all("school" not in [f.name for f in m._meta.get_fields()] for m in models)


# ── إضافةُ بند (مهمّةٌ مستقبليّة) ─────────────────────────────────────────


class TestCreateItem:
    PAYLOAD = {
        "title": "مهمّةٌ مستقبليّة",
        "lane": "sec",
        "effort": 2,
        "start": "2026-10-01",
        "end": "2026-10-09",
        "gate": "owner",
    }

    def _create(self, client, payload):
        return client.post(
            reverse("roadmap_item_create"),
            data=json.dumps(payload),
            content_type="application/json",
        )

    def test_a_developer_creates_an_item_with_a_generated_code_and_an_audit_trail(
        self, client_as, developer_user, seeded
    ):
        response = self._create(client_as(developer_user), self.PAYLOAD)

        assert response.status_code == 201
        row = response.json()["row"]
        assert row["id"] == "N-001" and row["src"] == "NEW" and row["status"] == "todo"
        item = RoadmapItem.objects.get(code="N-001")
        assert (
            item.title == "مهمّةٌ مستقبليّة"
            and item.updated_by == developer_user
            and item.gate == "owner"
        )
        assert AuditLog.objects.filter(changes__event="roadmap_item_create").count() == 1
        assert self._create(client_as(developer_user), self.PAYLOAD).json()["row"]["id"] == "N-002"

    @pytest.mark.parametrize(
        ("payload", "field"),
        [
            ({"lane": "sec"}, "title"),
            ({"title": "  ", "lane": "sec"}, "title"),
            ({"title": "x", "lane": "nope"}, "lane"),
            ({"title": "x", "lane": "sec", "status": "zzz"}, "status"),
            ({"title": "x", "lane": "sec", "effort": 0}, "effort"),
            ({"title": "x", "lane": "sec", "start": "2026-10-09", "end": "2026-10-01"}, "end"),
            ({"title": "x", "lane": "sec", "gate": "root"}, "gate"),
            ({"title": "x", "lane": "sec", "code": "HACK-1"}, "code"),
        ],
    )
    def test_a_bad_payload_is_a_400_and_creates_nothing(
        self, client_as, developer_user, seeded, payload, field
    ):
        before = RoadmapItem.objects.count()

        response = self._create(client_as(developer_user), payload)

        assert response.status_code == 400 and field in response.json()["fields"]
        assert RoadmapItem.objects.count() == before

    def test_only_the_developer_may_create(self, client_as, teacher_user, seeded):
        before = RoadmapItem.objects.count()

        assert self._create(client_as(teacher_user), self.PAYLOAD).status_code == 403
        assert RoadmapItem.objects.count() == before
