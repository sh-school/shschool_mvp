"""شاشاتُ رصد المعلّم واعتمادِه: إدخالٌ وطابورٌ وقرارٌ وتقرير، والظهورُ V1–V3 (W-20261002-020).

القاعدةُ في `attendance_policy` وقد اختُبرت بدوالّها؛ وهنا اختبارُ **الواجهات**: من يصل إلى ماذا، وما يُعرض، وأن لا استعلامَ يقفز
على مدرسةٍ أو شعبةٍ (IDOR)، وأنّ المعلَّق لا يظهر حضوراً ولا غياباً.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.attendance_entries import decide_entry, submit_entry
from operations.models import AttendanceDecision, AttendanceEntry, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _staff, at

pytestmark = pytest.mark.django_db


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


@pytest.fixture
def now_1500(monkeypatch):
    """بعد نهاية الدوام (13:30) — خارجَ نافذة الإدخال."""
    monkeypatch.setattr(timezone, "now", lambda: at(15, 0))


def _enter_url(session):
    return reverse("attendance_entry", args=[session.id])


def _post_entry(client_as, user, session, kid, status="absent", **extra):
    return client_as(user).post(
        _enter_url(session), {"student_id": str(kid.id), "status": status, **extra}
    )


def _entry(teacher, session, kid, status="absent"):
    return submit_entry(teacher, session, kid, status, now=at(7, 30))


# ══════════════════════════════════════════════════════════════════
# إدخال المعلّم
# ══════════════════════════════════════════════════════════════════


def test_the_session_teacher_enters_and_the_row_says_pending(
    client_as, now_0730, session, teacher, kid
):
    response = _post_entry(client_as, teacher, session, kid)
    assert response.status_code == 200
    assert "بانتظار الاعتماد" in response.content.decode()
    assert AttendanceEntry.objects.get(session=session, student=kid).status == "absent"
    assert not StudentAttendance.objects.filter(session=session, student=kid).exists()


def test_another_teacher_cannot_enter_a_colleagues_session(
    client_as, now_0730, session, other_teacher, kid
):
    response = _post_entry(client_as, other_teacher, session, kid)
    assert response.status_code == 403
    assert not AttendanceEntry.objects.exists()


def test_entering_before_the_session_starts_is_refused(
    client_as, monkeypatch, session, teacher, kid
):
    monkeypatch.setattr(timezone, "now", lambda: at(6, 0))
    assert _post_entry(client_as, teacher, session, kid).status_code == 403


def test_entering_after_the_school_day_is_refused(client_as, now_1500, session, teacher, kid):
    assert _post_entry(client_as, teacher, session, kid).status_code == 403


def test_a_bad_status_is_a_400_not_a_500(client_as, now_0730, session, teacher, kid):
    assert _post_entry(client_as, teacher, session, kid, status="excused").status_code == 400


def test_an_over_long_correction_reason_is_a_400(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = _entry(teacher, session, kid)
    decide_entry(holder, entry, approve=True, now=at(7, 31))
    response = _post_entry(client_as, teacher, session, kid, "present", reason="س" * 301)
    assert response.status_code == 400


def test_a_student_from_another_class_is_a_404(client_as, now_0730, school, year, session, teacher):
    from tests.conftest import ClassGroupFactory, StudentEnrollmentFactory, UserFactory

    other_class = ClassGroupFactory(
        school=school, grade="G8", section="2", level_type="prep", academic_year=year
    )
    stranger = UserFactory(full_name="غريب", national_id="29000005001")
    StudentEnrollmentFactory(student=stranger, class_group=other_class, enrolled_at=SUNDAY)
    assert _post_entry(client_as, teacher, session, stranger).status_code == 404


def test_a_session_of_another_school_is_a_404(client_as, now_0730, session, teacher, kid):
    from operations.models import Session
    from tests.conftest import SchoolFactory

    other_school = SchoolFactory()
    foreign = Session.objects.create(
        school=other_school,
        class_group=session.class_group,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(9, 0),
        end_time=dt.time(9, 45),
    )
    assert _post_entry(client_as, teacher, foreign, kid).status_code == 404


# ══════════════════════════════════════════════════════════════════
# V1–V3: الظهور
# ══════════════════════════════════════════════════════════════════


def test_v1_the_teacher_sees_the_pending_state_on_his_own_session_page(
    client_as, now_0730, session, teacher, kid
):
    _entry(teacher, session, kid)
    page = client_as(teacher).get(reverse("attendance", args=[session.id]))
    body = page.content.decode()
    assert page.status_code == 200
    assert "بانتظار الاعتماد" in body
    assert "طالب الشعبة" in body


def test_v1_after_the_window_the_session_stays_readable_but_not_editable(
    client_as, now_1500, session, teacher, kid
):
    _entry(teacher, session, kid)
    page = client_as(teacher).get(reverse("attendance", args=[session.id]))
    body = page.content.decode()
    assert page.status_code == 200
    assert "بانتظار الاعتماد" in body
    assert _enter_url(session) not in body


def test_v2_the_pending_entry_is_not_counted_present_or_absent_in_the_summary(
    client_as, now_0730, session, teacher, kid
):
    _entry(teacher, session, kid, "absent")
    context = client_as(teacher).get(reverse("attendance", args=[session.id])).context
    assert context["summary"].get("absent", 0) == 0
    assert context["pending_count"] == 1


def test_v2_an_approved_entry_shows_as_the_effective_status(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = _entry(teacher, session, kid, "absent")
    decide_entry(holder, entry, approve=True, now=at(7, 31))
    context = client_as(teacher).get(reverse("attendance", args=[session.id])).context
    assert context["summary"].get("absent", 0) == 1


def test_v3_another_teacher_cannot_open_a_colleagues_session_page(
    client_as, now_0730, session, other_teacher, kid
):
    assert client_as(other_teacher).get(reverse("attendance", args=[session.id])).status_code == 403


def test_v3_the_rejection_reason_is_not_shown_to_the_teacher(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = _entry(teacher, session, kid)
    decide_entry(holder, entry, approve=False, reason="سببٌ خاصٌّ بالحامل", now=at(7, 31))
    body = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert "لم يُعتمد إدخالُك" in body
    assert "سببٌ خاصٌّ بالحامل" not in body


# ══════════════════════════════════════════════════════════════════
# طابور الاعتماد والقرار
# ══════════════════════════════════════════════════════════════════


def test_the_wing_holder_sees_the_pending_entry_in_his_queue(
    client_as, now_0730, session, teacher, holder, kid
):
    _entry(teacher, session, kid)
    response = client_as(holder).get(reverse("attendance_approvals"))
    assert response.status_code == 200
    assert "طالب الشعبة" in response.content.decode()


def test_a_teacher_cannot_open_the_approvals_queue(client_as, session, teacher):
    assert client_as(teacher).get(reverse("attendance_approvals")).status_code == 403


def test_leadership_does_not_see_what_has_a_holder(
    client_as, school, now_0730, session, teacher, holder, kid
):
    leader = _staff(school, "vice_admin", "النائب", "29000005010")
    _entry(teacher, session, kid)
    body = client_as(leader).get(reverse("attendance_approvals")).content.decode()
    assert "طالب الشعبة" not in body


def test_leadership_sees_it_once_the_holder_is_the_teacher(
    client_as, school, wing, now_0730, session, teacher, kid
):
    wing.supervisor = teacher
    wing.save(update_fields=["supervisor"])
    leader = _staff(school, "vice_admin", "النائب", "29000005011")
    _entry(teacher, session, kid)
    body = client_as(leader).get(reverse("attendance_approvals")).content.decode()
    assert "طالب الشعبة" in body
    assert "بصفة القيادة" in body


def test_the_holder_approves_through_the_screen_and_the_effective_row_appears(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = _entry(teacher, session, kid, "absent")
    response = client_as(holder).post(
        reverse("attendance_decide", args=[entry.id]), {"decision": "approve"}
    )
    assert response.status_code == 200
    assert AttendanceDecision.objects.get(entry=entry).decision == "approved"
    assert StudentAttendance.objects.get(session=session, student=kid).status == "absent"


def test_a_rejection_without_a_reason_is_a_400_and_decides_nothing(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = _entry(teacher, session, kid)
    response = client_as(holder).post(
        reverse("attendance_decide", args=[entry.id]), {"decision": "reject"}
    )
    assert response.status_code == 400
    assert not AttendanceDecision.objects.exists()


def test_a_rejection_with_a_reason_is_recorded(client_as, now_0730, session, teacher, holder, kid):
    entry = _entry(teacher, session, kid)
    client_as(holder).post(
        reverse("attendance_decide", args=[entry.id]),
        {"decision": "reject", "reason": "لم يكن حاضراً"},
    )
    decision = AttendanceDecision.objects.get(entry=entry)
    assert (decision.decision, decision.reason) == ("rejected", "لم يكن حاضراً")
    assert not StudentAttendance.objects.filter(session=session, student=kid).exists()


def test_the_session_teacher_cannot_decide_his_own_entry_through_the_screen(
    client_as, now_0730, session, teacher, kid
):
    entry = _entry(teacher, session, kid)
    response = client_as(teacher).post(
        reverse("attendance_decide", args=[entry.id]), {"decision": "approve"}
    )
    assert response.status_code == 403
    assert not AttendanceDecision.objects.exists()


def test_the_holder_of_another_wing_cannot_decide(
    client_as, school, year, now_0730, session, teacher, kid
):
    from core.models import Wing

    other_holder = _staff(school, "admin_supervisor", "حاملٌ آخر", "29000005020")
    Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other_holder
    )
    entry = _entry(teacher, session, kid)
    response = client_as(other_holder).post(
        reverse("attendance_decide", args=[entry.id]), {"decision": "approve"}
    )
    assert response.status_code == 403
    assert not AttendanceDecision.objects.exists()


def test_an_entry_of_another_school_is_a_404_for_the_decision(
    client_as, now_0730, session, teacher, holder, kid
):
    from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

    other_school = SchoolFactory()
    outsider = UserFactory(full_name="مشرفٌ غريب", national_id="29000005030")
    MembershipFactory(
        user=outsider,
        school=other_school,
        role=RoleFactory(school=other_school, name="admin_supervisor"),
    )
    entry = _entry(teacher, session, kid)
    response = client_as(outsider).post(
        reverse("attendance_decide", args=[entry.id]), {"decision": "approve"}
    )
    assert response.status_code == 404


def test_the_decision_endpoint_rejects_get(client_as, now_0730, session, teacher, holder, kid):
    entry = _entry(teacher, session, kid)
    assert client_as(holder).get(reverse("attendance_decide", args=[entry.id])).status_code == 405


# ══════════════════════════════════════════════════════════════════
# تقرير «غيرُ معتمَد بعد X ساعة»
# ══════════════════════════════════════════════════════════════════


def test_the_unapproved_report_lists_sessions_by_count_without_student_names(
    client_as, school, monkeypatch, session, teacher, holder, kid
):
    _entry(teacher, session, kid)
    monkeypatch.setattr(timezone, "now", lambda: at(13, 0) + dt.timedelta(days=2))
    leader = _staff(school, "vice_admin", "النائب", "29000005040")
    body = client_as(leader).get(reverse("attendance_unapproved") + "?hours=24").content.decode()
    assert "1 إدخال" in body
    assert "طالب الشعبة" not in body
    assert "عند حاملِ الجناح" in body


def test_the_unapproved_report_marks_what_has_no_effective_holder(
    client_as, school, wing, monkeypatch, session, teacher, kid
):
    wing.supervisor = teacher
    wing.save(update_fields=["supervisor"])
    _entry(teacher, session, kid)
    monkeypatch.setattr(timezone, "now", lambda: at(13, 0) + dt.timedelta(days=2))
    leader = _staff(school, "vice_admin", "النائب", "29000005041")
    body = client_as(leader).get(reverse("attendance_unapproved")).content.decode()
    assert "الحاملُ هو المعلّم" in body


def test_the_unapproved_report_is_closed_to_teachers(client_as, session, teacher):
    assert client_as(teacher).get(reverse("attendance_unapproved")).status_code == 403


def test_a_non_numeric_hours_parameter_falls_back_instead_of_failing(
    client_as, school, session, teacher
):
    leader = _staff(school, "vice_admin", "النائب", "29000005042")
    assert client_as(leader).get(reverse("attendance_unapproved") + "?hours=abc").status_code == 200
