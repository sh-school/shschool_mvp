"""[SCHEDULE] عدّادُ المخالفات الصلبة: رقمٌ واحدٌ من مصدرٍ واحد (W-20260930-005).

كان المولّدُ يكتب `hard_violations = len(errors) + breaches.count` — والأخطاءُ نصوصٌ (نصائحُ الهامش وتقاريرُ
«يومٌ فارغ» وسطرٌ لكلّ متعذّرة) لا مخالفات — بينما تقرأ بوّابةُ الاعتماد `config_snapshot["breaches"]["count"]`
وحده. فخرج في مسوّدةٍ حيّة 8 والإقرارُ عن 1: إقرارٌ مضلِّل. فصار العمودُ يساوي عددَ المُقيِّم نفسِه في كلّ مسار،
وتُحفظ المتعذّرةُ رقماً مستقلّاً `unplaced`.
"""

import importlib

import pytest
from django.apps import apps as real_apps

from operations.models import ScheduleGeneration, Subject, SubjectClassAssignment, TimeSlotConfig
from operations.scheduler import generate_schedule
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"

migration = importlib.import_module("operations.migrations.0061_hard_violations_from_snapshot")


def _generation(school, hard_violations, snapshot):
    return ScheduleGeneration.objects.create(
        school=school,
        academic_year=YEAR,
        status="draft",
        hard_violations=hard_violations,
        config_snapshot=snapshot,
    )


# ── مسار التوليد ────────────────────────────────────────────────────


@pytest.fixture
def overloaded(school):
    """شعبةٌ مطلوبٌ لها حصّةٌ واحدةٌ فوق سعة الأسبوع (36 على 35 خانة) — فتخرج متعذّرةٌ ونصوصُ أخطاءٍ، والمخالفاتُ قليلة.

    وهي حصّةٌ واحدةٌ لا عشرون: الإزاحةُ الموجَّهةُ (`_try_eject`) أسّيّةٌ في عدد المتعذّرات، فكانت 60 حصّةً على 35
    تُنفق ≈290 ثانيةً في الاختبار الواحد وتضاعف خطوةَ pytest في بوّابة الجودة (W-20261002-033)؛ وهذا يحرس ما يلزم
    وحدَه — أنّ العدّادَ عددُ المُقيِّم لا أسطرُ الخطأ."""
    from datetime import time

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
    for index in range(3):
        teacher = UserFactory(full_name=f"معلّم {index}")
        MembershipFactory(user=teacher, school=school, role=role)
        subject = Subject.objects.create(school=school, name_ar=f"مادّة {index}", code=f"S{index}")
        SubjectClassAssignment.objects.create(
            school=school,
            academic_year=YEAR,
            teacher=teacher,
            class_group=group,
            subject=subject,
            weekly_periods=12,
            is_active=True,
        )
    return school


def test_the_generator_writes_the_evaluator_count_not_the_error_lines(overloaded, monkeypatch):
    # خطوةُ الإصلاح (الإزاحةُ الموجَّهة) خارجَ ما يحرسه هذا الاختبار وهي أغلى ما في التوليد — تُعطَّل هنا فقط.
    monkeypatch.setattr(
        "operations.scheduler._repair_pass", lambda grid, leftovers, *a, **k: list(leftovers)
    )

    result = generate_schedule(overloaded, YEAR)

    generation = ScheduleGeneration.objects.get(pk=result["generation"].pk)
    snapshot = generation.config_snapshot
    assert result["errors"], "الحمولةُ فوق السعة: نصوصُ أخطاءٍ لا بدّ منها"
    assert generation.hard_violations == snapshot["breaches"]["count"]
    assert len(result["errors"]) != snapshot["breaches"]["count"], "وإلّا لم يُثبت الاختبارُ شيئاً"
    assert snapshot["unplaced"] >= 1, "المتعذّرةُ رقمٌ مستقلٌّ في اللقطة"


# ── هجرةُ البيانات ──────────────────────────────────────────────────


def _align():
    migration.align_from_snapshot(real_apps, None)


def _restore():
    migration.restore_legacy(real_apps, None)


def test_the_migration_aligns_the_column_to_the_snapshot_and_remembers_the_old_value(school):
    drift = _generation(school, 8, {"breaches": {"count": 1, "items": []}, "mode": "x"})

    _align()

    drift.refresh_from_db()
    assert drift.hard_violations == 1
    assert drift.config_snapshot["breaches"]["count"] == 1
    assert drift.config_snapshot["mode"] == "x", "بقيّةُ اللقطة لا تُمسّ"
    assert drift.config_snapshot["legacy_hard_violations"] == 8


def test_the_migration_leaves_consistent_rows_and_rows_without_a_breach_record_alone(school):
    same = _generation(school, 3, {"breaches": {"count": 3}})
    old = _generation(school, 5, {"total_tasks": 4})
    broken = _generation(school, 2, {"breaches": "غير قاموس"})

    _align()

    for row, expected in ((same, 3), (old, 5), (broken, 2)):
        row.refresh_from_db()
        assert row.hard_violations == expected
        assert "legacy_hard_violations" not in row.config_snapshot


def test_the_migration_is_idempotent(school):
    drift = _generation(school, 8, {"breaches": {"count": 1}})

    _align()
    _align()

    drift.refresh_from_db()
    assert drift.hard_violations == 1
    assert (
        drift.config_snapshot["legacy_hard_violations"] == 8
    ), "التشغيلُ الثاني لا يمحو القيمةَ القديمة"


def test_reversing_the_migration_restores_the_exact_old_value(school):
    drift = _generation(school, 8, {"breaches": {"count": 1}, "mode": "x"})

    _align()
    _restore()

    drift.refresh_from_db()
    assert drift.hard_violations == 8
    assert drift.config_snapshot == {"breaches": {"count": 1}, "mode": "x"}
