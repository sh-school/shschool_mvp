"""أداةُ affected_tests تختار الحرّاسَ من الملفّات المعدَّلة ولا تُسقط شيئاً بصمت (W-20261003-004).

الخطرُ: أن يُعدَّل ملفٌّ فلا يُشغَّل حارسُه فيسقط CI بعد الدفع، أو أن يُنسب نجاحٌ إلى رأسٍ لم يُودَع إيداعُه فعلاً.
"""

import importlib.util
import json
import re
import subprocess
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "affected_tests", _ROOT / "scripts" / "affected_tests.py"
)
at = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(at)

#: حرّاسٌ سُمّيت في الجدول وليست على main بعد — تُسجَّل «غير موجودة» ولا تُتجاهَل.
KNOWN_ABSENT = {"tests/test_table_classification.py"}


def _all_exist(_path):
    return True


def test_a_python_change_selects_size_and_layering_guards():
    plan = at.select(["accounts/services.py"], exists=_all_exist)
    assert {"tests/test_file_size.py", "tests/test_layering.py"} <= set(plan["tests"])
    assert plan["tools"] == []


def test_core_shschool_and_governance_changes_select_the_mypy_ratchet():
    for path in ("core/x.py", "shschool/settings/base.py", "governance/y.py"):
        assert at.select([path], exists=_all_exist)["tools"] == ["mypy_ratchet"], path
    assert at.select(["quality/x.py"], exists=_all_exist)["tools"] == []


def test_css_template_workflow_and_model_changes_select_their_guards():
    assert (
        "tests/test_px_tokens.py"
        in at.select(["static/css/custom/20-components.css"], _all_exist)["tests"]
    )
    assert "tests/test_page_layouts.py" in at.select(["templates/a/b.html"], _all_exist)["tests"]
    wf = at.select([".github/workflows/quality-gate.yml"], _all_exist)
    assert "tests/test_ci_sharding.py" in wf["tests"] and wf["tools"] == ["actionlint"]
    models = at.select(["operations/models/subject.py"], _all_exist)
    assert "tests/test_model_naming.py" in models["tests"]


def test_a_view_or_url_change_selects_the_route_guard():
    assert (
        "tests/test_every_route_is_guarded.py"
        in at.select(["quality/urls.py"], _all_exist)["tests"]
    )
    assert (
        "tests/test_every_route_is_guarded.py"
        in at.select(["quality/views_x.py"], _all_exist)["tests"]
    )
    assert (
        "tests/test_every_route_is_guarded.py"
        not in at.select(["quality/services.py"], _all_exist)["tests"]
    )


def test_a_changed_test_file_runs_itself():
    assert "tests/test_foo.py" in at.select(["tests/test_foo.py"], _all_exist)["tests"]


def test_a_named_guard_that_does_not_exist_is_recorded_not_dropped():
    plan = at.select(["a/models.py"], exists=lambda p: p != "tests/test_table_classification.py")
    assert "tests/test_table_classification.py" in plan["absent"]
    assert "tests/test_table_classification.py" not in plan["tests"]


def test_selection_is_deterministic_and_order_independent():
    files = ["core/a.py", "templates/x.html", "static/css/custom/50-utilities.css"]
    assert at.select(files, _all_exist) == at.select(list(reversed(files)), _all_exist)


def test_every_named_guard_exists_except_the_known_absent_ones():
    named = {g for _n, _m, guards in at.RULES for g in guards}
    missing = {g for g in named if not (_ROOT / g).is_file()}
    assert missing <= KNOWN_ABSENT, f"حارسٌ مسمّى في الجدول ولا ملفَّ له: {missing - KNOWN_ABSENT}"


def test_the_rules_cover_every_test_the_ci_fast_guards_step_runs():
    """لو أُضيف حارسٌ إلى خطوة fast-guards في CI ولم تعرفه الأداةُ سقط هنا لا في CI بعد الدفع."""
    jobs = yaml.safe_load(
        (_ROOT / ".github/workflows/quality-gate.yml").read_text(encoding="utf-8")
    )["jobs"]
    step = next(s for s in jobs["fast-guards"]["steps"] if "-m pytest" in (s.get("run") or ""))
    in_ci = set(re.findall(r"tests/test_\w+\.py", step["run"]))
    covered = {g for _n, _m, guards in at.RULES for g in guards}
    assert in_ci, "لم أجد اختباراتِ fast-guards"
    assert in_ci <= covered, f"حرّاسُ CI بلا قاعدة في الأداة: {sorted(in_ci - covered)}"


# ── الإيداعُ الذي أخفقه خطّافُ التنسيق ──────────────────────────────


def test_dirty_entries_flag_staged_and_modified_but_not_untracked():
    porcelain = "M  staged.py\n M modified.py\n?? new_file.txt\nA  added.py\n"
    assert at.dirty_entries(porcelain) == ["M  staged.py", " M modified.py", "A  added.py"]
    assert at.dirty_entries("?? only_untracked.txt\n") == []
    assert at.dirty_entries("") == []


def _git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t", *args],
        capture_output=True,
        text=True,
        check=True,
    ).stdout


def test_a_real_failed_commit_leaves_a_dirty_tree_the_tool_detects(tmp_path):
    _git(tmp_path, "init", "-q")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(tmp_path, "add", "a.py")
    _git(tmp_path, "commit", "-q", "-m", "base")
    (tmp_path / "a.py").write_text("x = 2\n", encoding="utf-8")
    _git(tmp_path, "add", "a.py")  # الإيداعُ أخفق: بقي التعديلُ مُجهَّزاً لا مودَعاً
    assert at.dirty_entries(_git(tmp_path, "status", "--porcelain")) == ["M  a.py"]
    _git(tmp_path, "commit", "-q", "-m", "second")
    assert at.dirty_entries(_git(tmp_path, "status", "--porcelain")) == []


# ── البصمة ─────────────────────────────────────────────────────────


def _body(**over):
    body = {
        "version": 1,
        "head": "a" * 40,
        "base": "b" * 40,
        "changed": ["core/x.py"],
        "required_tests": ["tests/test_file_size.py"],
        "absent_guards": [],
        "required_tools": [],
        "results": {"pytest": {"status": "ok", "detail": ""}},
        "dirty": [],
        "tool_blob": "c" * 40,
    }
    body.update(over)
    body["digest"] = at.digest_of(body)
    return body


def test_the_digest_ignores_the_timestamp_and_changes_with_any_field():
    body = _body()
    assert at.digest_of({**body, "created": "2026-10-03T00:00:00+00:00"}) == body["digest"]
    assert at.digest_of({**body, "head": "d" * 40}) != body["digest"]
    assert (
        at.digest_of({**body, "results": {"pytest": {"status": "fail", "detail": ""}}})
        != body["digest"]
    )


def test_verify_rejects_a_tampered_fingerprint(tmp_path, monkeypatch):
    body = _body()
    body["results"]["pytest"]["status"] = "fail"  # تعديلٌ بعد الحساب
    path = tmp_path / "fp.json"
    path.write_text(json.dumps(body), encoding="utf-8")
    monkeypatch.setattr(at, "_git", lambda *a: subprocess.CompletedProcess(a, 0, "a" * 40, ""))
    assert at.verify(path) == 1


def test_verify_requires_the_current_head_and_the_main_copy_of_the_tool(tmp_path, monkeypatch):
    path = tmp_path / "fp.json"
    path.write_text(json.dumps(_body()), encoding="utf-8")

    def fake_git(*args):
        if args[0] == "rev-parse" and args[1] == "HEAD":
            return subprocess.CompletedProcess(args, 0, "a" * 40, "")
        return subprocess.CompletedProcess(args, 0, "c" * 40, "")  # blob الأداة في main = المكتوب

    monkeypatch.setattr(at, "_git", fake_git)
    assert at.verify(path) == 0

    monkeypatch.setattr(at, "_git", lambda *a: subprocess.CompletedProcess(a, 0, "z" * 40, ""))
    assert at.verify(path) == 1  # رأسٌ آخر ونسخةُ أداةٍ غيرُ main


def test_verify_fails_when_the_tool_is_not_on_main_yet(tmp_path, monkeypatch):
    path = tmp_path / "fp.json"
    path.write_text(json.dumps(_body()), encoding="utf-8")

    def fake_git(*args):
        if args[1] == "HEAD":
            return subprocess.CompletedProcess(args, 0, "a" * 40, "")
        return subprocess.CompletedProcess(args, 128, "", "fatal")

    monkeypatch.setattr(at, "_git", fake_git)
    assert at.verify(path) == 1


@pytest.mark.parametrize("status", ["fail", "missing"])
def test_verify_rejects_a_fingerprint_with_a_non_ok_result(tmp_path, monkeypatch, status):
    path = tmp_path / "fp.json"
    path.write_text(
        json.dumps(_body(results={"pytest": {"status": status, "detail": ""}})), encoding="utf-8"
    )
    monkeypatch.setattr(
        at,
        "_git",
        lambda *a: subprocess.CompletedProcess(a, 0, "a" * 40 if a[1] == "HEAD" else "c" * 40, ""),
    )
    assert at.verify(path) == 1


# ── حكمُ 0105: أسماءٌ بمسافات، وملفٌّ بلا حارس لا يُطبع سلامةً ──────────


def test_z_output_keeps_names_with_spaces_and_non_ascii():
    out = "core/a b.py\0templates/اختبار.html\0\0"
    assert at.parse_z(out) == ["core/a b.py", "templates/اختبار.html"]


def test_a_changed_file_with_no_rule_is_reported_as_unmatched():
    plan = at.select(["docs/notes.md", "core/x.py"], exists=_all_exist)
    assert plan["unmatched"] == ["docs/notes.md"]
    assert at.select(["docs/notes.md"], exists=_all_exist)["tests"] == []


def test_the_docstring_states_it_is_not_a_gate_or_an_approval_reference():
    doc = at.__doc__
    assert "ليست حاجزاً ولا مرجعاً للاعتماد" in doc and "نسخة main" in doc
    assert "لا يعني السلامة" in doc
    assert "ليس حاجزاً ولا مرجعاً للاعتماد" in (_ROOT / "Makefile").read_text(encoding="utf-8")


# ── W-20261004-009: رفضُ اتّصال القاعدة غيرُ مقيس، وبصمةُ الأداة من الملفّ الجاري ─────────────


@pytest.mark.parametrize(
    "text",
    [
        'psycopg2.OperationalError: connection to server at "localhost" (::1), port 5432 failed: Connection refused',
        "django.db.utils.OperationalError: could not connect to server: Connection refused",
        "sqlalchemy: connection refused (port 5433)",
    ],
)
def test_a_refused_database_connection_is_unmeasured_not_a_failure(monkeypatch, text):
    """بيئةٌ بلا قاعدةٍ ليست فشلَ اختبار: تُصنَّف «غير مقيس» (رمزُ الخروج 3) لا تمنعُ دفعاً كاذباً."""
    monkeypatch.setattr(at, "_run", lambda *a, **k: subprocess.CompletedProcess(a, 1, "", text))
    status, detail = at.run_pytest(["tests/test_x.py"])
    assert status == at.MISSING and "قاعدة" in detail


def test_a_real_test_failure_stays_a_failure(monkeypatch):
    out = "FAILED tests/test_x.py::test_a - AssertionError: assert 1 == 2"
    monkeypatch.setattr(at, "_run", lambda *a, **k: subprocess.CompletedProcess(a, 1, out, ""))
    assert at.run_pytest(["tests/test_x.py"])[0] == at.FAIL


def test_tool_blob_is_the_running_file_not_the_repo_path(tmp_path):
    """`--verify` من نسخة main في مجلّدٍ مؤقّت: البصمةُ تُكتب من الملفّ المنفَّذ لا من نسخة الفرع في المستودع."""
    copy = tmp_path / "affected_tests_main.py"
    copy.write_text(
        (_ROOT / "scripts" / "affected_tests.py").read_text(encoding="utf-8") + "\n# نسخةٌ مغايرة\n",
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location("affected_tests_copy", copy)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    plan = {"tests": [], "absent": [], "tools": [], "unmatched": []}

    body = mod.build_fingerprint("a" * 40, "b" * 40, [], plan, {}, [])

    running = subprocess.run(
        ["git", "hash-object", str(copy)], capture_output=True, text=True, check=True
    ).stdout.strip()
    repo_copy = subprocess.run(
        ["git", "hash-object", "scripts/affected_tests.py"],
        capture_output=True,
        text=True,
        cwd=_ROOT,
        check=True,
    ).stdout.strip()
    assert body["tool_blob"] == running and running != repo_copy
