"""نهايةُ دوام الطلبة — الصيفُ ليس «يومَ دراسة» (U-40، 2026-09-25).

كان يومُ الدراسة يُغلَق بإجازةٍ من التقويم أو قبل بدء الطلبة (`NOT_YET_OPEN`) فقط، فبعد آخر اختبارات
العام وإلى بدء العام التالي بقي كلُّ أحدٍ إلى خميسٍ «يومَ دراسة» مفتوحاً: حصصٌ تُولَّد وغيابٌ يُرصد ومهلةُ
عذرٍ تجري. فصار حدثُ `students_end` في التقويم يُغلق ما بعده إلى نهاية العام (`ENDED`) — مقيَّداً بنطاق
الصفّ كالإجازات، وبلا أثرٍ على عامٍ لا حدثَ له.
"""

import datetime as dt

import pytest

from core.models import AcademicYear, CalendarEvent
from operations.school_days import (
    ENDED,
    NOT_YET_OPEN,
    SchoolDays,
    is_school_day,
    school_day,
)

pytestmark = pytest.mark.django_db

#: العامُ 2026-2027 في البذر: آخرُ يومٍ لكلّ نطاق (مشتقٌّ من آخر اختبارات الفصل الثاني له).
LAST_G1_9 = dt.date(2027, 6, 14)  # الاثنين
LAST_G10_11 = dt.date(2027, 6, 15)  # الثلاثاء
LAST_G12 = dt.date(2027, 6, 17)  # الخميس
SUNDAY_AFTER = dt.date(2027, 6, 20)
IN_JULY = dt.date(2027, 7, 6)  # ثلاثاء
NEXT_YEAR_PREP = dt.date(2027, 8, 24)  # ثلاثاء قبل بدء طلبة 2027-2028 في 29 أغسطس


class TestTheSummerIsNotASchoolDay:
    def test_the_days_after_the_last_student_day_are_closed(self, school, seeded_calendar):
        for day in (SUNDAY_AFTER, IN_JULY):
            found = school_day(school, day)

            assert not found.is_open and found.holiday == ENDED
            assert found.closed_reason == ENDED
            assert found.bell_day_type == ""
            assert not is_school_day(school, day)

    def test_the_last_day_itself_is_still_open(self, school, seeded_calendar):
        """آخرُ يومٍ للطلبة يومُ دراسة — يُغلق ما بعده لا هو."""
        assert school_day(school, LAST_G12).is_open
        assert is_school_day(school, LAST_G12)

    def test_the_window_agrees(self, school, seeded_calendar):
        days = SchoolDays(school, dt.date(2027, 6, 13), dt.date(2027, 6, 24))

        assert LAST_G12 in days
        assert SUNDAY_AFTER not in days

    def test_a_named_break_wins_over_the_ending(self, school, seeded_calendar):
        """إجازةٌ في الصيف باسمها هي السبب — كما تغلب على «لم يبدأ الدوام»."""
        academic_year = AcademicYear.objects.get(
            school=school, start_date__lte=IN_JULY, end_date__gte=IN_JULY
        )
        CalendarEvent.objects.create(
            academic_year=academic_year,
            event_type="break",
            name="إجازةٌ للاختبار",
            start_date=IN_JULY,
            end_date=IN_JULY,
        )

        assert school_day(school, IN_JULY).holiday == "إجازةٌ للاختبار"


class TestTheGradeScope:
    """الصفوفُ الصغيرة تفرغ قبل الثاني عشر — فلا يُغلق يومٌ ما زال فيه صفٌّ يدرس."""

    def test_each_grade_closes_after_its_own_last_day(self, school, seeded_calendar):
        after_g1_9 = LAST_G1_9 + dt.timedelta(days=1)
        after_g10_11 = LAST_G10_11 + dt.timedelta(days=1)

        assert school_day(school, LAST_G1_9, grade="G7").is_open
        assert school_day(school, after_g1_9, grade="G7").holiday == ENDED
        assert school_day(school, after_g1_9, grade="G10").is_open
        assert school_day(school, after_g10_11, grade="G10").holiday == ENDED
        assert school_day(school, after_g10_11, grade="G12").is_open

    def test_a_screen_of_many_grades_closes_after_the_latest(self, school, seeded_calendar):
        """`grade=None`: ما في اليوم صفٌّ يدرس فيه — يبقى مفتوحاً."""
        assert school_day(school, LAST_G10_11 + dt.timedelta(days=1)).is_open
        assert school_day(school, SUNDAY_AFTER).holiday == ENDED


class TestOnlyTheEndedYearIsClosed:
    def test_the_next_year_has_its_own_boundaries(self, school, seeded_calendar):
        """بعد نهاية العام يبدأ عامٌ بحدّه — فلا يُغلق أوّلَه حدثُ العام السابق."""
        found = school_day(school, NEXT_YEAR_PREP)

        assert found.holiday == NOT_YET_OPEN

    def test_a_year_without_the_event_is_unchanged(self, school, seeded_calendar):
        CalendarEvent.objects.filter(event_type="students_end").delete()

        assert school_day(school, SUNDAY_AFTER).is_open, "بلا الحدث لا شيءَ يتغيّر — كما كان"
        assert is_school_day(school, IN_JULY)


class TestTheSeed:
    def test_every_year_has_one_ending_per_scope(self, school, seeded_calendar):
        rows = CalendarEvent.objects.filter(
            academic_year__school=school, event_type="students_end"
        ).values_list("academic_year__name", "grade_scope")

        assert len(set(rows)) == len(list(rows)) == 9  # ثلاثةُ أعوامٍ × ثلاثةُ نطاقات

    def test_each_ending_is_the_last_second_semester_exam_of_its_scope(
        self, school, seeded_calendar
    ):
        """اشتقاقٌ معلَن: آخرُ يومٍ للطلبة = آخرُ يومٍ في اختبارات الفصل الثاني لنطاقهم."""
        endings = CalendarEvent.objects.filter(
            academic_year__school=school, event_type="students_end"
        )
        for ending in endings:
            last_exam = (
                CalendarEvent.objects.filter(
                    academic_year=ending.academic_year,
                    event_type="final_exam",
                    grade_scope=ending.grade_scope,
                    name__contains="الفصل الثاني",
                )
                .order_by("-end_date")
                .first()
            )

            assert ending.start_date == ending.end_date == last_exam.end_date, (
                ending.academic_year.name,
                ending.grade_scope,
            )
            assert ending.audience == "students"
            assert "مشتقّة" in ending.name, "الحدثُ يقول في اسمه إنّه مشتقٌّ لا من نشرة الوزارة"
