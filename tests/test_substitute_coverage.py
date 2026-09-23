"""الإشغالُ عن معلّمٍ غائب — قراراتُ المالك 2026-09-23.

كان التعيينُ صفّاً في `SubstituteAssignment` وحدَه: لا يصل البديلَ إشعارٌ، ولا
تظهر الحصّةُ في «حصصي اليوم» عنده، والمنسّقُ يختار من المدرسة كلّها، ويُقبل
أيُّ معرّفٍ يُرسَل. والقرار:

- المنسّقُ يُشغِل من قسمه وحدَه، والقيادةُ من الكادر التعليميّ كلّه.
- أمام كلّ مرشَّحٍ عدّادُ إشغالاته ونصابُه وحصصُه يومَها، وتنبيهُ التلاصق.
- الإشغالُ تكليفٌ نافذ: تُسلَّم الحصّةُ للبديل، ويُبلَّغ الجميع.
"""

import datetime as dt

import pytest
from django.contrib.auth.models import Group
from django.urls import reverse

from core.academic_calendar import academic_year_for_school
from core.models import Department, Membership
from notifications.models import InAppNotification
from operations.models import (
    ScheduleSlot,
    Session,
    Subject,
    SubstituteAssignment,
    TeacherAbsence,
)
from operations.services import SubstituteService
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

#: أحدٌ ثابت — لا `date.today()`، فالجمعةُ والسبتُ بلا حصص.
SUNDAY = dt.date(2026, 9, 20)
DAY = SubstituteService._date_to_day(SUNDAY)


@pytest.fixture(autouse=True)
def _calendar(seeded_calendar):
    """عدّادُ الإشغال يُحسب على نافذة العام؛ وبلا تقويمٍ مبذورٍ يرتدّ العامُ إلى
    الثابت المجمَّد فتقع تواريخُ الاختبار خارجه ويُعدّ الإشغالُ صفراً."""
    return seeded_calendar


def _member(school, role, name, department=None):
    user = UserFactory(full_name=name)
    MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name=role),
        department_obj=department,
    )
    return user


def _slot(school, teacher, class_group, period, subject=None, day=DAY):
    return ScheduleSlot.objects.create(
        school=school,
        teacher=teacher,
        class_group=class_group,
        subject=subject,
        day_of_week=day,
        period_number=period,
        start_time=dt.time(6 + period, 0),
        end_time=dt.time(6 + period, 45),
        academic_year=academic_year_for_school(school),
    )


@pytest.fixture
def math(school):
    return Department.objects.create(school=school, name="الرياضيات", code="math")


@pytest.fixture
def science(school):
    return Department.objects.create(school=school, name="العلوم", code="science")


@pytest.fixture
def people(school, math, science):
    coordinator = _member(school, "coordinator", "منسّق الرياضيات", math)
    math.head = coordinator
    math.save(update_fields=["head"])
    return {
        "coordinator": coordinator,
        "absent": _member(school, "teacher", "الغائب", math),
        "math_free": _member(school, "teacher", "رياضيّاتٌ متفرّغ", math),
        "math_busy": _member(school, "teacher", "رياضيّاتٌ مشغول", math),
        "science_free": _member(school, "teacher", "علومٌ متفرّغ", science),
        "vice": _member(school, "vice_academic", "النائب الأكاديمي"),
    }


@pytest.fixture
def lesson(school, class_group, people):
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    slot = _slot(school, people["absent"], class_group, 3, subject)
    # مشغولٌ في الحصّة نفسها — في شعبةٍ أخرى، فالشعبةُ لا تحمل حصّتين في وقتٍ واحد.
    _slot(school, people["math_busy"], ClassGroupFactory(school=school), 3)
    return slot


@pytest.fixture
def absence(school, people, principal_user):
    return TeacherAbsence.objects.create(
        school=school, teacher=people["absent"], date=SUNDAY, reported_by=principal_user
    )


def _names(rows):
    return {row["name"] for row in rows}


class TestWhoCanBeChosen:
    def test_the_coordinator_chooses_from_his_department_only(self, absence, lesson, people, math):
        rows = SubstituteService.coverage_candidates(
            absence, [lesson], within_ids=math.get_teacher_ids()
        )[lesson.id]

        assert "رياضيّاتٌ متفرّغ" in _names(rows)
        assert "علومٌ متفرّغ" not in _names(rows), "من قسمٍ آخر"
        assert "رياضيّاتٌ مشغول" not in _names(rows), "له حصّةٌ في الوقت نفسه"
        assert "الغائب" not in _names(rows)

    def test_leadership_chooses_from_the_whole_teaching_staff(self, absence, lesson):
        rows = SubstituteService.coverage_candidates(absence, [lesson], within_ids=None)[lesson.id]

        assert {"رياضيّاتٌ متفرّغ", "علومٌ متفرّغ"} <= _names(rows)
        assert "النائب الأكاديمي" not in _names(rows), "ليس من الكادر التعليميّ"


class TestEachNameCarriesItsCounters:
    def test_substitutions_load_and_day_are_shown_and_the_least_used_comes_first(
        self, school, class_group, absence, lesson, people
    ):
        math_free, science_free = people["math_free"], people["science_free"]
        other = ClassGroupFactory(school=school)
        for period in (2, 4):  # حصّتا الرياضيّاتيّ حول الثالثة: سلسلةٌ من ثلاث
            _slot(school, math_free, other, period)
        _slot(school, math_free, other, 1, day=(DAY + 1) % 5)
        earlier = TeacherAbsence.objects.create(
            school=school, teacher=people["math_busy"], date=SUNDAY - dt.timedelta(days=7)
        )
        SubstituteAssignment.objects.create(
            school=school, absence=earlier, slot=lesson, substitute=math_free
        )

        rows = SubstituteService.coverage_candidates(absence, [lesson])[lesson.id]
        by_name = {row["name"]: row for row in rows}

        assert by_name["رياضيّاتٌ متفرّغ"]["subs"] == 1
        assert by_name["رياضيّاتٌ متفرّغ"]["load"] == 3
        assert by_name["رياضيّاتٌ متفرّغ"]["day"] == 2
        assert by_name["رياضيّاتٌ متفرّغ"]["long_run"] is True
        assert by_name["علومٌ متفرّغ"]["long_run"] is False
        assert [r["name"] for r in rows].index(science_free.full_name) < [
            r["name"] for r in rows
        ].index(math_free.full_name), "الأقلُّ إشغالاً أوّلاً"

    def test_the_counters_appear_in_the_chooser(self, client_as, principal_user, absence, lesson):
        body = client_as(principal_user).get(reverse("absence_detail", args=[absence.id]))

        assert "إشغال 0 · نصاب 0 · اليوم 0" in body.content.decode()


class TestTheChoiceIsCheckedOnTheServer:
    def test_a_coordinator_cannot_post_a_teacher_from_another_department(
        self, client_as, absence, lesson, people
    ):
        resp = client_as(people["coordinator"]).post(
            reverse("assign_substitute", args=[absence.id, lesson.id]),
            {"substitute": str(people["science_free"].id)},
        )

        assert resp.status_code == 400
        assert not SubstituteAssignment.objects.exists()

    def test_a_busy_teacher_is_refused_even_to_the_principal(
        self, client_as, principal_user, absence, lesson, people
    ):
        resp = client_as(principal_user).post(
            reverse("assign_substitute", args=[absence.id, lesson.id]),
            {"substitute": str(people["math_busy"].id)},
        )

        assert resp.status_code == 400


class TestTheSubstituteIsTold:
    def _assign(self, client_as, actor, absence, lesson, substitute):
        return client_as(actor).post(
            reverse("assign_substitute", args=[absence.id, lesson.id]),
            {"substitute": str(substitute.id)},
        )

    def test_the_lesson_is_handed_over_and_labelled_as_a_cover(
        self, client_as, school, absence, lesson, people
    ):
        resp = self._assign(client_as, people["coordinator"], absence, lesson, people["math_free"])
        assert resp.status_code == 200

        session = Session.objects.get(class_group=lesson.class_group, date=SUNDAY)
        assert session.teacher == people["math_free"]
        assert session.original_teacher == people["absent"]

        page = client_as(people["math_free"]).get(
            reverse("teacher_schedule"), {"date": SUNDAY.isoformat()}
        )
        assert "إشغال — عن الغائب" in page.content.decode()

    def test_everyone_named_by_the_owner_is_notified_but_not_the_actor(
        self,
        client_as,
        school,
        absence,
        lesson,
        people,
        principal_user,
        django_capture_on_commit_callbacks,
    ):
        developer = _member(school, "it_technician", "المطوّر")
        developer.groups.add(Group.objects.get_or_create(name="developers")[0])

        with django_capture_on_commit_callbacks(execute=True):
            self._assign(client_as, people["coordinator"], absence, lesson, people["math_free"])

        told = set(InAppNotification.objects.values_list("user__full_name", flat=True))
        assert {
            "رياضيّاتٌ متفرّغ",
            "الغائب",
            "النائب الأكاديمي",
            "مدير المدرسة",
            "المطوّر",
        } <= told
        assert "منسّق الرياضيات" not in told, "من قرّر لا يُبلَّغ بما فعل"


class TestSwapsKeepTheirLabel:
    def test_a_swapped_lesson_is_not_read_as_a_cover(self, school, class_group, people):
        session = Session.objects.create(
            school=school,
            class_group=class_group,
            teacher=people["math_free"],
            original_teacher=people["absent"],
            date=SUNDAY,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 45),
        )

        assert SubstituteService.cover_session_ids([session]) == set()


class TestTheCoordinatorCountsHisDepartment:
    def test_absences_in_other_departments_are_not_counted(self, school, people):
        from core.dashboard_selectors import get_teacher_ctx

        TeacherAbsence.objects.create(school=school, teacher=people["absent"], date=SUNDAY)
        TeacherAbsence.objects.create(school=school, teacher=people["science_free"], date=SUNDAY)
        membership = Membership.objects.get(user=people["coordinator"])

        ctx = get_teacher_ctx(people["coordinator"], school, SUNDAY, membership.role.name)

        assert ctx["coord_absent_today"] == 1
