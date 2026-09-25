"""[CI] ما تُعلنه سيرُ المراقبة صادق، والكنارُ عند نشرٍ ناجحٍ قائم (REP-17 أ).

مراقبا GitHub Actions (`monitor.yml` كلَّ 15 دقيقة و`worker-heartbeat.yml` كلَّ 10) عملا بنحو 7% و4.4% من وتيرتهما المتوقَّعة
(قياسُ 2026-09-25): جدولةُ GitHub بأفضل جهدٍ لا بضمان. وعنوانٌ يقول «كلَّ 15 دقيقة» يُقرأ ضماناً فيُظنّ أنّ غيابَ القضايا يعني
أنّ الإنتاج سليم. فالعنوانُ يقول الحقيقة (ثانويّ، بأفضل جهد)، والتحقّقُ الذي لا يعتمد الجدولةَ هو كنارٌ يعمل عند كلّ نشرٍ ناجح:
Railway (`railway-app[bot]`) يُنشئ في GitHub نشراً ويحدّث حالتَه ولو كانت الترقيةُ يدويّة.
"""

import pathlib
import re

import pytest
import yaml

WORKFLOWS = pathlib.Path(".github/workflows")
MONITORS = ("monitor.yml", "worker-heartbeat.yml")
CANARY = WORKFLOWS / "post-deploy-canary.yml"
MANUAL_DEPLOY = WORKFLOWS / "deploy-railway.yml"
RAILWAY_ENVIRONMENT = "shschool_mvp / production"


def _load(path: pathlib.Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    """PyYAML يقرأ المفتاحَ `on` قيمةً منطقيّة True."""
    return doc.get("on") or doc.get(True) or {}


@pytest.mark.parametrize("name", MONITORS)
def test_a_scheduled_monitor_does_not_advertise_a_cadence_it_cannot_promise(name):
    title = _load(WORKFLOWS / name)["name"]

    assert not re.search(
        r"كلَّ \d+ (?:دقيقة|دقائق)", title
    ), f"{name}: العنوانُ يَعِد بوتيرةٍ لا تضمنها جدولةُ GitHub — {title}"
    assert "بأفضل جهد" in title, f"{name}: العنوانُ لا يقول إنّ الجدولة بأفضل جهد — {title}"
    assert "ثانويّ" in title, f"{name}: العنوانُ لا يقول إنّه فحصٌ ثانويّ — {title}"


@pytest.mark.parametrize("name", MONITORS)
def test_a_scheduled_monitor_points_at_what_actually_guards_production(name):
    text = (WORKFLOWS / name).read_text(encoding="utf-8")

    assert "لا يثبت" in text, f"{name}: لا يقول إنّ غيابَ القضايا لا يثبت سلامةَ الإنتاج"
    assert "REP-17" in text, f"{name}: لا يشير إلى بند الصدق"


def test_the_canary_listens_to_a_successful_railway_production_deployment():
    doc = _load(CANARY)
    job = doc["jobs"]["canary"]

    assert "deployment_status" in _triggers(doc)
    condition = " ".join(job["if"].split())
    assert "github.event.deployment_status.state == 'success'" in condition
    assert f"github.event.deployment_status.environment == '{RAILWAY_ENVIRONMENT}'" in condition
    assert "github.event.deployment_status.creator.login == 'railway-app[bot]'" in condition


def test_the_canary_cannot_trigger_itself_through_the_manual_pipelines_own_deployment():
    """خطُّ النشر اليدويّ يُنشئ نشراً في بيئة `production` بعد نجاح canary اليدويّ؛ فلو تطابقت البيئتان دار الكنارُ في حلقة."""
    manual = MANUAL_DEPLOY.read_text(encoding="utf-8")
    manual_env = re.search(r"createDeployment\(\{.*?environment: '([^']+)'", manual, re.S)

    assert manual_env, "لم أجد إنشاءَ النشر في deploy-railway.yml — راجع الحارس"
    assert manual_env.group(1) != RAILWAY_ENVIRONMENT
    assert (
        f"== '{manual_env.group(1)}'"
        not in CANARY.read_text(encoding="utf-8").split("jobs:")[1].split("steps:")[0]
    )


def test_the_canary_runs_the_shared_check_with_the_deployed_sha_from_an_env_var():
    """الـSHA يصل عبر متغيّر بيئةٍ لا مُدرَجاً في نصّ الأمر (لا حقنَ)، ويُفحص بالسكربت المُختبَر."""
    job = _load(CANARY)["jobs"]["canary"]
    runs = [step["run"] for step in job["steps"] if "run" in step]

    assert any("scripts/canary-check.sh" in run for run in runs)
    assert not any("${{" in run for run in runs), "تعبيرُ ${{ }} داخل run: — يُمرَّر بمتغيّر بيئة"
    check = next(step for step in job["steps"] if "canary-check.sh" in step.get("run", ""))
    assert check["env"]["DEPLOY_SHA"] == "${{ github.event.deployment.sha }}"
    assert pathlib.Path("scripts/canary-check.sh").is_file()


def test_the_canary_is_bounded_and_supersedes_older_checks():
    doc = _load(CANARY)

    assert doc["concurrency"]["cancel-in-progress"] is True
    assert doc["jobs"]["canary"]["timeout-minutes"] <= 20


def test_a_canary_failure_uses_the_same_issue_as_the_manual_pipeline_so_either_success_closes_it():
    canary = CANARY.read_text(encoding="utf-8")
    manual = MANUAL_DEPLOY.read_text(encoding="utf-8")

    for marker in ("🔴 DEPLOY FAILED", "deploy-failure"):
        assert marker in canary and marker in manual, f"{marker} ليس مشتركاً بين المسارَين"
