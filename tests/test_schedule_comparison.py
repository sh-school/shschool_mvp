"""[SCHEDULE] مقارنةُ المسودّة بالمعتمَد بمُقيِّمٍ واحد (W-20261010-008).

المقارنةُ تقيس الجدولين بالمُقيِّم نفسِه وبالمؤشّرات الخمسة (IND-02/04/08/13/16) وعددِ الحصص المتغيّرة، وتخزّن
نتيجتها في `metrics` بلا هجرة وبلا أسماءَ، وتُعلن أنّ HC22 غيرُ مفحوص. ولا تمسّ المولّد.
"""

import json
from datetime import time

import pytest
from django.urls import reverse

from operations.models import ScheduleSlot, Subject, SubjectClassAssignment, TimeSlotConfig
from operations.schedule_comparison import (
    COMPARISON_KEY,
    INDICATORS,
    changed_slots,
    compare_generation,
    slot_keys,
)
from operations.schedule_lab import Context, ScheduleLab, Slot, edge_count
from operations.scheduler import generate_schedule
from operations.tasks import compare_generation_to_live_task
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"
NAMES = ("معلّم أوّل", "معلّم ثانٍ")


@pytest.fixture
def scene(school):
    for period in range(1, 8):
        for day_type in ("regular", "thursday"):
            TimeSlotConfig.objects.create(
                school=school,
                period_number=period,
                start_time=time(6 + period, 0),
                end_time=time(6 + period, 45),
                day_type=day_type,
            )
    role = RoleFactory(school=school, name="teacher")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    for index, name in enumerate(NAMES):
        teacher = UserFactory(full_name=name)
        MembershipFactory(user=teacher, school=school, role=role)
        subject = Subject.objects.create(school=school, name_ar=f"مادّة {index}", code=f"CM{index}")
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=group,
            subject=subject,
            weekly_periods=3,
            is_active=True,
        )
    return school


@pytest.fixture
def draft(scene):
    return scene, generate_schedule(scene, YEAR)["generation"]


def _publish_copy(draft_generation, *, drop=0):
    """يجعل نسخةً من حصص المسودّة هي الجدولَ المعتمَد الحيّ، ويُسقط منها `drop` حصصٍ."""
    rows = list(ScheduleSlot.objects.filter(generation=draft_generation))
    ScheduleSlot.objects.filter(generation=draft_generation).update(is_active=False)
    kept = rows[: len(rows) - drop] if drop else rows
    copies = []
    for r in kept:
        copies.append(
            ScheduleSlot.objects.create(
                school=r.school,
                teacher=r.teacher,
                class_group=r.class_group,
                subject=r.subject,
                day_of_week=r.day_of_week,
                period_number=r.period_number,
                start_time=r.start_time,
                end_time=r.end_time,
                academic_year=r.academic_year,
                is_active=True,
            )
        )
    return copies


def test_an_identical_live_schedule_shows_no_change_and_no_difference(draft):
    _school, generation = draft
    _publish_copy(generation)

    result = compare_generation(generation)

    assert [r["code"] for r in result["rows"]] == [c[0] for c in INDICATORS]
    assert result["changed_slots"] == {"added": 0, "removed": 0}
    assert all(r["delta"] in (0, None) and r["verdict"] == "same" for r in result["rows"])
    # IND-16 بلا تفضيلاتٍ معلنة: لا قيمةَ تُقاس فلا فرق ولا حكم
    assert {r["code"]: r["draft"]["value"] for r in result["rows"]}["IND-16"] is None
    assert result["has_live"] and result["draft"]["hard_total"] == result["live"]["hard_total"] == 0


def test_a_live_schedule_missing_a_lesson_is_less_complete_and_the_changed_count_matches(draft):
    _school, generation = draft
    kept = _publish_copy(generation, drop=1)

    result = compare_generation(generation)

    row = {r["code"]: r for r in result["rows"]}["IND-02"]
    assert row["live"]["detail"] == "5 من 6" and row["draft"]["detail"] == "6 من 6"
    assert row["live"]["value"] < row["draft"]["value"] == 100.0
    assert row["verdict"] == "better"
    # العدُّ المستقلّ: صفوفُ المسودّة التي ليست في المعتمَد = الحصّةُ المُسقَطة
    draft_cells = {
        (str(s.class_group_id), str(s.teacher_id), s.day_of_week, s.period_number)
        for s in ScheduleSlot.objects.filter(generation=generation)
    }
    live_cells = {
        (str(s.class_group_id), str(s.teacher_id), s.day_of_week, s.period_number) for s in kept
    }
    assert result["changed_slots"] == {
        "added": len(draft_cells - live_cells),
        "removed": len(live_cells - draft_cells),
    }
    assert result["changed_slots"]["added"] == 1


def test_a_live_schedule_with_hard_breaches_shows_them_and_a_clean_draft_shows_zero(draft):
    _school, generation = draft
    rows = _publish_copy(generation)
    # كلُّ حصص المادّة الأولى في اليوم نفسِه المتتالي: مخالفةٌ صلبةٌ في المعتمَد وحده
    first_subject = rows[0].subject_id
    for period, row in enumerate([r for r in rows if r.subject_id == first_subject], start=1):
        ScheduleSlot.objects.filter(pk=row.pk).update(day_of_week=0, period_number=period)

    result = compare_generation(generation)

    assert result["draft"]["hard_total"] == 0
    assert result["live"]["hard_total"] > 0 and result["live"]["hard_breaches"]


def test_the_result_is_stored_without_names_and_declares_hc22_unchecked(draft):
    _school, generation = draft
    _publish_copy(generation)

    result = compare_generation(generation)
    generation.refresh_from_db()

    assert generation.metrics[COMPARISON_KEY] == result
    text = json.dumps(result, ensure_ascii=False)
    assert not any(name in text for name in NAMES)
    assert any("HC22" in note and "غير مفحوص" in note for note in result["notes"])
    assert any("V1" in note and "V2" in note for note in result["notes"])
    assert result["seconds"] >= 0


def test_the_background_task_stores_the_comparison_and_is_idempotent(draft):
    _school, generation = draft
    _publish_copy(generation)

    first = compare_generation_to_live_task(str(generation.pk))
    generation.refresh_from_db()
    stored = json.loads(json.dumps(generation.metrics[COMPARISON_KEY]))
    second = compare_generation_to_live_task(str(generation.pk))
    generation.refresh_from_db()

    assert first["ok"] and second["ok"]
    stored.pop("seconds"), generation.metrics[COMPARISON_KEY].pop("seconds")
    assert generation.metrics[COMPARISON_KEY] == stored
    assert compare_generation_to_live_task("00000000-0000-0000-0000-000000000000")["ok"] is False


def test_comparing_without_a_live_schedule_says_so_and_does_not_fail(draft):
    _school, generation = draft
    ScheduleSlot.objects.filter(generation=generation).update(is_active=False)

    result = compare_generation(generation)

    assert result["has_live"] is False
    assert result["changed_slots"]["removed"] == 0


def test_edge_count_counts_the_first_and_last_occupied_slot_not_periods_one_and_seven():
    assert edge_count([2, 4, 6]) == 2  # كان المقياسُ القديم يعدّها صفراً (لا 1 ولا 7)
    assert edge_count([1, 7]) == 2
    assert edge_count([4]) == 1  # حصّةٌ وحيدة: أوّلٌ وآخرٌ معاً، تُعدّ مرّة
    assert edge_count([]) == 0


def _slot(teacher, day, period):
    return Slot(
        teacher_id=teacher,
        teacher_name=teacher,
        class_id=f"c{day}{period}",
        class_name="",
        subject_id="s",
        subject_code="",
        pedagogy="regular",
        requires_double=False,
        day=day,
        period=period,
        band_id="",
        elective_group="",
    )


def test_edge_cv_separates_a_teacher_who_starts_and_ends_early_and_late_from_one_who_does_not():
    ctx = Context()
    # أ: لكلّ يومٍ حصّتان (2 و6) = خمسُ أيامٍ طرفاها؛ ب: أيامٌ بثلاثٍ متوسّطة يكون طرفاها 3 و5 — لا 1 ولا 7
    a = [_slot("a", d, p) for d in range(5) for p in (2, 6)]
    b = [_slot("b", d, p) for d in range(5) for p in (3, 4, 5)]
    lab = ScheduleLab(a + b, ctx)

    shares = {
        t: sum(edge_count(ps) for ps in days.values()) / lab.load[t]
        for t, days in lab.by_teacher_day.items()
    }

    assert shares["a"] == 1.0 and shares["b"] == pytest.approx(2 / 3)
    assert lab.edge_fairness()["value"] > 0  # القديمُ كان صفراً للاثنين (لا حصّةَ 1 ولا 7)


def test_changed_slots_is_a_symmetric_count():
    assert changed_slots({1, 2, 3}, {2, 3, 4, 5}) == {"added": 1, "removed": 2}


def test_slot_keys_ignore_the_row_identity(draft):
    _school, generation = draft
    kept = _publish_copy(generation)

    assert slot_keys(ScheduleSlot.objects.filter(generation=generation)) == slot_keys(kept)


def test_the_generation_page_shows_the_five_indicators_without_names(client, school, draft):
    _school, generation = draft
    _publish_copy(generation)
    compare_generation(generation)
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="مدير المدرسة")
    MembershipFactory(user=user, school=school, role=role)
    client.force_login(user)

    response = client.get(f"{reverse('smart_schedule')}?year={YEAR}")

    html = response.content.decode()
    assert response.status_code == 200
    for code, name, *_ in INDICATORS:
        assert code in html and name in html
    assert "HC22" in html and "الحصص المتغيّرة" in html
    assert not any(name in html.split("gen-compare-")[1] for name in NAMES)
