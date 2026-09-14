"""[LAYERING] قراءاتُ لوحة التحكم ولوحة الإحصاءات والعمليّات — كلُّ selector بلا طلبٍ ولا قالب.

نُقلت من `core/views_dashboard.py` و`analytics/views.py` (2026-09-14، سقّاطةُ الطبقات
`tests/layering_ratchet.py`): `operations/selectors.py` لما تشترك فيه اللوحاتُ وشؤونُ
الطلبة، و`core/dashboard_selectors.py` لبقيّة عدّادات اللوحة، و`analytics/selectors.py`
لمؤشّرات المدير. وسياقُ اللوحة لكلّ دورٍ في `tests/test_dashboard_roles.py`.
"""

from __future__ import annotations

from datetime import time, timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from analytics import selectors as analytics_selectors
from core import dashboard_selectors
from core.models import StudentEnrollment
from operations import selectors as operations_selectors
from operations.models import (
    AbsenceAlert,
    Session,
    StudentAttendance,
    Subject,
    TeacherAbsence,
)
from tests.conftest import (
    BehaviorInfractionFactory,
    BookBorrowingFactory,
    ClassGroupFactory,
    ClinicVisitFactory,
    LibraryBookFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def world(db):
    school = SchoolFactory()
    teacher = UserFactory(full_name="المعلم")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    group = ClassGroupFactory(school=school, grade="G7", section="1", academic_year="2026-2027")
    students = []
    for name in ("سعد", "بدر", "خالد"):
        user = UserFactory(full_name=name)
        MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
        StudentEnrollment.objects.create(student=user, class_group=group, is_active=True)
        students.append(user)
    return SimpleNamespace(
        school=school,
        other=SchoolFactory(),
        teacher=teacher,
        group=group,
        students=students,
        subject=Subject.objects.create(school=school, name_ar="العلوم", code="SCI"),
        today=timezone.localdate(),
    )


def _session(w, day, hour=7, status="scheduled", teacher=None):
    return Session.objects.create(
        school=w.school,
        class_group=w.group,
        teacher=teacher or w.teacher,
        subject=w.subject,
        date=day,
        start_time=time(hour, 0),
        end_time=time(hour, 45),
        status=status,
    )


def _day(w, day, statuses, hour=7):
    session = _session(w, day, hour)
    for student, status in zip(w.students, statuses, strict=False):
        StudentAttendance.objects.create(
            session=session, student=student, school=w.school, status=status, excuse_type=""
        )
    return session


# ─── operations/selectors.py ──────────────────────────────────────────────


def test_attendance_status_counts_filters_and_counts_every_status(world):
    _day(world, world.today, ["present", "absent", "excused"])
    _day(world, world.today - timedelta(days=1), ["late"])
    counts = operations_selectors.attendance_status_counts(world.school, session__date=world.today)
    assert counts == {"total": 3, "present": 1, "absent": 1, "late": 0, "excused": 1}
    assert (
        operations_selectors.attendance_status_counts(world.school, student=world.students[0])[
            "total"
        ]
        == 2
    )


def test_pending_absence_alerts_order_and_limit(world):
    for count, status in ((4, "pending"), (9, "pending"), (20, "resolved")):
        AbsenceAlert.objects.create(
            school=world.school,
            student=world.students[0],
            absence_count=count,
            period_start=world.today,
            period_end=world.today,
            status=status,
        )
    assert [a.absence_count for a in operations_selectors.pending_absence_alerts(world.school)] == [
        9,
        4,
    ]
    newest = operations_selectors.pending_absence_alerts(world.school, order="-created_at", limit=1)
    assert [a.absence_count for a in newest] == [9]


def test_teacher_sessions_on_and_between(world):
    later = _session(world, world.today, hour=9)
    first = _session(world, world.today, hour=7)
    _session(world, world.today - timedelta(days=3))
    assert list(
        operations_selectors.teacher_sessions_on(world.school, world.teacher, world.today)
    ) == [first, later]
    between = operations_selectors.teacher_sessions_between(
        world.school, world.teacher, world.today - timedelta(days=1), world.today
    )
    assert between.count() == 2


def test_teacher_absence_count_is_scoped_to_school_and_day(world):
    TeacherAbsence.objects.create(school=world.school, teacher=world.teacher, date=world.today)
    assert operations_selectors.teacher_absence_count(world.school, world.today) == 1
    assert (
        operations_selectors.teacher_absence_count(world.school, world.today - timedelta(days=1))
        == 0
    )
    assert operations_selectors.teacher_absence_count(world.other, world.today) == 0


def test_swap_and_compensatory_counts_start_at_zero(world):
    """بلا طلبٍ لا عدد — وإنشاءُ طلب تبديلٍ حقيقيٍّ يحتاج خانتَي جدولٍ ومنسّقَين (`tests/test_temporary_swap.py`)."""
    assert operations_selectors.swap_count(world.school, "pending_b", "accepted_b") == 0
    assert operations_selectors.swap_count(world.school, "pending_b", teacher_b=world.teacher) == 0
    assert operations_selectors.pending_compensatory_count(world.school) == 0


def test_session_status_counts(world):
    _session(world, world.today, hour=7, status="completed")
    _session(world, world.today, hour=8, status="in_progress")
    _session(world, world.today, hour=9)
    assert operations_selectors.session_status_counts(world.school, world.today) == {
        "total": 3,
        "completed": 1,
        "in_progress": 1,
    }


def test_chronic_absentee_count(world):
    for offset in range(3):
        _day(
            world,
            world.today - timedelta(days=offset),
            ["absent", "absent", "present"],
            hour=7 + offset,
        )
    _day(world, world.today - timedelta(days=40), ["present", "absent"])
    since = world.today - timedelta(days=10)
    assert operations_selectors.chronic_absentee_count(world.school, since, min_days=3) == 2
    assert operations_selectors.chronic_absentee_count(world.school, since, min_days=4) == 0


def test_class_sessions_on(world):
    session = _session(world, world.today)
    _session(world, world.today + timedelta(days=1))
    assert list(operations_selectors.class_sessions_on(world.school, world.group, world.today)) == [
        session
    ]


# ─── core/dashboard_selectors.py ──────────────────────────────────────────


def test_annual_result_counts_are_zero_without_results(world):
    assert dashboard_selectors.annual_result_counts(world.school, "2026-2027") == {
        "total": 0,
        "passed": 0,
        "failed": 0,
    }
    assert dashboard_selectors.failing_student_count(world.school, "2026-2027") == 0
    assert dashboard_selectors.incomplete_setup_count(world.school, "2026-2027") == 0
    assert list(dashboard_selectors.teacher_setups(world.school, world.teacher, "2026-2027")) == []


def test_behaviour_counts(world):
    for level in (1, 3, 4):
        BehaviorInfractionFactory(school=world.school, student=world.students[0], level=level)
    BehaviorInfractionFactory(school=world.other, student=world.students[1], level=4)
    assert dashboard_selectors.behaviour_month_and_critical(world.school, world.today) == {
        "behavior_monthly": 3,
        "behavior_critical": 2,
    }
    assert (
        dashboard_selectors.infractions_since_count(world.school, world.today.replace(day=1)) == 3
    )
    assert dashboard_selectors.critical_infraction_count(world.school) == 2


def test_clinic_counts_on(world):
    """`visit_date__date` يُحسب بتوقيت المدرسة: يومُ الزيارة بتوقيتها لا بـUTC — كُتب أوّلاً
    بـ`visit_date.date()` فسقط بعد منتصف الليل بتوقيت قطر."""
    visit = ClinicVisitFactory(school=world.school, student=world.students[0], is_sent_home=True)
    day = timezone.localtime(visit.visit_date).date()
    counts = dashboard_selectors.clinic_counts_on(world.school, day)
    assert counts["clinic_today"] == 1 and counts["clinic_sent_home"] == 1
    assert dashboard_selectors.clinic_counts_on(world.school, day + timedelta(days=5)) == {
        "clinic_today": 0,
        "clinic_sent_home": 0,
    }


def test_loan_count_filters_by_status(world):
    book = LibraryBookFactory(school=world.school)
    book.available_qty = 2
    book.save()
    BookBorrowingFactory(book=book, user=world.students[0], status="OVERDUE")
    assert dashboard_selectors.loan_count(world.school, status="OVERDUE") == 1
    assert dashboard_selectors.loan_count(world.school, status="BORROWED") == 0


def test_school_user_count_counts_each_account_once(world):
    world.students[2].is_active = False
    world.students[2].save(update_fields=["is_active"])
    assert dashboard_selectors.school_user_count(world.school, active_only=False) == 4
    assert dashboard_selectors.school_user_count(world.school, active_only=True) == 3


# ─── analytics/selectors.py ───────────────────────────────────────────────


def test_school_overview_kpis(world):
    _day(world, world.today, ["present", "absent", "present"])
    BehaviorInfractionFactory(school=world.school, student=world.students[0], level=3)
    kpis = analytics_selectors.school_overview_kpis(world.school, "2026-2027", world.today)
    assert kpis["total_students"] == 3
    assert kpis["total_teachers"] == 1
    assert (kpis["present_today"], kpis["att_pct_today"]) == (2, 67)
    assert (kpis["behavior_month"], kpis["critical_issues"]) == (1, 1)
    assert (kpis["plan_pct"], kpis["total_procs"]) == (0, 0)
    assert set(kpis) == {
        "total_students",
        "total_teachers",
        "att_pct_today",
        "present_today",
        "clinic_today",
        "chronic_cases",
        "behavior_month",
        "critical_issues",
        "total_buses",
        "bus_students",
        "library_books",
        "active_loans",
        "overdue_books",
        "plan_pct",
        "completed_procs",
        "total_procs",
    }
