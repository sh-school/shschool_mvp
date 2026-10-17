"""[QUALITY] W-20261012-027: التقييمُ الذاتيّ للمعلّم — التحقّقُ الخادميّ والتواقيع والحقل.

الخادمُ هو الحكَم لا المتصفّح: حصّةٌ ليست في جدول المعلّم تُرفض ما لم تُوسَم «خارج جدولي»، وتاريخٌ أقدمُ
من `MAX_SELF_BACKDATE_DAYS` أو مستقبليٌّ يُرفض (D-417م)، والمعلّمُ هو المستخدم الحاليّ لا ما يقوله الطلب،
وجدولُ المعتمَد للقراءة فقط (D-381م): لا يُولَّد `Session` لتاريخٍ خارج النافذة.
"""

import datetime as dt
from unittest import mock

import pytest

from operations.models import Session, Subject
from quality.observation_models import MAX_SELF_BACKDATE_DAYS, ClassroomObservation
from quality.observation_selectors import (
    self_date_error,
    self_slot_error,
    teacher_schedule_context,
)
from quality.presentation import signature_stamps

pytestmark = pytest.mark.django_db

TODAY = dt.date(2026, 9, 21)  # اثنين — يوم دراسة


@pytest.fixture(autouse=True)
def _frozen_today(monkeypatch):
    """اليومُ مثبَّتٌ: النافذةُ تُحسب منه، فلا يمرّ الاختبار اليومَ ويكذب غداً."""
    monkeypatch.setattr("django.utils.timezone.localdate", lambda *a, **k: TODAY)


@pytest.fixture
def subject(school):
    return Subject.objects.create(school=school, name_ar="الرياضيات", code="MATH")


def _session(school, class_group, teacher, subject, day=TODAY, start=dt.time(7, 10)):
    return Session.objects.create(
        school=school,
        class_group=class_group,
        teacher=teacher,
        subject=subject,
        date=day,
        start_time=start,
        end_time=(dt.datetime.combine(day, start) + dt.timedelta(minutes=45)).time(),
        status="scheduled",
    )


def _header(session, period=1, day=TODAY):
    return {
        "subject_id": session.subject_id,
        "class_group_id": session.class_group_id,
        "period": period,
        "observation_date": day.isoformat(),
    }


# ── النافذة الزمنيّة (D-417م) ─────────────────────────────────────────────
def test_today_and_the_oldest_allowed_day_pass():
    assert self_date_error(TODAY) == ""
    assert self_date_error(TODAY - dt.timedelta(days=MAX_SELF_BACKDATE_DAYS)) == ""


def test_a_day_older_than_the_window_is_rejected():
    old = TODAY - dt.timedelta(days=MAX_SELF_BACKDATE_DAYS + 1)
    assert "لا يتجاوز" in self_date_error(old)


def test_a_future_day_is_rejected():
    assert "لم يأتِ" in self_date_error(TODAY + dt.timedelta(days=1))


def test_the_window_constant_is_seven_days():
    assert MAX_SELF_BACKDATE_DAYS == 7


# ── الحصّة من جدول المعلّم ────────────────────────────────────────────────
def test_a_slot_in_my_schedule_is_accepted(school, class_group, teacher_user, subject):
    s = _session(school, class_group, teacher_user, subject)

    assert self_slot_error(school, teacher_user, _header(s), outside_schedule=False) == ""


def test_a_slot_not_in_my_schedule_is_rejected(school, class_group, teacher_user, subject):
    s = _session(school, class_group, teacher_user, subject)
    wrong_period = _header(s, period=5)

    assert "ليست في جدولك" in self_slot_error(
        school, teacher_user, wrong_period, outside_schedule=False
    )


def test_a_slot_not_in_my_schedule_is_accepted_when_marked_outside(
    school, class_group, teacher_user, subject
):
    s = _session(school, class_group, teacher_user, subject)

    assert self_slot_error(school, teacher_user, _header(s, period=5), outside_schedule=True) == ""


def test_another_teachers_slot_is_not_mine(
    school, class_group, teacher_user, coordinator_user, subject
):
    """حصّةُ زميلٍ لا تُقبل مني: الجدولُ المستعلَم هو جدولُ المعلّم الحاليّ وحده."""
    theirs = _session(school, class_group, coordinator_user, subject)

    err = self_slot_error(school, teacher_user, _header(theirs), outside_schedule=False)

    assert "ليست في جدولك" in err
    mine = teacher_schedule_context(school, teacher_user.id, TODAY, self_mode=True)
    assert mine["periods"] == []


def test_the_window_is_checked_even_when_marked_outside(school, teacher_user):
    """«خارج جدولي» لا يفتح النافذة: التاريخُ القديمُ مرفوضٌ بكلّ حال."""
    old = TODAY - dt.timedelta(days=MAX_SELF_BACKDATE_DAYS + 1)
    header = {"observation_date": old.isoformat()}

    assert self_slot_error(school, teacher_user, header, outside_schedule=True) != ""


def test_sessions_are_never_generated_for_a_day_outside_the_window(school, teacher_user):
    """D-381م: الجدولُ المعتمَد للقراءة — لا `ensure_sessions_for_date` لتاريخٍ خارج النافذة."""
    old = TODAY - dt.timedelta(days=MAX_SELF_BACKDATE_DAYS + 3)
    future = TODAY + dt.timedelta(days=3)

    with mock.patch("operations.services.ScheduleService.ensure_sessions_for_date") as ensure:
        for day in (old, future):
            ctx = teacher_schedule_context(school, teacher_user.id, day, self_mode=True)
            assert ctx["periods"] == []
            assert ctx["error"]
        ensure.assert_not_called()


def test_the_supervisor_mode_is_not_limited_by_the_self_window(school, teacher_user):
    """الوضعُ الإشرافيّ كما كان: النافذةُ للتقييم الذاتيّ وحده."""
    old = TODAY - dt.timedelta(days=30)

    with mock.patch("operations.services.ScheduleService.ensure_sessions_for_date") as ensure:
        teacher_schedule_context(school, teacher_user.id, old)
        # الثلاثون يوماً قد تصادف عطلةً فلا يُولَّد شيء — المهمّ ألّا يكون الرفضُ بسبب النافذة.
        ctx = teacher_schedule_context(school, teacher_user.id, old)
    assert "لا يتجاوز" not in ctx["error"]
    assert ensure.call_count in (0, 2)


# ── التواقيع في الـPDF ────────────────────────────────────────────────────
def _obs(school, teacher, observer, kind, status, **extra):
    return ClassroomObservation.objects.create(
        school=school,
        teacher=teacher,
        observer=observer,
        kind=kind,
        status=status,
        **extra,
    )


def test_a_self_assessment_has_no_visitor_stamp_but_keeps_the_teachers(school, teacher_user):
    from django.utils import timezone

    obs = _obs(school, teacher_user, teacher_user, "self", "submitted", submitted_at=timezone.now())

    stamps = signature_stamps(obs)

    assert stamps["visitor"] is None
    assert stamps["teacher"] == {"name": teacher_user.full_name}


def test_a_self_draft_stamps_nobody(school, teacher_user):
    obs = _obs(school, teacher_user, teacher_user, "self", "draft")

    assert signature_stamps(obs) == {"visitor": None, "teacher": None}


def test_a_supervision_visit_still_stamps_the_visitor(school, teacher_user, coordinator_user):
    from django.utils import timezone

    obs = _obs(
        school,
        teacher_user,
        coordinator_user,
        "supervision",
        "submitted",
        submitted_at=timezone.now(),
    )

    stamps = signature_stamps(obs)

    assert stamps["visitor"] == {"name": coordinator_user.full_name}
    assert stamps["teacher"] is None


# ── الحقل والأدمن ─────────────────────────────────────────────────────────
def test_outside_schedule_defaults_to_false(school, teacher_user):
    obs = _obs(school, teacher_user, teacher_user, "self", "draft")

    assert obs.outside_schedule is False


def test_outside_schedule_is_visible_in_django_admin():
    from django.contrib import admin

    model_admin = admin.site._registry[ClassroomObservation]

    assert "outside_schedule" in model_admin.list_display
    assert "outside_schedule" in model_admin.list_filter


# ── المسار الكامل عبر العروض ────────────────────────────────────────────────
def _crits(school, n=2):
    from quality.observation_models import ObservationCriterion

    return [
        ObservationCriterion.objects.create(
            school=school, domain="planning", text=f"معيار {i}", order=i, is_active=True
        )
        for i in range(n)
    ]


def _post(client_as, teacher, crits, *, action="submit", rate_all=True, **extra):
    from django.urls import reverse

    data = {"observation_date": TODAY.isoformat(), "action": action, **extra}
    if rate_all:
        for c in crits:
            data[f"rating_{c.id}"] = "complete"
    return client_as(teacher).post(reverse("observation_self_create"), data)


def test_view_rejects_a_slot_outside_my_schedule(client_as, school, teacher_user):
    r = _post(client_as, teacher_user, _crits(school))
    assert r.status_code == 200
    assert not ClassroomObservation.objects.filter(kind="self").exists()


def test_view_accepts_outside_schedule_and_stores_the_flag(client_as, school, teacher_user):
    r = _post(client_as, teacher_user, _crits(school), outside_schedule="on")
    assert r.status_code == 302
    assert ClassroomObservation.objects.get(kind="self").outside_schedule is True


def test_view_blocks_submit_until_every_criterion_is_rated(client_as, school, teacher_user):
    crits = _crits(school)
    r = _post(client_as, teacher_user, crits[:0], rate_all=False, outside_schedule="on")
    assert r.status_code == 200
    assert not ClassroomObservation.objects.filter(kind="self").exists()
    r = _post(client_as, teacher_user, crits, action="draft", rate_all=False, outside_schedule="on")
    assert r.status_code == 302


def test_view_rejects_a_date_outside_the_window(client_as, school, teacher_user):
    from django.urls import reverse

    old = TODAY - dt.timedelta(days=MAX_SELF_BACKDATE_DAYS + 1)
    data = {"observation_date": old.isoformat(), "action": "draft", "outside_schedule": "on"}
    r = client_as(teacher_user).post(reverse("observation_self_create"), data)
    assert r.status_code == 200
    assert not ClassroomObservation.objects.filter(kind="self").exists()


def test_schedule_endpoint_in_self_mode_ignores_the_teacher_param(
    client_as, school, class_group, teacher_user, coordinator_user, subject
):
    from django.urls import reverse

    _session(school, class_group, coordinator_user, subject)
    r = client_as(teacher_user).get(
        reverse("observation_teacher_schedule"),
        {"self": "1", "teacher": str(coordinator_user.id), "observation_date": TODAY.isoformat()},
    )
    assert r.status_code == 200
    assert list(r.context["periods"]) == []
