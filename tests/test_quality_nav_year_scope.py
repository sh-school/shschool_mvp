"""[CALENDAR] روابط لجنة الجودة في القائمة موقوتةٌ بعام العضويّة.

`QualityCommitteeMember` يحمل `academic_year`، ولا شيء في المنصّة يُطفئ
`is_active` عند دوران العام: الصفّ يُنشأ لعامه ويبقى نشطاً إلى الأبد.
وكان `quality_nav_context` يُرشّح بالمدرسة والمستخدم والنشاط وحدها — فعضو
لجنة المراجعة في «2025-2026» يظلّ يرى رابط المراجعة في «2026-2027»، وهو
وصولٌ لا سند له. والمديران `review_committee` و`executor_committee` كانا
يُرشّحان بالعام أصلاً، فالقائمة وحدها هي التي شذّت.
"""

from datetime import date
from unittest import mock

import pytest
from django.contrib.auth.models import AnonymousUser
from django.test import RequestFactory

from core.context_processors import quality_nav_context
from core.models import AcademicYear
from quality.models import QualityCommitteeMember

TODAY = date(2026, 11, 1)
CURRENT = "2026-2027"
PREVIOUS = "2025-2026"


@pytest.fixture
def calendar(db, school):
    """عامان متتاليان — الجاري يغطّي `TODAY` والسابق انقضى."""
    AcademicYear.objects.create(
        school=school,
        name=PREVIOUS,
        start_date=date(2025, 8, 24),
        end_date=date(2026, 6, 30),
    )
    AcademicYear.objects.create(
        school=school,
        name=CURRENT,
        start_date=date(2026, 8, 23),
        end_date=date(2027, 6, 30),
        is_current=True,
    )
    return school


def _member(school, user, year, committee_type):
    return QualityCommitteeMember.objects.create(
        school=school,
        user=user,
        job_title="منسّق الجودة",
        responsibility="عضو",
        committee_type=committee_type,
        academic_year=year,
        is_active=True,
    )


def _nav(user, on=TODAY):
    """القائمة كما يراها المستخدم في يومٍ بعينه — واليوم مثبَّت لئلّا يتعلّق الحارس بتاريخ تشغيله."""
    request = RequestFactory().get("/")
    request.user = user
    with mock.patch("core.academic_calendar.timezone.localdate", return_value=on):
        return quality_nav_context(request)


# ═══════════════════════════════════════════════════════════════════
#  الحارس
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("committee_type", "flag"),
    [
        (QualityCommitteeMember.REVIEW, "is_quality_reviewer"),
        (QualityCommitteeMember.EXECUTOR, "is_quality_executor"),
    ],
)
def test_a_member_of_the_previous_year_loses_the_link(calendar, teacher_user, committee_type, flag):
    """العضويّة المنقضية لا تُبقي الرابط — وهي نشطةٌ في قاعدة البيانات."""
    member = _member(calendar, teacher_user, PREVIOUS, committee_type)

    assert member.is_active, "الصفّ باقٍ نشطاً — العام وحده هو ما تغيّر"
    assert _nav(teacher_user)[flag] is False


@pytest.mark.parametrize(
    ("committee_type", "flag"),
    [
        (QualityCommitteeMember.REVIEW, "is_quality_reviewer"),
        (QualityCommitteeMember.EXECUTOR, "is_quality_executor"),
    ],
)
def test_a_member_of_the_current_year_keeps_the_link(calendar, teacher_user, committee_type, flag):
    _member(calendar, teacher_user, CURRENT, committee_type)

    assert _nav(teacher_user)[flag] is True


def test_the_two_committees_do_not_leak_into_each_other(calendar, teacher_user):
    """عضو المراجعة الحاليّ لا يُمنح رابط التنفيذ."""
    _member(calendar, teacher_user, CURRENT, QualityCommitteeMember.REVIEW)

    nav = _nav(teacher_user)

    assert (nav["is_quality_reviewer"], nav["is_quality_executor"]) == (True, False)


def test_renewing_the_membership_restores_the_link(calendar, teacher_user):
    """الانقطاع ليس أبديّاً: تجديد العضويّة للعام الجاري يُعيد الرابط."""
    _member(calendar, teacher_user, PREVIOUS, QualityCommitteeMember.REVIEW)
    assert _nav(teacher_user)["is_quality_reviewer"] is False

    _member(calendar, teacher_user, CURRENT, QualityCommitteeMember.REVIEW)

    assert _nav(teacher_user)["is_quality_reviewer"] is True


def test_the_anonymous_visitor_gets_no_quality_flags(db):
    request = RequestFactory().get("/")
    request.user = AnonymousUser()

    assert quality_nav_context(request) == {}
