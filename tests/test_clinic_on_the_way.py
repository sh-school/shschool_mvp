"""W-20261128-003: «في الطريق من العيادة» و«لن يعود إلى الفصل» للمشرف والمعلّم — حركةٌ بلا سببٍ صحّيّ."""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from clinic import choices
from clinic.exit_selectors import return_states
from clinic.exit_services import depart_on_close
from clinic.services import ClinicService
from core.models import AuditLog
from operations.models import ClassExit, Session
from tests.test_movement_live import _exit, wing_a, wing_b  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

REASON = "سببٌ-صحّيٌّ-سرّيّ"
ON_WAY = "في الطريق من العيادة"
NO_RETURN = "لن يعود إلى الفصل"


def _left_clinic(school, klass, teacher, nurse, nid, outcome):
    """خروجٌ إلى العيادة استُلم ثمّ أُغلقت زيارتُه بـ`outcome`، ومضت على مغادرته أربعُ دقائق."""
    row = _exit(school, klass, teacher, "طالب العيادة", nid, minutes_ago=20)
    ClassExit.objects.filter(pk=row.pk).update(clinic_arrived_at=row.left_at)
    visit = ClinicService.start_visit(school, row.student, nurse)
    visit.reason = REASON
    visit.save(update_fields=["reason"])
    party = choices.FOLLOWUP_CHOICES[0][0] if outcome == choices.OUTCOME_REFERRAL else ""
    ClinicService.close_visit(visit, outcome, party)
    assert depart_on_close(school, row.student_id, timezone.localdate(), nurse)
    ClassExit.objects.filter(pk=row.pk).update(
        clinic_left_at=timezone.now() - dt.timedelta(minutes=4)
    )
    row.refresh_from_db()
    return row


def _state(school, row):
    return return_states(school, [row], timezone.now()).get(row.pk)


@pytest.mark.parametrize("outcome", [choices.OUTCOME_RETURN, choices.OUTCOME_REFERRAL])
def test_departed_and_unconfirmed_is_on_the_way(school, nurse_user, teacher_user, wing_a, outcome):
    row = _left_clinic(school, wing_a[0], teacher_user, nurse_user, "29000000003", outcome)

    state = _state(school, row)

    assert state is not None and not state.no_return
    assert state.text.startswith(f"{ON_WAY} · منذ ")
    assert state.minutes in (4, 5)
    assert row.returned_at is None


def test_sent_home_will_not_return(school, nurse_user, teacher_user, wing_a):
    row = _left_clinic(
        school, wing_a[0], teacher_user, nurse_user, "29000000004", choices.OUTCOME_LEAVE
    )

    assert _state(school, row).text == NO_RETURN


def test_no_state_before_departure_or_after_return(school, teacher_user, wing_a):
    waiting = _exit(school, wing_a[0], teacher_user, "طالب منتظر", "29000000005")
    back = _exit(school, wing_a[0], teacher_user, "طالب عاد", "29000000006", back_after=2)
    ClassExit.objects.filter(pk=back.pk).update(clinic_left_at=timezone.now())
    back.refresh_from_db()

    assert _state(school, waiting) is None
    assert _state(school, back) is None


def test_bell_continuation_keeps_the_departure(school, nurse_user, teacher_user, wing_a):
    """الجرسُ يُغلق السطرَ آليّاً وينشئ امتداداً: المغادرةُ تُسجَّل وتبقى ظاهرةً."""
    first = _exit(school, wing_a[0], teacher_user, "طالب ممتدّ", "29000000007", minutes_ago=30)
    bell = timezone.now() - dt.timedelta(minutes=10)
    ClassExit.objects.filter(pk=first.pk).update(
        clinic_arrived_at=first.left_at, returned_at=bell, returned_by_role="system"
    )
    session = Session.objects.create(
        school=school,
        class_group=wing_a[0],
        teacher=teacher_user,
        date=timezone.localdate(),
        start_time=dt.time(6, 0),
        end_time=dt.time(7, 0),
        status="scheduled",
    )
    carried = ClassExit.objects.create(
        school=school,
        session=session,
        student=first.student,
        destination="clinic",
        left_at=bell,
        allowed_by=teacher_user,
        continued_from=first,
    )

    assert depart_on_close(school, first.student_id, timezone.localdate(), nurse_user)

    assert _state(school, carried).text.startswith(ON_WAY)
    carried.refresh_from_db()
    assert carried.returned_at is None


@pytest.mark.parametrize(
    "outcome, expected", [(choices.OUTCOME_RETURN, ON_WAY), (choices.OUTCOME_LEAVE, NO_RETURN)]
)
def test_supervisor_live_panel_shows_movement_only_and_audits(
    client, school, nurse_user, teacher_user, wing_a, outcome, expected
):
    klass, supervisor = wing_a
    row = _left_clinic(school, klass, teacher_user, nurse_user, "29000000008", outcome)
    client.force_login(supervisor)

    html = client.get(reverse("student_affairs:movements_live")).content.decode()

    assert expected in html and REASON not in html
    # الوصولُ يؤكّده المشرف بالزرّ القائم.
    assert reverse("student_affairs:movement_return", args=[row.pk]) in html
    assert any(
        str(row.student_id) in log.changes.get("students", [])
        for log in AuditLog.objects.filter(user=supervisor, model_name="ClinicVisit")
    )


def test_student_events_page_shows_the_state_without_reason(
    client, school, nurse_user, teacher_user, wing_a
):
    klass, supervisor = wing_a
    row = _left_clinic(
        school, klass, teacher_user, nurse_user, "29000000009", choices.OUTCOME_RETURN
    )
    client.force_login(supervisor)

    url = reverse("wings:student_events", args=[klass.id, row.student_id])
    html = client.get(url).content.decode()

    assert ON_WAY in html and REASON not in html


def test_other_wing_supervisor_sees_nothing(
    client, school, nurse_user, teacher_user, wing_a, wing_b
):
    _left_clinic(school, wing_a[0], teacher_user, nurse_user, "29000000003", choices.OUTCOME_LEAVE)
    client.force_login(wing_b[1])

    html = client.get(reverse("student_affairs:movements_live")).content.decode()

    assert NO_RETURN not in html and "طالب العيادة" not in html


def test_nurse_cannot_confirm_arrival_in_class(client, school, nurse_user, teacher_user, wing_a):
    row = _left_clinic(
        school, wing_a[0], teacher_user, nurse_user, "29000000004", choices.OUTCOME_RETURN
    )
    client.force_login(nurse_user)

    response = client.post(reverse("student_affairs:movement_return", args=[row.pk]))

    row.refresh_from_db()
    assert response.status_code in (302, 403, 404)
    assert row.returned_at is None
