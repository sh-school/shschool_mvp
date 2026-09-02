"""[SCHEDULER] مقياسُ الجدول القائم — يُختبَر قبل أن يُصدَّق رقمُه.

الجدولُ المستورد مخرجُ قراراتٍ إداريّةٍ اتُّخذت فعلاً، فهو أصدقُ ما نملك عن
قواعد المدرسة. لكنّ مقياساً خاطئاً أسوأُ من لا مقياس: يُنتج «نمطاً مرصوداً»
لا وجودَ له، فتُبنى عليه سياسةٌ باسم المدرسة.

وأوّلُ تشغيلٍ للمقياس أثبت ذلك: أخرج «الخميس ثمانِ حصصٍ للثانويّ» والسقفُ سبع.
والسببُ أنّه كان يعدّ الحصصَ لا الخانات — وأربعُ شعبٍ ينقسم طلابُها في الخانة
الواحدة بين مادّتين. فالرقمُ صحيحٌ والدلالةُ خاطئة، ولو مضى لصار «تجاوزاً
للسقف» في تقريرٍ يُقرأ على المدير.

ولذلك تُثبَّت هنا حسابات: الفراغ، والتتابع، والانقسام، والتمييزُ بين الحصّة
والخانة.
"""

import pytest

from operations.schedule_profile import (
    Lesson,
    _gaps,
    _runs,
    _spread,
    fairness,
    observations,
    profile_availability,
    profile_sections,
    profile_subjects,
    profile_teachers,
)


def lesson(*, teacher="t1", klass="c1", subject="رياضيات", day=0, period=1, level="prep"):
    return Lesson(
        teacher_id=teacher,
        teacher_name=f"معلّم {teacher}",
        class_id=klass,
        class_name=f"شعبة {klass}",
        subject_id=subject,
        subject_name=subject,
        day=day,
        period=period,
        level_type=level,
    )


# ── الحسابات الصغيرة ─────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("periods", "expected"),
    [([], 0), ([3], 0), ([1, 2], 0), ([1, 3], 1), ([1, 4], 2), ([1, 2, 5, 6], 2), ([2, 3, 4], 0)],
)
def test_gaps_count_only_the_holes_between_first_and_last(periods, expected):
    """الفراغُ ما بين أوّل حصّةٍ وآخرها — لا ما قبلهما ولا ما بعدهما.

    فمن يبدأ الثالثةَ وينتهي الرابعة ليس له فراغ، وإن كانت الأولى والثانية
    خاليتين: ليس مطالَباً بالحضور قبل حصّته.
    """
    assert _gaps(periods) == expected


@pytest.mark.parametrize(
    ("periods", "expected"),
    [([], 0), ([4], 1), ([1, 2], 2), ([1, 3], 1), ([1, 2, 3], 3), ([1, 2, 4, 5, 6], 3)],
)
def test_the_longest_run_is_the_longest_unbroken_stretch(periods, expected):
    assert _runs(periods) == expected


def test_the_spread_uses_the_median_not_the_mean():
    """معلّمٌ واحدٌ بثمانيةَ عشرَ لا يرفع «الوسيط» كما يرفع المتوسّط."""
    assert _spread([1, 1, 1, 1, 18]) == {"min": 1, "median": 1, "max": 18}


def test_an_empty_spread_does_not_raise():
    assert _spread([]) == {"min": 0, "median": 0, "max": 0}


# ── عبءُ المعلّم ────────────────────────────────────────────────────


def test_a_teacher_profile_counts_days_load_gaps_and_runs():
    lessons = [
        lesson(day=0, period=1),
        lesson(day=0, period=2),
        lesson(day=0, period=5),
        lesson(day=2, period=7),
    ]

    profile = profile_teachers(lessons)[0]

    assert profile.weekly == 4
    assert profile.days_used == 2
    assert profile.max_daily == 3
    assert profile.gaps == 2, "الأحد: من الأولى إلى الخامسة، ثلاثُ حصصٍ وفراغان"
    assert profile.longest_run == 2
    assert profile.first_period == 1, "يومٌ واحدٌ يبدأ بالحصّة الأولى"
    assert profile.late_periods == 1, "السابعةُ وحدها متأخّرة"


def test_teachers_are_ordered_by_weekly_load():
    lessons = [lesson(teacher="light"), lesson(teacher="heavy"), lesson(teacher="heavy", period=2)]

    assert [p.teacher_id for p in profile_teachers(lessons)] == ["heavy", "light"]


# ── الشعبة: الحصّةُ ليست الخانة ──────────────────────────────────────


def test_a_split_period_is_two_lessons_in_one_slot_not_an_overrun():
    """أربعُ شعبٍ ينقسم طلابُها بين مادّتين في التوقيت نفسه.

    فتحمل الخانةُ حصّتين، ويبدو اليومُ متجاوزاً للسقف وهو ليس كذلك. وهذا
    بعينه ما أخرجه أوّلُ تشغيل: «الخميس ثمانِ حصص» والسقفُ سبع.
    """
    lessons = [lesson(day=4, period=p, subject=f"مادّة {p}") for p in range(1, 8)] + [
        lesson(day=4, period=3, subject="فنون بصرية", teacher="t2")
    ]

    section = profile_sections(lessons)[0]

    assert section.weekly == 8, "ثمانِ حصص"
    assert section.periods_per_day[4] == 7, "في سبع خانات"
    assert section.split_periods == 1


def test_a_section_without_splits_reports_none():
    lessons = [lesson(period=p, subject=f"م{p}") for p in range(1, 5)]

    section = profile_sections(lessons)[0]

    assert section.split_periods == 0
    assert section.weekly == section.periods_per_day[0] == 4


def test_repeating_a_subject_in_one_day_is_counted_and_adjacency_separately():
    """التكرارُ شيءٌ والتجاورُ شيءٌ آخر: الثاني حصّةٌ مزدوجةٌ مقصودة."""
    lessons = [
        lesson(subject="فنون", period=1),
        lesson(subject="فنون", period=2),
        lesson(subject="علوم", day=1, period=1),
        lesson(subject="علوم", day=1, period=5),
    ]

    section = profile_sections(lessons)[0]

    assert section.twice_in_a_day == 2, "الفنونُ والعلوم، كلٌّ مرّتين في يومه"
    assert section.adjacent_pairs == 1, "والفنونُ وحدها متجاورة"


# ── المواد ───────────────────────────────────────────────────────────


def test_subject_placement_is_measured_by_where_it_falls_in_the_day():
    lessons = [
        lesson(subject="رياضيات", period=1),
        lesson(subject="رياضيات", period=2),
        lesson(subject="رياضيات", period=7),
        lesson(subject="رياضيات", period=7, day=1),
    ]

    data = profile_subjects(lessons)["رياضيات"]

    assert data["total"] == 4
    assert data["in_last_period"] == 2
    assert data["morning_share"] == 50.0


# ── التوافر: يُوصف ولا يُسمّى إعفاءً ────────────────────────────────


def test_a_day_without_any_lesson_is_reported_as_an_absence_not_an_exemption():
    """قد يكون إعفاءً رسميّاً وقد يكون أثرَ الجدول — والفرقُ قرارٌ إداريّ."""
    lessons = [lesson(day=0), lesson(day=1), lesson(day=2)]

    free = profile_availability(lessons)

    assert free["معلّم t1"] == ["الأربعاء", "الخميس"]


def test_a_teacher_present_every_day_is_not_listed():
    lessons = [lesson(day=d) for d in range(5)]

    assert profile_availability(lessons) == {}


# ── العدالة ──────────────────────────────────────────────────────────


def test_fairness_shows_the_spread_not_a_single_average():
    """معلّمان بالنصاب نفسه قد يكون جدولاهما متباينين — والمتوسّطُ يُخفي ذلك."""
    lessons = [lesson(teacher="a", day=d, period=1) for d in range(5)]
    lessons += [lesson(teacher="b", day=0, period=p) for p in (1, 3, 5, 7)]
    lessons += [lesson(teacher="b", day=1, period=1)]

    fair = fairness(profile_teachers(lessons))

    assert fair["teachers"] == 2
    assert fair["weekly"]["min"] == fair["weekly"]["max"] == 5, "النصابُ واحد"
    assert fair["gaps"]["min"] == 0
    assert fair["gaps"]["max"] == 3, "والجدولان متباينان"


# ── الحكم يبقى معلَّقاً ──────────────────────────────────────────────


def test_every_candidate_policy_is_marked_as_needing_approval():
    """المقياسُ يعرض ما يستحقّ قراراً ولا يتّخذه.

    و«لا معلّمَ يتجاوز أربعاً» نمطٌ مرصود؛ قد يكون قرارَ إدارةٍ وقد يكون أثراً
    عرضيّاً لجدولٍ بُني هكذا. وكتابتُه قاعدةً من هذا وحده اختراعُ سياسةٍ باسم
    المدرسة.
    """
    lessons = [lesson(day=d, period=p) for d in range(3) for p in (1, 2)]
    teachers = profile_teachers(lessons)

    found = observations(lessons, teachers, profile_sections(lessons), fairness(teachers))

    assert found, "ثمّة ما يستحقّ النظر"
    assert all(o.needs_approval for o in found)
    assert all(o.fact and o.pattern and o.candidate for o in found)


def test_nothing_is_observed_from_an_empty_schedule():
    assert observations([], [], [], {}) == []


def test_thursday_is_measured_in_slots_not_lessons():
    """وهو التصحيحُ الذي أوجبه أوّلُ تشغيل."""
    lessons = [lesson(day=4, period=p, subject=f"م{p}", level="sec") for p in range(1, 8)]
    lessons.append(lesson(day=4, period=2, subject="فنون", teacher="t2", level="sec"))
    teachers = profile_teachers(lessons)
    sections = profile_sections(lessons)

    found = observations(lessons, teachers, sections, fairness(teachers))
    thursday = next(o for o in found if "الخميس" in o.fact)

    assert "sec=7" in thursday.fact, "سبعُ خاناتٍ لا ثمانِ حصص"
    assert any("تحمل أكثرَ من حصّة" in o.fact for o in found), "والانقسامُ يُذكر صراحةً"
