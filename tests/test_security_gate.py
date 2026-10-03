"""[SEC-GATE] بوابة الأمن المطلوبة قبل الدمج — تفشل مغلقةً.

`Security Summary` أحد سياقين مطلوبين في حماية `main` (`required_status_checks`)،
فهي **بوابة دمج فعلية** لا تقرير. وكانت تفشل على `== "failure"` لوظيفتين من
أربع، فيعبرها أمران:

    وظيفةٌ أُلغيت أو تجاوزت مهلتها  ⇒ `cancelled` لا `failure`
    و`safety` و`django-check`       ⇒ تُطبَعان ولا تحكمان

والأولى ليست افتراضاً: وقعت لوظيفة pytest في خطّ النشر (15:22 مقابل مهلة 15).

**وأوّل تشغيلٍ للبوابة المُغلقة كشف عطباً كان مخفياً:** `safety==3.2.3` تنهار
عند الاستيراد — `AttributeError: module 'typer' has no attribute 'rich_utils'`
— فتُنتج صفر فحص. وكان `|| true` ومُحلِّلٌ متساهل يُخفيان ذلك، فبدت خضراء وهي
لم تفحص حزمةً واحدة.

فتُقوعدت `safety check` — وتوثيق أداتها يُصنّفها deprecated لصالح `safety scan`
التي تتطلّب مصادقةً وترسل النتائج إلى منصّتها، وذلك قرار خدمةٍ خارجية لا ترقية
مكتبة. وحلّ محلّها **مصدر بياناتٍ ثانٍ** عبر `pip-audit`: PyPI وOSV.
"""

import ast
import importlib.util
import os
import pathlib
import subprocess
import sys

import pytest
import yaml

WORKFLOW = pathlib.Path(".github/workflows/security-scan.yml")
PRODUCTION_SETTINGS = pathlib.Path("shschool/settings/production.py")

#: الوظائف التي تحكم البوابة — تُطابق `needs` و`if` في الملخّص.
REQUIRED_JOBS = ("pip-audit-pypi", "pip-audit-osv", "bandit", "django-check")


def _workflow():
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


# ═══════════════════════════════════════════════════════════════════
#  الملخّص — بوابة الدمج نفسها
# ═══════════════════════════════════════════════════════════════════


def _summary_gate_step():
    """خطوةُ الحكم — واحدةٌ، تستدعي الحَكَمَ المشتركَ (`scripts/ci_needs_gate.py`، W-20261002-031).

    كان الحكمُ سطورَ bash تُعدّد الوظائفَ بالاسم في موضعَين؛ فصار سكربتاً يقرأ `toJSON(needs)` كلَّه،
    وهذه الاختباراتُ تحرس **السلوكَ** نفسَه: كلُّ وظيفةٍ مطلوبةٍ تُغلق البوّابة، والنجاحُ وحدَه يفتحها.
    """
    steps = _workflow()["jobs"]["summary"]["steps"]
    gate = [s for s in steps if "ci_needs_gate.py" in s.get("run", "")]

    assert len(gate) == 1, f"خطوة الحكم ليست واحدة: {[s.get('name') for s in steps]}"

    return gate[0]


def _judge():
    # المسارُ من موضع هذا الملفّ لا من مجلّد التشغيل — فلا ينكسر إن شُغّل pytest من غير جذر المستودع (0105 P3).
    root = pathlib.Path(__file__).resolve().parent.parent
    spec = importlib.util.spec_from_file_location(
        "ci_needs_gate", root / "scripts" / "ci_needs_gate.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_summary_job_name_is_the_protected_context():
    """الاسم عقدٌ مع حماية الفرع — تغييرُه يُسقط البوابة بلا أن يُنبّه أحد.

    `required_status_checks.contexts` تُطابق بالاسم النصّي. فاسمٌ جديد يعني
    سياقاً مطلوباً لا يصل أبداً، ودمجاً ينتظر إلى الأبد — أو أسوأ: يُزال
    الشرط فيصير الدمج بلا بوابة.
    """
    assert _workflow()["jobs"]["summary"]["name"] == "Security Summary"


def test_the_summary_waits_for_every_gating_job():
    assert set(_workflow()["jobs"]["summary"]["needs"]) == set(REQUIRED_JOBS)


def test_the_gate_step_reads_all_needs_unconditionally_and_without_exemptions():
    """الحكمُ على `toJSON(needs)` كلِّه، بلا شرطٍ على الخطوة (وإلّا تُتخطّى فتمرّ)، وبلا إعفاءٍ على أيّ حدث."""
    step = _summary_gate_step()

    assert "toJSON(needs)" in step["env"]["NEEDS_JSON"]
    assert "if" not in step
    assert "--no-exempt" in step["run"]
    assert str(_workflow()["jobs"]["summary"]["if"]).strip() == "always()"


@pytest.mark.parametrize("job", REQUIRED_JOBS)
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_every_required_job_can_block_the_merge(job, result):
    """الأربع كلّها تحكم — على كلّ حدثٍ، وأيُّ نتيجةٍ غيرِ النجاح (ومنها skipped) تُغلق."""
    gate = _judge()
    needs = {j: {"result": "success"} for j in REQUIRED_JOBS}
    needs[job] = {"result": result}

    for event in sorted(gate.KNOWN_EVENTS):
        _, failures = gate.judge(needs, event, exempt={})
        assert failures, f"{job}={result} على {event} لا يُغلق البوابة"


def test_the_gate_accepts_success_only_not_a_list_of_failures():
    """النجاحُ وحدَه نجاح — لا تعدادَ لصيغ الفشل.

    تعدادُ صيغ الفشل يترك ما لم يُعدّ: `cancelled` و`timed_out` و`skipped` —
    وصيغةً جديدة من GitHub غداً. وقبولُ النجاح وحده يجعل المجهول يُغلق لا يفتح.
    """
    gate = _judge()
    all_ok = {j: {"result": "success"} for j in REQUIRED_JOBS}

    assert gate.judge(all_ok, "pull_request", exempt={})[1] == []
    for odd in ("timed_out", "neutral", "", "something-new"):
        needs = {**all_ok, "bandit": {"result": odd}}
        assert gate.judge(needs, "pull_request", exempt={})[1], f"نتيجةٌ مجهولة {odd!r} فتحت البوابة"
    assert '== "failure"' not in _summary_gate_step()["run"]


@pytest.mark.parametrize("job", REQUIRED_JOBS)
def test_the_gate_reports_which_check_failed(job):
    """رسالةٌ بلا تفصيل تُجبر القارئ على فتح الوظائف واحدةً واحدة."""
    gate = _judge()
    needs = {j: {"result": "success"} for j in REQUIRED_JOBS}
    needs[job] = {"result": "failure"}

    _, failures = gate.judge(needs, "pull_request", exempt={})

    assert [f for f in failures if f.startswith(f"{job}:")], failures


# ═══════════════════════════════════════════════════════════════════
#  مصدرا البيانات — لا ماسحٌ واحد يُصدّق نفسه
# ═══════════════════════════════════════════════════════════════════


def _run_of(job):
    steps = _workflow()["jobs"][job]["steps"]
    scans = [s["run"] for s in steps if "pip-audit -r" in s.get("run", "")]

    assert len(scans) == 1, f"{job}: نداء فحصٍ ليس واحداً"

    return scans[0]


@pytest.mark.parametrize(
    ("job", "service"),
    [("pip-audit-pypi", "pypi"), ("pip-audit-osv", "osv")],
)
def test_each_audit_job_declares_its_advisory_source(job, service):
    """المصدر يُصرَّح ولا يُترك للافتراض.

    وظيفتان بلا تصريح تقرآن القاعدة نفسها، فتبدوان تغطيةً مزدوجة وهما واحدة.
    """
    assert f"--vulnerability-service {service}" in _run_of(job)


def test_the_two_audit_jobs_do_not_read_the_same_database():
    """الازدواج في **مصدر البيانات** لا في الأداة — وهو المقصود هنا.

    قاعدة PyPI وقاعدة OSV قد تسبق إحداهما الأخرى في نشر تحذير، فالقراءة منهما
    تُضيّق النافذة التي تمرّ فيها ثغرةٌ منشورةٌ في واحدةٍ دون الأخرى.
    """
    assert _run_of("pip-audit-pypi") != _run_of("pip-audit-osv")


@pytest.mark.parametrize("job", ["pip-audit-pypi", "pip-audit-osv"])
def test_no_audit_job_swallows_its_own_failure(job):
    """`|| true` كان يجعل سقوط الأداة يبدو فحصاً ناجحاً بلا ثغرات."""
    assert "|| true" not in _run_of(job)


@pytest.mark.parametrize("job", ["pip-audit-pypi", "pip-audit-osv"])
def test_each_audit_job_writes_its_own_report(job):
    """تقريران باسمين: اسمٌ واحد يجعل الأثر الثاني يطمس الأوّل."""
    assert f"{job}-report.json" in _run_of(job)


# ═══════════════════════════════════════════════════════════════════
#  تقاعُد Safety — وحارسٌ يمنع عودتها صامتةً
# ═══════════════════════════════════════════════════════════════════


def test_the_broken_safety_check_is_gone():
    """`safety check` deprecated وتنهار عند الاستيراد — ولا تعود بلا قرار.

    وعودتها بلا نقاشٍ تعني بوابةً تعتمد أمراً متقاعداً، أو انتقالاً إلى
    `safety scan` بمصادقةٍ وإرسال نتائج إلى منصّةٍ خارجية — وذاك قرارٌ مستقلّ.
    """
    jobs = _workflow()["jobs"]

    assert "safety" not in jobs, "عادت وظيفة safety"

    # الأوامر المُنفَّذة لا نصّ الملفّ: البحث النصّي يلتقط التعليق الذي يشرح
    # **لماذا** تقاعدت — وقد أسقط هذا الحارسَ نفسه قبل تصحيحه. التعليق ليس أمراً.
    commands = "\n".join(
        step.get("run", "") for job in jobs.values() for step in job.get("steps", [])
    )

    assert "safety check" not in commands, "عاد نداء `safety check`"
    assert "check_safety_report" not in commands, "عاد نداء الحَكَم المتقاعد"


def test_the_retired_parser_is_gone():
    """الحَكَم الخاصّ بـSafety ذهب معها — لا شيفرة ميتة تُوهم بأنها تحرس."""
    assert not pathlib.Path("scripts/check_safety_report.py").exists()


# ═══════════════════════════════════════════════════════════════════
#  فحصُ النشر: يُقلع، ولا يُسكِت إلا ما سُمّي
# ═══════════════════════════════════════════════════════════════════

#: المعرِّفات المُسكَتة في الإنتاج — تحذيراتُ **توثيق** API (drf-spectacular) لا أمانِ النشر.
#: القائمةُ لا تتّسع بصمت: من زاد معرِّفاً عدّل هذا الحارسَ وسُئل عنه في المراجعة.
ALLOWED_SILENCED_CHECKS = {"drf_spectacular.W001", "drf_spectacular.W002"}


def test_the_deploy_check_environment_boots_the_production_settings():
    """بيئةُ وظيفة django-check تُقلع بها إعداداتُ الإنتاج — وإلّا لم يفحص الأمرُ شيئاً.

    صار S3 إلزاميّاً في الإنتاج (#382) فانهارت الإعداداتُ عند الاستيراد
    (`ImproperlyConfigured: … AWS_STORAGE_BUCKET_NAME ناقصة`) في هذه الوظيفة بالذات، وبقيت
    خضراءَ لأنّ الأنبوب أخفى الانهيار. فمن أضاف متغيّراً إلزاميّاً غداً يسقط هنا لا في الظلّ.
    """
    job_env = {key: str(value) for key, value in _workflow()["jobs"]["django-check"]["env"].items()}
    result = subprocess.run(
        [sys.executable, "-c", "import shschool.settings.production"],
        env={**os.environ, **job_env},
        cwd=os.getcwd(),
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, "إعداداتُ الإنتاج لا تُقلع ببيئة الوظيفة:\n" + result.stderr[-900:]


def test_the_silenced_system_checks_are_only_the_known_documentation_warnings():
    """`SILENCED_SYSTEM_CHECKS` في الإنتاج تحذيراتُ توثيق API وحدَها — لا فحصَ أمنٍ يُسكَت هنا."""
    silenced = None
    for node in ast.parse(PRODUCTION_SETTINGS.read_text(encoding="utf-8")).body:
        if isinstance(node, ast.Assign) and any(
            getattr(target, "id", None) == "SILENCED_SYSTEM_CHECKS" for target in node.targets
        ):
            silenced = ast.literal_eval(node.value)

    assert silenced is not None, "SILENCED_SYSTEM_CHECKS غير معرَّفة في production.py"
    extra = set(silenced) - ALLOWED_SILENCED_CHECKS
    assert not extra, f"فحوصٌ جديدةٌ مُسكَتة بلا مراجعة: {sorted(extra)}"
