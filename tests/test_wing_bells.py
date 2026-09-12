"""جرسُ الطابق والجناح — ورقمُ الحصّة ليس وقتاً في هذه المدرسة.

«الحصّةُ الرابعة» تبدأ 10:00 في الطابق الأرضيّ و9:35 في الأوّل. ومن بنى شاشةً
على الرقم أخبر مشرفَ جناحٍ أنّ حصّةً تجري وقد انتهت. وجناح 3 أسوأ: ممرٌّ
بجرسين، فـ«ما الحصّةُ الآن؟» سؤالٌ جوابُه **اثنان** — يتطابقان من الأحد إلى
الأربعاء ويفترقان يومَ الخميس.

فهذا الملفُّ يحرس ثلاثةَ أشياء: أنّ الترتيبَ بالساعة لا بالرقم (فالصلاةُ في
الأرضيّ رقمُها 101 ووقتُها قبل السابعة)، وأنّ الطابقَ محفوظٌ لا مخمَّنٌ من
الرمز، وأنّ الجناحَ ذا الجرسين يُرجع جوابين لا واحداً.

والأرقامُ كلُّها من `seed_time_bands` و`seed_wings` — لا من جدولٍ يُكتب هنا
ثانيةً فيفترق عن مصدره صامتاً.
"""

import datetime as dt
import io

import pytest
from django.core.management import call_command

from core.academic_calendar import academic_year_for_school
from core.management.commands.seed_wings import WINGS
from core.models import ClassGroup, TimeBand, Wing
from operations.bells import (
    REGULAR,
    THURSDAY,
    bells_for,
    day_type_for,
    floor_bells,
    wing_bells,
    wing_position,
)
from tests.conftest import ClassGroupFactory

pytestmark = pytest.mark.django_db

#: أحدٌ وخميسٌ من العام الدراسيّ الجاري — تاريخان حقيقيّان لا مخترعان.
SUNDAY = dt.date(2026, 9, 13)
THURSDAY_DATE = dt.date(2026, 9, 17)

ESE_SECTIONS = [("G8", "ESE"), ("G9", "ESE"), ("G10", "ESE")]


def _level(grade):
    return "prep" if grade in ("G7", "G8", "G9") else "sec"


@pytest.fixture
def year(school):
    return academic_year_for_school(school)


@pytest.fixture
def wings(school, year):
    """المدرسةُ كما تُبذَر: ثمانٌ وعشرون شعبةً، ثلاثةُ أجراس، خمسةُ أجنحة."""
    for grade, section in [pair for *_head, pairs in WINGS for pair in pairs] + ESE_SECTIONS:
        ClassGroupFactory(
            school=school,
            grade=grade,
            section=section,
            level_type=_level(grade),
            academic_year=year,
            has_own_timetable=section == "ESE",
        )
    call_command("seed_time_bands", "--assign", stdout=io.StringIO())
    call_command("seed_wings", "--assign", stdout=io.StringIO())
    return {wing.code: wing for wing in Wing.objects.filter(school=school, academic_year=year)}


def _at(day, hour, minute):
    return dt.datetime.combine(day, dt.time(hour, minute))


class TestTheDayTypeFollowsTheWeek:
    @pytest.mark.parametrize(
        ("day", "expected"),
        [
            (dt.date(2026, 9, 13), REGULAR),  # الأحد
            (dt.date(2026, 9, 14), REGULAR),  # الاثنين
            (dt.date(2026, 9, 15), REGULAR),  # الثلاثاء
            (dt.date(2026, 9, 16), REGULAR),  # الأربعاء
            (dt.date(2026, 9, 17), THURSDAY),  # الخميس
        ],
    )
    def test_school_days_get_their_bell(self, day, expected):
        assert day_type_for(day) == expected

    @pytest.mark.parametrize("day", [dt.date(2026, 9, 18), dt.date(2026, 9, 19)])
    def test_the_weekend_has_no_bell_at_all(self, day):
        """الجمعةُ والسبتُ يومان بلا دراسة — و«جرسٌ افتراضيّ» فيهما كذبٌ مرتّب."""
        assert day_type_for(day) == ""

    def test_a_day_without_a_bell_yields_no_schedule(self, school, wings):
        assert wing_bells(wings["w1"], "") == []
        assert floor_bells(school, "ground", "") == []


class TestTheFloorIsStoredNotGuessed:
    def test_the_ground_bell_is_on_the_ground(self, school, wings):
        assert TimeBand.objects.get(school=school, code="ground").floor == "ground"

    def test_both_upper_bells_are_on_the_first_floor(self, school, wings):
        """`ninth` و`secondary` رمزان وطابقٌ واحد — ومن استدلّ بالاسم أخطأ."""
        floors = {
            code: TimeBand.objects.get(school=school, code=code).floor
            for code in ("ninth", "secondary")
        }

        assert floors == {"ninth": "first", "secondary": "first"}

    def test_the_ground_floor_rings_one_bell(self, school, wings):
        assert [b.band_code for b in floor_bells(school, "ground", REGULAR)] == ["ground"]

    def test_the_first_floor_rings_two(self, school, wings):
        assert [b.band_code for b in floor_bells(school, "first", REGULAR)] == [
            "ninth",
            "secondary",
        ]

    def test_no_wing_sits_on_a_foreign_floor(self, school, wings):
        """الصحيحُ أن تكون القائمةُ فارغةً في كلّ جناح."""
        for wing in wings.values():
            assert wing.bells_off_floor == [], f"{wing.code}: جرسٌ من طابقٍ آخر"

    def test_a_section_on_the_wrong_bell_is_caught(self, school, wings):
        """شعبةٌ أرضيّةٌ على جرسٍ علويٍّ تعني أنّ أحدَ الرقمين خطأ — فتُسمّى."""
        upper = TimeBand.objects.get(school=school, code="secondary")
        ClassGroup.objects.filter(school=school, grade="G7", section="1").update(time_band=upper)

        assert [b.code for b in wings["w1"].bells_off_floor] == ["secondary"]


class TestTheOrderIsTheClockNotTheNumber:
    def test_prayer_comes_before_the_seventh_period_on_the_ground_floor(self, school, wings):
        """الصلاةُ رقمُها 101 ووقتُها 12:20 — أي قبل السابعة. والترتيبُ بالرقم يكذب."""
        labels = [slot.label for slot in bells_for(school, REGULAR)["ground"].slots]

        assert labels.index("الصلاة") < labels.index("الحصّة 7")

    def test_the_ground_day_reads_in_clock_order(self, school, wings):
        bell = bells_for(school, REGULAR)["ground"]

        assert [slot.label for slot in bell.slots] == [
            "الحصّة 1",
            "الحصّة 2",
            "الحصّة 3",
            "الفسحة",
            "الحصّة 4",
            "الحصّة 5",
            "الحصّة 6",
            "الصلاة",
            "الحصّة 7",
        ]
        assert [f"{slot.start:%H:%M}" for slot in bell.slots] == [
            "07:10",
            "08:00",
            "08:50",
            "09:35",
            "10:00",
            "10:50",
            "11:35",
            "12:20",
            "12:40",
        ]

    def test_the_breaks_are_the_break_and_the_prayer(self, school, wings):
        bell = bells_for(school, REGULAR)["ground"]

        assert [s.label for s in bell.slots if s.is_break] == ["الفسحة", "الصلاة"]
        assert len(bell.periods) == 7

    def test_thursday_is_shorter_everywhere(self, school, wings):
        regular = bells_for(school, REGULAR)
        thursday = bells_for(school, THURSDAY)

        assert len(thursday["ground"].periods) == 6 < len(regular["ground"].periods)
        assert thursday["ground"].ends < regular["ground"].ends


class TestOneQueryNotFive:
    def test_the_whole_school_costs_a_single_query(self, school, wings, django_assert_num_queries):
        """خمسةُ أجنحةٍ تُعرض معاً — فلو قرأ كلُّ جناحٍ جرسَه لصارت خمسةَ استعلامات."""
        with django_assert_num_queries(1):
            bells_for(school, REGULAR)

    def test_a_shared_table_serves_every_wing(self, school, wings, django_assert_num_queries):
        table = bells_for(school, REGULAR)
        for wing in wings.values():  # يُسخّن `time_bands`
            wing_bells(wing, REGULAR, table)

        with django_assert_num_queries(5):  # استعلامُ `time_bands` لكلّ جناحٍ ولا غيره
            for wing in wings.values():
                wing_bells(wing, REGULAR, table)

    def test_a_slot_without_a_bell_is_dropped(self, school, wings):
        """خانةُ «جرسِ المدرسة الافتراضيّ» بقيّةٌ من قبل النطاقات — وخلطُها
        بجرسٍ مسمّىً يُنتج يوماً بحصّتين رابعتين."""
        from operations.models import TimeSlotConfig

        TimeSlotConfig.objects.create(
            school=school,
            band=None,
            day_type=REGULAR,
            period_number=4,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 45),
        )

        table = bells_for(school, REGULAR)

        assert set(table) == {"ground", "ninth", "secondary"}
        assert len(table["ground"].periods) == 7


class TestTheRunningSlot:
    def test_the_end_of_a_period_is_not_inside_it(self, school, wings):
        """9:35 آخرُ الثالثة وأوّلُ الفسحة — فمن جعل الحدَّ داخلاً عدّها مرّتين."""
        bell = bells_for(school, REGULAR)["ground"]

        assert bell.running(dt.time(9, 34)).label == "الحصّة 3"
        assert bell.running(dt.time(9, 35)).label == "الفسحة"

    def test_a_gap_between_slots_has_nothing_running(self, school, wings):
        """بين الفسحة (تنتهي 9:55) والرابعة (تبدأ 10:00) خمسُ دقائقَ فارغة."""
        bell = bells_for(school, REGULAR)["ground"]

        assert bell.running(dt.time(9, 57)) is None
        assert bell.upcoming(dt.time(9, 57)).label == "الحصّة 4"

    def test_before_the_day_nothing_runs_and_the_first_period_is_next(self, school, wings):
        bell = bells_for(school, REGULAR)["ground"]

        assert bell.running(dt.time(6, 30)) is None
        assert bell.upcoming(dt.time(6, 30)).label == "الحصّة 1"

    def test_after_the_day_nothing_is_next(self, school, wings):
        bell = bells_for(school, REGULAR)["ground"]

        assert bell.running(dt.time(14, 0)) is None
        assert bell.upcoming(dt.time(14, 0)) is None


class TestTheSplitWingAnswersTwice:
    def test_a_single_bell_wing_gives_one_answer(self, school, wings):
        assert len(wing_position(wings["w1"], _at(SUNDAY, 9, 45))) == 1

    def test_wing_three_gives_two(self, school, wings):
        codes = [p.bell.band_code for p in wing_position(wings["w3"], _at(SUNDAY, 9, 45))]

        assert codes == ["ninth", "secondary"]

    def test_its_two_bells_agree_from_sunday_to_wednesday(self, school, wings):
        """قبل الخميس الجرسان متطابقان حرفاً — فالجوابان واحد."""
        said = {p.says for p in wing_position(wings["w3"], _at(SUNDAY, 9, 45))}

        assert len(said) == 1

    def test_its_two_bells_disagree_on_thursday(self, school, wings):
        """9:45 خميساً: تاسع 3·4 في الفسحة، والعاشرُ في حصّته الرابعة.

        وهذا هو سببُ كون الجوابِ قائمةً: قيمةٌ واحدةٌ تختار أحدَهما صامتاً
        وتكذّب نصفَ الممرّ.
        """
        positions = {
            p.bell.band_code: p for p in wing_position(wings["w3"], _at(THURSDAY_DATE, 9, 45))
        }

        assert positions["ninth"].running.label == "الفسحة"
        assert positions["secondary"].running.label == "الحصّة 4"

    def test_the_ground_floor_and_the_first_differ_at_the_same_moment(self, school, wings):
        """9:45 أحداً: الأرضيُّ في فسحته، والأوّلُ في حصّته الرابعة."""
        ground = wing_position(wings["w1"], _at(SUNDAY, 9, 45))[0]
        first = wing_position(wings["w5"], _at(SUNDAY, 9, 45))[0]

        assert ground.running.label == "الفسحة"
        assert first.running.label == "الحصّة 4"

    def test_the_weekend_yields_no_position(self, school, wings):
        assert wing_position(wings["w1"], _at(dt.date(2026, 9, 18), 9, 45)) == []


class TestWhatTheScreenReads:
    def test_a_running_slot_names_itself_and_its_end(self, school, wings):
        position = wing_position(wings["w1"], _at(SUNDAY, 9, 45))[0]

        assert position.says == "الفسحة · حتّى 09:55"

    def test_a_gap_points_at_what_is_next(self, school, wings):
        position = wing_position(wings["w1"], _at(SUNDAY, 9, 57))[0]

        assert position.says == "قبل الحصّة 4 · تبدأ 10:00"

    def test_after_the_last_slot_it_says_the_day_is_done(self, school, wings):
        position = wing_position(wings["w1"], _at(SUNDAY, 14, 0))[0]

        assert position.says == "انتهى الدوام"
