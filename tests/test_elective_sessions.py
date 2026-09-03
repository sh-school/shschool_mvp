"""زوجُ الاختيار يُنتج جلستين لا واحدة.

شعبةٌ تتفرّق بين مادّتين في التوقيت نفسه (11/1: تكنولوجيا/فنون) لها في
الجدول حصّتان بمعلّمَين تحملان `elective_group`. وكانت `Session` لا تعرف
هذا الحقل، فقيدُها الفريد (الشعبة، التاريخ، الوقت) يُسقط الثانيةَ بصمتٍ في
`bulk_create(ignore_conflicts=True)`: 178 حصّةً في الجدول، 175 جلسة.
"""

import datetime as dt
from datetime import date

import pytest

from core.models import ClassGroup
from operations.models import ScheduleSlot, Session, Subject
from operations.services import ScheduleService
from tests.conftest import MembershipFactory, RoleFactory, UserFactory


def _slot(school, teacher, cg, subject, **extra):
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=cg,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        academic_year="2026-2027",
        **extra,
    )


@pytest.mark.django_db
def test_an_elective_pair_yields_two_sessions_in_the_same_slot(school):
    role = RoleFactory(school=school, name="teacher")
    tech, art = UserFactory(full_name="معلّم التكنولوجيا"), UserFactory(full_name="معلّم الفنون")
    for t in (tech, art):
        MembershipFactory(user=t, school=school, role=role)
    cg = ClassGroup.objects.create(
        school=school, grade="G11", section="1", academic_year="2026-2027"
    )
    _slot(
        school,
        tech,
        cg,
        Subject.objects.create(school=school, name_ar="التكنولوجيا"),
        elective_group="tech",
    )
    _slot(
        school,
        art,
        cg,
        Subject.objects.create(school=school, name_ar="الفنون البصرية"),
        elective_group="art",
    )

    sunday = date(2026, 3, 22)
    created = ScheduleService.ensure_sessions_for_date(school, sunday, academic_year="2026-2027")

    sessions = Session.objects.filter(school=school, date=sunday, class_group=cg)
    assert created == 2
    assert {s.teacher_id for s in sessions} == {tech.id, art.id}, "كلا المعلّمَين يجد حصّته"
    assert {s.elective_group for s in sessions} == {"tech", "art"}


@pytest.mark.django_db
def test_a_whole_class_period_is_still_one_session(school):
    """الحصّةُ العاديّة (بلا مجموعة) تبقى واحدةً — الاستدعاءُ الثاني لا يكرّرها."""
    role = RoleFactory(school=school, name="teacher")
    teacher = UserFactory(full_name="معلّم الرياضيات")
    MembershipFactory(user=teacher, school=school, role=role)
    cg = ClassGroup.objects.create(
        school=school, grade="G8", section="1", academic_year="2026-2027"
    )
    _slot(school, teacher, cg, Subject.objects.create(school=school, name_ar="الرياضيات"))

    sunday = date(2026, 3, 22)
    first = ScheduleService.ensure_sessions_for_date(school, sunday, academic_year="2026-2027")
    second = ScheduleService.ensure_sessions_for_date(school, sunday, academic_year="2026-2027")

    assert first == 1 and second == 0
    assert Session.objects.filter(school=school, date=sunday, class_group=cg).count() == 1
