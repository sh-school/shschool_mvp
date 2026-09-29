"""[SCHEDULE] حارسُ التوليدات العالقة (W-20260929-022، P0).

توليدٌ يعلق في «قيد التوليد»/«في الانتظار» حين يفشل العاملُ في تسجيل فشله هو
نفسُه (انقطاعُ اتّصال القاعدة أثناء الاستثناء الأصليّ) — فلا `_fail()` تكتب،
ولا شيءَ آخر يُخبر المستخدمَ أو النظامَ أنّ التوليدَ مات. الحارسُ هنا يُعلنه
فاشلاً بعد سقفٍ زمنيّ (`soft_time_limit` + هامش)، بصرف النظر عن السبب.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from operations.models import ScheduleGeneration
from operations.tasks import reap_stuck_schedule_generations_task

YEAR = "2026-2027"


def _generation(school, status, *, age_seconds=0):
    gen = ScheduleGeneration.objects.create(school=school, academic_year=YEAR, status=status)
    if age_seconds:
        ScheduleGeneration.objects.filter(pk=gen.pk).update(
            generated_at=timezone.now() - timedelta(seconds=age_seconds)
        )
    gen.refresh_from_db()
    return gen


@pytest.mark.django_db
def test_a_generation_older_than_the_ceiling_is_declared_failed(school):
    stuck = _generation(school, "running", age_seconds=900 + 300 + 1)

    outcome = reap_stuck_schedule_generations_task.run()

    stuck.refresh_from_db()
    assert outcome == {"reaped": 1}
    assert stuck.status == "failed"
    assert "توقّف العاملُ" in stuck.error_message
    assert stuck.finished_at is not None


@pytest.mark.django_db
def test_a_generation_still_within_the_ceiling_is_left_alone(school):
    fresh = _generation(school, "running", age_seconds=60)

    outcome = reap_stuck_schedule_generations_task.run()

    fresh.refresh_from_db()
    assert outcome == {"reaped": 0}
    assert fresh.status == "running"


@pytest.mark.django_db
def test_a_finished_generation_is_never_touched_no_matter_its_age(school):
    """مسودّةٌ أو معتمَدٌ قديمٌ ليس عالقاً — انتهى بنتيجةٍ فعلاً."""
    old_draft = _generation(school, "draft", age_seconds=1_000_000)

    outcome = reap_stuck_schedule_generations_task.run()

    old_draft.refresh_from_db()
    assert outcome == {"reaped": 0}
    assert old_draft.status == "draft"


@pytest.mark.django_db
def test_a_queued_generation_past_the_ceiling_is_also_reaped(school):
    """لا يلتقطه عاملٌ قطّ — عالقٌ في الطابور لا داخل المهمّة، والحكمُ واحد."""
    queued = _generation(school, "queued", age_seconds=900 + 300 + 1)

    outcome = reap_stuck_schedule_generations_task.run()

    queued.refresh_from_db()
    assert outcome == {"reaped": 1}
    assert queued.status == "failed"
