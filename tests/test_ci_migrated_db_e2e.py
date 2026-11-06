"""حارسُ استعادة القاعدة المهاجَرة لوظيفتَي axe-a11y وe2e — W-20261106-019.

تطبيقُ Migrations يأخذ ~169 ث في كلّ تشغيلٍ لهاتين الوظيفتين، فتُستعاد القاعدةُ المحفوظةُ
(migrated-db-cache على push إلى main) بمفتاحها نفسه. يقرأ YAML بلا شبكة.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

WORKFLOW = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "quality-gate.yml"
RESTORE = "actions/cache/restore@0057852bfaa89a56745cba8c7296529d2fc39830"
DUMP = "${{ runner.temp }}/migrated_db.dump"
CONSUMERS = ("axe-a11y", "e2e")
SAVER = "migrated-db-cache"
MIGRATE_NAME = "تطبيق Migrations"


def _jobs() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]


def _steps(job: str) -> list[dict]:
    return _jobs()[job]["steps"]


def _restore_step(steps: list[dict]) -> dict:
    """خطوةُ استعادة القاعدة المهاجَرة (لا استعادةُ حزم apt، ولا lookup-only للحفظ)."""
    matches = [
        s
        for s in steps
        if s.get("uses", "").startswith(RESTORE) and s.get("with", {}).get("path") == DUMP
    ]
    assert len(matches) == 1, "يجب أن توجد خطوةُ استعادةٍ واحدةٌ للقاعدة المهاجَرة"
    return matches[0]


def _migrate_index(steps: list[dict]) -> int:
    indexes = [i for i, s in enumerate(steps) if s.get("name") == MIGRATE_NAME]
    assert len(indexes) == 1, "يجب أن توجد خطوةُ «تطبيق Migrations» واحدةٌ"
    return indexes[0]


@pytest.mark.parametrize("job", CONSUMERS)
def test_restore_precedes_the_migrate_step(job):
    steps = _steps(job)
    restore = steps.index(_restore_step(steps))
    assert restore < _migrate_index(steps), (job, restore)


@pytest.mark.parametrize("job", CONSUMERS)
def test_restore_key_and_path_equal_the_saver_key(job):
    """يفشل إن اختلف مفتاحُ الاستعادة هنا عن مفتاح الحفظ في migrated-db-cache."""
    saver_lookup = next(
        s
        for s in _steps(SAVER)
        if s.get("uses", "").startswith(RESTORE) and s.get("with", {}).get("lookup-only")
    )
    restore = _restore_step(_steps(job))
    assert restore["with"]["key"] == saver_lookup["with"]["key"], job
    assert (
        restore["with"]["key"]
        == "migrated-db-pg16-${{ hashFiles('**/migrations/*.py', 'requirements.txt') }}"
    )


@pytest.mark.parametrize("job", CONSUMERS)
def test_restore_never_fails_the_job_on_a_miss(job):
    restore = _restore_step(_steps(job))
    assert not restore.get("fail-on-cache-miss")
    assert restore.get("id") == "migrated-db"


@pytest.mark.parametrize("job", CONSUMERS)
def test_migrate_step_restores_on_hit_and_migrates_on_miss(job):
    steps = _steps(job)
    migrate = steps[_migrate_index(steps)]
    env = migrate["env"]
    assert env["CACHE_HIT"] == "${{ steps.migrated-db.outputs.cache-hit }}"
    assert env["DUMP"] == DUMP
    assert env["PGPASSWORD"] == "test_pass"  # pragma: allowlist secret
    run = migrate["run"]
    assert 'if [ "$CACHE_HIT" = "true" ]; then' in run
    restore_cmd = 'pg_restore --no-owner -h 127.0.0.1 -U test_user -d test_db "$DUMP"'
    assert restore_cmd in run
    assert (
        run.index(restore_cmd) < run.index("else") < run.index("python manage.py migrate --noinput")
    )


@pytest.mark.parametrize("job", CONSUMERS)
def test_consumer_timeouts_are_untouched(job):
    assert _jobs()[job]["timeout-minutes"] == 20
