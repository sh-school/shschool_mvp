"""[CI] البوّاباتُ الصادقة — ما يُطبع PASS في جدول الملخّص فُحص فعلاً.

كان في `quality-gate.yml` فحصُ mypy يُشغَّل بـ`| head -50 || true` ثمّ `::warning`،
والملخّصُ يطبع `mypy | PASS` — فحصٌ لم يحكم قطّ وجدولٌ يقول إنّه حكم. وكان
`detect-secrets` بـ`|| true` وعددُ الأسرار الجديدة يُحسب ولا يُقارن. وعتبةُ
التغطية ثلاثة أرقام: 70 في البوّابة، و60 في nightly، و85 في عنوانه، والملخّصُ
يطبع PASS عند 60 بينما البوّابة تفشل عند 70.

فهذا الحارس يمنع العودة:

* وظيفةٌ يظهر اسمُها في جدول الملخّص (`needs.<job>.result`) لا تحمل
  `continue-on-error` ولا خطوةً تنتهي بـ`|| true` ولا تُقطَع بـ`| head` —
  فنتيجتُها هي ما جرى، لا ما اختير أن يُرى.
* عتبةُ التغطية رقمٌ واحدٌ في المستودع: `[tool.coverage.report].fail_under` في
  `pyproject.toml`. لا `--cov-fail-under` في سيرِ عملٍ ولا Makefile ولا سكربت،
  ولا `pytest.ini` ولا `.coveragerc` يُبطلان pyproject بصمت.
* ملخّصٌ يحسب حالةَ التغطية يقرأ العتبةَ من pyproject لا يكتب رقماً.
"""

from __future__ import annotations

import pathlib
import re
import tomllib

import yaml

WORKFLOWS = pathlib.Path(".github/workflows")
PYPROJECT = pathlib.Path("pyproject.toml")

#: `needs.<job>.result` داخل خطوةٍ تكتب إلى الملخّص — هذه الوظيفةُ «مُبلَّغٌ عنها».
REPORTED_JOB_RE = re.compile(r"needs\.([A-Za-z0-9_-]+)\.result")
#: `… || true` في آخر السطر (بعده تعليقٌ أو لا شيء) — لا داخلَ `$( … || true)` حيث
#: يُفحص الناتجُ بعدها، كما في حارس البيانات الشخصيّة.
SWALLOWED_RE = re.compile(r"\|\|\s*true\s*(#.*)?$")
TRUNCATED_RE = re.compile(r"\|\s*head\b")
#: مقارنةٌ برقمٍ حرفيّ في ملخّصٍ — العتبةُ تُقرأ لا تُكتب.
LITERAL_THRESHOLD_RE = re.compile(r"rate\s*>=\s*\d")


def _workflows() -> dict[str, dict]:
    return {
        f.name: yaml.safe_load(f.read_text(encoding="utf-8"))
        for f in sorted(WORKFLOWS.glob("*.yml"))
    }


def _run_lines(step: dict) -> list[str]:
    run = step.get("run")
    return run.splitlines() if isinstance(run, str) else []


def reported_jobs(doc: dict) -> dict[str, str]:
    """الوظيفةُ ← الوظيفةُ التي تُبلّغ عنها في ملخّصها."""
    found: dict[str, str] = {}
    for name, job in (doc.get("jobs") or {}).items():
        for step in job.get("steps") or []:
            for line in _run_lines(step):
                if "GITHUB_STEP_SUMMARY" not in line:
                    continue
                for job_id in REPORTED_JOB_RE.findall(line):
                    found[job_id] = name
    return found


def dishonesty_in(job_id: str, job: dict) -> list[str]:
    problems = []
    if job.get("continue-on-error"):
        problems.append(f"{job_id}: continue-on-error على الوظيفة")
    for step in job.get("steps") or []:
        label = step.get("name") or step.get("uses") or "?"
        if step.get("continue-on-error"):
            problems.append(f"{job_id} / {label}: continue-on-error")
        for line in _run_lines(step):
            if SWALLOWED_RE.search(line):
                problems.append(f"{job_id} / {label}: `{line.strip()}`")
            if TRUNCATED_RE.search(line):
                problems.append(f"{job_id} / {label}: مقطوعٌ بـ`| head`: `{line.strip()}`")
    return problems


def test_every_reported_job_is_allowed_to_fail():
    """PASS في الجدول = الوظيفةُ نجحت — لا «نجحت لأنّ الفشلَ ابتُلع»."""
    offenders = []
    for file, doc in _workflows().items():
        jobs = doc.get("jobs") or {}
        for job_id in reported_jobs(doc):
            assert job_id in jobs, f"{file}: الملخّص يذكر وظيفةً لا وجودَ لها: {job_id}"
            offenders += [f"{file}: {p}" for p in dishonesty_in(job_id, jobs[job_id])]
    assert not offenders, "وظيفةٌ تُطبع في الملخّص ولا يُسمح لها أن تفشل:\n  " + "\n  ".join(offenders)


def test_the_gate_summary_actually_reports_the_gate_jobs():
    """الحارسُ يمسح شيئاً: بوّابةُ الجودة تُبلّغ عن وظائفها الخمس."""
    reported = reported_jobs(_workflows()["quality-gate.yml"])
    assert {"test-coverage", "ruff", "mypy", "complexity", "secrets-scan"} <= set(reported)


def test_the_type_check_is_the_ratchet_not_a_warning():
    """mypy يحكم عبر السقّاطة — لا `::warning` ولا أعلامٌ تُخفّف إعدادَ pyproject."""
    job = _workflows()["quality-gate.yml"]["jobs"]["mypy"]
    runs = "\n".join("\n".join(_run_lines(s)) for s in job["steps"])
    assert "tests.mypy_ratchet" in runs
    assert "::warning" not in runs
    assert "--ignore-missing-imports" not in runs
    assert pathlib.Path("tests/mypy_ratchet_baseline.json").is_file()


def test_the_secrets_scan_fails_on_a_new_secret():
    """`detect-secrets-hook --baseline` يخرج بغير صفرٍ على سرٍّ ليس في السجلّ."""
    job = _workflows()["quality-gate.yml"]["jobs"]["secrets-scan"]
    runs = "\n".join("\n".join(_run_lines(s)) for s in job["steps"])
    assert "detect-secrets-hook" in runs and "--baseline .secrets.baseline" in runs
    assert pathlib.Path(".secrets.baseline").is_file()


def test_the_coverage_threshold_is_one_number_in_pyproject():
    project = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
    threshold = project["tool"]["coverage"]["report"]["fail_under"]
    assert isinstance(threshold, int | float) and threshold > 0

    pytest_opts = project["tool"]["pytest"]["ini_options"]
    assert not any(
        "--cov" in opt for opt in pytest_opts.get("addopts", [])
    ), "أعلامُ التغطية تُطلب في البوّابة صراحةً — لا في addopts حيث تُبطئ كلَّ تشغيلٍ محلّيّ"


def test_no_second_threshold_anywhere():
    """`--cov-fail-under` أو `fail_under` خارجَ pyproject رقمٌ ثانٍ — والاثنان يتناقضان يوماً."""
    candidates = [
        *WORKFLOWS.glob("*.yml"),
        pathlib.Path("Makefile"),
        *pathlib.Path("scripts").glob("*.sh"),
        *pathlib.Path("scripts").glob("*.ps1"),
        *pathlib.Path(".").glob("*.toml"),
        *pathlib.Path(".").glob("*.cfg"),
        *pathlib.Path(".").glob("*.ini"),
    ]
    hits = []
    for path in candidates:
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8")
        for n, line in enumerate(text.splitlines(), 1):
            # قراءةُ العتبة (`['fail_under']` عبر tomllib) مسموحة؛ كتابتُها (`fail_under =`) لا.
            if "--cov-fail-under" in line or (
                re.search(r"\bfail_under\s*=", line) and path != PYPROJECT
            ):
                hits.append(f"{path.as_posix()}:{n}: {line.strip()}")
    pyproject_hits = len(
        re.findall(r"^\s*fail_under\s*=", PYPROJECT.read_text(encoding="utf-8"), re.M)
    )
    assert pyproject_hits == 1, f"pyproject يحمل {pyproject_hits} عتبةً"
    assert not hits, "عتبةُ تغطيةٍ ثانية:\n  " + "\n  ".join(hits)


def test_no_shadow_config_file_overrides_pyproject():
    """pytest يقرأ أوّلَ ملفٍّ يجده ويتجاهل الباقي؛ وcoverage يقرأ `.coveragerc` قبل pyproject."""
    shadows = [p for p in ("pytest.ini", ".coveragerc", "tox.ini") if pathlib.Path(p).exists()]
    setup_cfg = pathlib.Path("setup.cfg")
    if setup_cfg.exists() and re.search(
        r"^\[(tool:pytest|coverage:\w+)\]", setup_cfg.read_text(encoding="utf-8"), re.M
    ):
        shadows.append("setup.cfg")
    assert not shadows, f"ملفُّ ضبطٍ يُبطل pyproject.toml بصمت: {shadows}"


def test_summaries_read_the_threshold_instead_of_writing_one():
    hits = []
    for file, doc in _workflows().items():
        for job_id, job in (doc.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                for line in _run_lines(step):
                    if LITERAL_THRESHOLD_RE.search(line):
                        hits.append(f"{file}:{job_id}: {line.strip()}")
    assert not hits, "ملخّصٌ يقارن برقمٍ مكتوبٍ لا مقروءٍ من pyproject:\n  " + "\n  ".join(hits)


def test_no_dead_webhook_rollback():
    """التراجعُ إمّا يُغيّر main (طلبُ دمج) أو يتحقّق — لا ويب هوك أُزيل من خطّ النشر.

    يُقرأ ما تُنفّذه الخطواتُ لا نصُّ الملفّ: التعليقُ في رأسه يذكر الويب هوك ليقول لِمَ زال.
    """
    doc = _workflows()["rollback.yml"]
    runs = "\n".join(
        "\n".join(_run_lines(step))
        for job in (doc.get("jobs") or {}).values()
        for step in job.get("steps") or []
    )
    assert "RAILWAY_DEPLOY_WEBHOOK" not in runs
    assert "commit-tree" in runs and "gh pr create" in runs
    assert "/health/" in runs


class TestTheGuardItself:
    """الحارسُ يمسك ما وُضع له."""

    def test_a_swallowed_step_is_caught(self):
        job = {"steps": [{"name": "x", "run": "mypy . | head -50 || true\necho done"}]}
        found = dishonesty_in("j", job)
        assert len(found) == 2 and "head" in found[1]

    def test_a_checked_substitution_is_not_swallowing(self):
        job = {
            "steps": [
                {"name": "x", "run": 'hits=$(git grep -n x | grep -v y || true)\n[ -z "$hits" ]'}
            ]
        }
        assert dishonesty_in("j", job) == []

    def test_continue_on_error_is_caught_on_job_and_step(self):
        assert dishonesty_in("j", {"continue-on-error": True, "steps": []})
        assert dishonesty_in("j", {"steps": [{"name": "s", "continue-on-error": True}]})

    def test_reported_jobs_are_read_from_the_summary_table(self):
        doc = {
            "jobs": {
                "a": {"steps": []},
                "summary": {
                    "steps": [
                        {
                            "run": "echo \"| a | ${{ needs.a.result == 'success' && 'PASS' || 'FAIL' }} |\" >> $GITHUB_STEP_SUMMARY"
                        }
                    ]
                },
            }
        }
        assert reported_jobs(doc) == {"a": "summary"}
