"""«طلابي» في سياق لوحة المعلّم: أعدادٌ مجمَّعة بلا أسماء وباستعلامات ثابتة (W-20261010-040، D-335م).

المحدِّد `_my_students_ctx` يغذّي بطاقةً مصغَّرة لاحقاً (W-20261010-039)؛ وهنا يُحرس أنّه يعدّ طلابَ شعب المعلّم في جدوله اليوم وحدَهم،
وأنّ عددَ الاستعلامات لا يتبع عددَ الشعب ولا الطلاب، وأنّ السياق لا يحمل اسمَ طالبٍ ولا هويّة، وأنّ القدرةَ تحكم العدّادَ المشترك مع المنسّق.
"""

import datetime as dt
import json

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext

from core.dashboard_selectors import _my_students_ctx, get_teacher_ctx
from core.models import CustomUser
from operations.class_exit import come_back, leave
from operations.models import ClassExit, Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, SATURDAY, SUNDAY, _staff, at
from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db

KEYS = {"exit_total", "out_now"}


def _kid(klass, name, national_id):
    student = UserFactory(full_name=name, national_id=national_id)
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
    return student


def _today_sessions(teacher):
    return list(Session.objects.filter(teacher=teacher, date=SUNDAY).select_related("class_group"))


@pytest.fixture
def kids(klass):
    return [_kid(klass, f"طالبٌ رقم {i}", f"2900000{i:04d}") for i in range(3)]


class TestCountsOnlyMyStudentsToday:
    def test_totals_and_still_out(self, school, session, teacher, kids):
        a, b, _c = kids
        leave(session, a, "clinic", by=teacher, now=at(7, 15))
        come_back(session, a, now=at(7, 25))
        leave(session, b, "restroom", by=teacher, now=at(7, 30))  # لم يعد؛ والثالث لم يخرج.

        ctx = _my_students_ctx(teacher, school, SUNDAY, _today_sessions(teacher))

        assert ctx["exit_total"] == 2, "خروجان اليوم: الطبّيّ يُعدّ مع الباقي (بإذن لا مخالفة)"
        assert ctx["out_now"] == 1, "الثاني وحدَه لم يعد"

    def test_another_teachers_section_is_not_mine(
        self, school, year, session, teacher, other_teacher, kids, band
    ):
        other_klass = ClassGroupFactory(
            school=school, grade="G8", section="2", level_type="prep", academic_year=year
        )
        stranger = _kid(other_klass, "طالبٌ غريب", "29000009999")
        theirs = Session.objects.create(
            school=school,
            class_group=other_klass,
            teacher=other_teacher,
            date=SUNDAY,
            start_time=dt.time(8, 0),
            end_time=dt.time(8, 45),
            status="scheduled",
        )
        leave(theirs, stranger, "restroom", by=other_teacher, now=at(8, 10))

        mine = _my_students_ctx(teacher, school, SUNDAY, _today_sessions(teacher))
        theirs_ctx = _my_students_ctx(other_teacher, school, SUNDAY, _today_sessions(other_teacher))

        assert (mine["exit_total"], mine["out_now"]) == (0, 0)
        assert (theirs_ctx["exit_total"], theirs_ctx["out_now"]) == (1, 1)

    def test_yesterdays_open_exit_is_not_out_now(self, school, session, teacher, kids):
        ClassExit.objects.create(
            school=school,
            session=session,
            student=kids[0],
            destination="restroom",
            left_at=at(7, 20, day=SATURDAY),
        )

        ctx = _my_students_ctx(teacher, school, SUNDAY, _today_sessions(teacher))

        assert (ctx["exit_total"], ctx["out_now"]) == (0, 0)

    def test_a_student_out_twice_in_the_day_is_counted_once_as_out(
        self, school, session, teacher, kids
    ):
        leave(session, kids[0], "restroom", by=teacher, now=at(7, 15))
        come_back(session, kids[0], now=at(7, 20))
        leave(session, kids[0], "clinic", by=teacher, now=at(7, 40))

        ctx = _my_students_ctx(teacher, school, SUNDAY, _today_sessions(teacher))

        assert ctx["exit_total"] == 2, "مرّتان"
        assert ctx["out_now"] == 1, "طالبٌ واحدٌ خارجٌ الآن"

    def test_a_day_without_sessions_is_zero_not_missing(self, school, teacher, bells):
        ctx = _my_students_ctx(teacher, school, SUNDAY, [])

        assert (ctx["exit_total"], ctx["out_now"]) == (0, 0)


class TestNoNamesAndFlatShape:
    def test_only_counts_no_name_no_identity_no_ranking(self, school, session, teacher, kids):
        leave(session, kids[0], "clinic", by=teacher, now=at(7, 15))

        ctx = _my_students_ctx(teacher, school, SUNDAY, _today_sessions(teacher))

        assert set(ctx) == KEYS, "لا تفصيلَ بالوجهة ولا بالطالب ولا ترتيب"
        assert all(isinstance(v, int) for v in ctx.values())
        blob = json.dumps(ctx, ensure_ascii=False)
        for student in kids:
            assert student.full_name not in blob and student.national_id not in blob

    def test_the_teacher_context_carries_one_new_key_and_keeps_the_old(
        self, school, session, teacher, kids
    ):
        ctx = get_teacher_ctx(teacher, school, SUNDAY, "teacher")

        assert set(ctx["my_students"]) == KEYS
        for old in (
            "view_type",
            "sessions",
            "next_session",
            "my_setups",
            "my_pending_swaps",
            "my_weekly_schedule_url",
            "general_schedule_url",
        ):
            assert old in ctx


class TestConstantQueries:
    def _measure(self, school, teacher):
        fresh = CustomUser.objects.get(pk=teacher.pk)  # بلا ذاكرةٍ مخبوءةٍ من القياس السابق
        sessions = _today_sessions(fresh)
        with CaptureQueriesContext(connection) as queries:
            _my_students_ctx(fresh, school, SUNDAY, sessions)
        return len(queries)

    def test_one_section_and_ten_sections_cost_the_same(
        self, school, year, band, klass, session, teacher, kids
    ):
        one = self._measure(school, teacher)

        for n in range(10):
            group = ClassGroupFactory(
                school=school, grade="G9", section=f"s{n}", level_type="prep", academic_year=year
            )
            for i in range(30):
                _kid(group, f"طالب {n}-{i}", f"291{n:02d}{i:06d}")
            Session.objects.create(
                school=school,
                class_group=group,
                teacher=teacher,
                date=SUNDAY,
                start_time=dt.time(9 + n, 0),
                end_time=dt.time(9 + n, 45),
                status="scheduled",
            )
        ten = self._measure(school, teacher)

        assert ten == one, f"الاستعلامات تتبع عددَ الشعب: {one} ← {ten}"
        assert ten <= 4, f"أكثر من القدرة + استعلامَي الخروج: {ten}"


class TestCapabilityGuardsTheSharedCounter:
    def test_teacher_and_coordinator_see_the_counts(self, school, session, teacher, kids):
        leave(session, kids[0], "restroom", by=teacher, now=at(7, 15))
        coordinator = _staff(school, "coordinator", "منسّق", "29000001030")
        Session.objects.filter(pk=session.pk).update(teacher=coordinator)

        seen = _my_students_ctx(coordinator, school, SUNDAY, _today_sessions(coordinator))

        assert seen["exit_total"] == 1 and seen["out_now"] == 1

    def test_a_role_without_the_capability_gets_no_counts(self, school, session, teacher, kids):
        leave(session, kids[0], "restroom", by=teacher, now=at(7, 15))
        assistant = _staff(school, "librarian", "أمين مكتبة", "29000001031")

        ctx = _my_students_ctx(assistant, school, SUNDAY, _today_sessions(teacher))

        assert ctx == {"exit_total": None, "out_now": None}
