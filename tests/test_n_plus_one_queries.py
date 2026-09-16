"""استعلاماتُ N+1 السبعُ من تدقيق المعماريّة — عددُ الاستعلامات لا يتبع عددَ الصفوف.

الطريقةُ في كلّ صفحة: طلبُ إحماءٍ أوّلاً (يُشبع ما يُحمَّل كسولاً مرّةً)، ثمّ
عدُّ الاستعلامات والصفحةُ تحمل صفّاً واحداً، ثمّ ثلاثةً — والعددان يجب أن
يتساويا. فما كان استعلاماً لكلّ صفٍّ يظهر فرقاً، وما صار `annotate`/`prefetch`
لا يظهر. وحيث كان الاستعلامُ ثابتاً لكنّه ثقيلاً (42 لرسم أربعةَ عشرَ يوماً،
أو جلبُ كلّ الدرجات لعدّها) يُعدّ ما يمسّ الجدولَ نفسَه.

كلُّ اختبارٍ هنا **سقط قبل الإصلاح** (2026-09-14) بالأرقام المذكورة في تعليقه.
"""

from __future__ import annotations

import json
from datetime import time, timedelta
from decimal import Decimal

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from assessments.models import (
    Assessment,
    AssessmentPackage,
    StudentAssessmentGrade,
    SubjectClassSetup,
)
from core.models import ParentStudentLink, StudentEnrollment
from operations.models import Session, StudentAttendance, Subject
from quality.models import ProcedureEvidence, QualityCommitteeMember
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolBusFactory,
    UserFactory,
)
from tests.test_views_quality2 import make_admin, make_domain, make_procedure, make_teacher
from transport.models import BusRoute

pytestmark = pytest.mark.django_db


def queries_for(client, url) -> list[str]:
    """جملُ SQL التي أطلقها طلبٌ واحد — والصفحةُ يجب أن تُفتح (200)."""
    with CaptureQueriesContext(connection) as ctx:
        response = client.get(url)
    assert response.status_code == 200, response.status_code
    return [q["sql"] for q in ctx.captured_queries]


def assert_flat(client, url, add_rows, *, before_note: str):
    """عددُ استعلامات الصفحة بصفٍّ واحد يساويه بثلاثة."""
    client.get(url)  # إحماء
    with_one = queries_for(client, url)
    add_rows(2)
    with_three = queries_for(client, url)
    assert len(with_three) == len(with_one), (
        f"{before_note}: صفٌّ واحد {len(with_one)} استعلاماً، ثلاثةٌ {len(with_three)} —\n"
        + "\n".join(
            sql for sql in with_three if sql not in with_one and "django_session" not in sql
        )
    )


def _student(school, name="طالب"):
    role = RoleFactory(school=school, name="student")
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=role)
    return user


# ══════════════════════════════════════════════════════════════════════
#  1. parents/views.py:parent_behavior — ثلاثةُ استعلاماتٍ لكلّ ابن
# ══════════════════════════════════════════════════════════════════════


def test_parent_behavior_is_flat(client, school, teacher_user):
    """كان: 3 × الأبناء (القائمة، العدُّ، غيرُ المحلول). صار: استعلامان للكلّ."""
    role = RoleFactory(school=school, name="parent")
    parent = UserFactory(full_name="وليّ أمر")
    parent.consent_given_at = timezone.now()
    parent.save(update_fields=["consent_given_at"])
    MembershipFactory(user=parent, school=school, role=role)

    def add_children(n):
        for i in range(n):
            child = _student(school, f"ابن {i}")
            ParentStudentLink.objects.create(
                parent=parent, student=child, school=school, can_view_behavior=True
            )
            for j in range(3):
                BehaviorInfractionFactory(
                    school=school, student=child, reported_by=teacher_user, is_resolved=j == 0
                )

    add_children(1)
    client.force_login(parent)
    assert_flat(client, reverse("parent_behavior"), add_children, before_note="سلوك الأبناء")


def test_parent_behavior_numbers_still_right(client, school, teacher_user):
    role = RoleFactory(school=school, name="parent")
    parent = UserFactory(full_name="وليّ أمر")
    parent.consent_given_at = timezone.now()
    parent.save(update_fields=["consent_given_at"])
    MembershipFactory(user=parent, school=school, role=role)
    child = _student(school)
    ParentStudentLink.objects.create(parent=parent, student=child, school=school)
    for j in range(12):
        BehaviorInfractionFactory(
            school=school, student=child, reported_by=teacher_user, is_resolved=j < 4
        )
    client.force_login(parent)
    row = client.get(reverse("parent_behavior")).context["children_behavior"][0]
    assert row["total_infractions"] == 12
    assert row["unresolved"] == 8
    assert len(row["infractions"]) == 10
    assert row["unresolved_tone"] == "amber"


# ══════════════════════════════════════════════════════════════════════
#  2. student_affairs/views.py:attendance_overview — 42 استعلاماً للرسم
# ══════════════════════════════════════════════════════════════════════


def _attendance_day(school, class_group, teacher, students, day, statuses):
    session = Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher,
        date=day,
        start_time=time(7, 10),
        end_time=time(7, 55),
    )
    for student, status in zip(students, statuses, strict=True):
        StudentAttendance.objects.create(
            session=session, student=student, school=school, status=status
        )


def test_attendance_overview_chart_is_one_query(client, school, principal_user, teacher_user):
    """كان: 3 استعلاماتٍ × 14 يوماً + 5 لملخّص اليوم = 49 على جدول الحضور. صار ≤ 4."""
    class_group = ClassGroupFactory(school=school)
    students = [_student(school, f"طالب {i}") for i in range(4)]
    today = timezone.localdate()
    _attendance_day(
        school, class_group, teacher_user, students, today, ["present"] * 3 + ["absent"]
    )
    _attendance_day(
        school,
        class_group,
        teacher_user,
        students,
        today - timedelta(days=3),
        ["present", "absent", "late", "excused"],
    )
    client.force_login(principal_user)
    url = reverse("student_affairs:attendance_overview")
    client.get(url)
    queries = queries_for(client, url)
    on_attendance = [q for q in queries if "operations_studentattendance" in q]
    assert len(on_attendance) <= 4, f"{len(on_attendance)} استعلاماً على جدول الحضور"

    response = client.get(url)
    assert response.context["summary"] == {
        "present": 3,
        "absent": 1,
        "late": 0,
        "excused": 0,
        "total": 4,
        "pct": 75,
    }
    present = response.context["chart_present_json"]
    absent = response.context["chart_absent_json"]
    # يومان فيهما رصدٌ وحدهما: قبل ثلاثة أيّامٍ 25/25، واليوم 75/25. الأيّامُ بينهما
    # بلا رصد فلا تُرسم أصفاراً (جولةُ المشرف 2026-09-16).
    assert json.loads(present) == [25, 75], present
    assert json.loads(absent) == [25, 25], absent
    earlier = today - timedelta(days=3)
    assert json.loads(response.context["chart_labels_json"]) == [
        f"{earlier.day}/{earlier.month}",
        f"{today.day}/{today.month}",
    ]


# ══════════════════════════════════════════════════════════════════════
#  3. templates/base/base.html — `request.user.memberships.count` في كلّ صفحة
# ══════════════════════════════════════════════════════════════════════


def _membership_count_queries(sqls):
    return [q for q in sqls if "COUNT(*)" in q and "core_membership" in q]


def test_base_template_does_not_count_memberships(client, teacher_user):
    """كان: `SELECT COUNT(*) FROM core_membership` في كلّ صفحة. صار: من القائمة المحمَّلة."""
    client.force_login(teacher_user)
    client.get("/dashboard/")
    queries = queries_for(client, "/dashboard/")
    assert not _membership_count_queries(queries), "\n".join(_membership_count_queries(queries))


def test_role_switch_link_follows_active_memberships(client, school, teacher_user):
    client.force_login(teacher_user)
    assert "تبديل الدور" not in client.get("/dashboard/").content.decode()
    MembershipFactory(
        user=teacher_user, school=school, role=RoleFactory(school=school, name="coordinator")
    )
    client.force_login(teacher_user)  # جلسةٌ جديدة — الكائنُ يُحمَّل من جديد
    assert "تبديل الدور" in client.get("/dashboard/").content.decode()


# ══════════════════════════════════════════════════════════════════════
#  4. templates/assessments/setup_detail.html:44 — `assessment.grades.count`
# ══════════════════════════════════════════════════════════════════════


@pytest.fixture
def setup_with_package(school, class_group, teacher_user):
    subject = Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")
    setup = SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=class_group,
        teacher=teacher_user,
        academic_year="2025-2026",
    )
    package = AssessmentPackage.objects.create(
        setup=setup,
        school=school,
        package_type="P1",
        semester="S1",
        weight=Decimal("50"),
        semester_max_grade=Decimal("40"),
    )
    students = [_student(school, f"طالب {i}") for i in range(2)]
    for student in students:
        StudentEnrollment.objects.create(student=student, class_group=class_group, is_active=True)
    return setup, package, students


def test_setup_detail_counts_grades_without_loading_them(client, teacher_user, setup_with_package):
    """كان: كلُّ صفوف الدرجات تُجلب لتُعدّ (`prefetch assessments__grades`). صار: عدٌّ في الاستعلام."""
    setup, package, students = setup_with_package

    def add_assessments(n):
        for i in range(n):
            assessment = Assessment.objects.create(
                package=package,
                school=setup.school,
                title=f"تقييم {i}",
                max_grade=Decimal("20"),
                weight_in_package=Decimal("50"),
                status="published",
            )
            for student in students:
                StudentAssessmentGrade.objects.create(
                    assessment=assessment, student=student, school=setup.school, grade=Decimal("15")
                )

    add_assessments(1)
    client.force_login(teacher_user)
    url = f"/assessments/setup/{setup.id}/"
    queries = queries_for(client, url)
    loading_grades = [q for q in queries if 'FROM "assessments_studentassessmentgrade"' in q]
    assert not loading_grades, "\n".join(loading_grades)
    assert_flat(client, url, add_assessments, before_note="تفاصيل إعداد المادّة")
    assert "3/2 مُدخَل" not in client.get(url).content.decode()
    assert "2/2 مُدخَل" in client.get(url).content.decode()


# ══════════════════════════════════════════════════════════════════════
#  5. templates/transport/bus_detail.html — `route.students.count` لكلّ خطّ
# ══════════════════════════════════════════════════════════════════════


def test_bus_detail_is_flat(client, school, bus_supervisor_user):
    """كان: استعلامُ عدٍّ لكلّ خطّ سير. صار: `annotate`."""
    bus = SchoolBusFactory(school=school, supervisor=bus_supervisor_user)

    def add_routes(n):
        for i in range(n):
            route = BusRoute.objects.create(bus=bus, area_name=f"منطقة {i}")
            route.students.add(_student(school, f"راكب {i}"), _student(school, f"راكب {i}ب"))

    add_routes(1)
    client.force_login(bus_supervisor_user)
    url = f"/transport/bus/{bus.id}/"
    assert_flat(client, url, add_routes, before_note="تفاصيل الحافلة")
    html = client.get(url).content.decode()
    assert html.count("2 طالب") == 3


# ══════════════════════════════════════════════════════════════════════
#  6. templates/quality/executor_member_detail.html — `proc.evidences.count`
# ══════════════════════════════════════════════════════════════════════


def test_executor_member_detail_is_flat(client, school):
    """كان: استعلامُ عدٍّ لكلّ إجراء. صار: `annotate`."""
    admin = make_admin(school)
    teacher = make_teacher(school, "71")
    domain = make_domain(school)
    member = QualityCommitteeMember.objects.create(
        school=school,
        user=teacher,
        job_title=teacher.full_name,
        responsibility="عضو",
        committee_type=QualityCommitteeMember.EXECUTOR,
        academic_year="2025-2026",
        is_active=True,
    )

    def add_procedures(n):
        for _ in range(n):
            proc = make_procedure(school, domain, executor_user=teacher)
            ProcedureEvidence.objects.create(procedure=proc, title="دليل", uploaded_by=teacher)
            ProcedureEvidence.objects.create(procedure=proc, title="دليل ثانٍ", uploaded_by=teacher)

    add_procedures(1)
    client.force_login(admin)
    url = reverse("executor_member_detail", kwargs={"member_id": member.pk}) + "?year=2025-2026"
    assert_flat(client, url, add_procedures, before_note="تقرير إنجاز المنفّذ")
    rows = client.get(url).context["procedures"]
    assert [p.evidence_count for p in rows] == [2, 2, 2]


# ══════════════════════════════════════════════════════════════════════
#  7. templates/assessments/dashboard.html:79 — `setup.packages.count` لكلّ مادّة
# ══════════════════════════════════════════════════════════════════════


def test_assessments_dashboard_is_flat(client, school, principal_user, teacher_user, class_group):
    """كان: استعلامُ عدٍّ لكلّ إعداد مادّة. صار: `annotate`."""
    counter = iter(range(100))

    def add_setups(n):
        for _ in range(n):
            i = next(counter)
            subject = Subject.objects.create(school=school, name_ar=f"مادّة {i}", code=f"S{i}")
            setup = SubjectClassSetup.objects.create(
                school=school,
                subject=subject,
                class_group=class_group,
                teacher=teacher_user,
                academic_year="2025-2026",
            )
            for ptype in ("P1", "P4"):
                AssessmentPackage.objects.create(
                    setup=setup,
                    school=school,
                    package_type=ptype,
                    semester="S1",
                    weight=Decimal("50"),
                    semester_max_grade=Decimal("40"),
                )

    add_setups(1)
    client.force_login(principal_user)
    url = "/assessments/?year=2025-2026"
    assert_flat(client, url, add_setups, before_note="لوحة التقييمات")
    assert client.get(url).content.decode().count("2 باقة") == 3
