"""الرصدُ بحصّةٍ مؤقّتة للمعلّم (W-20261005-006، D-217م وD-218م): خدمةُ الإنشاء ومساراتُها ومفتاحُ التشغيل.

المعلّمُ ينشئ لشُعب إسناده فقط وفي اليوم الدراسيّ الجاري فقط (404 لا 403)، برقمِ حصّةٍ 1–7 وزمنٍ من `TimeSlotConfig`، ومفتاحُ
`PROVISIONAL_SESSIONS_ENABLED` يعزل الميزةَ كلَّها (مطفأً: لا مسارَ ولا زرّ ولا إنشاء). والمؤقّتةُ تُغلق ولا تُحذف.
"""

import datetime as dt

import pytest
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from core.models import AuditLog
from operations.models import Session, Subject, SubjectClassAssignment
from operations.services import provisional_session as provisional
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import MONDAY, SATURDAY, SUNDAY, _staff

FRIDAY = SUNDAY + dt.timedelta(days=5)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _flag_on_and_today_is_sunday(settings, monkeypatch):
    settings.PROVISIONAL_SESSIONS_ENABLED = True
    monkeypatch.setattr(timezone, "localdate", lambda *a, **k: SUNDAY)


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="العلوم", code="SCI")


@pytest.fixture
def assigned(school, year, klass, teacher, subject, band, bells):
    """معلّمٌ مُسنَدةٌ إليه الشعبةُ، وجرسُها `ground` بثلاث حصص (1 و2 و3)."""
    type(klass).objects.filter(pk=klass.pk).update(time_band=band)
    klass.refresh_from_db()
    SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=2,
        academic_year=year,
    )
    return klass


def test_a_teacher_creates_a_provisional_session_for_an_assigned_class(
    school, assigned, teacher, subject
):
    session, created = provisional.create(teacher, school, assigned.id, 1)

    assert created is True
    assert (session.provisional, session.teacher, session.class_group) == (True, teacher, assigned)
    assert (session.date, session.period_number, session.subject) == (SUNDAY, 1, subject)
    # الزمنُ من TimeSlotConfig لجرس الشعبة لا من الرقم
    assert (session.start_time, session.end_time) == (dt.time(7, 10), dt.time(7, 55))
    assert session.provisional_until > timezone.now() + dt.timedelta(days=13)
    assert AuditLog.objects.filter(
        object_id=str(session.pk), object_repr__contains="مؤقّتة"
    ).exists()


def test_creating_twice_returns_the_same_session(school, assigned, teacher):
    first, _ = provisional.create(teacher, school, assigned.id, 2)

    again, created = provisional.create(teacher, school, assigned.id, 2)

    assert (again.pk, created) == (first.pk, False)
    assert Session.objects.filter(provisional=True).count() == 1


def test_a_class_that_is_not_assigned_is_not_found(school, assigned, other_teacher):
    with pytest.raises(provisional.ProvisionalNotAllowedError):
        provisional.create(other_teacher, school, assigned.id, 1)
    assert not Session.objects.filter(provisional=True).exists()


@pytest.mark.parametrize("day", [SUNDAY - dt.timedelta(days=7), MONDAY, SATURDAY, FRIDAY])
def test_only_the_current_school_day_is_allowed(school, assigned, teacher, day):
    with pytest.raises(provisional.ProvisionalNotAllowedError):
        provisional.create(teacher, school, assigned.id, 1, day=day)


@pytest.mark.parametrize("number", [0, 8, -1, "x", None])
def test_a_period_outside_1_to_7_is_refused_in_the_service(school, assigned, teacher, number):
    with pytest.raises(provisional.ProvisionalRefusedError):
        provisional.create(teacher, school, assigned.id, number)


def test_a_period_with_no_bell_time_for_the_class_is_refused(school, assigned, teacher):
    with pytest.raises(provisional.ProvisionalRefusedError):
        provisional.create(teacher, school, assigned.id, 5)  # جرسُ الاختبار ثلاثُ حصصٍ فقط


def test_it_refuses_a_slot_that_a_real_session_already_holds(school, assigned, teacher, session):
    """`session` حقيقيّةٌ لهذه الشعبة 07:10 — فلا مؤقّتةَ فوقها (بند 4)."""
    with pytest.raises(provisional.ProvisionalRefusedError):
        provisional.create(teacher, school, assigned.id, 1)


def test_it_refuses_when_the_teacher_already_teaches_at_that_time(
    school, year, assigned, teacher, wing
):
    from tests.conftest import ClassGroupFactory

    other = ClassGroupFactory(school=school, grade="G9", section="z", academic_year=year, wing=wing)
    Session.objects.create(
        school=school,
        class_group=other,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    with pytest.raises(provisional.ProvisionalRefusedError):
        provisional.create(teacher, school, assigned.id, 2)


def test_the_unique_keys_hold_at_the_database(school, assigned, teacher, subject):
    provisional.create(teacher, school, assigned.id, 1)
    with pytest.raises(IntegrityError):
        Session.objects.create(
            school=school,
            class_group=assigned,
            teacher=_staff(school, "teacher", "معلّم ثانٍ", "29000001099"),
            subject=subject,
            date=SUNDAY,
            start_time=dt.time(9, 0),
            end_time=dt.time(9, 45),
            period_number=1,
            provisional=True,
        )


def test_a_provisional_session_is_closed_not_deleted(school, assigned, teacher):
    session, _ = provisional.create(teacher, school, assigned.id, 1)

    assert provisional.close(session, reason="schedule_approved", by=teacher) is True
    assert provisional.close(session, reason="schedule_approved", by=teacher) is False

    session.refresh_from_db()
    assert session.provisional_until <= timezone.now()
    assert Session.objects.filter(pk=session.pk).exists(), "تبقى تاريخاً"
    assert AuditLog.objects.filter(
        object_id=str(session.pk), object_repr__contains="إغلاق"
    ).exists()


# ── الواجهة: المنتقي فوق قائمة الطلبة، 404 لغير المُسنَد، والمفتاح المطفأ ──


def test_the_class_page_puts_the_period_picker_above_the_students(
    client_as, assigned, teacher, kid
):
    body = client_as(teacher).get(reverse("provisional_class", args=[assigned.id])).content.decode()

    assert all(f"ح{n}" in body for n in range(1, 8))
    assert "07:10" in body and "بلا زمن" in body
    assert body.index("pp-picker") < body.index(kid.full_name), "المنتقي فوق قائمة الطلبة"


def test_picking_a_period_creates_it_and_opens_the_register(client_as, assigned, teacher):
    response = client_as(teacher).post(
        reverse("provisional_create", args=[assigned.id]), {"period": "2"}
    )

    session = Session.objects.get(provisional=True)
    assert response.status_code == 302
    assert response.url == reverse("attendance", args=[session.id])
    assert session.period_number == 2


def test_an_unassigned_teacher_gets_404_not_403(client_as, assigned, other_teacher):
    client = client_as(other_teacher)

    assert client.get(reverse("provisional_class", args=[assigned.id])).status_code == 404
    assert (
        client.post(reverse("provisional_create", args=[assigned.id]), {"period": "1"}).status_code
        == 404
    )
    assert not Session.objects.filter(provisional=True).exists()


def test_the_supervisor_approves_but_does_not_create(client_as, assigned, holder):
    response = client_as(holder).post(
        reverse("provisional_create", args=[assigned.id]), {"period": "1"}
    )

    assert response.status_code == 404
    assert not Session.objects.filter(provisional=True).exists()


def test_a_period_out_of_range_is_refused_with_a_message_not_an_error(client_as, assigned, teacher):
    response = client_as(teacher).post(
        reverse("provisional_create", args=[assigned.id]), {"period": "9"}
    )

    assert response.status_code == 302
    assert response.url == reverse("provisional_class", args=[assigned.id])
    assert not Session.objects.filter(provisional=True).exists()


def test_with_the_switch_off_nothing_exists(client_as, settings, assigned, teacher):
    settings.PROVISIONAL_SESSIONS_ENABLED = False
    client = client_as(teacher)

    assert client.get(reverse("provisional_classes")).status_code == 404
    assert client.get(reverse("provisional_class", args=[assigned.id])).status_code == 404
    assert (
        client.post(reverse("provisional_create", args=[assigned.id]), {"period": "1"}).status_code
        == 404
    )
    assert provisional.assigned_classes(teacher, assigned.school) == []
    assert not Session.objects.filter(provisional=True).exists()
    page = client.get(reverse("teacher_schedule")).content.decode()
    assert "شُعبي للرصد" not in page, "لا زرَّ مطفأً"


def test_with_the_switch_on_the_schedule_offers_the_door(client_as, assigned, teacher):
    page = client_as(teacher).get(reverse("teacher_schedule")).content.decode()

    assert "شُعبي للرصد" in page
