"""[SCHEDULE] الحصة المنقسمة: مادّتان ومعلّمان في خانةٍ واحدة.

أربعُ شعبٍ يتفرّق طلابها بين مادّتين في التوقيت نفسه — 11/1 و12/1 بين
التكنولوجيا والفنون البصرية، و11/4 و12/4 بين الكيمياء والفنون. قسمٌ يذهب
إلى معمل الحاسب أو غرفة الفنون، وقسمٌ يبقى.

وكان `no_class_period_overlap` يمنع النصف الثاني — حصّةٌ واحدة لشعبةٍ في
التوقيت الواحد — فكان الاستيراد يُسقطه ويرى المعلّم والطالب خليّةً ناقصة.
فدخلت `elective_group` في القيد: فارغةٌ في حصص الشعبة كاملةً فيبقى المنع
كما كان، ومُسمّاةٌ في المنقسمة فيسع القيدُ نصفيها.

وكان `get_weekly_schedule` يُعيد حصّةً مفردة مع فلتر الفصل وقائمةً بدونه.
ونوعُ إرجاعٍ متبدّل فخٌّ في ذاته: قالبٌ يقرأ `slot.subject` من قائمةٍ لا
يُخطئ — يطبع فراغاً. فوُحِّد الشكل قائمةً في كل الأحوال.
"""

from datetime import time

import pytest
from django.db.utils import IntegrityError

from core.models import ClassGroup, CustomUser
from operations.models import ScheduleSlot, Subject
from operations.services import ScheduleService

YEAR = "2026-2027"


@pytest.fixture
def section(db, school):
    return ClassGroup.objects.create(
        school=school, grade="G11", section="1", level_type="sec", academic_year=YEAR
    )


@pytest.fixture
def subjects(db, school):
    return {
        name: Subject.objects.create(school=school, name_ar=name)
        for name in ("التكنولوجيا", "الفنون البصرية", "الرياضيات")
    }


@pytest.fixture
def teachers(db):
    def _make(*names):
        return [
            CustomUser.objects.create(national_id=f"1000000000{i}", full_name=n)
            for i, n in enumerate(names)
        ]

    return _make


def _slot(school, section, subject, teacher, *, period=4, group=""):
    return ScheduleSlot.objects.create(
        school=school,
        class_group=section,
        subject=subject,
        teacher=teacher,
        day_of_week=1,
        period_number=period,
        start_time=time(11, 0),
        end_time=time(11, 45),
        academic_year=YEAR,
        elective_group=group,
    )


# ── ما يسعه القيد وما يمنعه ──────────────────────────────────────────


def test_two_electives_share_one_period(db, school, section, subjects, teachers):
    """نصفا الشعبة في التوقيت نفسه — ولكلٍّ مادّتُه ومعلّمُه."""
    tech, art = teachers("محمد اسماعيل السيد", "يوسف يعقوب عوض")

    _slot(school, section, subjects["التكنولوجيا"], tech, group="التكنولوجيا")
    _slot(school, section, subjects["الفنون البصرية"], art, group="الفنون البصرية")

    assert ScheduleSlot.objects.filter(class_group=section, period_number=4).count() == 2


def test_a_whole_class_period_still_admits_only_one(db, school, section, subjects, teachers):
    """المجموعة فارغةٌ في حصص الشعبة كاملةً — فيبقى المنع كما كان."""
    one, two = teachers("أ", "ب")
    _slot(school, section, subjects["الرياضيات"], one)

    with pytest.raises(IntegrityError):
        _slot(school, section, subjects["التكنولوجيا"], two)


def test_one_elective_group_cannot_be_doubled(db, school, section, subjects, teachers):
    """نصفٌ واحد لا يُدرَّس مرّتين في التوقيت نفسه."""
    one, two = teachers("أ", "ب")
    _slot(school, section, subjects["التكنولوجيا"], one, group="التكنولوجيا")

    with pytest.raises(IntegrityError):
        _slot(school, section, subjects["الرياضيات"], two, group="التكنولوجيا")


# ── ما يراه الجدول ───────────────────────────────────────────────────


def test_the_class_cell_carries_both_subjects_and_both_teachers(
    db, school, section, subjects, teachers
):
    """المطلوب في الشاشة: المادّتان واسما المعلّمين في الخلية الواحدة."""
    tech, art = teachers("محمد اسماعيل السيد", "يوسف يعقوب عوض")
    _slot(school, section, subjects["التكنولوجيا"], tech, group="التكنولوجيا")
    _slot(school, section, subjects["الفنون البصرية"], art, group="الفنون البصرية")

    grid = ScheduleService.get_weekly_schedule(school, class_group=section, academic_year=YEAR)

    cell = grid[1][4]
    assert {s.subject.name_ar for s in cell} == {"التكنولوجيا", "الفنون البصرية"}
    assert {s.teacher.full_name for s in cell} == {
        "محمد اسماعيل السيد",
        "يوسف يعقوب عوض",
    }


@pytest.mark.parametrize("scope", ["class", "teacher", "school"])
def test_the_cell_is_a_list_whatever_the_filter(db, school, section, subjects, teachers, scope):
    """نوعُ إرجاعٍ متبدّل فخّ: قالبٌ يقرأ حقلاً من قائمةٍ يطبع فراغاً ولا يشكو."""
    (one,) = teachers("أ")
    _slot(school, section, subjects["الرياضيات"], one)

    kwargs = {"class_group": section} if scope == "class" else {}
    if scope == "teacher":
        kwargs = {"teacher": one}
    grid = ScheduleService.get_weekly_schedule(school, academic_year=YEAR, **kwargs)

    assert isinstance(grid[1][4], list)
    assert grid[1][4][0].subject.name_ar == "الرياضيات"


def test_an_empty_period_stays_absent(db, school, section):
    """الخانة الفارغة تبقى غائبةً لا قائمةً فارغة — فالقالب يفرّق بينهما."""
    grid = ScheduleService.get_weekly_schedule(school, class_group=section, academic_year=YEAR)

    assert grid[1] == {}


# ── القوالب ──────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "template",
    [
        "templates/schedule/print_schedule.html",
        "templates/schedule/print_pages.html",
    ],
)
def test_no_template_reads_a_field_straight_off_the_cell(template):
    """قراءةُ حقلٍ من الخانة مباشرةً تطبع فراغاً بلا شكوى بعد توحيد الشكل."""
    import pathlib

    src = pathlib.Path(template).read_text(encoding="utf-8")

    assert "cell.subject" not in src
    assert "slot=grid|" not in src, "الخانة قائمة، فلا تُسمّى حصّة"


def test_the_rendered_cell_shows_both_subjects_and_both_teachers(
    db, client, school, section, subjects, teachers, principal_user
):
    """الدعوى على الشاشة لا على البنية: الورقةُ تكتب المادّتين والاسمين معاً.

    (كانت على شبكة `weekly.html` القديمة؛ وصارت الورقةُ هي صفحةَ الجدول.)
    """
    from django.urls import reverse

    tech, art = teachers("محمد اسماعيل السيد", "يوسف يعقوب عوض")
    _slot(school, section, subjects["التكنولوجيا"], tech, group="التكنولوجيا")
    _slot(school, section, subjects["الفنون البصرية"], art, group="الفنون البصرية")

    client.force_login(principal_user)
    html = client.get(
        reverse("schedule_print"), {"view": "class", "class": section.id, "year": YEAR}
    ).content.decode()

    for text in ("التكنولوجيا", "الفنون البصرية", "محمد اسماعيل السيد", "يوسف يعقوب عوض"):
        assert text in html, text
