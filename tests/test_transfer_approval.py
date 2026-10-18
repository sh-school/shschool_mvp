"""نقلُ الطالب بين الشعب بطلبٍ واعتماد (W-20261001-017، قرار المالك D-343م).

المنسّق يقدّم، والمدير أو النائب الإداري يعتمد ويُتمّ، ولهما النقل المباشر. ولا إتمامَ قبل الموافقة، والرفضُ بسبب،
ولا يغيّر تعديلُ الطالب الشعبة، والغياب يبقى مع الطالب بعد النقل (D-201م). ولا رقمَ وطنيّاً في أيّ لوج.
"""

import datetime as dt
import logging

import pytest
from django.urls import reverse

from core.capabilities import capability, has_capability
from core.models import StudentEnrollment
from operations.models import StudentAttendance
from student_affairs.models import StudentTransfer
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory
from tests.visual_snapshots import FIXED_NOW

# الساعةُ مثبَّتةٌ: نافذةُ رجوع التاريخ تقرأ «اليوم»، فيُحسب الماضي من اليوم المثبَّت (W-20261008-021).
pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

PAST = FIXED_NOW.date() - dt.timedelta(days=1)  # النقلُ بتاريخٍ ماضٍ محدودٌ بأسبوع


@pytest.fixture
def klass2(school, year, wing):
    return ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
    )


@pytest.fixture
def vice_admin_user(school):
    user = UserFactory(full_name="النائب الإداري")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="vice_admin"))
    return user


@pytest.fixture
def vice_academic_user(school):
    user = UserFactory(full_name="النائب الأكاديمي")
    MembershipFactory(
        user=user, school=school, role=RoleFactory(school=school, name="vice_academic")
    )
    return user


def _request(school, student, target, user, status="pending", date=PAST):
    return StudentTransfer.objects.create(
        school=school,
        student=student,
        direction="internal",
        other_school_name=school.name,
        to_class_group=target,
        transfer_date=date,
        status=status,
        academic_year="2026-2027",
        created_by=user,
        updated_by=user,
    )


def _decide(client, user, transfer, action, notes=""):
    client.force_login(user)
    return client.post(
        reverse("student_affairs:transfer_review", args=[transfer.pk]),
        {"action": action, "notes": notes},
    )


def _active_class(student):
    return StudentEnrollment.objects.get(student=student, is_active=True).class_group


# ── من يملك ماذا ──


def test_only_the_principal_and_the_admin_deputy_may_approve(
    principal_user, vice_admin_user, student_affairs_coordinator_user, teacher_user
):
    assert has_capability(principal_user, "student_affairs.transfer_approve")
    assert has_capability(vice_admin_user, "student_affairs.transfer_approve")
    assert not has_capability(student_affairs_coordinator_user, "student_affairs.transfer_approve")
    assert not has_capability(teacher_user, "student_affairs.transfer_approve")


def test_the_capability_roles_are_exactly_the_principal_and_the_admin_deputy(vice_academic_user):
    """حارسُ مجموعة الأدوار: D-343م تسمّي المدير والنائب الإداري حرفياً، ولا يُزاد عليهما بلا قرار المالك."""
    assert capability("student_affairs.transfer_approve").roles == frozenset(
        {"principal", "vice_admin"}
    )
    assert not has_capability(
        vice_academic_user, "student_affairs.transfer_approve"
    ), "النائب الأكاديمي مراقب (D-271م)"


# ── انتقالات الحالة ──


def test_the_coordinator_submits_but_cannot_approve_reject_or_complete(
    client, school, kid, klass, klass2, student_affairs_coordinator_user
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)

    for action in ("approved", "rejected", "completed"):
        response = _decide(client, student_affairs_coordinator_user, transfer, action, "سبب")
        assert response.status_code == 403, action

    transfer.refresh_from_db()
    assert transfer.status == "pending" and transfer.decided_by is None
    assert _active_class(kid) == klass


def test_approval_records_who_and_when_and_moves_nothing_yet(
    client, school, kid, klass, klass2, principal_user, student_affairs_coordinator_user
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)

    _decide(client, principal_user, transfer, "approved")

    transfer.refresh_from_db()
    assert transfer.status == "approved"
    assert (transfer.decided_by, bool(transfer.decided_at)) == (principal_user, True)
    assert _active_class(kid) == klass


def test_completion_is_refused_before_approval_and_writes_nothing(
    client, school, kid, klass, klass2, principal_user, student_affairs_coordinator_user
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)

    _decide(client, principal_user, transfer, "completed")

    transfer.refresh_from_db()
    assert transfer.status == "pending"
    assert StudentEnrollment.objects.filter(student=kid).count() == 1
    assert _active_class(kid) == klass


def test_an_approved_request_is_completed_by_the_admin_deputy(
    client,
    school,
    kid,
    klass,
    klass2,
    vice_admin_user,
    principal_user,
    student_affairs_coordinator_user,
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)
    _decide(client, principal_user, transfer, "approved")

    _decide(client, vice_admin_user, transfer, "completed")

    transfer.refresh_from_db()
    assert (transfer.status, transfer.decided_by) == ("completed", vice_admin_user)
    assert _active_class(kid) == klass2
    assert not StudentEnrollment.objects.get(student=kid, class_group=klass).is_active


def test_a_rejection_needs_a_reason_and_ends_the_request(
    client, school, kid, klass, klass2, principal_user, student_affairs_coordinator_user
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)

    _decide(client, principal_user, transfer, "rejected", "")
    transfer.refresh_from_db()
    assert transfer.status == "pending", "رفضٌ بلا سببٍ يُردّ"

    _decide(client, principal_user, transfer, "rejected", "الشعبة مكتملة")
    transfer.refresh_from_db()
    assert transfer.status == "rejected" and "الشعبة مكتملة" in transfer.notes
    assert _active_class(kid) == klass

    _decide(client, principal_user, transfer, "approved")
    transfer.refresh_from_db()
    assert transfer.status == "rejected", "المرفوض نهائيّ"


def test_the_submitter_cancels_only_their_own_pending_request(
    client, school, kid, klass2, student_affairs_coordinator_user
):
    other = UserFactory(full_name="منسّق آخر")
    MembershipFactory(
        user=other,
        school=school,
        role=RoleFactory(school=school, name="student_affairs_coordinator"),
    )
    mine = _request(school, kid, klass2, student_affairs_coordinator_user)
    theirs = _request(school, kid, klass2, other)

    assert _decide(client, student_affairs_coordinator_user, theirs, "cancelled").status_code == 403
    _decide(client, student_affairs_coordinator_user, mine, "cancelled")

    mine.refresh_from_db()
    theirs.refresh_from_db()
    assert (mine.status, theirs.status) == ("cancelled", "pending")


def test_the_detail_page_offers_the_decision_form_only_to_the_approvers(
    client, school, kid, klass2, principal_user, student_affairs_coordinator_user
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)
    url = reverse("student_affairs:transfer_detail", args=[transfer.pk])

    client.force_login(student_affairs_coordinator_user)
    submitter_page = client.get(url).content.decode()
    client.force_login(principal_user)
    approver_page = client.get(url).content.decode()

    assert 'id="f-action"' in approver_page and 'type="hidden" name="action"' not in approver_page
    assert 'type="hidden" name="action" value="cancelled"' in submitter_page
    assert 'id="f-action"' not in submitter_page, "المنسّق لا يرى قائمة القرار"
    assert klass2.short_label in approver_page, "الشعبة المنقول إليها ظاهرةٌ في التفاصيل"


# ── النقل المباشر ──


def _direct_post(client, user, kid, target, **extra):
    client.force_login(user)
    data = {
        "student_id": str(kid.pk),
        "direction": "internal",
        "to_class_group_id": str(target.pk),
        "transfer_date": PAST.isoformat(),
        "direct": "1",
        **extra,
    }
    return client.post(reverse("student_affairs:transfer_create"), data)


def test_the_principal_moves_a_student_directly_in_one_step(
    client, school, kid, klass, klass2, principal_user
):
    response = _direct_post(client, principal_user, kid, klass2)

    assert response.status_code == 302
    transfer = StudentTransfer.objects.get()
    assert (transfer.status, transfer.decided_by, transfer.created_by) == (
        "completed",
        principal_user,
        principal_user,
    )
    assert _active_class(kid) == klass2
    assert StudentEnrollment.objects.filter(student=kid).count() == 2, "بلا حذف"


def test_the_coordinator_cannot_move_directly_and_nothing_is_written(
    client, school, kid, klass, klass2, student_affairs_coordinator_user
):
    response = _direct_post(client, student_affairs_coordinator_user, kid, klass2)

    assert response.status_code == 403
    assert not StudentTransfer.objects.exists()
    assert _active_class(kid) == klass


def test_a_direct_move_to_a_future_date_or_another_grade_is_refused_whole(
    client, school, kid, klass, klass2, principal_user
):
    response = _direct_post(client, principal_user, kid, klass2, transfer_date="2099-01-01")

    assert response.status_code == 200
    assert not StudentTransfer.objects.exists()
    assert _active_class(kid) == klass


def test_a_direct_move_is_only_for_internal_requests(client, kid, klass2, principal_user):
    response = _direct_post(
        client, principal_user, kid, klass2, direction="out", other_school_name="مدرسة أخرى"
    )

    assert response.status_code == 200
    assert not StudentTransfer.objects.exists()


def test_the_create_form_shows_the_direct_option_only_to_the_approvers(
    client, principal_user, student_affairs_coordinator_user
):
    url = reverse("student_affairs:transfer_create")

    client.force_login(principal_user)
    approver_page = client.get(url).content.decode()
    client.force_login(student_affairs_coordinator_user)
    submitter_page = client.get(url).content.decode()

    assert 'name="direct"' in approver_page and 'name="direct"' not in submitter_page


# ── D-201م: ما يرحل مع الطالب، وسرّيّة الرقم الوطني ──


def test_the_absence_stays_with_the_student_and_the_old_session_stays_history(
    client, school, kid, klass, klass2, session, principal_user
):
    attendance = StudentAttendance.objects.create(
        session=session, student=kid, school=school, status="absent"
    )

    _direct_post(client, principal_user, kid, klass2)

    attendance.refresh_from_db()
    assert attendance.student_id == kid.pk
    assert attendance.session.class_group == klass, "حصّةٌ قديمةٌ بشعبتها أثرٌ تاريخيّ"
    assert StudentAttendance.objects.filter(student=kid).count() == 1


def test_no_national_id_is_logged_while_deciding(
    client, school, kid, klass2, principal_user, student_affairs_coordinator_user, caplog
):
    transfer = _request(school, kid, klass2, student_affairs_coordinator_user)

    with caplog.at_level(logging.DEBUG):
        _decide(client, principal_user, transfer, "approved")
        _decide(client, principal_user, transfer, "completed")

    assert kid.national_id not in caplog.text
    assert kid.national_id not in transfer.notes
