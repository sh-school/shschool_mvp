"""[CI] وظيفةُ «تقرير فقط» (`continue-on-error: true`) بمهلةٍ صريحة — وإلّا قطعها حدُّ GitHub (360 دقيقة) فوُسم السيرُ «cancelled».

`mutmut` في `quality.yml` دار ستَّ ساعاتٍ كلَّ أحدٍ ثمّ قطعه الحدُّ، فبقي السيرُ الأسبوعيُّ غيرَ أخضرَ ثلاثةَ أسابيعَ (09-06 و09-13 و09-20)
حتّى بعد أن يخضرّ كلُّ ما عداه — وخطوةُ التقرير التي بعده لم تبلغ فلم يُنتَج تقرير. `continue-on-error` لا يحمي من الإلغاء بالمهلة:
يحمي من الفشل وحدَه. فالمهلةُ تُكتب على الوظيفة نفسِها، والأمرُ البطيءُ فيها يُحدَّ بـ`timeout` ليخرج بصفرٍ فيبلغ التقرير.
"""

import pathlib

import pytest
import yaml

WORKFLOWS = sorted(str(p.as_posix()) for p in pathlib.Path(".github/workflows").glob("*.yml"))


def _report_only_jobs(path: str) -> list[tuple[str, dict]]:
    jobs = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))["jobs"]
    return [(name, job) for name, job in jobs.items() if job.get("continue-on-error") is True]


@pytest.mark.parametrize("path", WORKFLOWS)
def test_a_report_only_job_declares_its_own_timeout(path):
    unbounded = [name for name, job in _report_only_jobs(path) if "timeout-minutes" not in job]
    assert not unbounded, (
        f"{path}: وظيفةُ تقريرٍ بلا `timeout-minutes` — تدور حتّى حدِّ GitHub فيُوسم السيرُ cancelled: "
        + "، ".join(unbounded)
    )


def test_the_guard_still_sees_the_known_report_only_jobs():
    """الحارسُ نفسُه: لو لم يجد أيَّ وظيفةِ تقرير (تغيّر شكلُ الملفّات) لمرّ على لا شيء."""
    found = {name for path in WORKFLOWS for name, _ in _report_only_jobs(path)}
    assert {"mutation-testing", "vulture"} <= found, found
