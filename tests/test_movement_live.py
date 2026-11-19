"""[STUDENT_AFFAIRS] W-20261114-009: لوحة «خارج الفصل الآن» وسجلّ الخروج التاريخي."""

import datetime as dt
import logging

import pytest
from django.urls import reverse
from django.utils import timezone

from core.academic_calendar import academic_year_for_school
from core.models import Wing
from operations.models import ClassExit, Session
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def _wing(school, code, nid):
    year = academic_year_for_school(school)
    klass = ClassGroupFactory(school=school, academic_year=year)
    sup = UserFactory(full_name=f"مشرف {code}", national_id=nid)
    MembershipFactory(
        user=sup, school=school, role=RoleFactory(school=school, name="admin_supervisor")
    )
    wing = Wing.objects.create(
        school=school, code=code, name=code, academic_year=year, supervisor=sup
    )
    klass.wing = wing
    klass.save(update_fields=["wing"])
    return klass, sup


@pytest.fixture
def wing_a(school):
    return _wing(school, "wa", "29000000001")


@pytest.fixture
def wing_b(school):
    return _wing(school, "wb", "29000000002")


def _exit(
    school, klass, teacher, name, nid, *, minutes_ago=5, back_after=None, dest="clinic", day=None
):
    """خروجٌ قبل `minutes_ago` دقيقة؛ و`back_after` دقائقُ الغياب إن عاد."""
    student = UserFactory(full_name=name, national_id=nid)
    StudentEnrollmentFactory(student=student, class_group=klass)
    now = timezone.now()
    when = day or timezone.localdate(now)
    # قيدُ عدم التداخل يمنع حصتين بالبداية نفسها للمعلّم/الشعبة، فنُزيح الدقيقة بعدد الحصص القائمة
    taken = Session.objects.filter(school=school, date=when).count()
    session = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=when,
        start_time=dt.time(5, taken),
        end_time=dt.time(6, 0),
        status="scheduled",
    )
    left = now - dt.timedelta(minutes=minutes_ago)
    return ClassExit.objects.create(
        school=school,
        session=session,
        student=student,
        destination=dest,
        left_at=left,
        returned_at=left + dt.timedelta(minutes=back_after) if back_after is not None else None,
        allowed_by=teacher,
    )


def _live(client, user):
    client.force_login(user)
    return client.get(reverse("student_affairs:movements_live")).content.decode()


def test_live_panel_shows_only_those_who_have_not_returned(
    client, school, principal_user, teacher_user, wing_a
):
    klass, _ = wing_a
    _exit(school, klass, teacher_user, "طالب خارج", "29000000011")
    _exit(school, klass, teacher_user, "طالب عاد", "29000000012", back_after=3)

    html = _live(client, principal_user)

    assert "طالب خارج" in html
    assert "طالب عاد" not in html


def test_live_panel_orders_longest_first_and_colors_by_destination_grace(
    client, school, principal_user, teacher_user, wing_a
):
    """«خارج الآن» مرتّبٌ بالأطول أولاً وملوَّنٌ بمهلة الوجهة لا بعتبةٍ ثابتة: المتأخّرُ وحدَه أحمر."""
    klass, _ = wing_a
    _exit(school, klass, teacher_user, "قصير الغياب", "29000000021", minutes_ago=2)
    long_ = _exit(school, klass, teacher_user, "طويل الغياب", "29000000022", minutes_ago=25)
    ClassExit.objects.filter(pk=long_.pk).update(routed_at=long_.left_at, allowed_minutes=20)

    html = _live(client, principal_user)

    assert html.index("طويل الغياب") < html.index("قصير الغياب")
    assert html.count("status-danger") == 1


def test_supervisor_live_panel_hides_other_wing(client, school, teacher_user, wing_a, wing_b):
    klass_a, sup_a = wing_a
    klass_b, _ = wing_b
    _exit(school, klass_a, teacher_user, "طالب جناحي", "29000000031")
    _exit(school, klass_b, teacher_user, "طالب جناح آخر", "29000000032")

    html = _live(client, sup_a)

    assert "طالب جناحي" in html
    assert "طالب جناح آخر" not in html


def test_leadership_live_panel_sees_every_wing(
    client, school, principal_user, teacher_user, wing_a, wing_b
):
    _exit(school, wing_a[0], teacher_user, "طالب أ", "29000000041")
    _exit(school, wing_b[0], teacher_user, "طالب ب", "29000000042")

    html = _live(client, principal_user)

    assert "طالب أ" in html and "طالب ب" in html


def test_main_screen_self_refreshes_only_on_today(
    client, school, principal_user, teacher_user, wing_a
):
    client.force_login(principal_user)
    url = reverse("student_affairs:student_movements")
    today = timezone.localdate().isoformat()
    past = (timezone.localdate() - dt.timedelta(days=3)).isoformat()

    assert "every 10s" in client.get(url, {"date": today}).content.decode()
    assert "every 10s" not in client.get(url, {"date": past}).content.decode()


def test_history_sums_minutes_by_destination(client, school, principal_user, teacher_user, wing_a):
    klass, _ = wing_a
    first = _exit(school, klass, teacher_user, "طالب السجلّ", "29000000051", back_after=10)
    student = first.student
    for hour, dest, mins in ((8, "clinic", 5), (9, "restroom", 7)):
        session = Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher_user,
            date=timezone.localdate(),
            start_time=dt.time(hour, 0),
            end_time=dt.time(hour, 40),
            status="scheduled",
        )
        left = timezone.now() - dt.timedelta(minutes=60 + hour)
        ClassExit.objects.create(
            school=school,
            session=session,
            student=student,
            destination=dest,
            left_at=left,
            returned_at=left + dt.timedelta(minutes=mins),
            allowed_by=teacher_user,
        )
    client.force_login(principal_user)

    resp = client.get(reverse("student_affairs:movements_history"))
    row = resp.context["rows"][0]

    assert len(resp.context["rows"]) == 1
    assert row["count"] == 3 and row["minutes"] == 22
    cells = {d["label"]: (d["count"], d["minutes"]) for d in row["destinations"]}
    assert cells == {"العيادة": (2, 15), "دورة المياه": (1, 7)}
    assert str(student.pk) in row["link"]


def test_history_filters_by_range_and_scope(client, school, teacher_user, wing_a, wing_b):
    klass_a, sup_a = wing_a
    _exit(school, klass_a, teacher_user, "طالب ضمن الفترة", "29000000061", back_after=4)
    old = timezone.localdate() - dt.timedelta(days=90)
    _exit(school, klass_a, teacher_user, "طالب قديم", "29000000062", back_after=4, day=old)
    _exit(school, wing_b[0], teacher_user, "طالب جناح آخر", "29000000063", back_after=4)
    client.force_login(sup_a)

    html = client.get(reverse("student_affairs:movements_history")).content.decode()

    assert "طالب ضمن الفترة" in html
    assert "طالب قديم" not in html
    assert "طالب جناح آخر" not in html


def test_history_ignores_a_bad_student_filter(client, school, principal_user):
    client.force_login(principal_user)

    resp = client.get(
        reverse("student_affairs:movements_history"), {"student": "x", "start": "bad"}
    )

    assert resp.status_code == 200


def test_no_student_names_in_application_logs(
    client, school, principal_user, teacher_user, wing_a, caplog
):
    _exit(school, wing_a[0], teacher_user, "اسم سرّي للطالب", "29000000071", back_after=2)
    client.force_login(principal_user)

    with caplog.at_level(logging.DEBUG):
        client.get(reverse("student_affairs:student_movements"))
        client.get(reverse("student_affairs:movements_live"))
        client.get(reverse("student_affairs:movements_history"))

    assert "اسم سرّي للطالب" not in caplog.text
