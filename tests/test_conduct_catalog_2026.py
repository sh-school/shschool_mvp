"""[LEGAL] قائمةُ المخالفات وسلالمُها — الدليل التنظيميّ لسياسة إدارة سلوك الطلبة 2026.

الحرّاسُ على ثلاثة:
- **العددُ كما في جدول التصنيف (ص84)**: 9 · 7 · 10 · 15، والتنمّرُ سبعَ عشرةَ
  (ص83). وكان الاستخراجُ الأوّل يقول أربعاً وأربعين.
- **السلّمُ كما في جداول الإجراءات**: عددُ تكراراته، وما بعد آخره.
- **العدُّ كما قرّرت المدرسة (2026-09-13)**: لكلّ مخالفةٍ على حدة، ويُصفَّر كلَّ
  فصلٍ دراسيّ، والمخالفتان في اليوم نفسِه تكراران.
"""

import importlib
from collections import Counter
from datetime import timedelta

import pytest

from behavior.conduct_2026 import BY_CODE, CATALOG, LADDERS, PERIOD_TARDY_CODE, TEAM, ladder_text

# ══════════════════════════════════════════════════════════════════
# القائمة
# ══════════════════════════════════════════════════════════════════


def test_the_catalog_matches_the_classification_table():
    assert Counter(item.degree for item in CATALOG) == {1: 9, 2: 7, 3: 10, 4: 15}
    assert len(CATALOG) == 41, "جدولُ ص84 واحدٌ وأربعون — لا أربعةٌ وأربعون"


def test_bullying_infractions_are_the_seventeen_in_red():
    assert sum(item.bullying for item in CATALOG) == 17


def test_codes_are_unique_and_numbered_within_their_degree():
    assert len(BY_CODE) == len(CATALOG)
    for degree, size in {1: 9, 2: 7, 3: 10, 4: 15}.items():
        expected = {f"{degree}-{n:02d}" for n in range(1, size + 1)}
        assert {i.code for i in CATALOG if i.degree == degree} == expected


def test_every_infraction_has_a_ladder_and_every_ladder_is_used():
    assert {item.ladder for item in CATALOG} == set(LADDERS)


# ══════════════════════════════════════════════════════════════════
# السلالم
# ══════════════════════════════════════════════════════════════════

#: عددُ التكرارات في كلّ جدول — يُقرأ من عمود «عدد التكرار».
REPETITIONS = {
    "d1": 6,
    "d2_appearance": 6,
    "d2_class_escape": 6,
    "d2_sleep": 6,
    "d2_quarrel": 5,
    "d2_bus": 4,
    "d2_uniform": 4,
    "d3_internet": 4,
    "d3_photo": 3,
    "d3_devices": 3,
    "d3_conflict": 3,
    "d3_property": 3,
    "d3_school_escape": 3,
    "d4_disrespect": 2,
    "d4_identity": 2,
    "d4_ideas": 2,
    "d4_prohibited": 2,
    "d4_hacking": 2,
    "d4_violence": 2,
    "d4_forgery": 2,
    "d4_assault": 1,
    "d4_cars": 1,
    "d4_danger": 2,
}


@pytest.mark.parametrize("key,count", REPETITIONS.items())
def test_each_ladder_has_the_tables_repetitions(key, count):
    assert len(LADDERS[key].steps) == count


def test_the_first_degree_ladder_starts_with_the_teacher_and_ends_with_the_team():
    """التأخّرُ عن الحصّة: المعلّمُ أوّلُ من يتصرّف، والفريقُ في السادسة."""
    ladder = BY_CODE[PERIOD_TARDY_CODE].steps
    assert ladder.step(1) == (("المعلّم", ladder.step(1)[0][1]),)
    assert {actor for actor, _ in ladder.step(2)} == {"المعلّم", "المشرف الإداريّ"}
    sixth = " ".join(action for _, action in ladder.step(6))
    assert "يوماً واحداً" in sixth and "داخليّ" in sixth


def test_beyond_the_first_degree_ladder_is_the_protection_department():
    ladder = BY_CODE["1-01"].steps
    assert ladder.is_beyond(7)
    assert "قسم حماية ورعاية الطلبة" in ladder.beyond


def test_silent_tables_do_not_invent_a_referral():
    """جدولا النوم والحافلات لا يذكران ما بعد السلّم — فلا يُخترع."""
    assert LADDERS["d2_sleep"].beyond == ""
    assert LADDERS["d2_bus"].beyond == ""


def test_escaping_a_class_is_counted_per_subject_in_the_notes():
    assert any("لكلّ مادّةٍ" in note for note in LADDERS["d2_class_escape"].notes)


def test_ladder_text_is_numbered_and_ends_with_beyond():
    rows = ladder_text("1-01")
    assert [n for n, _ in rows] == [1, 2, 3, 4, 5, 6, 7]
    assert rows[-1][1].startswith("ما بعد ذلك")


def test_drugs_and_weapons_referral_opens_the_second_repetition():
    """ص125 (4-14 و4-15): الإحالةُ إلى الجهة المختصّة أوّلُ صفوف «الثانية» لا آخرُ «الأولى».

    حدُّ خليّة «عدد التكرار» يقع بين صفّ الاختصاصيّ النفسيّ وصفّ الإحالة (تحقّقٌ بصريٌّ
    من الـPDF، 2026-09-25). فالتكرارُ الأوّل لا فاعلَ فيه من الفريق، وأوّلُ ما يفعله
    الفريقُ في الثانية الإحالةُ ثمّ الفصلُ لحين وصول ردّ الجهة المختصّة.
    """
    assert BY_CODE["4-14"].steps is BY_CODE["4-15"].steps is LADDERS["d4_danger"]
    ladder = LADDERS["d4_danger"]
    first, second = ladder.step(1), ladder.step(2)

    assert all(actor != TEAM for actor, _ in first)
    assert not any("الجهة المختصّة" in action for _, action in first)

    (actor, action), (next_actor, next_action) = second[0], second[1]
    assert actor == TEAM
    assert "إحالةُ الطالب إلى الجهة المختصّة (قسم حماية ورعاية الطلبة)" in action
    assert "المخدّرات" in action
    assert next_actor == TEAM and next_action.startswith("فصلُ الطالب من المدرسة")
    assert len(second) == 6, "الإحالةُ + الفصلُ + التحفّظُ + الأمنيّةُ + توقيعُ الوليّ + تعهّدُ الطالب"


def test_prohibited_items_name_lists_the_sources_examples():
    """ص117 (4-07): الممنوعاتُ أربعةٌ مسمّاة — لا «السجائر والسجائر» المكرَّرة."""
    name = BY_CODE["4-07"].name

    for item in (
        "السجائر الإلكترونيّة",
        "الشيشة الإلكترونيّة",
        "السويكة أو ما شابه",
    ):
        assert item in name
    assert "السجائر والسجائر" not in name


def test_fight_damage_is_assessed_by_the_school_administration():
    """ص120 (4-09 و4-10): «يقدَّر من قِبَل إدارة المدرسة» — لا النائبُ أو المدير بعينهما."""
    assert BY_CODE["4-09"].steps is BY_CODE["4-10"].steps is LADDERS["d4_violence"]
    rows = [action for _, action in LADDERS["d4_violence"].step(2) if "ضرر" in action]

    assert len(rows) == 1
    assert "إدارة المدرسة" in rows[0]
    assert "النائب" not in rows[0]


# ══════════════════════════════════════════════════════════════════
# العدّ
# ══════════════════════════════════════════════════════════════════


@pytest.fixture
def category_1_01(db):
    from behavior.models import ViolationCategory

    item = BY_CODE["1-01"]
    category, _ = ViolationCategory.objects.update_or_create(
        code=item.code, defaults={"degree": 1, "name_ar": item.name, "is_active": True}
    )
    return category


def _record(school, student, reporter, category):
    from behavior.services import BehaviorService

    return BehaviorService.create_infraction(
        school=school,
        student=student,
        reporter=reporter,
        level=category.degree,
        description="تأخّرٌ عن الحصّة",
        violation_category=category,
    )


def test_twice_on_the_same_day_is_two_repetitions(
    school, seeded_calendar, student_user, teacher_user, category_1_01
):
    first = _record(school, student_user, teacher_user, category_1_01)
    second = _record(school, student_user, teacher_user, category_1_01)

    assert (first.escalation_step, second.escalation_step) == (1, 2)
    assert first.date == second.date


def test_the_count_resets_each_semester(
    school, seeded_calendar, student_user, teacher_user, category_1_01
):
    from behavior.models import BehaviorInfraction
    from core.academic_calendar import AcademicCalendar

    semester = AcademicCalendar.current(school).semester
    old = _record(school, student_user, teacher_user, category_1_01)
    BehaviorInfraction.objects.filter(pk=old.pk).update(
        date=semester.start_date - timedelta(days=1)
    )

    fresh = _record(school, student_user, teacher_user, category_1_01)

    assert fresh.escalation_step == 1


def test_each_infraction_counts_for_itself(
    school, seeded_calendar, student_user, teacher_user, category_1_01
):
    """تأخّرٌ ثمّ طعامٌ في الدرس: سلّمٌ واحدٌ، وتكرارٌ أوّلُ لكلٍّ منهما."""
    from behavior.models import ViolationCategory

    food = ViolationCategory.objects.update_or_create(
        code="1-06", defaults={"degree": 1, "name_ar": BY_CODE["1-06"].name}
    )[0]
    _record(school, student_user, teacher_user, category_1_01)

    assert _record(school, student_user, teacher_user, food).escalation_step == 1


def test_the_seventh_repetition_is_beyond_the_ladder(
    school, seeded_calendar, student_user, teacher_user, category_1_01
):
    steps = [
        _record(school, student_user, teacher_user, category_1_01).escalation_step for _ in range(8)
    ]

    assert steps == [1, 2, 3, 4, 5, 6, 7, 7]
    assert category_1_01.get_escalation_steps()[-1][1].startswith("ما بعد ذلك")


# ══════════════════════════════════════════════════════════════════
# الهجرة
# ══════════════════════════════════════════════════════════════════


def test_the_migration_left_the_2026_catalog_active(db):
    from behavior.models import ViolationCategory

    active = set(
        ViolationCategory.objects.filter(is_active=True, code__regex=r"^\d-\d{2}$").values_list(
            "code", flat=True
        )
    )
    assert active == set(BY_CODE)


def test_the_4_07_name_migration_updates_only_the_old_source_name(db):
    """0020: من هُجِّر على اسم 0015 يلحق بالمصدر، ومن عدّل اسمَه بيده لا يُمسّ."""
    from django.apps import apps

    from behavior.models import ViolationCategory

    migration = importlib.import_module("behavior.migrations.0020_conduct_4_07_name_from_source")
    category = ViolationCategory.objects.get(code="4-07")
    assert category.name_ar == BY_CODE["4-07"].name == migration.NEW_NAME

    ViolationCategory.objects.filter(pk=category.pk).update(name_ar=migration.OLD_NAME)
    migration.forwards(apps, None)
    category.refresh_from_db()
    assert category.name_ar == migration.NEW_NAME

    ViolationCategory.objects.filter(pk=category.pk).update(name_ar="اسمٌ عدّله المدير")
    migration.forwards(apps, None)
    category.refresh_from_db()
    assert category.name_ar == "اسمٌ عدّله المدير"
