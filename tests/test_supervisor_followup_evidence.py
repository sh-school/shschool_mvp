"""قرائنُ المؤشرات 1 و2 و3 في «نموذج 19» (W-20261128-006)."""

import datetime as dt
import uuid

import pytest
from django.db import connection
from django.template.loader import render_to_string
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from core.models.academic import Wing
from operations.models import ClassExit, PeriodConfirmation, Session, StudentAttendance
from quality import supervisor_followup_selectors as selectors
from quality.models import SupervisorFollowUp
from quality.supervisor_followup_evidence import UNAVAILABLE, indicator_evidence
from tests.conftest import (
    BehaviorInfractionFactory,
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    UserFactory,
)

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

# أحدٌ واثنان: يوما دراسة.
SUNDAY = dt.date(2025, 10, 5)
MONDAY = dt.date(2025, 10, 6)


def _member(school, role):
    user = UserFactory()
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def supervisor(school):
    return _member(school, "admin_supervisor")


@pytest.fixture
def vice(school):
    return _member(school, "vice_admin")


@pytest.fixture
def sections(school, supervisor):
    from core.academic_calendar import academic_year_for_school

    year = academic_year_for_school(school, MONDAY)
    wing = Wing.objects.create(
        school=school, code="w1", name="جناح 1", supervisor=supervisor, academic_year=year
    )
    return [ClassGroupFactory(school=school, wing=wing, academic_year=year) for _ in range(2)]


def _session(school, klass, day):
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=_member(school, "teacher"),
        date=day,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
    )


def _legacy(school, klass, day, by):
    PeriodConfirmation.objects.create(
        school=school,
        class_group=klass,
        date=day,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        confirmed_by=by,
        first_confirmed_at=timezone.now(),
    )


def _approved(school, klass, day, by, status="present"):
    StudentAttendance.objects.create(
        school=school,
        session=_session(school, klass, day),
        student=UserFactory(),
        status=status,
        source="teacher",
        marked_by=by,
    )


def _exit(session, *, minutes=0, **fields):
    left = timezone.make_aware(dt.datetime.combine(session.date, dt.time(7, 20)))
    left += dt.timedelta(minutes=minutes)
    return ClassExit.objects.create(
        school=session.school,
        session=session,
        student=fields.pop("student", None) or UserFactory(),
        left_at=left,
        returned_at=left + dt.timedelta(minutes=5),
        **fields,
    )


def _evidence(school, supervisor):
    return indicator_evidence(school, supervisor, SUNDAY, MONDAY)


def test_nothing_recorded_means_unavailable_not_zero(school, supervisor, sections):
    assert _evidence(school, supervisor) == {1: UNAVAILABLE, 2: UNAVAILABLE, 3: UNAVAILABLE}


def test_no_period_means_unavailable(school, supervisor):
    assert set(indicator_evidence(school, supervisor, None, None).values()) == {UNAVAILABLE}
    assert set(indicator_evidence(school, supervisor, MONDAY, SUNDAY).values()) == {UNAVAILABLE}


def test_attendance_counts_only_days_with_every_wing_section_confirmed(
    school, supervisor, sections
):
    first, second = sections
    _legacy(school, first, SUNDAY, supervisor)
    _approved(school, second, SUNDAY, supervisor)  # المساران معاً يكملان اليوم
    _legacy(school, first, MONDAY, supervisor)  # شعبةٌ واحدةٌ لا تكفي
    # تأخّرُ طالبٍ واحدٍ ليس رصداً للشعبة.
    _approved(school, second, MONDAY, supervisor, status="late")
    assert "1 من 2" in _evidence(school, supervisor)[1]
    # بلا جناح: لا قرينة.
    assert _evidence(school, _member(school, "admin_supervisor"))[1] == UNAVAILABLE


def test_class_exits_received_or_returned_by_the_supervisor(school, supervisor, sections):
    session = _session(school, sections[0], SUNDAY)
    later = _session(school, sections[1], SUNDAY)
    _exit(session, routed_by=supervisor)
    original = _exit(session, minutes=1, routed_by=supervisor)
    # امتدادُ الجرس لا يُعدّ خروجاً ثانياً، وتأخّرُ عودته يُنسب لأصله.
    _exit(
        later,
        student=original.student,
        continued_from=original,
        routed_by=supervisor,
        returned_by=supervisor,
        late_return_seconds=90,
    )
    _exit(session, minutes=2, returned_by=supervisor)
    _exit(session, minutes=3, routed_by=_member(school, "admin_supervisor"))
    text = _evidence(school, supervisor)[2]
    assert "عودتَه: 3،" in text and "متأخراً: 1." in text


def test_infractions_reported_by_the_supervisor_and_referrals(school, supervisor):
    # التاريخُ `auto_now_add` فيُقرأ من السجلّ نفسِه لا من الساعة المثبَّتة.
    day = BehaviorInfractionFactory(school=school, reported_by=supervisor).date
    BehaviorInfractionFactory(
        school=school,
        reported_by=supervisor,
        disciplinary_action_type="social_specialist_referral",
    )
    BehaviorInfractionFactory(school=school)  # غيرُه
    BehaviorInfractionFactory(reported_by=supervisor)  # مدرسةٌ أخرى
    text = indicator_evidence(school, supervisor, day, day)[3]
    assert "سجّلها: 2،" in text and "الاجتماعي: 1." in text


def test_query_count_does_not_grow_with_data(school, supervisor, sections):
    session = _session(school, sections[0], SUNDAY)
    _legacy(school, sections[0], SUNDAY, supervisor)
    _exit(session, routed_by=supervisor)
    _evidence(school, supervisor)  # تسخينُ ما يُخبَّأ (العامُ الدراسيّ) قبل العدّ
    with CaptureQueriesContext(connection) as small:
        _evidence(school, supervisor)
    _approved(school, sections[1], MONDAY, supervisor)
    for minutes in range(1, 6):
        _exit(session, minutes=minutes, routed_by=supervisor)
    with CaptureQueriesContext(connection) as big:
        _evidence(school, supervisor)
    assert len(big) == len(small)


def _followup(school, supervisor, vice):
    today = timezone.localdate()
    return SupervisorFollowUp.objects.create(
        pk=uuid.uuid4(),
        school=school,
        supervisor=supervisor,
        follower=vice,
        follow_date=today,
        status="sent",
        period_start=today,
        period_end=today,
    )


def test_evidence_shows_to_the_evaluator_in_form_and_detail(client_as, school, supervisor, vice):
    form = client_as(vice).get(reverse("supervisor_followup_new", args=[supervisor.pk]))
    assert form.content.decode().count("قرينة آلية") == 3
    followup = _followup(school, supervisor, vice)
    detail = client_as(vice).get(reverse("supervisor_followup_detail", args=[followup.pk]))
    assert detail.content.decode().count("قرينة آلية") == 3
    # لا تملأ التقدير.
    assert not followup.scores.exists()


def test_the_supervisor_never_sees_the_evidence(client_as, school, supervisor, vice):
    followup = _followup(school, supervisor, vice)
    response = client_as(supervisor).get(reverse("supervisor_followup_detail", args=[followup.pk]))
    assert response.status_code == 200
    assert "قرينة" not in response.content.decode()


def test_the_pdf_has_no_evidence(school, supervisor, vice):
    followup = _followup(school, supervisor, vice)
    context = selectors.print_context(school, followup)
    html = render_to_string("quality/supervisor_followup_pdf.html", context)
    assert "قرينة" not in html
