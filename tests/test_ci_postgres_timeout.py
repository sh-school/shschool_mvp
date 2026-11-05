"""[CI] كلُّ خطوةٍ تستعمل `native-postgres` لها مهلةٌ قصيرة — W-20261105-021.

في W-20261105-014 علقت خطوةُ الإجراء المحلّيّ في shard 3/8 ثلاثين دقيقةً حتى مهلة الوظيفة، فأُغلقت بطاقةٌ سليمة.
بـ`timeout-minutes: 5` على الخطوة يصبح التعليقُ فشلَ بنيةٍ خلال خمس دقائق (والزمنُ الطبيعيّ نحو 11 ثانية)،
و`scripts/ci_needs_gate.py` يصنّفه «بنية». يقرأ YAML بلا شبكة.
"""

from pathlib import Path

import yaml

WORKFLOWS = Path(__file__).resolve().parent.parent / ".github" / "workflows"
ACTION = "./.github/actions/native-postgres"
MAX_MINUTES = 5


def _native_steps():
    """يُرجع (الملف، الوظيفة، رقم الخطوة، الخطوة) لكلّ خطوةٍ تستعمل الإجراء المحلّيّ."""
    for path in sorted(WORKFLOWS.glob("*.yml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        for job_name, job in (data.get("jobs") or {}).items():
            for index, step in enumerate(job.get("steps") or []):
                if step.get("uses") == ACTION:
                    yield path.name, job_name, index, step


def test_every_native_postgres_step_has_a_short_timeout():
    """خطوةُ native-postgres بلا timeout-minutes (أو بمهلةٍ طويلة) تُفشل الاختبار."""
    steps = list(_native_steps())
    # حارسٌ من الفراغ: إن تغيّر المسارُ لم يمرّ الاختبارُ على لا شيء بنجاح
    assert steps, "لم يُعثر على أيّ خطوة native-postgres — تحقّق من المسار"
    offenders = []
    for wf, job, index, step in steps:
        minutes = step.get("timeout-minutes")
        if not isinstance(minutes, int) or not 1 <= minutes <= MAX_MINUTES:
            offenders.append(f"{wf}::{job}::الخطوة {index}: timeout-minutes={minutes!r}")
    assert not offenders, offenders
