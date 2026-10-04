"""[W-20261004-014] شبكةُ المشرف تعرض إدخالَ المعلّم المبدئيّ كما تعرضه صفحةُ المعلّم، ويعتمده الحاملُ في مكانه.

كانت الشبكةُ (`wings:record_section`) تقرأ ما رصده المشرفُ وحدَه (`source=supervisor`) فلا ترى إدخالاً معلَّقاً ولا ما اعتُمد من إدخال المعلّم،
واعتمادُه في صفحةٍ منفصلة. الآن: علامةٌ بحالة الإدخال في خليّة الطالب/الحصّة (معلَّق، معتمَد، لم يُعتمد، تصحيح دون معاينة)، وزرُّ اعتمادٍ
لمن يملك `can_approve` وحدَه، ورفضٌ يبقى في صفحة الاعتماد لأنّ الرفضَ يلزمه سبب. ولا تغييرَ لكتابة الحامل المباشرة (`confirm_period`).
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.attendance_entries import decide_entry, submit_entry
from operations.models import StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _staff, at

pytestmark = pytest.mark.django_db

REASON = "سببٌ حرٌّ لا يُعرض في الشبكة"


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


def _grid(client_as, user, klass):
    return client_as(user).get(
        reverse("wings:record_section", args=[klass.id]), {"date": SUNDAY.isoformat()}
    )


def _entry(teacher, session, kid, status="absent"):
    return submit_entry(teacher, session, kid, status, now=at(7, 30))


def test_a_pending_teacher_entry_shows_in_the_holders_grid_with_an_approve_button(
    client_as, now_0730, klass, session, teacher, holder, kid
):
    entry = _entry(teacher, session, kid)
    response = _grid(client_as, holder, klass)
    html = response.content.decode()
    assert response.status_code == 200
    assert "المعلّم: غائب — بانتظار الاعتماد" in html
    assert reverse("attendance_decide", args=[entry.id]) in html
    assert "ينتظر اعتمادك في هذه الشعبة" in html


def test_a_leader_who_cannot_decide_sees_the_badge_but_no_approve_button(
    client_as, now_0730, klass, session, teacher, holder, kid, school
):
    """القيادةُ ترى الحالةَ، لكنّ القرارَ للحامل ما دام للجناح حاملٌ فعليّ (can_approve)."""
    entry = _entry(teacher, session, kid)
    vice = _staff(school, "vice_admin", "نائب", "29000001030")
    html = _grid(client_as, vice, klass).content.decode()
    assert "المعلّم: غائب — بانتظار الاعتماد" in html
    assert reverse("attendance_decide", args=[entry.id]) not in html
    assert "ينتظر اعتمادك" not in html


def test_the_teacher_has_no_access_to_the_wing_grid(
    client_as, now_0730, klass, session, teacher, kid
):
    _entry(teacher, session, kid)
    response = _grid(client_as, teacher, klass)
    assert response.status_code in (302, 403)
    assert kid.full_name not in response.content.decode()


def test_approving_from_the_grid_cell_writes_the_effective_row_and_redraws_the_mark(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = _entry(teacher, session, kid)
    response = client_as(holder).post(
        reverse("attendance_decide", args=[entry.id]),
        {"decision": "approve", "surface": "grid"},
    )
    html = response.content.decode()
    assert response.status_code == 200
    assert "المعلّم: معتمَد غائب" in html
    assert 'id="mark-' in html and "<li" not in html  # علامةٌ وحدَها لا بطاقةُ الطابور
    row = StudentAttendance.objects.get(session=session, student=kid)
    assert (row.status, row.source) == ("absent", "teacher")


def test_a_wrong_user_cannot_approve_from_the_grid(
    client_as, now_0730, session, teacher, kid, school
):
    entry = _entry(teacher, session, kid)
    other = _staff(school, "admin_supervisor", "مشرف آخر", "29000001031")
    response = client_as(other).post(
        reverse("attendance_decide", args=[entry.id]), {"decision": "approve", "surface": "grid"}
    )
    assert response.status_code == 403
    assert not StudentAttendance.objects.filter(session=session, student=kid).exists()


def test_after_approval_the_grid_shows_the_approved_state_not_the_button(
    client_as, now_0730, klass, session, teacher, holder, kid
):
    entry = _entry(teacher, session, kid)
    decide_entry(holder, entry, True, now=at(7, 40))
    html = _grid(client_as, holder, klass).content.decode()
    assert "المعلّم: معتمَد غائب" in html
    assert reverse("attendance_decide", args=[entry.id]) not in html
    assert "بانتظار الاعتماد" not in html


def test_a_rejected_entry_shows_its_state_without_the_reason(
    client_as, now_0730, klass, session, teacher, holder, kid
):
    entry = _entry(teacher, session, kid)
    decide_entry(holder, entry, False, reason=REASON, now=at(7, 40))
    html = _grid(client_as, holder, klass).content.decode()
    assert "لم يُعتمد إدخالُ المعلّم" in html
    assert REASON not in html


def test_the_grid_is_unchanged_when_no_teacher_entered_anything(
    client_as, now_0730, klass, session, holder, kid
):
    html = _grid(client_as, holder, klass).content.decode()
    assert "rec-entry" not in html
    assert "ينتظر اعتمادك" not in html
