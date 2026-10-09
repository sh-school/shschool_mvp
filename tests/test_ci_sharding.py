"""تقسيمُ pytest على shards لا يُضيّع اختباراً ولا يكرّره (W-20261002-034).

الخطرُ الوحيد في التقسيم: ملفٌّ يسقط بين shards فيمرّ CI أخضرَ بلا أن يُشغَّل اختباره. فالحارسُ هنا يثبت أنّ
الإسناد قسمةٌ كاملةٌ غيرُ متداخلة حتميّةٌ لأيّ مجموعة ملفّات، وأنّ الملفّ الثقيلَ مثبَّتٌ، وأنّ الإضافة لا تفعل شيئاً
بلا متغيّرات البيئة (فلا يتأثّر التشغيلُ المحلّيّ والليليّ).
"""

import json
import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests import ci_sharding


def _data(**overrides):
    base = {"weights": {}, "default": 1.0, "dedicated": []}
    base.update(overrides)
    return base


FILES = [f"tests/test_{n}.py" for n in range(60)]


@pytest.mark.parametrize("count", [1, 2, 4, 5, 7])
def test_every_file_lands_in_exactly_one_shard(count):
    weights = {f: random.Random(f).uniform(0.1, 90) for f in FILES}
    mapping = ci_sharding.assign(FILES, count, _data(weights=weights))
    assert set(mapping) == set(FILES), "ملفٌّ بلا shard"
    assert all(1 <= shard <= count for shard in mapping.values())


def test_the_assignment_is_deterministic_and_independent_of_input_order():
    data = _data(weights={f: float(i % 9 + 1) for i, f in enumerate(FILES)})
    shuffled = FILES[:]
    random.Random(7).shuffle(shuffled)
    assert ci_sharding.assign(FILES, 5, data) == ci_sharding.assign(shuffled, 5, data)


def test_dedicated_files_go_to_the_last_shard_and_load_it():
    heavy = "tests/test_heavy.py"
    data = _data(weights={heavy: 1000.0}, dedicated=[heavy])
    mapping = ci_sharding.assign([heavy, *FILES], 5, data)
    assert mapping[heavy] == 5
    others_in_last = [f for f in FILES if mapping[f] == 5]
    assert not others_in_last, "الثقيلُ يحمل الـshard الأخير وحدَه ما دامت بقيّةُ الـshards أخفّ"


def test_an_unknown_file_still_gets_a_shard_with_the_default_weight():
    mapping = ci_sharding.assign(["tests/test_new.py"], 4, _data(default=3.0))
    assert mapping == {"tests/test_new.py": 1}


def test_the_greedy_split_is_balanced_within_the_heaviest_file():
    weights = {f: float(random.Random(f).randint(1, 50)) for f in FILES}
    mapping = ci_sharding.assign(FILES, 4, _data(weights=weights))
    loads = [sum(weights[f] for f in FILES if mapping[f] == s) for s in range(1, 5)]
    assert max(loads) - min(loads) <= max(weights.values())


# ── الإضافةُ نفسُها على عناصر pytest ─────────────────────────────────


def _items():
    return [SimpleNamespace(nodeid=f"{f}::test_{i}") for f in FILES[:20] for i in range(3)]


def _config(deselected):
    hook = SimpleNamespace(pytest_deselected=lambda items: deselected.extend(items))
    return SimpleNamespace(hook=hook)


def test_without_the_env_vars_the_plugin_does_nothing(monkeypatch):
    monkeypatch.delenv("CI_SHARD_COUNT", raising=False)
    monkeypatch.delenv("CI_SHARD_INDEX", raising=False)
    items, dropped = _items(), []
    before = list(items)
    ci_sharding.pytest_collection_modifyitems(_config(dropped), items)
    assert items == before and not dropped


def test_the_shards_partition_the_collected_items(monkeypatch, tmp_path):
    seen: list[str] = []
    for index in range(1, 5):
        monkeypatch.setenv("CI_SHARD_COUNT", "4")
        monkeypatch.setenv("CI_SHARD_INDEX", str(index))
        monkeypatch.setenv("CI_SHARD_REPORT", str(tmp_path / f"r{index}.json"))
        items, dropped = _items(), []
        ci_sharding.pytest_collection_modifyitems(_config(dropped), items)
        assert len(items) + len(dropped) == 60
        seen += [i.nodeid for i in items]
    assert sorted(seen) == sorted(i.nodeid for i in _items()), "اختبارٌ ضاع أو تكرّر بين الـshards"

    reports = [
        json.loads((tmp_path / f"r{i}.json").read_text(encoding="utf-8")) for i in range(1, 5)
    ]
    assert {r["total"] for r in reports} == {60}
    assert sum(r["selected"] for r in reports) == 60


def test_an_index_outside_the_count_is_rejected(monkeypatch):
    monkeypatch.setenv("CI_SHARD_COUNT", "3")
    monkeypatch.setenv("CI_SHARD_INDEX", "4")
    with pytest.raises(ValueError):
        ci_sharding.pytest_collection_modifyitems(_config([]), _items())


# ── ملفُّ الأوزان المشحون ───────────────────────────────────────────


def test_the_shipped_weights_pin_only_files_that_exist():
    data = ci_sharding.load_weights()
    assert data["default"] > 0
    missing = [f for f in data["dedicated"] if not Path(f).is_file()]
    assert not missing, f"ملفٌّ مثبَّتٌ لم يعد موجوداً — يُحذف من dedicated: {missing}"


# ── الـworkflow والمُحقِّق ───────────────────────────────────────────

import importlib.util  # noqa: E402

import yaml  # noqa: E402

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "ci_shard_verify", _ROOT / "scripts" / "ci_shard_verify.py"
)
verify_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(verify_mod)

_WF = yaml.safe_load((_ROOT / ".github/workflows/quality-gate.yml").read_text(encoding="utf-8"))[
    "jobs"
]


def _write_reports(tmp_path, reports, coverage_files=True):
    for report in reports:
        (tmp_path / f"shard-report-{report['index']}.json").write_text(
            json.dumps(report), encoding="utf-8"
        )
        if coverage_files:
            (tmp_path / f".coverage.shard{report['index']}").write_bytes(b"")


def _report(index, selected, files, total=10, count=2):
    return {"index": index, "count": count, "total": total, "selected": selected, "files": files}


def test_the_verifier_passes_a_complete_disjoint_cover(tmp_path):
    _write_reports(tmp_path, [_report(1, 6, ["a.py"]), _report(2, 4, ["b.py"])])
    assert verify_mod.verify(tmp_path, 2) == []


def test_the_verifier_catches_a_lost_test(tmp_path):
    _write_reports(tmp_path, [_report(1, 6, ["a.py"]), _report(2, 3, ["b.py"])])
    assert any("ضاع" in p for p in verify_mod.verify(tmp_path, 2))


def test_the_verifier_catches_a_missing_shard_and_a_duplicated_file(tmp_path):
    _write_reports(tmp_path, [_report(1, 10, ["a.py"])])
    assert verify_mod.verify(tmp_path, 2), "shard غاب"
    other = tmp_path / "sub"
    other.mkdir()
    _write_reports(other, [_report(1, 5, ["a.py"]), _report(2, 5, ["a.py"])])
    assert any("shardَين" in p for p in verify_mod.verify(other, 2))


def test_the_workflow_matrix_size_matches_what_the_aggregator_verifies():
    size = len(_WF["pytest-shards"]["strategy"]["matrix"]["shard"])
    steps = _WF["test-coverage"]["steps"]
    verify_step = next(s for s in steps if "ci_shard_verify.py" in (s.get("run") or ""))
    assert verify_step["run"].split()[-1] == str(
        size
    ), "عددُ الـshards في المصفوفة غيرُ ما يتحقّق منه المُجمِّع"


def test_the_aggregator_keeps_the_required_name_and_is_in_the_gate_needs():
    assert _WF["test-coverage"]["name"] == "pytest — تغطية"
    assert {"pytest-shards", "test-coverage"} <= set(_WF["gate-summary"]["needs"])


def test_a_shard_run_never_judges_coverage_and_the_aggregator_does():
    shard_runs = "\n".join(s.get("run", "") for s in _WF["pytest-shards"]["steps"])
    assert "-p tests.ci_sharding" in shard_runs and "--cov-fail-under=0" in shard_runs
    agg_runs = "\n".join(s.get("run", "") for s in _WF["test-coverage"]["steps"])
    assert "coverage combine" in agg_runs and "coverage report" in agg_runs


def test_docs_only_classification_is_kept_in_both_jobs():
    for job in ("pytest-shards", "test-coverage"):
        diff = next(s for s in _WF[job]["steps"] if s.get("id") == "diff")
        assert diff["if"] == "github.event_name == 'pull_request'"


def test_the_verifier_catches_a_missing_coverage_file(tmp_path):
    """shard نجح وقدّم تقريره لكنّ ملفَّ تغطيته لم يصل: يسقط من الدمج بصمتٍ (مراجعة 0105)."""
    _write_reports(tmp_path, [_report(1, 6, ["a.py"]), _report(2, 4, ["b.py"])])
    (tmp_path / ".coverage.shard2").unlink()
    assert any("التغطية" in p for p in verify_mod.verify(tmp_path, 2))


def test_the_zero_threshold_exemption_is_confined_to_the_shard_job():
    """`--cov-fail-under=0` يظهر في أوامر pytest-shards وحدَها — لا في المُجمِّع ولا في أيّ وظيفة أخرى."""
    carriers = [
        name
        for name, job in _WF.items()
        if any("--cov-fail-under" in (s.get("run") or "") for s in job.get("steps") or [])
    ]
    assert carriers == ["pytest-shards"], f"استثناءُ العتبة 0 خرج عن وظيفة الـshards: {carriers}"


def test_docs_only_prepares_no_environment_in_shards_2_to_5():
    steps = _WF["pytest-shards"]["steps"]
    setup = [
        s
        for s in steps
        if s.get("uses", "").startswith("actions/setup-python")
        or "apt-get install" in (s.get("run") or "")
        or "pip install -r requirements.txt" in (s.get("run") or "")
    ]
    assert len(setup) == 3
    for step in setup:
        assert step["if"] == "steps.diff.outputs.docs_only != 'true' || matrix.shard == 1"


def test_each_shard_keeps_native_postgres_and_redis_and_the_job_env():
    """خدماتُ كلّ shard وبيئتُه كاملتان: postgres وredis أصليّان على الـrunner (لا حاويةَ تُسحب من Docker Hub — سقفُ السحب
    أسقط الفحوصَ 2026-10-09). وفقدُ متغيّرات البيئة سقط به ملفُّ الـworkflow كلُّه (GitHub: workflow file issue)."""
    job = _WF["pytest-shards"]
    assert "services" not in job, "حاويةُ خدمةٍ تعيد الاعتمادَ على سحب Docker Hub"
    native = [s for s in job["steps"] if s.get("uses") == "./.github/actions/native-postgres"]
    assert len(native) == 1 and native[0]["with"]["redis"] == "true"
    for key in ("DJANGO_SETTINGS_MODULE", "SECRET_KEY", "CI_SHARD_COUNT", "CI_SHARD_INDEX"):
        assert key in job["env"], f"{key} غاب عن بيئة وظيفة الـshards"
