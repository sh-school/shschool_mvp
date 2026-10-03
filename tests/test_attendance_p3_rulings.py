"""حكمُ 0105 P3: سقفُ سبب الرفض/التصحيح، وتصحيحُ طالبٍ نُقل بعد الحصّة (W-20261002-020).

- **السبب نصٌّ حرٌّ** يُكتب في سجلّ التدقيق، وقد يحمل اسماً أو معلومةً صحّيّة: سقفُه 300 حرف (كما في mark للكادر).
- **الطالبُ المنقول:** القيدُ النشطُ الحاليُّ شرطٌ لأوّل إدخالٍ فقط. من أُدخل له رصدٌ في هذه الحصّة وهو في شعبتها ثمّ نُقل قبل
  أن يصحّح المعلّمُ يُصحَّح له في نافذة اليوم — القرارُ: الرصدُ حدثٌ وقع في الحصّة لا حالةُ قيدٍ اليوم.
"""

import pytest

from operations.attendance_entries import (
    MAX_REASON_LENGTH,
    EntryError,
    EntryRefusedError,
    decide_entry,
    submit_entry,
)
from operations.attendance_policy import can_enter
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at

pytestmark = pytest.mark.django_db

NOW = at(7, 30)
LATER = at(9, 0)


def _transfer_out(kid):
    kid.enrollments.update(is_active=False)


def test_a_student_transferred_after_the_entry_can_still_be_corrected_in_the_window(
    session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=NOW)
    decide_entry(holder, entry, approve=True, now=NOW)
    _transfer_out(kid)
    assert can_enter(teacher, session, kid, now=LATER)
    corrected = submit_entry(
        teacher, session, kid, "present", now=LATER, correction_reason="خطأ في الرصد"
    )
    assert corrected.supersedes_id == entry.pk


def test_a_student_transferred_before_any_entry_is_still_not_enrolled(session, teacher, kid):
    _transfer_out(kid)
    verdict = can_enter(teacher, session, kid, now=NOW)
    assert not verdict
    assert verdict.reason == "not_enrolled"


def test_a_transferred_student_with_no_entry_in_this_session_is_not_corrected_by_another_sessions_entry(
    school, klass, session, teacher, kid, bells
):
    import datetime as dt

    from operations.models import Session

    other = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=session.date,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    submit_entry(teacher, other, kid, "absent", now=at(8, 10))
    _transfer_out(kid)
    assert can_enter(teacher, session, kid, now=NOW).reason == "not_enrolled"


def test_a_correction_reason_over_the_cap_is_refused(session, teacher, holder, kid):
    entry = submit_entry(teacher, session, kid, "absent", now=NOW)
    decide_entry(holder, entry, approve=True, now=NOW)
    with pytest.raises(EntryError) as raised:
        submit_entry(
            teacher,
            session,
            kid,
            "present",
            now=LATER,
            correction_reason="س" * (MAX_REASON_LENGTH + 1),
        )
    assert raised.value.code == "reason_too_long"


def test_a_correction_reason_at_the_cap_is_accepted(session, teacher, holder, kid):
    entry = submit_entry(teacher, session, kid, "absent", now=NOW)
    decide_entry(holder, entry, approve=True, now=NOW)
    corrected = submit_entry(
        teacher,
        session,
        kid,
        "present",
        now=LATER,
        correction_reason="س" * MAX_REASON_LENGTH,
    )
    assert len(corrected.correction_reason) == MAX_REASON_LENGTH


def test_a_rejection_reason_over_the_cap_is_refused_and_decides_nothing(
    session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=NOW)
    with pytest.raises(EntryError) as raised:
        decide_entry(holder, entry, approve=False, reason="س" * (MAX_REASON_LENGTH + 1))
    assert raised.value.code == "reason_too_long"
    from operations.models import AttendanceDecision

    assert not AttendanceDecision.objects.exists()


def test_the_cap_does_not_hide_a_policy_refusal(session, other_teacher, kid):
    with pytest.raises(EntryRefusedError):
        submit_entry(other_teacher, session, kid, "absent", now=NOW)
