"""
جدولُ طلاب الشعبة: كلُّ إشارةٍ في عمودٍ مستقلّ ومحاذاةٌ مركزيّة (W-20261108-012).

[LEGAL] العتبةُ المعروضةُ ورقمُها من الدليل التنظيمي لسياسة إدارة سلوك الطلبة 2026:
الصفوف 1–11 خمسةُ أيّامٍ ثمّ ثمانيةٌ ثمّ إحدى عشرةَ ثمّ خمسةَ عشر، ويُحتسب المتأخّرُ حاضراً.
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.4.1.3
"""

from __future__ import annotations

import datetime as dt

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from behavior.models import BehaviorInfraction
from core.models import Wing
from operations.models import Session, StudentAttendance, Subject
from student_affairs.models import StudentTransfer
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def _member(school, role, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def year(seeded_calendar):
    return seeded_calendar


@pytest.fixture
def principal(school, year):
    return _member(school, "principal", "مدير الاختبار", "29500000001")


@pytest.fixture
def klass(school, year):
    return ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=year
    )


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


def _student(school, klass, name, national_id):
    student = _member(school, "student", name, national_id)
    # تاريخُ القيد صريحٌ قبل اليوم المثبَّت: افتراضُه `timezone.now` مربوطٌ عند تعريف النموذج
    # فلا تمسّه الساعةُ المثبَّتة، فيقع بعد اليوم ويُسقط الطالبَ من `on_roll` ويقدَّم على قيدٍ أحدث.
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=dt.date(2026, 9, 1))
    return student


def _mark(school, klass, teacher, subject, student, day, status, hour=8):
    """حصّةٌ واحدةٌ مرصودةٌ لطالبٍ في يومٍ."""
    # الحصّةُ لكلّ (شعبة، يوم، ساعة) واحدةٌ يشترك فيها الطلبة: القيدُ الفريد يمنع تكرارها.
    session, _ = Session.objects.get_or_create(
        class_group=klass,
        date=day,
        start_time=dt.time(hour, 0),
        defaults={
            "school": school,
            "teacher": teacher,
            "subject": subject,
            "end_time": dt.time(hour, 45),
            "status": "scheduled",
        },
    )
    StudentAttendance.objects.create(session=session, student=student, school=school, status=status)


def _absent_days(school, klass, teacher, subject, student, count):
    """`count` أيّامٍ غيابٍ كاملةٍ بلا عذرٍ قبل اليوم (حصّةٌ واحدةٌ تكفي: المجدولُ يومَها واحد)."""
    today = timezone.localdate()
    for back in range(1, count + 1):
        _mark(school, klass, teacher, subject, student, today - dt.timedelta(days=back), "absent")


def _get(client, user, klass, **query):
    client.force_login(user)
    url = reverse("student_info:section_students", args=[klass.id])
    if query:
        url += "?" + "&".join(f"{k}={v}" for k, v in query.items())
    return client.get(url)


def _row(response, name):
    return next(r for r in response.context["rows"] if r.enrollment.student.full_name == name)


@pytest.fixture
def world(school, klass, subject, teacher_user, year):
    """أربعةُ طلاب: غائبُ اليوم، ومتأخّرٌ، وقربَ العتبة بتعهّدٍ مفتوح، وبلا إشارة."""
    today = timezone.localdate()
    absent = _student(school, klass, "أحمد الغائب", "29500000011")
    late = _student(school, klass, "بدر المتأخر", "29500000012")
    near = _student(school, klass, "جاسم القريب", "29500000013")
    quiet = _student(school, klass, "داود الهادئ", "29500000014")
    _mark(school, klass, teacher_user, subject, absent, today, "absent")
    _mark(school, klass, teacher_user, subject, late, today, "late")
    _mark(school, klass, teacher_user, subject, quiet, today, "present")
    _absent_days(school, klass, teacher_user, subject, near, 4)
    BehaviorInfraction.objects.create(
        school=school,
        student=near,
        reported_by=teacher_user,
        level=2,
        description="مخالفة",
        disciplinary_action_type="parent_pledge",
        is_resolved=False,
    )
    return {"absent": absent, "late": late, "near": near, "quiet": quiet}


def test_each_signal_has_its_own_column_and_late_counts_as_present(client, principal, klass, world):
    response = _get(client, principal, klass)
    html = response.content.decode()

    for heading in ("الطالب", "حضور اليوم", "الغياب مقابل العتبة", "حالة القيد", "بندٌ مفتوح"):
        assert f"<th>{heading}</th>" in html
    assert _row(response, "أحمد الغائب").today[0] == "absent"
    late = _row(response, "بدر المتأخر")
    assert late.today[0] == "late"
    assert "يُحتسب حاضراً" in late.today[1]
    assert late.signals == 0  # المتأخّرُ حاضرٌ: لا يُعدّ إشارةَ غياب
    assert _row(response, "داود الهادئ").today[0] == "present"
    assert _row(response, "جاسم القريب").today[0] == "unrecorded"


def test_threshold_number_comes_from_the_policy_and_names_its_source(
    client, principal, klass, world
):
    """[LEGAL] أربعةُ أيّامٍ من خمسةٍ للصفّ السابع، والمرجعُ م 3.4.1.3 ظاهرٌ تحت الجدول."""
    response = _get(client, principal, klass)

    near = _row(response, "جاسم القريب")
    assert near.absence_text == "4 من 5"
    assert near.near_threshold is True
    assert "م 3.4.1.3" in response.content.decode()


def test_open_item_and_empty_cells_show_a_dim_dash(client, principal, klass, world):
    response = _get(client, principal, klass)

    assert _row(response, "جاسم القريب").open_item == ("تعهّد", "warning")
    assert _row(response, "داود الهادئ").open_item is None
    assert 'class="ui-meta" aria-label="لا إشارة">–</span>' in response.content.decode()


def test_rows_with_signals_come_first(client, principal, klass, world):
    names = [r.enrollment.student.full_name for r in _get(client, principal, klass).context["rows"]]

    assert names[0] == "جاسم القريب"  # قربُ العتبة وبندٌ مفتوح: إشارتان
    assert names[1] == "أحمد الغائب"
    assert names[-2:] == ["بدر المتأخر", "داود الهادئ"]


@pytest.mark.parametrize(
    ("key", "expected"),
    [
        ("absent", ["أحمد الغائب"]),
        ("near", ["جاسم القريب"]),
        ("open", ["جاسم القريب"]),
    ],
)
def test_summary_buttons_filter(client, principal, klass, world, key, expected):
    response = _get(client, principal, klass, filter=key)

    assert [r.enrollment.student.full_name for r in response.context["rows"]] == expected
    # الأعدادُ من القائمة الكاملة لا المصفّاة.
    assert response.context["counts"] == {"absent": 1, "near": 1, "open": 1}


def test_name_search_and_unknown_filter_is_ignored(client, principal, klass, world):
    by_name = _get(client, principal, klass, q="بدر")
    bogus = _get(client, principal, klass, filter="x")

    assert [r.enrollment.student.full_name for r in by_name.context["rows"]] == ["بدر المتأخر"]
    assert len(bogus.context["rows"]) == 4


def test_enrollment_status_shows_new_transferred_withdrawn(school, klass, year, principal, client):
    new = _student(school, klass, "نايف الجديد", "29500000021")
    moved = _student(school, klass, "ماجد المنقول", "29500000022")
    gone = _student(school, klass, "سالم المنسحب", "29500000023")
    for student, direction, to_group in (
        (new, "in", None),
        (moved, "internal", klass),
        (gone, "out", None),
    ):
        StudentTransfer.objects.create(
            school=school,
            student=student,
            direction=direction,
            other_school_name="مدرسة",
            to_class_group=to_group,
            transfer_date=timezone.localdate(),
            status="completed",
            academic_year=year,
        )

    response = _get(client, principal, klass)

    assert _row(response, "نايف الجديد").enrollment_status[0] == "جديد"
    assert _row(response, "ماجد المنقول").enrollment_status[0] == "منقول"
    assert _row(response, "سالم المنسحب").enrollment_status[0] == "منسحب"


def test_the_wing_supervisor_sees_signals_of_his_students_only(
    client, school, year, subject, teacher_user
):
    supervisor = _member(school, "admin_supervisor", "مشرف الاختبار", "29500000031")
    wing = Wing.objects.create(
        school=school, code="w1", name="جناح 1", academic_year=year, supervisor=supervisor
    )
    mine_klass = ClassGroupFactory(
        school=school, grade="G7", section="1", level_type="prep", academic_year=year, wing=wing
    )
    mine = _student(school, mine_klass, "طالب جناحي", "29500000032")
    # قيدٌ جاري في شعبةٍ بلا جناحه: لا يظهر له رغم قيده القديم النشط هنا.
    moved = _student(school, mine_klass, "طالب انتقل", "29500000033")
    elsewhere = ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year
    )
    StudentEnrollmentFactory(student=moved, class_group=elsewhere, enrolled_at=dt.date(2026, 10, 1))
    _mark(school, mine_klass, teacher_user, subject, mine, timezone.localdate(), "absent")
    _mark(school, mine_klass, teacher_user, subject, moved, timezone.localdate(), "absent")

    response = _get(client, supervisor, mine_klass)

    assert [r.enrollment.student_id for r in response.context["rows"]] == [mine.id]
    assert response.context["counts"]["absent"] == 1


def test_queries_do_not_grow_with_the_number_of_students(client, principal, klass, school, world):
    client.force_login(principal)
    url = reverse("student_info:section_students", args=[klass.id])
    client.get(url)  # يسخّن الجلسةَ والتخزينَ المؤقّت
    with CaptureQueriesContext(connection) as small:
        client.get(url)
    for i in range(6):
        _student(school, klass, f"طالب إضافي {i}", f"2950000004{i}")
    with CaptureQueriesContext(connection) as large:
        client.get(url)

    assert len(large) == len(small)


def test_cells_are_centred_centrally_not_by_a_local_style(client, principal, klass, world):
    """المحاذاةُ بقاعدة الجداول المركزيّة: الاسمُ `cell-name` وغيرُه بلا نمطٍ محلّيّ."""
    html = _get(client, principal, klass).content.decode()

    assert 'class="cell-name"' in html
    assert "text-align" not in html.split("<table", 1)[1].split("</table>", 1)[0]
