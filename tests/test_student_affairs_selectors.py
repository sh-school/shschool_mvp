"""[LAYERING] قراءاتُ شؤون الطلاب — كلُّ selector يُختبر بلا طلبٍ ولا قالب.

نُقلت هذه الاستعلاماتُ من `student_affairs/views.py` (2026-09-14، سقّاطةُ الطبقات
`tests/layering_ratchet.py`). والعرضُ يُختبر بصفحته في اختباراتٍ أخرى؛ وهنا
الدالّةُ وحدها: مدرسةٌ ويومٌ وسجلّاتٌ معروفة، وما يُرجَع بأعداده.
"""

from __future__ import annotations

from datetime import date, time, timedelta
from types import SimpleNamespace

import pytest
from django.utils import timezone

from behavior.models import BehaviorInfraction, ViolationCategory
from core.models import ParentStudentLink, StudentEnrollment
from core.models.audit import AuditLog
from operations.models import AbsenceAlert, Session, StudentAttendance, Subject
from student_affairs import selectors
from student_affairs.models import StudentActivity, StudentTransfer
from student_affairs.services import TardinessService
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

YEAR = "2026-2027"


def _session(world, class_group, day, hour=7):
    return Session.objects.create(
        school=world.school,
        class_group=class_group,
        teacher=world.teacher,
        subject=world.subject,
        date=day,
        start_time=time(hour, 0),
        end_time=time(hour, 45),
        status="scheduled",
    )


def _infraction(world, student, days_ago=0, **fields):
    """`date` حقلُ `auto_now_add`: يُكتب اليومُ عند الإنشاء أيّاً كان المُمرَّر — فيُنقل بعده."""
    infraction = BehaviorInfractionFactory(school=world.school, student=student, **fields)
    if days_ago:
        BehaviorInfraction.objects.filter(pk=infraction.pk).update(
            date=world.today - timedelta(days=days_ago)
        )
        infraction.refresh_from_db()
    return infraction


def _mark(world, session, student, status):
    return StudentAttendance.objects.create(
        session=session, student=student, school=world.school, status=status, excuse_type=""
    )


@pytest.fixture
def world(db):
    """مدرسةٌ بشعبتين وأربعة طلبة (ثلاثةٌ مقيَّدون) ومدرسةٌ أخرى لا يتسرّب منها شيء."""
    school = SchoolFactory()
    other = SchoolFactory()
    teacher = UserFactory(full_name="المعلم")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    role = RoleFactory(school=school, name="student")
    g7 = ClassGroupFactory(
        school=school, grade="G7", section="1", academic_year=YEAR, level_type="prep"
    )
    g10 = ClassGroupFactory(
        school=school, grade="G10", section="2", academic_year=YEAR, level_type="sec"
    )
    students = []
    for name, group in (("سعد", g7), ("أحمد", g7), ("بدر", g10), ("خالد", None)):
        user = UserFactory(full_name=name)
        MembershipFactory(user=user, school=school, role=role)
        if group:
            StudentEnrollment.objects.create(student=user, class_group=group, is_active=True)
        students.append(user)
    outsider = UserFactory(full_name="غريب")
    MembershipFactory(user=outsider, school=other, role=RoleFactory(school=other, name="student"))
    return SimpleNamespace(
        school=school,
        other=other,
        teacher=teacher,
        g7=g7,
        g10=g10,
        students=students,
        outsider=outsider,
        subject=Subject.objects.create(school=school, name_ar="العلوم", code="SCI"),
        today=timezone.localdate(),
    )


# ─── سجلّ الطلاب ───────────────────────────────────────────────────────────


def test_student_memberships_are_the_schools_active_students(world):
    assert {m.user for m in selectors.student_memberships(world.school)} == set(world.students)


def test_register_defaults_to_the_enrolled_and_annotates_class_and_guardian(world):
    parent = UserFactory(full_name="وليّ سعد", phone="55501")
    ParentStudentLink.objects.create(
        parent=parent, student=world.students[0], school=world.school, relationship="mother"
    )
    rows = {m.user.full_name: m for m in selectors.student_register(world.school, YEAR)}

    assert set(rows) == {"سعد", "أحمد", "بدر"}
    assert (rows["بدر"].grade_code, rows["بدر"].section_code, rows["بدر"].grade_key) == (
        "G10",
        "2",
        "10",
    )
    assert (rows["سعد"].guardian_name, rows["سعد"].guardian_relation) == ("وليّ سعد", "mother")


def test_register_filters_status_grade_parent_and_search(world):
    names = lambda qs: {m.user.full_name for m in qs}  # noqa: E731
    ParentStudentLink.objects.create(
        parent=UserFactory(), student=world.students[1], school=world.school
    )

    assert names(selectors.student_register(world.school, YEAR, status="unenrolled")) == {"خالد"}
    assert len(names(selectors.student_register(world.school, YEAR, status="all"))) == 4
    assert names(selectors.student_register(world.school, YEAR, grade="G7")) == {"سعد", "أحمد"}
    assert names(selectors.student_register(world.school, YEAR, section="2")) == {"بدر"}
    assert names(selectors.student_register(world.school, YEAR, parent_status="linked")) == {"أحمد"}
    assert names(selectors.student_register(world.school, YEAR, parent_status="unlinked")) == {
        "سعد",
        "بدر",
    }
    assert names(selectors.student_register(world.school, YEAR, q="G10")) == {"بدر"}


def test_guardian_relation_labels_come_from_the_model():
    assert selectors.guardian_relation_labels()["mother"] == "الأم"


def test_register_filter_options_order_grades_numerically(world):
    grades, sections = selectors.register_filter_options(world.school, YEAR)
    assert grades == ["G7", "G10"]
    assert list(sections) == ["1", "2"]


def test_students_for_export_pairs_each_member_with_its_enrolment(world):
    rows = selectors.students_for_export(world.school, YEAR, grade="G7")
    assert {(m.user.full_name, e["class_group__section"]) for m, e in rows} == {
        ("أحمد", "1"),
        ("سعد", "1"),
    }
    everyone = {m.user.full_name: e for m, e in selectors.students_for_export(world.school, YEAR)}
    assert everyone["خالد"] == {}


# ─── ملفّ الطالب ───────────────────────────────────────────────────────────


def test_current_enrolment_is_this_years_active_one(world):
    assert selectors.current_enrolment(world.students[0], YEAR).class_group == world.g7
    assert selectors.current_enrolment(world.students[3], YEAR) is None


def test_guardian_links_stay_inside_the_school(world):
    parent = UserFactory()
    ParentStudentLink.objects.create(parent=parent, student=world.students[0], school=world.school)
    ParentStudentLink.objects.create(
        parent=UserFactory(), student=world.students[0], school=world.other
    )
    assert [link.parent for link in selectors.guardian_links(world.students[0], world.school)] == [
        parent
    ]


def test_annual_results_are_empty_for_a_student_without_results(world):
    assert list(selectors.annual_results(world.students[0], world.school, YEAR)) == []


def test_recent_activities_are_newest_first_and_capped(world):
    for offset in range(3):
        StudentActivity.objects.create(
            school=world.school,
            student=world.students[0],
            activity_type="certificate",
            title=f"نشاط {offset}",
            date=world.today - timedelta(days=offset),
        )
    titles = [
        a.title for a in selectors.recent_activities(world.students[0], world.school, limit=2)
    ]
    assert titles == ["نشاط 0", "نشاط 1"]


def test_student_infractions_are_newest_first(world):
    old = _infraction(world, world.students[0], days_ago=5)
    new = _infraction(world, world.students[0])
    assert list(selectors.student_infractions(world.students[0], world.school)) == [new, old]


def test_profile_records_count_attendance_in_the_academic_year_and_infractions_by_level(
    world, monkeypatch
):
    monkeypatch.setattr(
        selectors,
        "academic_year_window",
        lambda school: (world.today - timedelta(days=10), world.today),
    )
    student = world.students[0]
    for offset, status in ((0, "present"), (1, "present"), (2, "absent"), (30, "absent")):
        _mark(
            world, _session(world, world.g7, world.today - timedelta(days=offset)), student, status
        )
    BehaviorInfractionFactory(school=world.school, student=student, level=2)
    StudentTransfer.objects.create(
        school=world.school,
        student=student,
        direction="in",
        other_school_name="أخرى",
        academic_year=YEAR,
        transfer_date=world.today,
    )

    records = selectors.student_profile_records(student, world.school, YEAR)

    assert records["attendance"] == {
        "present": 2,
        "absent": 1,
        "late": 0,
        "excused": 0,
        "total": 3,
        "pct": 66.7,
    }
    assert records["behavior"]["total"] == 1
    assert records["behavior"]["by_level"] == {1: 0, 2: 1, 3: 0, 4: 0}
    assert records["enrollment"].class_group == world.g7
    assert len(records["transfers"]) == 1
    assert records["grades_summary"] == {"total_subjects": 0, "passed": 0, "failed": 0}
    assert records["health_record"] is None


def test_profile_pdf_records_cover_the_last_thirty_days(world):
    student = world.students[0]
    for offset, status in ((0, "late"), (29, "present"), (31, "absent")):
        _mark(
            world, _session(world, world.g7, world.today - timedelta(days=offset)), student, status
        )

    records = selectors.student_profile_pdf_records(student, world.school, YEAR, world.today)

    assert records["att_summary"] == {"total": 2, "present": 1, "absent": 0, "late": 1}
    assert len(records["attendance"]) == 2


# ─── الحضور والغياب ────────────────────────────────────────────────────────


def _attendance_day(world, day, statuses):
    session = _session(world, world.g7, day)
    for student, status in zip(world.students, statuses, strict=False):
        _mark(world, session, student, status)


def test_attendance_counts_on_a_day(world):
    _attendance_day(world, world.today, ["present", "absent", "late", "excused"])
    _attendance_day(world, world.today - timedelta(days=1), ["absent"])
    assert selectors.attendance_counts_on(world.school, world.today) == {
        "total": 4,
        "present": 1,
        "absent": 1,
        "late": 1,
        "excused": 1,
    }


def test_absence_ranking_since_a_date(world):
    for offset in (0, 1, 40):
        _attendance_day(
            world, world.today - timedelta(days=offset), ["absent", "present", "absent"]
        )
    _attendance_day(world, world.today - timedelta(days=2), ["absent"])
    ranking = list(
        selectors.absence_ranking(
            world.school, world.today - timedelta(days=30), "student__full_name"
        )
    )
    assert ranking[0] == {"student__full_name": "سعد", "absence_count": 3}
    assert ranking[1] == {"student__full_name": "بدر", "absence_count": 2}


def test_attendance_by_grade_on_a_day(world):
    _attendance_day(world, world.today, ["present", "absent"])
    _mark(world, _session(world, world.g10, world.today, hour=8), world.students[2], "late")
    rows = list(selectors.attendance_by_grade_on(world.school, world.today))
    assert [(r["session__class_group__grade"], r["total"], r["late_count"]) for r in rows] == [
        ("G7", 2, 0),
        ("G10", 1, 1),
    ]


def test_daily_trend_fills_missing_days_with_zero(world):
    _attendance_day(world, world.today, ["present", "absent", "present", "present"])
    trend = selectors.daily_attendance_trend(world.school, world.today, days=3)
    assert len(trend.labels) == 3
    assert trend.present == [0, 0, 75]
    assert trend.absent == [0, 0, 25]


def test_pending_absence_alerts_are_highest_first(world):
    for count, status in ((4, "pending"), (9, "pending"), (20, "resolved")):
        AbsenceAlert.objects.create(
            school=world.school,
            student=world.students[0],
            absence_count=count,
            period_start=world.today,
            period_end=world.today,
            status=status,
        )
    assert [a.absence_count for a in selectors.pending_absence_alerts(world.school)] == [9, 4]


def test_attendance_on_by_class_orders_grade_then_name(world):
    _mark(world, _session(world, world.g10, world.today, hour=8), world.students[2], "present")
    _attendance_day(world, world.today, ["present", "absent"])
    rows = list(selectors.attendance_on_by_class(world.school, world.today))
    assert [r.session.class_group.grade for r in rows] == ["G7", "G7", "G10"]


# ─── السلوك ────────────────────────────────────────────────────────────────


def test_behaviour_window_falls_back_to_the_calendar_year(world, monkeypatch):
    monkeypatch.setattr(selectors, "academic_year_window", lambda school: None)
    assert selectors.behaviour_window(world.school, date(2026, 9, 14)) == (
        date(2026, 1, 1),
        date(2026, 12, 31),
    )


def test_behaviour_year_summary(world, monkeypatch):
    monkeypatch.setattr(
        selectors,
        "academic_year_window",
        lambda school: (world.today - timedelta(days=30), world.today),
    )
    degree_2 = ViolationCategory.objects.create(code="TST2", name_ar="مخالفة", degree=2)
    BehaviorInfractionFactory(
        school=world.school, student=world.students[0], violation_category=degree_2
    )
    BehaviorInfractionFactory(school=world.school, student=world.students[0], is_resolved=True)
    BehaviorInfractionFactory(school=world.school, student=world.students[1])
    _infraction(world, world.students[2], days_ago=90)

    summary = selectors.behaviour_year_summary(world.school, world.today)

    assert summary["total_infractions"] == 3
    assert summary["unresolved"] == 2
    assert (summary["students_with_infractions"], summary["total_students"]) == (2, 4)
    assert summary["infraction_pct"] == 50
    assert summary["degree_counts"] == [(2, 1)]
    assert list(summary["worst_students"])[0]["infraction_count"] == 2


def test_monthly_infraction_trend_ends_with_this_month(world):
    _infraction(world, world.students[0])
    labels, counts = selectors.monthly_infraction_trend(world.school, world.today, months=3)
    assert len(labels) == 3
    assert counts[-1] == 1


def test_infraction_counts_by_student(world):
    for _ in range(2):
        BehaviorInfractionFactory(school=world.school, student=world.students[1])
    BehaviorInfractionFactory(school=world.other, student=world.outsider)
    assert list(
        selectors.infraction_counts_by_student(world.school).values_list("count", flat=True)
    ) == [2]


# ─── التأخّر الصباحي ───────────────────────────────────────────────────────


@pytest.fixture
def late_world(world):
    _attendance_day(world, world.today, ["late", "late", "present", "present"])
    _mark(world, _session(world, world.g10, world.today, hour=8), world.students[2], "late")
    _attendance_day(world, world.today - timedelta(days=1), ["late"])
    return world


def test_late_arrivals_filter_by_day_grade_and_section(late_world):
    w = late_world
    assert selectors.late_arrivals(w.school, w.today).count() == 3
    assert selectors.late_arrivals(w.school, w.today, grade="G10").count() == 1
    assert selectors.late_arrivals(w.school, w.today, section="1").count() == 2


def test_late_register_orders_grade_section_then_name(late_world):
    w = late_world
    rows = list(selectors.late_register(selectors.late_arrivals(w.school, w.today)))
    assert [r.session.class_group.grade for r in rows] == ["G7", "G7", "G10"]


def test_cumulative_late_counts_for_the_year(late_world):
    w = late_world
    counts = selectors.cumulative_late_counts(w.school, YEAR)
    assert counts[w.students[0].pk] == 2
    assert counts[w.students[2].pk] == 1


def test_students_marked_on_counts_each_student_once(late_world):
    assert selectors.students_marked_on(late_world.school, late_world.today) == 4


def test_late_this_week_starts_on_monday(world):
    monday = world.today - timedelta(days=world.today.weekday())
    _attendance_day(world, monday, ["late"])
    _attendance_day(world, monday - timedelta(days=1), ["late"])
    assert selectors.late_this_week(world.school, monday + timedelta(days=2)) == 1


def test_late_by_class_and_by_stage(late_world):
    w = late_world
    late = selectors.late_arrivals(w.school, w.today)
    assert [
        (r["session__class_group__grade"], r["count"]) for r in selectors.late_by_class(late)
    ] == [
        ("G7", 2),
        ("G10", 1),
    ]
    assert selectors.late_by_stage(late) == [
        {"stage_label": "إعدادي", "count": 2},
        {"stage_label": "ثانوي", "count": 1},
    ]


def test_tardiness_session_prefers_the_students_own_class(world):
    own = _session(world, world.g10, world.today, hour=9)
    first = _session(world, world.g7, world.today, hour=7)
    assert selectors.tardiness_session(world.school, world.students[2], world.today) == own
    assert selectors.tardiness_session(world.school, world.students[3], world.today) == first
    assert (
        selectors.tardiness_session(
            world.school, world.students[3], world.today + timedelta(days=1)
        )
        is None
    )


# ─── الكتابة: TardinessService ─────────────────────────────────────────────


def test_record_morning_tardiness_writes_attendance_and_audit(world):
    _session(world, world.g7, world.today)
    now = timezone.localtime()
    attendance = TardinessService.record_morning_tardiness(
        school=world.school,
        student=world.students[0],
        minutes=10,
        excuse_file=None,
        marked_by=world.teacher,
        now=now,
    )
    assert (attendance.status, attendance.tardiness_minutes, attendance.excuse_notes) == (
        "late",
        10,
        "إذن تأخير 10 دقيقة",
    )
    assert AuditLog.objects.filter(object_id=str(attendance.pk), action="create").count() == 1

    again = TardinessService.record_morning_tardiness(
        school=world.school,
        student=world.students[0],
        minutes=None,
        excuse_file=None,
        marked_by=world.teacher,
        now=now,
    )
    assert again.pk == attendance.pk and again.excuse_notes == ""


def test_record_morning_tardiness_without_a_session_writes_nothing(world):
    result = TardinessService.record_morning_tardiness(
        school=world.school,
        student=world.students[0],
        minutes=5,
        excuse_file=None,
        marked_by=world.teacher,
        now=timezone.localtime(),
    )
    assert result is None
    assert not StudentAttendance.objects.exists()
