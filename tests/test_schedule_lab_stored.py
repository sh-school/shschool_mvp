"""[SCHEDULE] صفحةُ التوليد تقرأ مؤشّرات المختبر المخزَّنة ولا تُعيد حسابها عند كلّ فتح (W-20261010-015).

كانت حلقةُ `ScheduleLab.compute()` لكلّ توليدٍ أثقلَ ما في الصفحة (747ms و39 استعلاماً)، والحصصُ لا تتغيّر
بعد التوليد. فهنا: المخزَّنُ يطابق المحسوبَ الآنَ (لا تعريفَ جديد)، وما يُقرأ لا يُحسب، وما غاب يُحسب مرّةً
ويُخزَّن فلا تنكسر صفحةٌ بتوليدٍ قديم، وللصفحة سقفُ استعلاماتٍ معلَنٌ يحرسه اختبار.
"""

import json

import pytest
from django.urls import reverse

from operations.models import ScheduleBaseline
from operations.schedule_decision import metrics_for
from operations.schedule_lab import CATALOG, ScheduleLab, store_metrics
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_schedule_decision import snapshot
from tests.test_schedule_lab import YEAR, small_school  # noqa: F401 — fixture

pytestmark = pytest.mark.django_db

#: سقفُ استعلامات فتح الصفحة بتوليدٍ من V2 ومقاييسُه مخزَّنة — معلَنٌ ويُرفع بقرارٍ لا بصمت.
PAGE_QUERY_CAP = 45  # المقيس 42 (بينها وسطاء المصادقة والمدرسة)


def _roundtrip(value):
    """التخزينُ JSON: المقارنةُ بعد الدوران نفسِه الذي تمرّ به القيمةُ في القاعدة."""
    return json.loads(json.dumps(value))


@pytest.fixture
def generation(small_school):  # noqa: F811
    from operations.scheduler import generate_schedule

    gen = generate_schedule(small_school, YEAR)["generation"]
    gen.config_snapshot = snapshot()
    gen.save(update_fields=["config_snapshot"])
    return gen


def test_the_stored_metrics_equal_what_compute_gives_now(generation):
    store_metrics(generation)
    generation.refresh_from_db()

    assert generation.metrics == _roundtrip(ScheduleLab.for_generation(generation).compute())
    assert all(key in generation.metrics for key in CATALOG)


def test_complete_stored_metrics_are_read_not_recomputed(generation, monkeypatch):
    store_metrics(generation)
    generation.refresh_from_db()

    def boom(self, **kwargs):
        raise AssertionError("لا يُعاد الحسابُ لمقاييس مخزَّنةٍ كاملة")

    monkeypatch.setattr(ScheduleLab, "compute", boom)

    assert metrics_for(generation) == generation.metrics


def test_missing_metrics_are_computed_once_then_stored(generation, monkeypatch):
    generation.metrics = {}
    generation.save(update_fields=["metrics"])
    calls = []
    original = ScheduleLab.compute

    def counting(self, **kwargs):
        calls.append(1)
        return original(self, **kwargs)

    monkeypatch.setattr(ScheduleLab, "compute", counting)

    first = metrics_for(generation)
    generation.refresh_from_db()
    second = metrics_for(generation)

    assert len(calls) == 1
    assert generation.metrics and second == generation.metrics
    assert first["validity.completeness"]["value"] == 100.0


def test_a_metric_added_after_storing_triggers_one_recompute(generation):
    store_metrics(generation)
    generation.refresh_from_db()
    generation.metrics.pop("fairness.stress")
    generation.save(update_fields=["metrics"])

    again = metrics_for(generation)

    assert "fairness.stress" in again
    generation.refresh_from_db()
    assert "fairness.stress" in generation.metrics


def test_the_page_reads_stored_metrics_within_the_declared_query_cap(
    client_as,
    generation,
    small_school,
    django_assert_max_num_queries,
    monkeypatch,  # noqa: F811
):
    store_metrics(generation)
    generation.refresh_from_db()
    ScheduleBaseline.objects.create(
        school=small_school, academic_year=YEAR, label="أساس", metrics=generation.metrics
    )
    principal = UserFactory(full_name="المدير")
    MembershipFactory(
        user=principal, school=small_school, role=RoleFactory(school=small_school, name="principal")
    )

    def boom(self, **kwargs):
        raise AssertionError("الصفحةُ لا تحسب مؤشّراتٍ مخزَّنة")

    monkeypatch.setattr(ScheduleLab, "compute", boom)
    # طلبُ مقارنة المسودّة بالمعتمَد مهمّةٌ خلفيّة (#969)؛ والتنفيذ الفوريّ في الاختبار يحسبها داخل الطلب
    # فيُضخّم العدّ بما لا تفعله الصفحةُ في الإنتاج. نقيس الصفحةَ لا المهمّة.
    monkeypatch.setattr(
        "operations.tasks.compare_generation_to_live_task.delay", lambda *args, **kwargs: None
    )

    with django_assert_max_num_queries(PAGE_QUERY_CAP):
        response = client_as(principal).get(reverse("smart_schedule") + f"?year={YEAR}")

    assert response.status_code == 200
    assert "من الأساس" in response.content.decode()
