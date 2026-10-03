"""ملاحظاتُ 0105 الأربع على المراجعة النهائية لـW-20261002-020 — تُسدّ قبل الدمج.

١) قسمُ «تصحيحٌ دون معاينة» وسببُه الحرُّ للقيادة أو حاملِ جناح تلك الحصّة وحدَهما.
٢) اصطدامُ القيد الفريد في التصحيح تعارضٌ (409) لا 500.
٣) `student_id` ليس UUID ← 404، وقيدان لطالبٍ في الشعبة نفسِها لا يكرّران الصفّ.
٤) بديلُ التغطية بدورٍ خارج `WING_DAY_RECORD` (ملاحظُ طلبة أو عاملُ خدمات) يفتح الطابورَ ويقرّر — فالتكليفُ هو الإذن.
"""

import pytest
from django.db import IntegrityError
from django.urls import reverse
from django.utils import timezone

from core.models import Wing
from operations.attendance_entries import (
    EntryConflictError,
    correct_without_observation,
    decide_entry,
    submit_entry,
)
from operations.models import AttendanceDecision, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _cover, _staff, at

pytestmark = pytest.mark.django_db

REASON = "سببٌ حرٌّ لا يراه غيرُ أصحابه"


@pytest.fixture
def now_1300(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(13, 0))


def _corrected(session, teacher, holder, kid):
    entry = submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    decide_entry(holder, entry, approve=True, now=at(7, 31))
    correct_without_observation(
        holder,
        session,
        kid,
        "present",
        reason=REASON,
        evidence_type="gate_log",
        now=at(9, 0),
    )


def _report(client_as, user):
    return client_as(user).get(reverse("attendance_unapproved")).content.decode()


# ١) نطاقُ قسم التصحيحات


def test_1_the_holder_of_that_wing_sees_the_correction(
    client_as, now_1300, session, teacher, holder, kid
):
    _corrected(session, teacher, holder, kid)
    assert REASON in _report(client_as, holder)


def test_1_leadership_sees_the_correction(
    client_as, now_1300, school, session, teacher, holder, kid
):
    _corrected(session, teacher, holder, kid)
    leader = _staff(school, "vice_admin", "النائب", "29000007001")
    assert REASON in _report(client_as, leader)


def test_1_a_supervisor_of_another_wing_does_not_see_the_correction_or_its_reason(
    client_as, now_1300, school, year, session, teacher, holder, kid
):
    _corrected(session, teacher, holder, kid)
    other = _staff(school, "admin_supervisor", "مشرفُ جناحٍ آخر", "29000007002")
    Wing.objects.create(
        school=school, code="w2", name="جناح 2", academic_year=year, supervisor=other
    )
    body = _report(client_as, other)
    assert REASON not in body
    assert "طالب الشعبة" not in body


# ٢) التعارض لا 500


def test_2_a_unique_collision_on_the_correction_is_a_conflict(monkeypatch, session, holder, kid):
    def collide(self, *args, **kwargs):
        raise IntegrityError("duplicate key")

    monkeypatch.setattr(StudentAttendance, "save", collide)
    with pytest.raises(EntryConflictError) as raised:
        correct_without_observation(
            holder, session, kid, "absent", reason="س", evidence_type="gate_log", now=at(9, 0)
        )
    assert raised.value.code == "concurrent"


def test_2_the_screen_answers_409_on_that_collision(
    client_as, monkeypatch, now_1300, session, holder, kid
):
    def collide(self, *args, **kwargs):
        raise IntegrityError("duplicate key")

    monkeypatch.setattr(StudentAttendance, "save", collide)
    response = client_as(holder).post(
        reverse("attendance_correct_submit", args=[session.id]),
        {"student_id": str(kid.id), "status": "absent", "evidence_type": "gate_log", "reason": "س"},
    )
    assert response.status_code == 409


# ٣) نوعُ student_id وتكرارُ القيد


def test_3_a_non_uuid_student_id_is_a_404_not_a_500(client_as, now_1300, session, teacher, holder):
    entry_url = reverse("attendance_entry", args=[session.id])
    correct_url = reverse("attendance_correct_submit", args=[session.id])
    assert (
        client_as(teacher).post(entry_url, {"student_id": "xyz", "status": "absent"}).status_code
        == 404
    )
    response = client_as(holder).post(
        correct_url,
        {"student_id": "xyz", "status": "absent", "evidence_type": "gate_log", "reason": "س"},
    )
    assert response.status_code == 404


def test_3_a_missing_student_id_is_a_404(client_as, now_1300, session, teacher):
    assert (
        client_as(teacher)
        .post(reverse("attendance_entry", args=[session.id]), {"status": "absent"})
        .status_code
        == 404
    )


def test_3_two_enrollments_of_one_student_in_the_class_do_not_break_the_lookup(
    client_as, now_1300, klass, session, teacher, kid
):
    from tests.conftest import StudentEnrollmentFactory

    StudentEnrollmentFactory(student=kid, class_group=klass, is_active=False)
    response = client_as(teacher).post(
        reverse("attendance_entry", args=[session.id]),
        {"student_id": str(kid.id), "status": "present"},
    )
    assert response.status_code == 200


# ٤) بديلُ التغطية بدورٍ خارج WING_DAY_RECORD


@pytest.mark.parametrize("role", ["student_observer", "services_worker"])
def test_4_a_covering_substitute_with_a_non_recording_role_decides_by_assignment(
    client_as, now_1300, school, wing, session, teacher, holder, kid, role
):
    substitute = _staff(school, role, "بديلٌ بالتكليف", "29000007010")
    _cover(wing, substitute, SUNDAY, None, by=holder)
    entry = submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    queue = client_as(substitute).get(reverse("attendance_approvals"))
    assert queue.status_code == 200
    assert "طالب الشعبة" in queue.content.decode()
    decided = client_as(substitute).post(
        reverse("attendance_decide", args=[entry.id]), {"decision": "approve"}
    )
    assert decided.status_code == 200
    assert AttendanceDecision.objects.get(entry=entry).decided_by_id == substitute.id


def test_4_the_original_holder_loses_the_queue_while_the_cover_runs(
    client_as, now_1300, school, wing, session, teacher, holder, kid
):
    substitute = _staff(school, "student_observer", "بديلٌ", "29000007011")
    _cover(wing, substitute, SUNDAY, None, by=holder)
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    assert (
        "طالب الشعبة" not in client_as(holder).get(reverse("attendance_approvals")).content.decode()
    )
