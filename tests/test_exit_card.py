"""بطاقةُ الخروج: الوصولُ والعودةُ ومُهَلُ الوجهات وتأخّرُ العودة والتصعيد (W-20261119-002، إدارةُ الأجنحة 2/4).

[LEGAL] لا نصَّ في الدليل التنظيميّ يحدّد مُهَلَ العودة ولا مدّةَ التصعيد؛ فهي إعدادٌ وقرارُ مالكٍ (2026-11-19)
والاختباراتُ تثبّت ألّا تُنشأ مخالفةٌ من التأخّر (المخالفةُ آليّةٌ خارج النطاق).
المصدر: AAdocs/ministry_data/2026_2027/08_conduct_policy_2026.md م3.4.3
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from behavior.models import BehaviorInfraction
from core.models import AuditLog, Wing, WingAssignment
from operations import class_exit, exit_card
from operations.models import ClassExit, DailyExitTally, ExitDestinationGrace
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_movement_live import _exit, _wing, wing_a, wing_b  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

T0 = timezone.make_aware(dt.datetime(2026, 11, 19, 9, 0))


def _card(school, klass, teacher, nid, dest="wing_sup", **kwargs):
    """بطاقةٌ مفتوحة لطالبٍ في شعبة — `_exit` يضبط الحصّة والطالب."""
    return _exit(school, klass, teacher, f"طالب {nid}", nid, dest=dest, **kwargs)


def _field_supervisor(school, wing, nid):
    user = UserFactory(full_name="ميداني", national_id=nid)
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="student_observer")
    )
    WingAssignment.objects.create(
        wing=wing,
        user=user,
        role="field_supervisor",
        start_date=timezone.localdate() - dt.timedelta(days=1),
    )
    return user


def test_return_after_ten_minutes_with_seven_minute_grace_is_180_seconds(
    school, wing_a, teacher_user
):
    klass, sup = wing_a
    exit_card.set_grace(school, "restroom", 7, sup)
    card = _card(school, klass, teacher_user, "29000000101")

    assert exit_card.route(card, "restroom", sup, now=T0) is True
    assert card.allowed_minutes == 7 and card.status == "arrived"
    done, mine = exit_card.return_exit(card.pk, sup, now=T0 + dt.timedelta(minutes=10))

    assert mine is True and done is not None
    assert done.late_return_seconds == 180 and done.status == "returned"
    assert done.returned_by == sup and done.returned_by_role == "wing_supervisor"
    class_exit.refresh_tally(school, done.student, done.session.date)
    assert DailyExitTally.objects.get(student=done.student).late_return_seconds == 180
    # إعادةُ الحساب لا تزيد: idempotent
    class_exit.refresh_tally(school, done.student, done.session.date)
    assert DailyExitTally.objects.get(student=done.student).late_return_seconds == 180


def test_grace_is_a_snapshot_and_changing_the_setting_later_does_not_touch_it(
    school, wing_a, teacher_user
):
    klass, sup = wing_a
    exit_card.set_grace(school, "pe", 7, sup)
    card = _card(school, klass, teacher_user, "29000000102")
    exit_card.route(card, "pe", sup, now=T0)
    exit_card.set_grace(school, "pe", 30, sup)

    done, _ = exit_card.return_exit(card.pk, sup, now=T0 + dt.timedelta(minutes=10))

    assert done is not None and done.allowed_minutes == 7 and done.late_return_seconds == 180


def test_clinic_has_no_grace_and_no_lateness_even_if_a_value_is_stored(
    school, wing_a, teacher_user
):
    klass, sup = wing_a
    assert exit_card.grace_minutes_for(school, "clinic") is None
    with pytest.raises(ValueError):
        exit_card.set_grace(school, "clinic", 5, sup)
    card = _card(school, klass, teacher_user, "29000000103")
    exit_card.route(card, "clinic", sup, now=T0)

    done, _ = exit_card.return_exit(card.pk, sup, now=T0 + dt.timedelta(hours=1))

    assert done is not None and done.allowed_minutes is None and done.late_return_seconds is None


def test_two_supervisors_pressing_return_record_one_return_by_the_first(
    client, school, wing_a, teacher_user
):
    klass, sup = wing_a
    field = _field_supervisor(school, Wing.objects.get(school=school, code="wa"), "29000000104")
    card = _card(school, klass, teacher_user, "29000000105", dest="clinic")

    client.force_login(sup)
    first = client.post(reverse("student_affairs:movement_return", args=[card.pk]))
    client.force_login(field)
    second = client.post(reverse("student_affairs:movement_return", args=[card.pk]), follow=True)

    card.refresh_from_db()
    assert first.status_code == 302
    assert card.returned_by == sup and card.returned_by_role == "wing_supervisor"
    assert "سجّلها" in second.content.decode()
    assert (
        AuditLog.objects.filter(object_id=str(card.pk), object_repr__contains="عودة").count() == 1
    )


def test_field_supervisor_return_is_recorded_with_its_role(school, wing_a, teacher_user):
    klass, _ = wing_a
    field = _field_supervisor(school, Wing.objects.get(school=school, code="wa"), "29000000106")
    card = _card(school, klass, teacher_user, "29000000107", dest="clinic")

    done, mine = exit_card.return_exit(card.pk, field)

    assert mine and done is not None and done.returned_by_role == "field_supervisor"


def test_current_period_teacher_can_return_even_if_not_the_one_who_sent_him(
    school, wing_a, teacher_user
):
    klass, _ = wing_a
    card = _card(school, klass, teacher_user, "29000000108", dest="clinic")
    other_teacher = UserFactory(full_name="معلم آخر", national_id="29000000109")
    MembershipFactory(
        user=other_teacher, school=school, role=RoleFactory(school=school, name="teacher")
    )

    done = class_exit.come_back(card.session, card.student, by=other_teacher)

    assert (
        done is not None
        and done.returned_by == other_teacher
        and done.returned_by_role == "teacher"
    )


def test_bell_closing_is_unknown_not_lateness(school, wing_a, teacher_user):
    klass, sup = wing_a
    exit_card.set_grace(school, "restroom", 1, sup)
    card = _card(school, klass, teacher_user, "29000000110", dest="restroom")
    end = class_exit.session_end(card.session)
    # الخروجُ قبل الجرس بعشر دقائق مهما كانت ساعةُ التثبيت: الإغلاقُ لا يمسّ إلا ما خرج قبل الجرس.
    ClassExit.objects.filter(pk=card.pk).update(left_at=end - dt.timedelta(minutes=10))
    card.refresh_from_db()
    exit_card.route(card, "restroom", sup, now=card.left_at)

    class_exit.close_unreturned(card.session, now=end + dt.timedelta(minutes=1))

    card.refresh_from_db()
    assert card.returned_at == end and card.late_return_seconds is None
    assert card.returned_by_role == "system" and card.returned_by is None
    assert card.system_closed is True and card.status == "unknown"


def test_unreceived_card_alerts_the_other_supervisor_then_the_vice_once(
    school, wing_a, teacher_user, monkeypatch
):
    klass, sup = wing_a
    field = _field_supervisor(school, Wing.objects.get(school=school, code="wa"), "29000000111")
    vice = UserFactory(full_name="نائب", national_id="29000000112")
    MembershipFactory(user=vice, school=school, role=RoleFactory(school=school, name="vice_admin"))
    card = _card(school, klass, teacher_user, "29000000113", minutes_ago=0)
    sent: list[list] = []
    from notifications.hub import NotificationHub

    monkeypatch.setattr(
        NotificationHub, "dispatch", staticmethod(lambda **kw: sent.append(kw["recipients"]))
    )
    left = card.left_at

    assert exit_card.escalate_unreceived(school, left + dt.timedelta(minutes=2)) == 0
    assert exit_card.escalate_unreceived(school, left + dt.timedelta(minutes=5)) == 1
    assert sent == [[field]]
    assert exit_card.escalate_unreceived(school, left + dt.timedelta(minutes=5)) == 0  # idempotent
    assert exit_card.escalate_unreceived(school, left + dt.timedelta(minutes=10)) == 1
    assert sent[-1] == [vice]
    assert exit_card.escalate_unreceived(school, left + dt.timedelta(minutes=30)) == 0
    assert len(sent) == 2


def test_received_card_is_not_escalated(school, wing_a, teacher_user, monkeypatch):
    klass, sup = wing_a
    card = _card(school, klass, teacher_user, "29000000114", minutes_ago=0)
    exit_card.route(card, "restroom", sup, now=card.left_at)

    assert exit_card.escalate_unreceived(school, card.left_at + dt.timedelta(minutes=20)) == 0


def test_notice_goes_to_both_supervisors(school, wing_a, teacher_user, monkeypatch):
    klass, sup = wing_a
    field = _field_supervisor(school, Wing.objects.get(school=school, code="wa"), "29000000115")
    student = UserFactory(full_name="طالب إشعار", national_id="29000000116")
    from operations.models import Session
    from tests.conftest import StudentEnrollmentFactory

    StudentEnrollmentFactory(student=student, class_group=klass)
    session = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher_user,
        date=timezone.localdate(),
        start_time=dt.time(5, 40),
        end_time=dt.time(6, 0),
        status="scheduled",
    )
    sent: list[list] = []
    from notifications.hub import NotificationHub

    monkeypatch.setattr(
        NotificationHub, "dispatch", staticmethod(lambda **kw: sent.append(kw["recipients"]))
    )

    class_exit.leave(session, student, "wing_sup", teacher_user)

    assert len(sent) == 1 and set(sent[0]) == {sup, field}


def test_second_click_on_leave_after_integrity_conflict_returns_the_open_row(
    school, wing_a, teacher_user, monkeypatch
):
    klass, _ = wing_a
    card = _card(school, klass, teacher_user, "29000000117", dest="restroom")
    real = class_exit.open_exit
    calls: list[int] = []

    def flaky(session, student):
        calls.append(1)
        return None if len(calls) == 1 else real(session, student)

    monkeypatch.setattr(class_exit, "open_exit", flaky)

    got = class_exit.leave(card.session, card.student, "wing_sup", teacher_user)

    assert got is not None and got.pk == card.pk
    assert ClassExit.objects.filter(session=card.session, student=card.student).count() == 1


def test_supervisor_choosing_destination_arrives_once_and_later_change_keeps_arrival(
    client, school, wing_a, teacher_user
):
    klass, sup = wing_a
    exit_card.set_grace(school, "arts", 9, sup)
    card = _card(school, klass, teacher_user, "29000000118")
    client.force_login(sup)

    client.post(
        reverse("student_affairs:movement_change_destination", args=[card.pk]),
        {"destination": "arts"},
    )
    card.refresh_from_db()
    arrived = card.routed_at
    client.post(
        reverse("student_affairs:movement_change_destination", args=[card.pk]),
        {"destination": "restroom"},
    )
    card.refresh_from_db()

    assert arrived is not None and card.routed_at == arrived and card.routed_by == sup
    assert card.destination == "restroom" and card.status == "arrived"


def test_followup_needs_a_written_reason_and_creates_no_infraction(
    client, school, wing_a, teacher_user
):
    klass, sup = wing_a
    card = _card(school, klass, teacher_user, "29000000119", dest="restroom")
    exit_card.set_grace(school, "restroom", 1, sup)
    exit_card.route(card, "restroom", sup, now=T0)
    exit_card.return_exit(card.pk, sup, now=T0 + dt.timedelta(minutes=30))
    client.force_login(sup)
    url = reverse("student_affairs:movement_followup", args=[card.pk])

    client.post(url, {"reason": "   "})
    card.refresh_from_db()
    assert card.followup_at is None

    client.post(url, {"reason": "تكرّر التأخّر هذا الأسبوع"})
    card.refresh_from_db()
    assert card.followup_at is not None and card.followup_reason
    assert not BehaviorInfraction.objects.exists()
    log = AuditLog.objects.filter(object_id=str(card.pk), object_repr__contains="متابعة").get()
    assert "تكرّر" not in str(log.changes)


def test_grace_setting_is_for_leadership_and_coordinator_only(
    client, school, wing_a, principal_user
):
    _, sup = wing_a
    url = reverse("student_affairs:movement_grace_save")
    client.force_login(sup)
    assert client.post(url, {"grace_restroom": "7"}).status_code == 403

    client.force_login(principal_user)
    client.post(url, {"grace_restroom": "7", "grace_pe": ""})
    assert ExitDestinationGrace.objects.get(school=school, destination="restroom").minutes == 7
    client.post(url, {"grace_restroom": "abc"})
    assert ExitDestinationGrace.objects.get(school=school, destination="restroom").minutes == 7
    client.post(url, {"grace_restroom": ""})
    assert not ExitDestinationGrace.objects.filter(school=school).exists()


def test_incoming_zone_lists_only_unreceived_wing_supervisor_cards(
    client, school, wing_a, teacher_user, principal_user
):
    klass, sup = wing_a
    _card(school, klass, teacher_user, "29000000120")
    received = _card(school, klass, teacher_user, "29000000121")
    exit_card.route(received, "restroom", sup, now=timezone.now())
    client.force_login(sup)

    html = client.get(reverse("student_affairs:movements_live")).content.decode()

    assert html.count("قادمون إليك") == 1
    incoming = html.split("قادمون إليك")[1].split("خارج الآن")[0]
    assert "طالب 29000000120" in incoming and "طالب 29000000121" not in incoming
    assert 'hx-trigger="every 10s"' in html


def test_status_is_derived_from_the_fields(school, wing_a, teacher_user):
    klass, sup = wing_a
    card = _card(school, klass, teacher_user, "29000000122")
    assert card.status == "issued"
    exit_card.route(card, "pe", sup, now=T0)
    assert card.status == "arrived"
    ClassExit.objects.filter(pk=card.pk).update(
        returned_at=T0 + dt.timedelta(minutes=3), system_closed=True
    )
    card.refresh_from_db()
    assert card.status == "unknown"
