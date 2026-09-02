"""[SCHEDULER] تشريحُ الجدول — تُثبَّت حساباتُه قبل أن يُبنى عليه قرار.

وأوّلُ ما يُثبَّت هنا هويّةُ المادّة. فقد أخرج التقريرُ الأوّل «تكنولوجيا
المعلومات: أربعُ حصصٍ متلاصقة» و«التكنولوجيا: ثمانٍ وثلاثون بلا تلاصق» في
سطرين متجاورين، فبدا أنّه تناقضٌ في مادّةٍ واحدة. وهما مادّتان بكودين `IT`
و`TECH`. والاسمُ وحده لا يفرّق، والمعرّفُ يفرّق.

ولو مضى الالتباسُ لصار سؤالاً يُطرح على الإدارة عن مادّةٍ لا وجودَ لها.
"""

import pytest

from operations.schedule_deep_profile import (
    declared_versus_observed_doubles,
    gap_anatomy,
    grade_section_variance,
    peer_outliers,
    subject_adjacency,
)
from operations.schedule_profile import Lesson, profile_teachers


def lesson(*, klass="10/1", subject="رياضيات", code="MATH", sid=None, day=0, period=1, grade="G10"):
    return Lesson(
        teacher_id="t1",
        teacher_name="معلّم",
        class_id=klass,
        class_name=klass,
        subject_id=sid or f"id-{code}",
        subject_name=subject,
        subject_code=code,
        day=day,
        period=period,
        grade=grade,
    )


# ── الهويّة ──────────────────────────────────────────────────────────


def test_two_subjects_sharing_a_similar_name_are_never_merged():
    """«تكنولوجيا المعلومات» و«التكنولوجيا» لا يجتمعان في صفٍّ واحد."""
    lessons = [
        lesson(subject="تكنولوجيا المعلومات", code="IT", day=0, period=1),
        lesson(subject="تكنولوجيا المعلومات", code="IT", day=0, period=2),
        lesson(subject="التكنولوجيا", code="TECH", day=1, period=1),
        lesson(subject="التكنولوجيا", code="TECH", day=1, period=5),
    ]

    rows = subject_adjacency(lessons)

    assert set(rows) == {"id-IT", "id-TECH"}, "المفتاحُ المعرّفُ لا الاسم"
    assert rows["id-IT"].adjacent == 1 and rows["id-IT"].apart == 0
    assert rows["id-TECH"].adjacent == 0 and rows["id-TECH"].apart == 1
    assert rows["id-IT"].label == "تكنولوجيا المعلومات [IT]"


def test_the_same_subject_under_one_id_is_merged_even_across_sections():
    lessons = [
        lesson(klass="10/1", day=0, period=1),
        lesson(klass="10/1", day=0, period=2),
        lesson(klass="10/2", day=0, period=3),
        lesson(klass="10/2", day=0, period=6),
    ]

    rows = subject_adjacency(lessons)

    assert list(rows) == ["id-MATH"]
    assert rows["id-MATH"].daily_doubles == 2, "شعبتان، كلٌّ مرّتين في يومها"
    assert rows["id-MATH"].adjacent == 1


# ── تباينُ الشُّعب ───────────────────────────────────────────────────


def test_sections_of_one_grade_are_compared_only_against_each_other():
    """نصابٌ واحدٌ وصفٌّ واحدٌ ومادّةٌ واحدة — فما بقي فارقٌ يقع على الطالب."""
    lessons = [lesson(klass="10/1", day=d, period=p) for d, p in ((0, 1), (1, 2), (2, 3))]
    lessons += [lesson(klass="10/2", day=d, period=p) for d, p in ((0, 6), (1, 7), (2, 6))]

    row = grade_section_variance(lessons)["G10 · رياضيات [MATH]"]

    assert row["equal_weekly"], "النصابُ ثلاثةٌ للشعبتين"
    assert row["sections"]["10/1"]["late_pct"] == 0.0
    assert row["sections"]["10/2"]["late_pct"] == 100.0
    assert row["late_spread"] == 100.0
    assert row["latest_section"] == "10/2"


def test_a_subject_taught_to_a_single_section_has_nothing_to_compare():
    lessons = [lesson(klass="10/1", day=d) for d in range(3)]

    assert grade_section_variance(lessons) == {}


def test_repeated_days_and_adjacent_doubles_are_counted_per_section():
    lessons = [
        lesson(klass="10/1", day=0, period=1),
        lesson(klass="10/1", day=0, period=2),
        lesson(klass="10/2", day=0, period=1),
        lesson(klass="10/2", day=0, period=5),
    ]

    rows = grade_section_variance(lessons)["G10 · رياضيات [MATH]"]["sections"]

    assert rows["10/1"] == pytest.approx(rows["10/1"])
    assert (rows["10/1"]["repeated_days"], rows["10/1"]["adjacent_double"]) == (1, 1)
    assert (rows["10/2"]["repeated_days"], rows["10/2"]["adjacent_double"]) == (1, 0)


# ── الفراغ ───────────────────────────────────────────────────────────


def test_free_periods_before_the_first_lesson_are_not_internal_gaps():
    """من يعمل الثالثةَ والرابعة ليس له فراغٌ داخليّ — ولا حضورَ مطلوبٌ قبلهما."""
    lessons = [lesson(period=3), lesson(period=4)]

    row = gap_anatomy(lessons)["معلّم"]

    assert row["internal_gap"] == 0
    assert row["leading_free"] == 2
    assert row["trailing_free"] == 3


def test_a_two_period_hole_is_reported_apart_from_two_single_holes():
    """P1,P2,P6 فجوةٌ واحدةٌ طولُها ثلاث — أثقلُ من ثلاثِ فجواتٍ مفردة."""
    lessons = [lesson(period=p) for p in (1, 2, 6)]

    row = gap_anatomy(lessons)["معلّم"]

    assert row["internal_gap"] == 3
    assert (row["single_gap"], row["multi_gap"], row["worst_gap"]) == (0, 1, 3)
    assert row["days_with_gap"] == 1


def test_a_single_hole_is_not_promoted_to_a_multi_gap():
    lessons = [lesson(period=p) for p in (1, 3, 5)]

    row = gap_anatomy(lessons)["معلّم"]

    assert (row["single_gap"], row["multi_gap"], row["worst_gap"]) == (2, 0, 1)


# ── المُعلَن مقابل الواقع ────────────────────────────────────────────


@pytest.mark.django_db
def test_a_declared_double_that_never_happens_is_reported_against_its_own_id(db):
    from core.models import School
    from operations.models import Subject

    school = School.objects.create(name="مدرسة", code="X1")
    it = Subject.objects.create(
        school=school, name_ar="تكنولوجيا المعلومات", code="IT", requires_double_period=True
    )
    tech = Subject.objects.create(
        school=school, name_ar="التكنولوجيا", code="TECH", requires_double_period=True
    )
    lessons = [
        lesson(subject=it.name_ar, code="IT", sid=str(it.id), day=0, period=1),
        lesson(subject=it.name_ar, code="IT", sid=str(it.id), day=0, period=2),
        lesson(subject=tech.name_ar, code="TECH", sid=str(tech.id), day=1, period=1),
        lesson(subject=tech.name_ar, code="TECH", sid=str(tech.id), day=2, period=1),
    ]

    rows = declared_versus_observed_doubles(school, lessons)

    assert rows[str(it.id)]["declared_double"] is True
    assert rows[str(it.id)]["adjacency_rate"] == 100.0
    assert rows[str(tech.id)]["declared_double"] is True
    assert rows[str(tech.id)]["daily_doubles"] == 0, "إعلانٌ بلا أثرٍ في الجدول"
    assert rows[str(tech.id)]["code"] == "TECH"


# ── مقارنةُ النظراء ──────────────────────────────────────────────────


def test_a_band_too_small_to_compare_is_named_not_dropped():
    """ستّةُ معلّمين سقطوا صامتين من أوّل تشغيل — ومن يسقط من القياس يُسمّى.

    فتقريرٌ يقول «ثلاثٌ وسبعون معلّماً» ثمّ يعرض سبعةً وستّين بلا بيانٍ
    يُخفي حدَّ معرفته، وهو أخطرُ من ألّا يقيس أصلاً.
    """
    lessons = [
        Lesson(
            teacher_id=f"t{i}",
            teacher_name=f"معلّم {i}",
            class_id="10/1",
            class_name="10/1",
            subject_id="s",
            subject_name="م",
            day=0,
            period=p,
        )
        for i in range(4)
        for p in ([1, 2, 3, 4] if i < 3 else [1])
    ]

    data = peer_outliers(profile_teachers(lessons), lessons)

    assert "4–5" in data["bands"], "ثلاثةٌ بنصابٍ أربعة يُقارَنون"
    assert "0–1" in data["too_small"], "والرابعُ وحده يُذكر ولا يُطوى"
    assert data["too_small"]["0–1"][0]["name"] == "معلّم 3"


def test_the_band_reports_its_extremes_and_names_no_one_an_outlier():
    lessons = [
        Lesson(
            teacher_id=f"t{i}",
            teacher_name=f"معلّم {i}",
            class_id="10/1",
            class_name="10/1",
            subject_id="s",
            subject_name="م",
            day=0,
            period=p,
        )
        for i, periods in enumerate(([1, 2, 3, 4], [1, 2, 3, 5], [1, 3, 5, 7]))
        for p in periods
    ]

    band = peer_outliers(profile_teachers(lessons), lessons)["bands"]["4–5"]

    assert (band["min_gaps"], band["max_gaps"]) == (0, 3)
    assert band["heaviest"][0]["name"] == "معلّم 2"
    assert "outliers" not in band, "لا يُسمّى أحدٌ شاذّاً بعتبةٍ مخترعة"
