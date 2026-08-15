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

import pathlib

import pytest
import yaml

WORKFLOW = pathlib.Path(".github/workflows/security-scan.yml")

#: الوظائف التي تحكم البوابة — تُطابق `needs` و`if` في الملخّص.
REQUIRED_JOBS = ("pip-audit-pypi", "pip-audit-osv", "bandit", "django-check")


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


def test_the_summary_waits_for_every_gating_job():
    assert set(_workflow()["jobs"]["summary"]["needs"]) == set(REQUIRED_JOBS)


@pytest.mark.parametrize("job", REQUIRED_JOBS)
def test_every_required_job_can_block_the_merge(job):
    """الأربع كلّها تحكم — لا بعضها يحكم وبعضها يُطبَع."""
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


@pytest.mark.parametrize("job", REQUIRED_JOBS)
def test_the_gate_reports_which_check_failed(job):
    """رسالةٌ بلا تفصيل تُجبر القارئ على فتح الوظائف واحدةً واحدة."""
    message = _summary_gate_step().split("then")[1]

    assert f"needs.{job}.result }}}}" in message


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
