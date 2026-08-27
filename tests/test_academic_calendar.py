"""[CALENDAR] الزمن الأكاديمي يُشتقّ من تقويم الوزارة لا من ثابتٍ في الإعدادات.

`settings.CURRENT_ACADEMIC_YEAR = "2025-2026"` ثابتٌ وقت النشر يُستعمل في
عشرات المواضع. وثابتٌ كهذا يتجاوزه الزمن **بصمت**: في ٢٧ أغسطس ٢٠٢٦ كانت
المنصّة ما تزال تقول «2025-2026» بينما المدارس بدأت «2026-2027» في ٢٣ أغسطس —
ولا شيء يكشف ذلك، لأن القيمة صحيحةٌ نحوياً في كل موضعٍ تظهر فيه.

والتقويم عندنا تاريخيّ: الوزارة تُصدر التواريخ لثلاثة أعوامٍ مقدَّماً. فالعام
والفصل يُشتقّان من اليوم، ولا رايةَ `is_current` على الفصل تُنسى فتُسجَّل
الدرجات في الفصل الخطأ.
"""

from datetime import date, timedelta

import pytest
from django.core.management import call_command

from core.academic_calendar import AcademicCalendar
from core.models import AcademicYear, CalendarEvent, Semester


@pytest.fixture
def seeded(db, school):
    call_command("seed_academic_calendar", school=school.code, verbosity=0)
    return school


# ═══════════════════════════════════════════════════════════════════
#  الاشتقاق
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("day", "year", "code"),
    [
        (date(2026, 8, 23), "2026-2027", "S1"),  # أوّل يوم — دوام الموظفين
        (date(2026, 8, 22), "2025-2026", "S2"),  # آخر يوم في العام السابق
        (date(2026, 10, 27), "2026-2027", "S1"),  # إجازة منتصف الفصل
        (date(2026, 12, 25), "2026-2027", "S1"),  # إجازة منتصف العام تتبع المنتهي
        (date(2027, 1, 4), "2026-2027", "S2"),  # أوّل يوم للطلبة في الفصل الثاني
        (date(2027, 7, 15), "2026-2027", "S2"),  # الصيف يتبع الفصل الأخير
    ],
)
def test_the_year_and_semester_are_derived_from_the_day(seeded, day, year, code):
    now = AcademicCalendar.current(seeded, on=day)

    assert (now.year_name, now.semester_code) == (year, code)


def test_no_day_of_the_year_falls_outside_a_semester(seeded):
    """فجوةٌ بلا فصل تُجبر كل شاشة على اختراع سلوكٍ لتلك الأيام."""
    year = AcademicYear.objects.get(school=seeded, name="2026-2027")

    day, gaps = year.start_date, []
    while day <= year.end_date:
        if AcademicCalendar.current(seeded, on=day).semester is None:
            gaps.append(day)
        day += timedelta(days=1)

    assert not gaps, f"أيّامٌ بلا فصل: {gaps[:5]}"


def test_the_years_do_not_overlap(seeded):
    years = list(AcademicYear.objects.filter(school=seeded).order_by("start_date"))

    for earlier, later in zip(years, years[1:], strict=False):
        assert earlier.end_date < later.start_date


def test_the_semesters_are_contiguous_and_within_their_year(seeded):
    for year in AcademicYear.objects.filter(school=seeded):
        s1 = year.semesters.get(code="S1")
        s2 = year.semesters.get(code="S2")

        assert s1.start_date == year.start_date
        assert s2.end_date == year.end_date
        assert s2.start_date == s1.end_date + timedelta(days=1)


# ═══════════════════════════════════════════════════════════════════
#  ما كان الثابت يُخطئ فيه
# ═══════════════════════════════════════════════════════════════════


def test_the_derived_year_disagrees_with_the_frozen_setting(seeded):
    """الدليل على أن الثابت تجاوزه الزمن — لا افتراضاً بل بمقارنة."""
    from django.conf import settings

    derived = AcademicCalendar.year_name(seeded, on=date(2026, 8, 27))

    assert derived == "2026-2027"
    assert derived != settings.CURRENT_ACADEMIC_YEAR


# ═══════════════════════════════════════════════════════════════════
#  نطاق الصفوف والجمهور
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("grade", "expected_start"),
    [("G10", date(2026, 10, 13)), ("G7", date(2026, 10, 14))],
)
def test_exam_windows_differ_by_grade_band(seeded, grade, expected_start):
    """نوافذ الوزارة تختلف: الصفّان ١٠–١١ يبدآن قبل الصفوف ١–٩ بيوم."""
    events = AcademicCalendar.events(
        seeded, grade=grade, audience="students", on=date(2026, 10, 15)
    ).filter(event_type="midterm_exam", start_date__year=2026)

    assert [e.start_date for e in events] == [expected_start]


def test_staff_only_events_do_not_reach_students(seeded):
    """إجازة الموظفين ليست إجازة طلبة — وعرضُها لهم معلومةٌ خاطئة."""
    students = AcademicCalendar.events(seeded, audience="students", on=date(2026, 9, 1)).filter(
        name__startswith="إجازة الموظفين"
    )

    assert not students.exists()


def test_the_second_round_belongs_to_the_year_it_examines_not_its_own(seeded):
    """اختبارات الدور الثاني لعام ٢٠٢٥/٢٠٢٦ تقع في أغسطس ٢٠٢٦ — أي داخل
    تقويم العام التالي. فالحدث ينتمي إلى عامٍ قد لا يكون عام تاريخه."""
    event = CalendarEvent.objects.get(
        academic_year__school=seeded,
        academic_year__name="2026-2027",
        event_type="second_round",
    )

    assert event.start_date == date(2026, 8, 23)
    assert "٢٠٢٥/٢٠٢٦" in event.name


# ═══════════════════════════════════════════════════════════════════
#  البنية
# ═══════════════════════════════════════════════════════════════════


def test_the_semester_carries_its_weight_as_data(seeded):
    """٤٠ و٦٠ درجةً بياناتٌ لا ثابتٌ في الشيفرة — الوزارة قد تُعدّلهما."""
    year = AcademicYear.objects.get(school=seeded, name="2026-2027")

    assert year.semesters.get(code="S1").max_grade == 40
    assert year.semesters.get(code="S2").max_grade == 60


def test_the_semester_has_no_current_flag():
    """رايةٌ يدوية تُنسى، فتُسجَّل الدرجات في الفصل الخطأ بلا أن يكشف ذلك شيء."""
    assert not hasattr(Semester, "is_current")


def test_seeding_twice_does_not_duplicate(seeded):
    """البذر يُعاد عند تحديث الوزارة تقويمها — فلا يجوز أن يُضاعف."""
    before = CalendarEvent.objects.filter(academic_year__school=seeded).count()

    call_command("seed_academic_calendar", school=seeded.code, verbosity=0)

    assert CalendarEvent.objects.filter(academic_year__school=seeded).count() == before
