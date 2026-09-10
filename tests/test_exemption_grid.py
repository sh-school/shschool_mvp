"""[SCHEDULE] شبكةُ التفريغ: الخانةُ تُظلَّل، ولا تُضرب الأيّامُ في الحصص.

    (الأحدَ الأولى) و(الاثنينَ الثالثة) خانتان — لا أربع.

الاستمارةُ القديمةُ كانت تضرب (الأيّامَ المختارة) × (الحصصَ المختارة)، فطلبُ
خانتين متفرّقتين يُنتج أربعاً. ولهذا سكنت قيودُ معلّمٍ واحدٍ عشرين تفريغاً
منفصلاً: عشرون سجلّاً لتعبيرٍ واحدٍ لم تحمله الاستمارة.

وهنا ثلاثةُ أشياءَ تُحرَس:

  1. **الصيغة** — «يوم:حصّة» خانةٌ، و«يوم:*» يومٌ كامل. والتمييزُ ليس شكليّاً:
     `build_tasks` يقرأ أيّامَ التفريغ من `full_day` وحدَها ومنها يُنقص مقامَ
     قسمة النصاب على الأيّام، فسبعُ خاناتٍ مفردةٍ تُفرّغ اليومَ في الشبكة ولا
     تُعَدّ يوماً فارغاً في الحساب.
  2. **خاناتُ الأسبوع** — ليست خمساً وثلاثين لكلّ أحد: سابعةُ الخميس لا وجودَ
     لها لمن لا يُدرّس ثانويّاً، فتُطرح من العدّ ولا تُعرض فرصةً.
  3. **الحارس** — «خاناتُ الأسبوع − النصاب» حدٌّ يُردُّ في الخادم لا يُنبَّه
     في الشاشة فقط: العدّادُ يُتجاوَز بإطفاء السكربت.
"""

import pytest

from operations.exemption_grid import build_grid, cells_of, parse_slots
from operations.models import ScheduleSlot, Subject, SubjectClassAssignment, TeacherExemption
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


# ════════════════════ الصيغة: parse_slots ════════════════════
# لا قاعدةَ بياناتٍ لها — منطقٌ نقيٌّ يُقرأ وحدَه.


@pytest.mark.django_db(transaction=False)
def test_scattered_slots_stay_two_not_four():
    """الحاسمُ: ما عجزت عنه الاستمارةُ القديمة."""
    assert parse_slots(["0:1", "1:3"]) == [(0, 1), (1, 3)]


def test_a_whole_day_is_one_row_not_seven_cells():
    """«يوم كامل» زوجٌ بحصّةٍ `None` — وهو ما يُنقص مقامَ القسمة."""
    assert parse_slots(["2:*"]) == [(2, None)]


def test_a_whole_day_swallows_its_own_cells():
    """اليومُ الكاملُ يغني عن خاناته، فلا يُسجَّل التفريغُ مرّتين بوجهين."""
    assert parse_slots(["1:*", "1:3", "1:5", "2:2"]) == [(1, None), (2, 2)]


def test_malformed_input_is_dropped_not_raised():
    """المدخلُ من المتصفّح لا يُوثق به — وما فسد يُطرح ولا يُسقط الصفحة."""
    assert parse_slots(["", "x:1", "0:99", "9:1", "0", "0:1:2", "0:1"]) == [(0, 1)]


def test_a_repeated_cell_is_counted_once():
    assert parse_slots(["3:4", "3:4", "3:4"]) == [(3, 4)]


def test_empty_input_gives_nothing():
    assert parse_slots([]) == []


# ════════════════════ الشبكة: build_grid ════════════════════


@pytest.fixture
def prep_teacher(school):
    """معلّمٌ لا يُدرّس إلّا الإعداديَّ — فسابعةُ الخميس ليست من أسبوعه."""
    user = UserFactory(full_name="معلّمُ الإعداديّ")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MAT")
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=group,
        subject=subject,
        teacher=user,
        weekly_periods=5,
        academic_year=YEAR,
    )
    return user


@pytest.fixture
def secondary_teacher(school):
    """معلّمٌ يُدرّس الثانويَّ — فسابعةُ الخميس مشروعةٌ في أسبوعه."""
    user = UserFactory(full_name="معلّمُ الثانويّ")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    subject = Subject.objects.create(school=school, name_ar="الفيزياء", code="PHY")
    group = ClassGroupFactory(school=school, grade="G11", level_type="sec", academic_year=YEAR)
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=group,
        subject=subject,
        teacher=user,
        weekly_periods=4,
        academic_year=YEAR,
    )
    return user


def test_thursdays_seventh_is_off_for_a_prep_teacher(school, prep_teacher):
    """سقفُ اليوم صفةُ الشعبة: الخميسُ ستُّ حصصٍ في الإعداديّ."""
    grid = build_grid(school, prep_teacher, YEAR)
    thursday = next(row for row in grid.rows if row.day == 4)
    assert [cell.period for cell in thursday.cells if cell.disabled] == [7]
    assert grid.week_slots == 34


def test_thursdays_seventh_stays_for_a_secondary_teacher(school, secondary_teacher):
    """ومن يُدرّس الثانويَّ لا تُحجب عنه خانةٌ يعمل فيها."""
    grid = build_grid(school, secondary_teacher, YEAR)
    thursday = next(row for row in grid.rows if row.day == 4)
    assert [cell for cell in thursday.cells if cell.disabled] == []
    assert grid.week_slots == 35


def test_the_allowance_is_week_slots_minus_load(school, prep_teacher):
    """القاعدةُ المعلَنة: خاناتُ الأسبوع − النصاب = ما يجوز تفريغُه."""
    grid = build_grid(school, prep_teacher, YEAR)
    assert (grid.week_slots, grid.load) == (34, 5)
    assert grid.allowance == 29


def test_an_existing_release_is_marked_and_subtracted(school, prep_teacher):
    """المفرَّغُ سلفاً يُعرض مظلّلاً ويُطرح من الباقي — فلا يُطلب مرّتين."""
    row = TeacherExemption.objects.create(
        school=school,
        teacher=prep_teacher,
        academic_year=YEAR,
        exemption_type="specific_period",
        day_of_week=0,
        period_number=3,
        reason="اجتماعُ منسّقين",
        source="school",
    )
    grid = build_grid(school, prep_teacher, YEAR)
    sunday = next(r for r in grid.rows if r.day == 0)
    cell = next(c for c in sunday.cells if c.period == 3)
    assert cell.exemption_id == str(row.id)
    assert grid.blocked == 1
    assert grid.remaining == grid.allowance - 1


def test_a_whole_day_release_marks_its_whole_row(school, prep_teacher):
    TeacherExemption.objects.create(
        school=school,
        teacher=prep_teacher,
        academic_year=YEAR,
        exemption_type="full_day",
        day_of_week=1,
        period_number=None,
        reason="دورةٌ خارج المدرسة",
        source="school",
    )
    grid = build_grid(school, prep_teacher, YEAR)
    monday = next(r for r in grid.rows if r.day == 1)
    assert all(cell.exemption_id and cell.from_full_day for cell in monday.cells)
    assert grid.blocked == 7


def test_the_grid_carries_no_schedule(school, prep_teacher):
    """أداةُ تفريغٍ لا عرضٌ للجدول: الخانةُ لا تحمل شاغلَها (قرار 2026-09-09)."""
    group = ClassGroupFactory(school=school, grade="G7", level_type="prep", academic_year=YEAR)
    ScheduleSlot.objects.create(
        school=school,
        teacher=prep_teacher,
        class_group=group,
        subject=Subject.objects.create(school=school, name_ar="العلوم", code="SCI"),
        day_of_week=0,
        period_number=1,
        start_time="07:10",
        end_time="08:00",
        academic_year=YEAR,
    )
    grid = build_grid(school, prep_teacher, YEAR)
    cell = next(c for r in grid.rows if r.day == 0 for c in r.cells if c.period == 1)
    assert not hasattr(cell, "label")


def test_level_says_impossible_when_nothing_remains(school, prep_teacher):
    """لا يبقى مسموحٌ = مستنفَد، تقرؤه الشاشةُ لوناً."""
    for day in range(5):
        for period in range(1, 8):
            if (day, period) == (4, 7):
                continue
            TeacherExemption.objects.create(
                school=school,
                teacher=prep_teacher,
                academic_year=YEAR,
                exemption_type="specific_period",
                day_of_week=day,
                period_number=period,
                reason="ملء",
                source="school",
            )
    grid = build_grid(school, prep_teacher, YEAR)
    assert grid.remaining == 0
    assert grid.level == "impossible"


# ════════════════════ cells_of: ما سيُفرَّغ فعلاً ════════════════════


def test_cells_of_a_whole_day_is_the_whole_row(school, prep_teacher):
    grid = build_grid(school, prep_teacher, YEAR)
    assert len(cells_of(grid, 0, None)) == 7


def test_cells_of_one_period_is_one_cell(school, prep_teacher):
    grid = build_grid(school, prep_teacher, YEAR)
    cells = cells_of(grid, 0, 3)
    assert [c.period for c in cells] == [3]


def test_cells_of_an_unknown_day_is_empty(school, prep_teacher):
    grid = build_grid(school, prep_teacher, YEAR)
    assert cells_of(grid, 9, 1) == []


# ════════════════════ الحارس في الخادم ════════════════════


@pytest.fixture
def vice(school):
    user = UserFactory(full_name="النائبُ الأكاديميّ")
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="vice_academic")
    )
    return user


def post_release(client, teacher, slots, *, reason="فحص"):
    return client.post(
        "/teacher/schedule-settings/exemption/add/",
        {
            "teacher": str(teacher.id),
            "slots": slots,
            "reason": reason,
            "source": "school",
            "year": YEAR,
        },
        follow=True,
    )


def test_scattered_cells_are_saved_as_two_rows(client, school, vice, prep_teacher):
    """الحاسمُ من طرف الخادم: خانتان متفرّقتان سجلّان لا أربعة."""
    client.force_login(vice)
    post_release(client, prep_teacher, "0:1,1:3")

    rows = TeacherExemption.objects.filter(teacher=prep_teacher, is_active=True)
    assert rows.count() == 2
    assert {(r.day_of_week, r.period_number) for r in rows} == {(0, 1), (1, 3)}


def test_a_whole_day_is_saved_as_full_day(client, school, vice, prep_teacher):
    """النوعُ يُشتقّ من الخانة — و`full_day` هو ما يقرؤه المولّد مقامَ قسمة."""
    client.force_login(vice)
    post_release(client, prep_teacher, "2:*")

    row = TeacherExemption.objects.get(teacher=prep_teacher, is_active=True)
    assert (row.exemption_type, row.day_of_week, row.period_number) == ("full_day", 2, None)


def test_both_kinds_ride_in_one_request(client, school, vice, prep_teacher):
    client.force_login(vice)
    post_release(client, prep_teacher, "2:*,0:1")

    rows = TeacherExemption.objects.filter(teacher=prep_teacher, is_active=True)
    assert {(r.exemption_type, r.day_of_week, r.period_number) for r in rows} == {
        ("full_day", 2, None),
        ("specific_period", 0, 1),
    }


def test_a_release_beyond_the_allowance_is_refused(client, school, vice, prep_teacher):
    """الحارس: ما يتجاوز «خانات الأسبوع − النصاب» لا يُحفظ ولو أُرسل."""
    client.force_login(vice)
    every_day = ",".join(f"{day}:*" for day in range(5))
    response = post_release(client, prep_teacher, every_day)

    assert TeacherExemption.objects.filter(teacher=prep_teacher, is_active=True).count() == 0
    assert any("يتجاوز المسموح" in str(m) for m in response.context["messages"])


def test_a_release_within_the_allowance_is_kept(client, school, vice, prep_teacher):
    client.force_login(vice)
    post_release(client, prep_teacher, "0:1,0:2,0:3")

    assert TeacherExemption.objects.filter(teacher=prep_teacher, is_active=True).count() == 3


def test_an_empty_selection_says_so(client, school, vice, prep_teacher):
    client.force_login(vice)
    response = post_release(client, prep_teacher, "")

    assert TeacherExemption.objects.filter(teacher=prep_teacher).count() == 0
    assert any("ظلِّل خانةً" in str(m) for m in response.context["messages"])


def test_a_teacher_may_not_release_anyone(client, school, prep_teacher):
    """البابُ للمدير والنائب — ومن سواهما لا يفتحه بمعرفةِ مساره."""
    client.force_login(prep_teacher)
    post_release(client, prep_teacher, "0:1")

    assert TeacherExemption.objects.filter(teacher=prep_teacher).count() == 0


def test_the_grid_of_another_school_is_not_readable(client, school, vice):
    """أسبوعُ معلّمٍ في مدرسةٍ أخرى لا يُقرأ بتغيير معرّفٍ في الرابط."""
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    stranger = UserFactory(full_name="غريبٌ عن المدرسة")
    MembershipFactory(user=stranger, school=other, role=RoleFactory(school=other, name="teacher"))

    client.force_login(vice)
    response = client.get(
        "/teacher/schedule-settings/exemption/grid/",
        {"teacher": str(stranger.id), "year": YEAR},
    )
    assert response.status_code == 200
    assert b"data-exg" not in response.content
