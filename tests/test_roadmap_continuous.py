"""[ROADMAP] حالةُ «مستمر» — عملٌ دائمٌ لا يُغلق ويُقاس بإيقاع مراجعة (W-20261009-025).

حرّاسُ الاتّفاق: (1) المستمرُّ لا يدخل التقدّمَ المرجَّح ولا «المتأخّر عن موعده» (كالمؤجَّل في الأوّل)؛
(2) إيقاعُ المراجعة وتاريخُها يُتحقَّق منهما ويُفرَّغان لغير المستمر؛ (3) الواجهةُ مرآةٌ للخدمة (الأوزانُ وأيّامُ الإيقاع
من الخادم لا ثوابتُ مكرّرة)؛ (4) الحقلان في Django admin. لا قراءةَ ساعةٍ حقيقيّة: «اليوم» يُمرَّر أو يُثبَّت.
"""

import re
from datetime import date, timedelta
from pathlib import Path

import pytest
from django.contrib import admin as django_admin
from django.utils import timezone

from roadmap import services
from roadmap.admin_monitor import roadmap_status
from roadmap.models import ItemStatus, ReviewCadence, RoadmapItem
from roadmap.services import (
    CADENCE_DAYS,
    RoadmapError,
    create_item,
    page_context,
    review_due,
    review_state,
    update_item,
    weighted_progress,
)

pytestmark = pytest.mark.django_db

TODAY = date(2026, 10, 10)
JS = (Path(__file__).resolve().parent.parent / "static/js/roadmap.js").read_text(encoding="utf-8")


@pytest.fixture
def item(db):
    return RoadmapItem.objects.create(
        code="C-01", lane="sec", title="بند", status="doing", progress=30
    )


@pytest.fixture(autouse=True)
def pinned_today(monkeypatch):
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: TODAY)


# ── الحساب ────────────────────────────────────────────────────────────────


class TestWeightedProgress:
    def test_a_continuous_item_weighs_nothing_like_a_deferred_one(self):
        assert weighted_progress([("doing", 1, 50), ("continuous", 99, 0)]) == 50
        assert weighted_progress([("continuous", 5, 0)]) == 0

    def test_continuous_and_deferred_share_one_definition(self):
        assert services.UNWEIGHTED_STATUSES == {ItemStatus.DEFERRED, ItemStatus.CONTINUOUS}


class TestReviewState:
    @pytest.mark.parametrize(
        ("status", "cadence", "reviewed", "expected"),
        [
            (
                "continuous",
                "monthly",
                TODAY - timedelta(days=30),
                "ontime",
            ),  # الموعدُ اليومَ ليس فائتاً
            ("continuous", "monthly", TODAY - timedelta(days=31), "late"),
            ("continuous", "weekly", TODAY - timedelta(days=7), "ontime"),
            ("continuous", "weekly", TODAY - timedelta(days=8), "late"),
            ("continuous", "weekly", None, "late"),  # لم تُراجَع قطّ
            ("continuous", "", TODAY, "none"),  # بلا إيقاعٍ لا قياس
            ("continuous", "daily", TODAY, "none"),  # إيقاعٌ مجهول
            ("doing", "weekly", TODAY - timedelta(days=99), "none"),  # ليس مستمرّاً
        ],
    )
    def test_the_state_follows_the_cadence_and_the_last_review(
        self, status, cadence, reviewed, expected
    ):
        assert review_state(status, cadence, reviewed, TODAY) == expected

    def test_due_is_the_last_review_plus_the_cadence_days(self):
        assert review_due("weekly", TODAY) == TODAY + timedelta(days=7)
        assert review_due("weekly", None) is None
        assert review_due("", TODAY) is None

    def test_every_cadence_choice_has_days(self):
        assert set(CADENCE_DAYS) == set(ReviewCadence)


# ── التحديث ───────────────────────────────────────────────────────────────


class TestUpdate:
    def test_moving_to_continuous_demands_a_cadence(self, item, developer_user):
        with pytest.raises(RoadmapError) as exc:
            update_item("C-01", {"status": "continuous"}, user=developer_user)
        assert "cadence" in exc.value.errors
        item.refresh_from_db()
        assert item.status == "doing"  # لا كتابةَ جزئيّة

    def test_the_move_is_itself_a_review_and_stamps_today(self, item, developer_user):
        row = update_item(
            "C-01", {"status": "continuous", "cadence": "monthly"}, user=developer_user
        )
        assert (row["status"], row["cadence"], row["reviewed"]) == (
            "continuous",
            "monthly",
            "2026-10-10",
        )

    def test_an_explicit_review_date_wins_and_may_not_be_in_the_future(self, item, developer_user):
        row = update_item(
            "C-01",
            {"status": "continuous", "cadence": "weekly", "reviewed": "2026-10-01"},
            user=developer_user,
        )
        assert row["reviewed"] == "2026-10-01"
        with pytest.raises(RoadmapError) as exc:
            update_item("C-01", {"reviewed": "2026-10-11"}, user=developer_user)
        assert "reviewed" in exc.value.errors

    def test_marking_reviewed_today_resets_a_late_item(self, item, developer_user):
        update_item(
            "C-01",
            {"status": "continuous", "cadence": "weekly", "reviewed": "2026-09-01"},
            user=developer_user,
        )
        row = update_item("C-01", {"reviewed": "2026-10-10"}, user=developer_user)
        assert (
            review_state("continuous", row["cadence"], date.fromisoformat(row["reviewed"]), TODAY)
            == "ontime"
        )

    def test_an_unknown_cadence_is_refused(self, item, developer_user):
        with pytest.raises(RoadmapError) as exc:
            update_item("C-01", {"status": "continuous", "cadence": "daily"}, user=developer_user)
        assert "cadence" in exc.value.errors

    def test_a_cadence_on_a_non_continuous_item_is_refused(self, item, developer_user):
        with pytest.raises(RoadmapError) as exc:
            update_item("C-01", {"cadence": "weekly"}, user=developer_user)
        assert "cadence" in exc.value.errors

    def test_leaving_continuous_clears_the_review_fields_and_the_row_drops_them(
        self, item, developer_user
    ):
        update_item("C-01", {"status": "continuous", "cadence": "weekly"}, user=developer_user)
        row = update_item("C-01", {"status": "doing"}, user=developer_user)
        item.refresh_from_db()
        assert (item.review_cadence, item.last_reviewed) == ("", None)
        assert "cadence" not in row and "reviewed" not in row

    def test_a_continuous_item_keeps_its_stored_progress_untouched(self, item, developer_user):
        update_item("C-01", {"status": "continuous", "cadence": "weekly"}, user=developer_user)
        item.refresh_from_db()
        assert item.progress == 30

    def test_the_change_is_audited_with_the_review_fields(self, item, developer_user):
        from core.models import AuditLog

        update_item("C-01", {"status": "continuous", "cadence": "weekly"}, user=developer_user)
        entry = AuditLog.objects.filter(object_id="C-01").latest("id")
        assert "cadence" in str(entry.changes) or "cadence" in str(entry.new_values or "")


class TestCreate:
    def test_a_new_continuous_item_needs_a_cadence(self, developer_user):
        RoadmapItem.objects.all().delete()
        from roadmap.models import RoadmapMeta

        RoadmapMeta.objects.create(key="roadmap", data={"lanes": [{"key": "sec", "name": "أمن"}]})
        with pytest.raises(RoadmapError) as exc:
            create_item(
                {"title": "حارس", "lane": "sec", "status": "continuous"}, user=developer_user
            )
        assert "cadence" in exc.value.errors
        row = create_item(
            {"title": "حارس", "lane": "sec", "status": "continuous", "cadence": "weekly"},
            user=developer_user,
        )
        assert (row["status"], row["cadence"], row["reviewed"]) == (
            "continuous",
            "weekly",
            "2026-10-10",
        )


# ── الصفحة والواجهة ───────────────────────────────────────────────────────


class TestPage:
    def test_the_page_ships_the_cadence_days_from_the_service(self, item):
        data = page_context()["roadmap_data"]
        assert data["reviewDays"] == {"weekly": 7, "monthly": 30}

    def test_the_overall_progress_ignores_continuous_items(self, item):
        before = page_context()["overall_progress"]
        RoadmapItem.objects.create(
            code="C-02", lane="sec", title="دائم", status="continuous", progress=0, effort=50,
            review_cadence="weekly", last_reviewed=TODAY,
        )  # fmt: skip
        assert page_context()["overall_progress"] == before

    def test_the_js_mirrors_the_service_not_a_second_table_of_days(self):
        assert "D.reviewDays" in JS
        assert not re.search(
            r"weekly\s*:\s*7|monthly\s*:\s*30", JS
        ), "أيّامُ الإيقاع مكرّرةٌ في الواجهة"
        assert "continuous: 'مستمر'" in JS

    def test_the_js_weight_zeroes_exactly_the_statuses_the_service_does(self):
        weight = re.search(r"function weight\(i\) \{(.*?)\}", JS, re.S).group(1)
        for status in services.UNWEIGHTED_STATUSES:
            assert f"'{status.value}'" in weight, status

    def test_the_js_keeps_continuous_out_of_overdue_and_soon(self):
        # الفلترتان اللتان تعدّان «المتأخّر» و«القادم»: كلتاهما تستثني المغلَق (والجدولةُ الزمنيّةُ تعرض كلَّ بندٍ بتاريخه)
        lines = [ln for ln in JS.splitlines() if "i.status !== 'done'" in ln and "dt(i.end)" in ln]
        assert len(lines) == 2 and all("'continuous'" in ln for ln in lines), lines

    def test_the_status_pill_is_never_colour_only(self):
        # أيقونةٌ نصّيّةٌ ↻ ونصُّ حالة المراجعة (WCAG 1.4.1)
        assert "'↻ '" in JS and "مراجعتُه متأخّرة" in JS


# ── Django admin ومراقبة الإدارة ───────────────────────────────────────────


def test_the_review_fields_are_editable_in_django_admin():
    model_admin = django_admin.site._registry[RoadmapItem]
    shown = {f for _, opts in model_admin.fieldsets for f in opts["fields"]}
    assert {"review_cadence", "last_reviewed"} <= shown


def test_the_admin_monitor_does_not_count_a_continuous_item_as_overdue():
    RoadmapItem.objects.create(
        code="C-09", lane="sec", title="دائم", status="continuous", end_date=TODAY - timedelta(days=30),
        review_cadence="weekly", last_reviewed=TODAY,
    )  # fmt: skip
    RoadmapItem.objects.create(
        code="C-10", lane="sec", title="فائت", status="doing", end_date=TODAY - timedelta(days=1)
    )
    assert roadmap_status().value.startswith("1 ")
