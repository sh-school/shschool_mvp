"""[ROADMAP] هجرةُ 0089 حارسة: تنقل البنودَ الـ45 إلى مساراتٍ تعرفها الصفحة، ولا تلمس ما عدّله المطوّر."""

import importlib

import pytest

from roadmap.models import RoadmapItem, RoadmapMeta
from tests.test_roadmap_lane_guard import LANE_KEYS

pytestmark = pytest.mark.django_db

_m = importlib.import_module("roadmap.migrations.0089_fix_item_lanes_2026_11_20")


class _Apps:
    @staticmethod
    def get_model(_app, name):
        return {"RoadmapItem": RoadmapItem, "RoadmapMeta": RoadmapMeta}[name]


def _meta(keys=LANE_KEYS):
    RoadmapMeta.objects.create(key="roadmap", data={"lanes": [{"key": k, "name": k} for k in keys]})


def _item(code, lane, **kw):
    return RoadmapItem.objects.create(
        code=code,
        lane=lane,
        title="بند",
        status=kw.get("status", "done"),
        progress=100,
        note="قديم",
    )


def test_table_covers_the_45_measured_items():
    olds = [old for old, _new in _m.LANE_FIXES.values()]
    assert len(_m.LANE_FIXES) == 45
    assert {o: olds.count(o) for o in set(olds)} == {
        "security": 11,
        "operations": 24,
        "behavior": 4,
        "design": 3,
        "tools": 3,
    }


def test_every_target_is_a_known_lane_and_no_source_is():
    for old, new in _m.LANE_FIXES.values():
        assert new in LANE_KEYS
        assert old not in LANE_KEYS


def test_moves_items_still_on_the_old_lane():
    _meta()
    _item("N-169", "security")
    _item("CLN-06", "operations")
    _item("N-155", "operations")
    _m.forwards(_Apps, None)
    lanes = dict(RoadmapItem.objects.values_list("code", "lane"))
    assert lanes == {"N-169": "sec", "CLN-06": "backend", "N-155": "ops"}


def test_an_item_the_developer_already_moved_is_untouched():
    _meta()
    _item("N-169", "backend")
    _m.forwards(_Apps, None)
    assert RoadmapItem.objects.get(code="N-169").lane == "backend"


def test_never_moves_to_a_lane_missing_from_meta():
    _meta(keys=[k for k in LANE_KEYS if k != "sec"])
    _item("N-169", "security")
    _item("N-147", "tools")
    _m.forwards(_Apps, None)
    lanes = dict(RoadmapItem.objects.values_list("code", "lane"))
    assert lanes == {"N-169": "security", "N-147": "quality"}


def test_status_progress_and_note_are_kept_and_rerun_is_a_noop():
    _meta()
    _item("N-076", "security", status="doing")
    _m.forwards(_Apps, None)
    _m.forwards(_Apps, None)
    item = RoadmapItem.objects.get(code="N-076")
    assert (item.lane, item.status, item.progress, item.note) == ("sec", "doing", 100, "قديم")


def test_noop_on_empty_db():
    _m.forwards(_Apps, None)
    assert RoadmapItem.objects.count() == 0


def test_public_text_has_no_local_paths_or_hosts():
    text = (_m.__doc__ or "") + " ".join(_m.LANE_FIXES)
    for bad in ("C:/", "C:\\", "D:\\", "localhost", "railway.app", "@", "8011"):
        assert bad not in text


def test_depends_on_0088():
    assert _m.Migration.dependencies == [("roadmap", "0088_sync_items_2026_11_20")]
