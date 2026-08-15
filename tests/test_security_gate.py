"""[SEC-GATE] بوابة الأمن المطلوبة قبل الدمج — تفشل مغلقةً.

`Security Summary` أحد سياقين مطلوبين في حماية `main` (`required_status_checks`)،
فهي **بوابة دمج فعلية** لا تقرير. وكانت تفشل على `== "failure"` لوظيفتين من
أربع، فيعبرها أمران:

    وظيفةٌ أُلغيت أو تجاوزت مهلتها  ⇒ `cancelled` لا `failure`
    `safety` و`django-check`        ⇒ تُطبَعان ولا تحكمان

والأولى ليست افتراضاً: وقعت لوظيفة pytest في خطّ النشر (15:22 مقابل مهلة 15).

ومعها كان حَكَمُ تقرير Safety يفشل مفتوحاً — تقريرٌ غائب أو غير قابلٍ للتحليل
يخرج بنجاح. «لم أفحص» كانت تُقرأ «لم أجد».
"""

import json
import pathlib
import subprocess
import sys

import pytest
import yaml

WORKFLOW = pathlib.Path(".github/workflows/security-scan.yml")
REQUIRED_JOBS = ("pip-audit", "bandit", "safety", "django-check")


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════
#  الملخّص — بوابة الدمج نفسها
# ═══════════════════════════════════════════════════════════════════


def _summary_gate_step():
    steps = _workflow()["jobs"]["summary"]["steps"]
    gate = [s for s in steps if "exit 1" in s.get("run", "")]

    assert len(gate) == 1, f"خطوة الحكم ليست واحدة: {[s.get('name') for s in steps]}"

    return gate[0]["run"]


def test_the_summary_job_name_is_the_protected_context():
    """الاسم عقدٌ مع حماية الفرع — تغييرُه يُسقط البوابة بلا أن يُنبّه أحد.

    `required_status_checks.contexts` تُطابق بالاسم النصّي. فاسمٌ جديد يعني
    سياقاً مطلوباً لا يصل أبداً، ودمجاً ينتظر إلى الأبد — أو أسوأ: يُزال
    الشرط فيصير الدمج بلا بوابة.
    """
    assert _workflow()["jobs"]["summary"]["name"] == "Security Summary"


def test_the_summary_waits_for_all_four_security_jobs():
    assert set(_workflow()["jobs"]["summary"]["needs"]) == set(REQUIRED_JOBS)


@pytest.mark.parametrize("job", REQUIRED_JOBS)
def test_every_required_job_can_block_the_merge(job):
    """الأربع كلّها تحكم — لا اثنتان تحكمان واثنتان تُطبَعان."""
    condition = f'"${{{{ needs.{job}.result }}}}" != "success"'

    assert condition in _summary_gate_step(), f"{job} لا يُغلق البوابة"


def test_the_gate_accepts_success_only_not_a_list_of_failures():
    """`!= success` لا `== failure`.

    تعدادُ صيغ الفشل يترك ما لم يُعدّ: `cancelled` و`timed_out` و`skipped` —
    وصيغةً جديدة من GitHub غداً. وقبولُ النجاح وحده يجعل المجهول يُغلق لا يفتح.
    """
    gate = _summary_gate_step()

    assert '== "failure"' not in gate, "عادت المقارنة إلى تعداد صيغ الفشل"
    assert gate.count('!= "success"') == len(REQUIRED_JOBS)


def test_the_gate_reports_which_check_failed():
    """رسالةٌ بلا تفصيل تُجبر القارئ على فتح أربع وظائف ليعرف أيّها سقط."""
    gate = _summary_gate_step()

    for job in REQUIRED_JOBS:
        assert f"needs.{job}.result }}}}" in gate.split("exit 1")[0].split("then")[1]


# ═══════════════════════════════════════════════════════════════════
#  حَكَم تقرير Safety — أربع حالات
# ═══════════════════════════════════════════════════════════════════

SCRIPT = pathlib.Path("scripts/check_safety_report.py")


def _run(report_path):
    return subprocess.run(
        [sys.executable, str(SCRIPT), str(report_path)],
        capture_output=True,
        text=True,
        check=False,
    )


def _write(tmp_path, payload):
    report = tmp_path / "safety-report.json"
    report.write_text(
        payload if isinstance(payload, str) else json.dumps(payload), encoding="utf-8"
    )
    return report


def test_a_missing_report_fails_the_check(tmp_path):
    """«لم أفحص» يجب أن تُغلق البوابة كما تُغلقها «وجدتُ ثغرة»."""
    result = _run(tmp_path / "does-not-exist.json")

    assert result.returncode == 1, result.stdout


def test_an_unparseable_report_fails_the_check(tmp_path):
    """تقريرٌ مبتور — من أداةٍ سقطت في منتصفها — ليس تقريراً نظيفاً."""
    result = _run(_write(tmp_path, "{not json"))

    assert result.returncode == 1, result.stdout


def test_an_empty_report_fails_the_check(tmp_path):
    result = _run(_write(tmp_path, ""))

    assert result.returncode == 1, result.stdout


def test_a_report_without_the_expected_structure_fails(tmp_path):
    """بنيةٌ لا نعرفها — تغيّرت الأداة مثلاً — لا تُقرأ على أنها سلامة."""
    result = _run(_write(tmp_path, {"unexpected": "shape"}))

    assert result.returncode == 1, result.stdout


@pytest.mark.parametrize("severity", ["HIGH", "CRITICAL", "high", "critical"])
def test_a_blocking_finding_fails_the_check(tmp_path, severity):
    """والحساسية لحالة الأحرف مقصودة: الأداة لا تضمن صيغةً واحدة."""
    report = _write(
        tmp_path,
        {
            "vulnerabilities": [
                {
                    "package_name": "example",
                    "vulnerability_id": "PYSEC-0000",
                    "severity": severity,
                }
            ]
        },
    )

    result = _run(report)

    assert result.returncode == 1, result.stdout
    assert "example" in result.stdout, "الرسالة لا تُسمّي الحزمة"


def test_a_clean_valid_report_passes(tmp_path):
    """الضبط الموجب: حارسٌ يرفض كل شيء لا يحرس شيئاً."""
    result = _run(_write(tmp_path, {"vulnerabilities": []}))

    assert result.returncode == 0, result.stdout


def test_low_severity_findings_do_not_block(tmp_path):
    """السياسة الحالية تحجب HIGH/CRITICAL وحدها — والباقي يُسجَّل ولا يُوقف."""
    report = _write(
        tmp_path,
        {"vulnerabilities": [{"package_name": "x", "severity": "MEDIUM"}]},
    )

    assert _run(report).returncode == 0


# ═══════════════════════════════════════════════════════════════════
#  الوظيفة نفسها — لا تبتلع فشل الأداة
# ═══════════════════════════════════════════════════════════════════


def _safety_steps():
    return _workflow()["jobs"]["safety"]["steps"]


def test_the_safety_run_does_not_swallow_tool_failure():
    """`|| true` كان يجعل سقوط الأداة يبدو فحصاً ناجحاً بلا ثغرات."""
    check = [s for s in _safety_steps() if s.get("name") == "Safety check"][0]

    assert "|| true" not in check["run"]


def test_the_verdict_lives_in_a_tested_script_not_in_yaml():
    """منطقٌ داخل YAML لا يُشغّله إلا CI — فلا يُكتشف عطبه إلا حين يُحتاج."""
    verdict = [s for s in _safety_steps() if s.get("name") == "Check for HIGH severity"][0]

    assert "scripts/check_safety_report.py" in verdict["run"]
    assert "import json" not in verdict["run"], "عاد المنطق إلى YAML"
