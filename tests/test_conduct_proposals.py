"""اقتراحاتُ المخالفة 1-01 لغيابٍ أو تأخّرٍ بين الحصص (W-20261013-034): التوليد والتوقيت والفرادة والاعتماد والصلاحية."""

import datetime as dt

import pytest
from django.urls import reverse

from behavior.models import BehaviorInfraction, ViolationCategory
from operations.models import StudentAttendance
from tests.test_period_register import (  # noqa: F401
    SUNDAY,
    _auto,
    _confirm,
    _periods,
    kids,
    klass,
    supervisor,
    teacher,
    year,
)
from tests.test_school_wide_absence_supervisor import _staff, general, principal  # noqa: F401
from wings import conduct_services as service
from wings.models import ConductProposal
from wings.scope import student_scope

pytestmark = pytest.mark.django_db

#: الظهور في يوم الواقعة نفسه (قرارُ المالك 2026-10-30): قبله لا شيء.
BEFORE = dt.date(2026, 9, 12)
AFTER = SUNDAY


@pytest.fixture
def category(school):
    return ViolationCategory.objects.get_or_create(
        code="1-01", defaults={"name_ar": "التأخّر أو عدم حضور الحصّة", "degree": 1}
    )[0]


def _day(klass, supervisor, teacher, school, marks_by_period, count=7):
    """يثبّت حصصَ اليوم؛ `marks_by_period` = {رقمُ الحصّة من 0: {طالب: حالة}}."""
    sessions = _periods(school, klass, teacher, count=count)
    for i, session in enumerate(sessions):
        _confirm(klass, session, marks_by_period.get(i, {}), supervisor)
    return sessions


def test_a_regular_student_missing_two_early_periods_gets_one_proposal(
    school, klass, kids, supervisor, teacher
):
    a = kids[0]
    _day(klass, supervisor, teacher, school, {0: {a: "absent"}, 1: {a: "absent"}})
    stats = service.generate_for_day(school, SUNDAY)
    assert stats["created"] == 1
    proposal = ConductProposal.objects.get()
    assert (proposal.student, proposal.kind, proposal.status) == (a, "absence", "proposed")
    assert proposal.periods == ["07:10", "08:10"]
    # التوليدُ ثانيةً لا يكرّر ولا يغيّر شيئاً.
    again = service.generate_for_day(school, SUNDAY)
    assert again == {"created": 0, "updated": 0, "withdrawn": 0}
    assert ConductProposal.objects.count() == 1


def test_it_appears_on_the_day_itself_not_before(school, klass, kids, supervisor, teacher):
    _day(klass, supervisor, teacher, school, {0: {kids[0]: "absent"}})
    service.generate_for_day(school, SUNDAY)
    scope = student_scope(supervisor, school)
    assert service.queue_for(school, scope, BEFORE) == []
    assert [p.student for p in service.queue_for(school, scope, AFTER)] == [kids[0]]


def test_fewer_than_four_attended_periods_is_not_regular(school, klass, kids, supervisor, teacher):
    marks = {i: {kids[0]: "absent"} for i in range(0, 4)}
    _day(klass, supervisor, teacher, school, marks)  # حضر ثلاثاً فقط
    assert service.generate_for_day(school, SUNDAY)["created"] == 0


def test_absence_between_two_attendances_is_the_automatic_escape_not_a_proposal(
    school, klass, kids, supervisor, teacher
):
    a = kids[0]
    _day(klass, supervisor, teacher, school, {3: {a: "absent"}})
    assert _auto(a, "class_escape").count() == 1
    assert service.generate_for_day(school, SUNDAY)["created"] == 0


def test_a_tardy_after_an_attended_period_is_proposed_but_the_first_period_is_not(
    school, klass, kids, supervisor, teacher
):
    a, b = kids[0], kids[1]
    _day(
        klass,
        supervisor,
        teacher,
        school,
        {
            0: {b: {"status": "late", "late_minutes": 12}},  # تأخّرٌ صباحيٌّ: آليّتُه القائمة
            2: {a: {"status": "late", "late_minutes": 10}},
        },
    )
    service.generate_for_day(school, SUNDAY)
    proposal = ConductProposal.objects.get()
    assert (proposal.student, proposal.kind) == (a, "tardy")


def test_an_accepted_excuse_withdraws_an_unapproved_proposal_and_spares_an_approved_one(
    school, klass, kids, supervisor, teacher, category
):
    a, b = kids[0], kids[1]
    _day(klass, supervisor, teacher, school, {0: {a: "absent", b: "absent"}})
    service.generate_for_day(school, SUNDAY)
    scope = student_scope(supervisor, school)
    keep = ConductProposal.objects.get(student=b)
    service.approve(keep.pk, supervisor, scope, AFTER)
    StudentAttendance.objects.filter(student__in=[a, b], session__date=SUNDAY).update(
        status="excused", excuse_type="medical"
    )
    stats = service.generate_for_day(school, SUNDAY)
    assert stats["withdrawn"] == 1
    assert ConductProposal.objects.get(student=a).status == "withdrawn"
    assert ConductProposal.objects.get(student=b).status == "approved"


def test_approval_makes_one_first_degree_infraction_without_notice_and_is_idempotent(
    school, klass, kids, supervisor, teacher, category
):
    a = kids[0]
    _day(klass, supervisor, teacher, school, {0: {a: "absent"}})
    service.generate_for_day(school, SUNDAY)
    proposal = ConductProposal.objects.get()
    scope = student_scope(supervisor, school)
    done = service.approve(proposal.pk, supervisor, scope, AFTER)
    service.approve(proposal.pk, supervisor, scope, AFTER)
    infraction = BehaviorInfraction.objects.get(student=a)
    assert (done.status, done.decided_by, done.infraction) == ("approved", supervisor, infraction)
    assert infraction.level == 1 and infraction.auto_rule == ""
    assert infraction.violation_category.code == "1-01"
    assert BehaviorInfraction.objects.count() == 1


def test_an_excuse_accepted_after_it_appeared_blocks_the_approval(
    school, klass, kids, supervisor, teacher, category
):
    from operations.models import AbsenceExcuse

    a = kids[0]
    _day(klass, supervisor, teacher, school, {0: {a: "absent"}})
    service.generate_for_day(school, SUNDAY)
    AbsenceExcuse.objects.create(
        school=school,
        student=a,
        date_from=SUNDAY,
        date_to=SUNDAY,
        kind="medical",
        status="accepted",
        granted_by=supervisor,
    )
    scope = student_scope(supervisor, school)
    with pytest.raises(service.ProposalError):
        service.approve(ConductProposal.objects.get().pk, supervisor, scope, AFTER)
    assert BehaviorInfraction.objects.count() == 0


def test_approval_before_the_day_is_refused(school, klass, kids, supervisor, teacher, category):
    _day(klass, supervisor, teacher, school, {0: {kids[0]: "absent"}})
    service.generate_for_day(school, SUNDAY)
    scope = student_scope(supervisor, school)
    with pytest.raises(service.ProposalError):
        service.approve(ConductProposal.objects.get().pk, supervisor, scope, BEFORE)
    assert BehaviorInfraction.objects.count() == 0


def test_reject_closes_it_without_an_infraction(school, klass, kids, supervisor, teacher):
    _day(klass, supervisor, teacher, school, {0: {kids[0]: "absent"}})
    service.generate_for_day(school, SUNDAY)
    scope = student_scope(supervisor, school)
    done = service.reject(ConductProposal.objects.get().pk, supervisor, scope, AFTER)
    assert done.status == "rejected" and BehaviorInfraction.objects.count() == 0


def test_the_supervisor_sees_the_page_but_the_school_wide_observer_does_not(
    client_as, school, klass, kids, supervisor, teacher, general
):
    _day(klass, supervisor, teacher, school, {0: {kids[0]: "absent"}})
    service.generate_for_day(school, SUNDAY)
    url = reverse("wings:conduct_proposals")
    page = client_as(supervisor).get(url)
    assert page.status_code == 200 and kids[0].full_name in page.content.decode()
    assert client_as(general).get(url).status_code in (302, 403)
    pk = ConductProposal.objects.get().pk
    post = client_as(general).post(
        reverse("wings:conduct_proposal_decide", args=[pk]), {"decision": "approve"}
    )
    assert post.status_code in (302, 403)
    assert ConductProposal.objects.get().status == "proposed"


def test_a_whole_trailing_streak_is_the_school_escape_and_proposes_nothing(
    school, klass, kids, supervisor, teacher
):
    """غيابُ آخر اليوم متّصلاً: هروبٌ من المدرسة (3-10) يُنشئه الرصد، فلا يُقترح لأيٍّ من حصصه (مراجعة Copilot)."""
    a = kids[0]
    _day(klass, supervisor, teacher, school, {i: {a: "absent"} for i in (4, 5, 6)})
    assert _auto(a, "school_escape").count() == 1
    assert service.generate_for_day(school, SUNDAY)["created"] == 0


def test_a_changed_kind_updates_the_same_row_instead_of_adding_another(
    school, klass, kids, supervisor, teacher
):
    a = kids[0]
    sessions = _day(klass, supervisor, teacher, school, {0: {a: "absent"}})
    service.generate_for_day(school, SUNDAY)
    StudentAttendance.objects.filter(student=a, session=sessions[0]).update(status="present")
    StudentAttendance.objects.filter(student=a, session=sessions[2]).update(
        status="late", late_minutes=10
    )
    assert service.generate_for_day(school, SUNDAY)["updated"] == 1
    proposal = ConductProposal.objects.get()
    assert (proposal.kind, proposal.status) == ("tardy", "proposed")


def test_a_decided_proposal_is_final_even_if_the_kind_changes(
    school, klass, kids, supervisor, teacher
):
    a = kids[0]
    sessions = _day(klass, supervisor, teacher, school, {0: {a: "absent"}})
    service.generate_for_day(school, SUNDAY)
    scope = student_scope(supervisor, school)
    service.reject(ConductProposal.objects.get().pk, supervisor, scope, AFTER)
    StudentAttendance.objects.filter(student=a, session=sessions[0]).update(status="present")
    StudentAttendance.objects.filter(student=a, session=sessions[2]).update(
        status="late", late_minutes=10
    )
    assert service.generate_for_day(school, SUNDAY) == {"created": 0, "updated": 0, "withdrawn": 0}
    proposal = ConductProposal.objects.get()
    assert (proposal.kind, proposal.status) == ("absence", "rejected")


def test_a_supervisor_decision_between_read_and_write_is_not_overwritten(
    school, klass, kids, supervisor, teacher, monkeypatch
):
    _day(klass, supervisor, teacher, school, {0: {kids[0]: "absent"}})
    service.generate_for_day(school, SUNDAY)
    real = service.evaluate_day

    def decided_meanwhile(*args):
        found = real(*args)
        ConductProposal.objects.update(status="rejected")  # قرارُ مشرفٍ بعد قراءة الحالة
        return found

    ConductProposal.objects.update(note="قديمة")
    monkeypatch.setattr(service, "evaluate_day", decided_meanwhile)
    stats = service.generate_for_day(school, SUNDAY)
    assert stats["updated"] == 0
    assert ConductProposal.objects.get().status == "rejected"


def test_approval_is_refused_when_the_attendance_was_corrected_after_it_appeared(
    school, klass, kids, supervisor, teacher, category
):
    a = kids[0]
    sessions = _day(klass, supervisor, teacher, school, {0: {a: "absent"}})
    service.generate_for_day(school, SUNDAY)
    StudentAttendance.objects.filter(student=a, session=sessions[0]).update(status="present")
    scope = student_scope(supervisor, school)
    with pytest.raises(service.ProposalError):
        service.approve(ConductProposal.objects.get().pk, supervisor, scope, AFTER)
    assert BehaviorInfraction.objects.count() == 0


def test_approval_is_refused_when_the_tardy_was_corrected_after_it_appeared(
    school, klass, kids, supervisor, teacher, category
):
    a = kids[0]
    marks = {2: {a: {"status": "late", "late_minutes": 10}}}
    sessions = _day(klass, supervisor, teacher, school, marks)
    service.generate_for_day(school, SUNDAY)
    StudentAttendance.objects.filter(student=a, session=sessions[2]).update(
        status="present", late_minutes=None
    )
    scope = student_scope(supervisor, school)
    with pytest.raises(service.ProposalError):
        service.approve(ConductProposal.objects.get().pk, supervisor, scope, AFTER)
    assert BehaviorInfraction.objects.count() == 0


def test_the_proposals_link_shows_only_to_whoever_holds_a_wing(
    client_as, school, klass, kids, supervisor, teacher, general
):
    link = reverse("wings:conduct_proposals")
    mine = client_as(supervisor).get(reverse("wings:record_index"))
    assert mine.status_code == 200 and link in mine.content.decode()
    other = client_as(general).get(reverse("wings:record_index"))
    assert link not in other.content.decode()
