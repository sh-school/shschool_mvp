"""فصلُ حكم التصحيح عن حكم الاعتماد (D-271م S1، D-201م): تصحيحُ المشرف لما لم يشاهده باقٍ بسببٍ إلزاميّ حتى لو أُلغي الاعتماد.

كان `can_correct` يعيد `can_approve(...)` حرفاً، فحذفُ الاعتماد كان سيكسر التصحيح؛ بل كان يرفضه اليومَ في الجلسة النهائيّة (`final_entry`).
الآن: يصحّح حاملُ الجناح الفعليّ يومَ الحصّة، وحاصرُ الغياب العامّ، والمديرُ والنائبُ الإداريّ حين لا حاملَ؛ لا معلّمُ الحصّة ولا المطوّر
ولا النائبُ الأكاديميّ (يراقب فقط) ولا من خارج المدرسة.
"""

import pytest

from operations.attendance_policy import can_approve, can_correct
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff

pytestmark = pytest.mark.django_db


def test_the_wing_holder_corrects(session, holder):
    assert can_correct(holder, session).allowed


def test_correction_is_independent_of_approval_in_a_final_entry_session(
    settings, session, holder, klass
):
    """الجلسةُ النهائيّة: الاعتمادُ مرفوضٌ بسبب `final_entry` والتصحيحُ مقبول."""
    settings.PROVISIONAL_GRID_ENABLED = True
    settings.ATTENDANCE_GRID_DIRECT_WINGS = "*"

    assert not can_approve(holder, session).allowed
    assert can_approve(holder, session).reason == "final_entry"
    assert can_correct(holder, session).allowed


def test_the_teacher_of_the_session_never_corrects_their_own(session, teacher):
    verdict = can_correct(teacher, session)
    assert not verdict.allowed and verdict.reason == "own_session"


def test_the_developer_never_corrects(school, session):
    developer = _staff(school, "platform_developer", "المطوّر", "29000003001")
    verdict = can_correct(developer, session)
    assert not verdict.allowed and verdict.reason == "developer"


def test_someone_outside_the_school_never_corrects(session):
    from tests.conftest import UserFactory

    stranger = UserFactory(full_name="غريب", national_id="29000003002")
    assert not can_correct(stranger, session).allowed


def test_another_wings_holder_may_not_correct(school, session, holder):
    other = _staff(school, "admin_supervisor", "مشرفُ جناحٍ آخر", "29000003003")
    verdict = can_correct(other, session)
    assert not verdict.allowed and verdict.reason == "not_holder"


def test_the_school_wide_absence_holder_corrects(school, session, holder):
    from core import capability_grants as grants

    principal = _staff(school, "principal", "المدير", "29000003004")
    general = _staff(school, "admin_supervisor", "حاصرُ الغياب", "29000003005")
    grants.grant(
        user=general,
        capability="wings.school_wide",
        by=principal,
        reason="حصرُ الغياب في المدرسة كلِّها بتكليفٍ من الإدارة",
    )

    assert can_correct(general, session).allowed


def test_leadership_corrects_only_when_there_is_no_holder_and_the_deputy_academic_never(
    school, special_klass, teacher, bells
):
    """شعبةٌ بلا جناح (لا حامل): المديرُ والنائبُ الإداريّ يصحّحان، والنائبُ الأكاديميّ مراقبٌ فقط (D-201م)."""
    import datetime as dt

    from operations.models import Session
    from tests.attendance_fixtures import SUNDAY

    orphan = Session.objects.create(
        school=school,
        class_group=special_klass,
        teacher=teacher,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )
    principal = _staff(school, "principal", "المدير", "29000003006")
    vice_admin = _staff(school, "vice_admin", "النائب الإداري", "29000003007")
    vice_academic = _staff(school, "vice_academic", "النائب الأكاديمي", "29000003008")

    assert can_correct(principal, orphan).allowed
    assert can_correct(vice_admin, orphan).allowed
    verdict = can_correct(vice_academic, orphan)
    assert not verdict.allowed and verdict.reason == "not_holder"


def test_leadership_does_not_override_an_existing_holder(school, session, holder):
    """وجودُ حاملٍ فعليٍّ ← هو وحاصرُ الغياب العامّ وحدَهما؛ المديرُ لا يزاحمه."""
    principal = _staff(school, "principal", "المدير", "29000003009")

    verdict = can_correct(principal, session)

    assert not verdict.allowed and verdict.reason == "not_holder"


def test_a_school_wide_absence_role_is_covered_through_the_holder_check_not_by_name(
    school, session, holder
):
    """منسّقُ شؤون الطلبة (D-266م) حاصرُ غيابٍ عامّ بدوره في #895: يُغطّى تلقائياً عبر `holds_school_wide` دون ذكر اسمه في الكود.

    نُحاكي ذلك بدورٍ وهميٍّ يعيد `holds_school_wide` له (قبل دمج #895 لا يملك الدورُ هذه الصفة فيُرفض).
    """
    from unittest.mock import patch

    coordinator = _staff(school, "student_affairs_coordinator", "منسّق شؤون الطلبة", "29000003010")

    assert not can_correct(coordinator, session).allowed, "قبل صفة حاصر الغياب العامّ: مرفوض"
    with patch("wings.services.holds_school_wide", lambda user: user.id == coordinator.id):
        assert can_correct(coordinator, session).allowed
