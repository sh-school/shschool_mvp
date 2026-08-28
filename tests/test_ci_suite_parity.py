"""[CI] وظيفةٌ تُعلن ميزانيةً وتُجري المجموعة الكاملة تُجريها متوازيةً.

قياس ٢٨ أغسطس ٢٠٢٦ على عمليات ناجحة من `main`:

    CD   pytest tests/ -v         11:55 · 12:07 · 12:22 · 14:59
    CI   pytest tests/ -n auto     8:37 ·  9:03 ·  9:19 ·  9:24 ·  9:50

والميزانية ١٥:٠٠. أي أن أسوأ ما رُصد في `CD` ترك **ثانيةً واحدة**. ولم يكن
الفارق في ما تُجريه الوظيفتان — بل في كيف: هناك `-n auto`، وهنا تسلسلٌ محض.

والمجموعة مُثبتةُ الصلاحية للتوازي بالدليل الجاري لا بالافتراض: `ci.yml`
يُجريها هكذا في كل طلب دمج منذ [#28](https://github.com/sh-school/shschool_mvp/pull/28).

والحارس هنا يمنع الانفراج من العودة: وظيفةٌ جديدة تُجري المجموعة تسلسلياً
ستقع في المهلة نفسها بعد أشهر، ولن يربط أحدٌ بين الفشل وسببه.
"""

import pathlib
import re

import pytest
import yaml

WORKFLOWS = pathlib.Path(".github/workflows")

#: نداء `pytest` وما يليه حتى نهاية الأمر.
_CALL = re.compile(r"\bpytest\s+(?P<rest>[^|&;\n]*)")


def _looks_like_a_path(token: str) -> bool:
    """`tests/` و`tests/test_x.py` و`.` مسارات — و`auto` قيمةُ راية.

    التمييز بالشكل لا بالموضع: `-n auto` يضع `auto` موضعَ المسار، فمَن عدّ
    كلَّ ما لا يبدأ بشرطةٍ مساراً ظنّ المجموعةَ الكاملة مقيَّدةً بملفّ.
    """
    return token == "." or token.endswith(".py") or "/" in token


def runs_the_whole_suite(text: str) -> bool:
    """نداءٌ بلا مسارٍ يجمع كل شيء — والمقيَّد بملفٍّ لا يعنينا.

    كان التمييز هنا بالسلسلة `pytest tests/`، فلمّا زال قيدُ المجلّد صار
    الحارس يمسح لا شيء وهو يبدو أخضر. والمعنى أثبتُ من النصّ.
    """
    joined = text.replace("\\\n", " ")
    for m in _CALL.finditer(joined):
        if not any(_looks_like_a_path(t) for t in m.group("rest").split()):
            return True
    return False


def _joined(job) -> str:
    """كل أوامر الوظيفة في نصٍّ واحد."""
    runs = [s.get("run", "") for s in job.get("steps") or [] if isinstance(s.get("run"), str)]
    return chr(10).join(runs)


def _steps():
    for f in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for job_name, job in (doc.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                run = step.get("run")
                if isinstance(run, str):
                    yield f"{f.name}:{job_name}", job, run


def test_the_sweep_finds_the_suite_runners():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    runners = {w for w, _, run in _steps() if runs_the_whole_suite(run)}

    assert len(runners) >= 3, f"لم يُعثر إلّا على {runners}"


def test_a_full_suite_job_that_declares_a_budget_runs_in_parallel():
    """المهلة وعدٌ، والتسلسل لا يفي بوعدِ خمس عشرة دقيقة.

    والوظائف الأخرى التي تُجري المجموعة كاملةً — الليلية وتقارير التغطية
    واختبار الطفرات — لا تُعلن مهلةً أصلاً، فلا وعدَ عليها تُخلفه. ولذلك
    ليست القاعدة «كلّ من يُجري المجموعة يوازيها» بل «كلّ من وعد وفى».
    """
    broken = []
    for f in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for name, job in (doc.get("jobs") or {}).items():
            runs = _joined(job)
            if not runs_the_whole_suite(runs) or job.get("timeout-minutes") is None:
                continue
            if "-n auto" not in runs:
                broken.append(f"{f.name}:{name} timeout={job['timeout-minutes']}")

    assert not broken, f"ميزانيةٌ معلنة بلا توازٍ في: {broken}"


def test_the_deploy_job_is_the_one_that_declares_a_budget():
    """لو أُعلنت ميزانيةٌ في وظيفةٍ أخرى لَما شملها الحارس أعلاه بلا قصد."""
    budgeted = set()
    for f in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for name, job in (doc.get("jobs") or {}).items():
            runs = _joined(job)
            if runs_the_whole_suite(runs) and job.get("timeout-minutes") is not None:
                budgeted.add(f"{f.name}:{name}")

    assert budgeted == {"deploy-railway.yml:test"}, budgeted


def test_the_parallel_runner_is_installed_where_it_is_used():
    """`-n auto` بلا `pytest-xdist` خطأُ وسيطٍ لا بطء."""
    missing = []
    for f in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for job_name, job in (doc.get("jobs") or {}).items():
            body = _joined(job)
            if "-n auto" not in body:
                continue
            if "pytest-xdist" not in body and "requirements" not in body:
                missing.append(f"{f.name}:{job_name}")

    assert not missing, f"توازٍ بلا xdist في: {missing}"


@pytest.mark.parametrize("workflow,job", [("deploy-railway.yml", "test")])
def test_the_deploy_suite_keeps_its_budget(workflow, job):
    """المهلة تبقى ١٥ دقيقة — الإصلاح في السبب لا في رفع السقف."""
    doc = yaml.safe_load((WORKFLOWS / workflow).read_text(encoding="utf-8"))

    assert doc["jobs"][job]["timeout-minutes"] == 15
