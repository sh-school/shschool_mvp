"""[STUDENT-INFO] إشاراتُ الاستثناء في صفحة طلاب الشعبة (W-20261108-009).

[LEGAL] عتبةُ الغياب في الشارة من `operations.absence_policy` المنقولةِ من نصّ الدليل التنظيمي:
الصفوفُ 1–11 عتباتُها 5 · 8 · 11 · 15 يوماً بلا عذر، والإنذارُ يسبق العتبةَ بيومين.
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.4.1.3

القاعدة: الخليّةُ فارغةٌ إلا عند إشارة، والمتأخّرُ يُحتسب حاضراً، والمقيَّدُ بجناحه لا يُحسب له
ما يحمل قرارَ الأخصائيّ، والاستعلاماتُ بعددٍ ثابتٍ مهما بلغ الطلاب.
"""

import datetime as dt
from datetime import time

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.academic_calendar import academic_year_window
from core.models import Wing
from operations.models import Session, StudentAttendance, Subject
from operations.models.absence_followup import AbsenceActionLog
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


@pytest.fixture
def klass(school, seeded_calendar):
    return ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=seeded_calendar
    )


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


def _student(school, klass, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    # قيدٌ بدأ مع العام لا بعده، فلا تكون «قيد جديد» إشارةً تُفسد اختبار الخليّة الفارغة.
    start = academic_year_window(school)[0]
    StudentEnrollmentFactory(student=user, class_group=klass, enrolled_at=start)
    return user


def _mark(school, klass, teacher, subject, student, on, status, hour=8):
    # حصةٌ واحدة للشعبة في الموعد نفسه: قيد «لا تداخل لحصص المعلّم» يمنع تكرارها لكلّ طالب.
    session, _ = Session.objects.get_or_create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=on,
        start_time=time(hour, 0),
        defaults={"subject": subject, "end_time": time(hour, 45), "status": "scheduled"},
    )
    StudentAttendance.objects.create(session=session, student=student, school=school, status=status)


def _page(client, user, klass, **query):
    client.force_login(user)
    url = reverse("student_info:section_students", args=[klass.id])
    if query:
        url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    return client.get(url)


def _names(response):
    return [r.enrollment.student.full_name for r in response.context["rows"]]


def test_a_student_with_no_signal_has_an_empty_cell(
    client, school, klass, principal_user, teacher_user, subject
):
    quiet = _student(school, klass, "طالب هادئ", "29000000001")
    _mark(school, klass, teacher_user, subject, quiet, timezone.localdate(), "present")

    response = _page(client, principal_user, klass)
    (row,) = response.context["rows"]

    assert not row.has_signal
    html = response.content.decode()
    assert 'class="sec-sig"' not in html
    # بلا إشارةٍ فلا شريطَ ملخّصٍ أيضاً: الأصفارُ تُخفى.
    assert "ملخّص إشارات الشعبة" not in html


def test_late_counts_as_present_and_absent_is_flagged(
    client, school, klass, principal_user, teacher_user, subject
):
    today = timezone.localdate()
    on_time = _student(school, klass, "طالب حاضر", "29000000001")
    late = _student(school, klass, "طالب متأخر", "29000000002")
    absent = _student(school, klass, "طالب غائب", "29000000003")
    unrecorded = _student(school, klass, "طالب لم يُرصد", "29000000004")
    for student, status in ((on_time, "present"), (late, "late"), (absent, "absent")):
        _mark(school, klass, teacher_user, subject, student, today, status)

    response = _page(client, principal_user, klass)
    counts = response.context["counts"]

    assert (counts["present"], counts["late"], counts["absent"], counts["unrecorded"]) == (
        2,
        1,
        1,
        1,
    )
    assert "حاضر 2 منهم متأخر 1" in response.context["today_line"]
    # أصحابُ الإشارات أولاً (غائب · متأخر · غير مرصود) ثم من لا إشارةَ له.
    assert _names(response)[-1] == "طالب حاضر"
    assert set(_names(response)[:3]) == {absent.full_name, late.full_name, unrecorded.full_name}


def test_a_section_nobody_recorded_today_does_not_flag_everyone_unrecorded(
    client, school, klass, principal_user
):
    _student(school, klass, "طالب", "29000000001")

    response = _page(client, principal_user, klass)

    assert response.context["counts"]["unrecorded"] == 0


def test_the_summary_filters_the_table_and_hides_zero_counts(
    client, school, klass, principal_user, teacher_user, subject
):
    today = timezone.localdate()
    gone = _student(school, klass, "طالب غائب", "29000000001")
    _student(school, klass, "طالب آخر", "29000000002")
    _mark(school, klass, teacher_user, subject, gone, today, "absent")

    full = _page(client, principal_user, klass)
    only_absent = _page(client, principal_user, klass, f="absent")
    html = full.content.decode()

    assert "غائب اليوم" in html
    assert "قرب العتبة" not in html and "بندٌ مفتوح" not in html
    assert _names(only_absent) == [gone.full_name]


def test_unknown_filter_value_is_ignored(client, school, klass, principal_user):
    _student(school, klass, "طالب", "29000000001")

    response = _page(client, principal_user, klass, f="x;drop")

    assert response.context["f"] == ""
    assert len(response.context["rows"]) == 1


def test_search_by_name(client, school, klass, principal_user):
    _student(school, klass, "سالم الأول", "29000000001")
    _student(school, klass, "خالد الثاني", "29000000002")

    response = _page(client, principal_user, klass, q="خالد")

    assert _names(response) == ["خالد الثاني"]


def test_near_the_absence_threshold_flags_with_the_legal_source(
    client, school, klass, principal_user, teacher_user, subject
):
    """أربعةُ أيامٍ بلا عذر والحدُّ خمسة: يبقى يومٌ واحد فيدخل هامشَ الإنذار (يومان)."""
    today = timezone.localdate()
    near = _student(school, klass, "طالب قريب", "29000000001")
    far = _student(school, klass, "طالب بعيد", "29000000002")
    _mark(school, klass, teacher_user, subject, far, today - dt.timedelta(days=20), "absent")
    for back in range(1, 5):
        _mark(school, klass, teacher_user, subject, near, today - dt.timedelta(days=back), "absent")

    response = _page(client, principal_user, klass, f="near")
    html = response.content.decode()
    (row,) = response.context["rows"]

    assert row.enrollment.student_id == near.id
    assert row.near == {"days": 4, "max": 5}
    assert "المصدر: 08_conduct_policy_2026.md م3.4.1.3" in html
    assert response.context["counts"]["near"] == 1


def test_open_items_cover_behavior_cases_and_pledges(
    client, school, klass, principal_user, teacher_user
):
    flagged = _student(school, klass, "طالب بسلوك", "29000000001")
    settled = _student(school, klass, "طالب عولج", "29000000002")
    pledged = _student(school, klass, "طالب بتعهد", "29000000003")
    BehaviorInfractionFactory(school=school, student=flagged, reported_by=teacher_user)
    BehaviorInfractionFactory(
        school=school, student=settled, reported_by=teacher_user, is_resolved=True
    )
    AbsenceActionLog.objects.create(
        school=school,
        student=pledged,
        absence_date=timezone.localdate(),
        action_kind="written_notice",
        status="not_done",
    )

    response = _page(client, principal_user, klass, f="open")

    assert set(_names(response)) == {flagged.full_name, pledged.full_name}
    assert "sec-sig__open" in response.content.decode()


def test_wing_bound_supervisor_is_not_given_specialist_referrals(
    client, school, seeded_calendar, klass, principal_user
):
    supervisor = UserFactory(full_name="مشرف الجناح", national_id="29000000009")
    MembershipFactory(
        user=supervisor, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    klass.wing = Wing.objects.create(
        school=school,
        code="w1",
        name="جناح 1",
        academic_year=seeded_calendar,
        supervisor=supervisor,
    )
    klass.save()
    kid = _student(school, klass, "طالب محال", "29000000001")
    AbsenceActionLog.objects.create(
        school=school,
        student=kid,
        absence_date=timezone.localdate(),
        action_kind="refer_social",
        status="not_done",
    )

    seen_by_supervisor = _page(client, supervisor, klass)
    seen_by_principal = _page(client, principal_user, klass)

    assert seen_by_supervisor.context["counts"]["open"] == 0
    assert seen_by_principal.context["counts"]["open"] == 1


def test_query_count_does_not_grow_with_the_class(
    client, school, klass, principal_user, teacher_user, subject
):
    def count_queries() -> int:
        client.force_login(principal_user)
        url = reverse("student_info:section_students", args=[klass.id])
        client.get(url)  # يسخّن الذاكرات (صلاحيات، تقويم) فلا تُحسب في المقارنة
        with CaptureQueriesContext(connection) as ctx:
            client.get(url)
        return len(ctx)

    first = _student(school, klass, "طالب 0", "29000000000")
    _mark(school, klass, teacher_user, subject, first, timezone.localdate(), "absent")
    few = count_queries()
    for i in range(1, 10):
        kid = _student(school, klass, f"طالب {i}", f"2900000000{i}")
        _mark(school, klass, teacher_user, subject, kid, timezone.localdate(), "late")
        BehaviorInfractionFactory(school=school, student=kid, reported_by=teacher_user)

    assert count_queries() == few
