"""حارسُ مهلةِ خطوة native-postgres — W-20261106-001.

تعليقُ الخطوة في W-20261105-014 (shard 3/8) أخذ 30 دقيقةً حتى مهلةِ الوظيفة فأُغلقت بطاقةٌ سليمة. فكلُّ خطوةٍ
`uses: ./.github/actions/native-postgres` لها `timeout-minutes` صريح قصير (5 دقائق)، فيصير التعليقُ فشلَ بنيةٍ
سريعاً. الزمنُ الطبيعيّ للخطوة نحو 11 ثانية، فالسقفُ بعيدٌ عنه. يقرأ YAML بلا شبكة.
"""

from __future__ import annotations

from pathlib import Path

import yaml

_ROOT = Path(__file__).resolve().parent.parent
_WORKFLOWS = sorted((_ROOT / ".github" / "workflows").glob("*.yml"))
_ACTION = "./.github/actions/native-postgres"
_MAX_MINUTES = 5


def _native_steps():
    """يعيد (الملف، الوظيفة، رقم الخطوة، الخطوة) لكلّ استعمالٍ للإجراء المحلّيّ."""
    for path in _WORKFLOWS:
        for job_name, job in (
            yaml.safe_load(path.read_text(encoding="utf-8")).get("jobs") or {}
        ).items():
            for index, step in enumerate(job.get("steps") or []):
                if step.get("uses") == _ACTION:
                    yield path.name, job_name, index, step


def test_every_native_postgres_step_has_a_short_timeout():
    """كلُّ خطوةٍ تستعمل native-postgres تملك `timeout-minutes` صريحاً بين 1 و5 دقائق."""
    steps = list(_native_steps())
    assert steps, "لم يُعثر على أيّ خطوةِ native-postgres — الحارسُ لا يحرس شيئاً"
    offenders = []
    for wf, job, index, step in steps:
        minutes = step.get("timeout-minutes")
        if not isinstance(minutes, int) or not 1 <= minutes <= _MAX_MINUTES:
            offenders.append(f"{wf}::{job}::step{index}={minutes!r}")
    assert not offenders, f"خطوات native-postgres بلا مهلة قصيرة صريحة: {offenders}"
