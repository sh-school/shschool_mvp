"""المفاضلةُ بين محاولات التوليد بدرجة المختبر، داخل ميزانيةٍ زمنيّة.

كان البحثُ يقف عند أوّل جدولٍ كامل، ويفاضل بعدد الرخص لا بما يراه النائبُ في
المختبر. فصار: المتعذّرُ، ثمّ الأيّامُ الفارغة، ثمّ الكثافة، ثمّ درجةُ المختبر
نفسِه — وثلاثُ محاولاتٍ على الأقلّ، وتوقّفٌ حين يثبت الأفضل أو تنفد الميزانية.
"""

import pytest

from operations.models import Subject, SubjectClassAssignment
from operations.schedule_lab import grid_lab_score, load_context, slots_from_grid
from operations.scheduler import (
    MAX_ATTEMPTS,
    MIN_ATTEMPTS,
    PATIENCE,
    _search_exhausted,
    generate_schedule,
)
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db
YEAR = "2026-2027"


def test_the_search_runs_at_least_the_minimum_then_stops_on_patience_or_budget():
    assert not _search_exhausted(1, 0.0, 60, idle=5, complete=True), "لا قبل الحدّ الأدنى"
    assert _search_exhausted(MIN_ATTEMPTS, 0.0, 60, idle=PATIENCE, complete=True)
    assert not _search_exhausted(
        MIN_ATTEMPTS, 0.0, 60, idle=PATIENCE, complete=False
    ), "ما دام في الأفضل متعذّرٌ يستمرّ البحث"
    assert _search_exhausted(MIN_ATTEMPTS, 61.0, 60, idle=0, complete=False), "الميزانية"
    assert _search_exhausted(MAX_ATTEMPTS, 0.0, 60, idle=0, complete=False), "الأقصى"


@pytest.fixture
def tiny(school):
    group = ClassGroupFactory(school=school, grade="G8", level_type="prep", academic_year=YEAR)
    for code, name in (("MAT", "الرياضيات"), ("ARA", "اللغة العربية")):
        subject = Subject.objects.create(school=school, name_ar=name, code=code)
        teacher = UserFactory(full_name=name)
        MembershipFactory(
            user=teacher, school=school, role=RoleFactory(school=school, name="teacher")
        )
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=group,
            subject=subject,
            weekly_periods=5,
            is_active=True,
        )
    return school


def test_the_generation_records_every_attempt_and_the_chosen_one(tiny):
    result = generate_schedule(tiny, YEAR)
    snap = result["generation"].config_snapshot

    log = snap["attempt_log"]
    assert snap["attempts"] == len(log) >= MIN_ATTEMPTS
    assert all({"seed", "leftovers", "score", "ms"} <= set(a) for a in log)
    complete = [a for a in log if a["leftovers"] == 0 and a["uncovered"] == 0 and a["densed"] == 0]
    chosen = log[snap["chosen_attempt"]]
    assert chosen["score"] == max(a["score"] for a in complete), "المختارُ أعلى التامّات درجةً"


def test_the_grid_is_scored_by_the_same_lab_as_the_live_schedule(tiny):
    result = generate_schedule(tiny, YEAR)
    ctx = load_context(tiny, YEAR)

    slots = slots_from_grid(result["grid"], ctx)
    score, metrics = grid_lab_score(result["grid"], ctx)

    assert len(slots) == 10, "صفٌّ لكلّ حصّة كصفوف القاعدة"
    assert metrics["validity.completeness"]["value"] == 100.0
    assert 0 < score <= 100
