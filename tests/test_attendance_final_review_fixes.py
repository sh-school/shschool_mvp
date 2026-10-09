"""ملاحظاتُ 0105 الأربع على المراجعة النهائية لـW-20261002-020 — تُسدّ قبل الدمج.

١) قسمُ «تصحيحٌ دون معاينة» وسببُه الحرُّ للقيادة أو حاملِ جناح تلك الحصّة وحدَهما.
٢) اصطدامُ القيد الفريد في التصحيح تعارضٌ (409) لا 500.
٣) `student_id` ليس UUID ← 404، وقيدان لطالبٍ في الشعبة نفسِها لا يكرّران الصفّ.
٤) بديلُ التغطية بدورٍ خارج `WING_DAY_RECORD` (ملاحظُ طلبة أو عاملُ خدمات) يفتح الطابورَ ويقرّر — فالتكليفُ هو الإذن.
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from core.models import Wing
from operations.attendance_entries import (
    correct_without_observation,
    decide_entry,
    submit_entry,
)
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff, at

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


# ٣) نوعُ student_id وتكرارُ القيد


# ٤) بديلُ التغطية بدورٍ خارج WING_DAY_RECORD
