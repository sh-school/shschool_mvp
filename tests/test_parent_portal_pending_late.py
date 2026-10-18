"""[LEGAL] بوّابةُ وليّ الأمر تُخفي «متأخّر» حتى يثبّته المشرف (D-139م، W-20261002-020).

نقرةُ المعلّم «دخل متأخّراً» (`source="teacher_late"`) استثناءٌ مسمّىً من «مبدئيٌّ حتى الاعتماد» (D-136م): تكتب `late` في
`StudentAttendance` فوراً ويثبّتها المشرفُ أو يكتب فوقها. وقرّر المالكُ (D-139م) أنّها **لا تُعرض لوليّ الأمر قبل تثبيت
المشرف** — فتظهر له بعد التثبيت (`source="supervisor"`) وحدَها. والبوّابةُ هنا في `parents/services.py` بمواضعها الأربعة:
العدّاداتُ الشهريّة، وسجلُّ الغياب والتأخّر، ونسبةُ الحضور، واتّجاهُ الأسبوع.

ما لا يتغيّر: غيرُ البوّابة (التقاريرُ ولوحاتُ الموظّفين) يقرؤها كما هي — القرارُ خاصٌّ بوليّ الأمر وحدَه.
"""

import datetime as dt

import pytest
from django.utils import timezone

from core.models import ParentStudentLink
from operations.models import Session, StudentAttendance
from parents.services import ParentService
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import _staff
from tests.conftest import UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


@pytest.fixture
def parent(school, kid):
    user = _staff(school, "parent", "وليّ الأمر", "29000005001")
    ParentStudentLink.objects.create(parent=user, student=kid, school=school)
    return user


@pytest.fixture
def today_session(school, klass, teacher):
    """حصّةٌ اليومَ (بتاريخ الخادم) كي تقع داخل نوافذ «آخر 7/30 يوماً» في البوّابة."""
    return Session.objects.create(
        school=school,
        class_group=klass,
        teacher=teacher,
        date=timezone.now().date(),
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )


def _row(session, kid, source, status="late", minutes=7):
    return StudentAttendance.objects.create(
        session=session,
        student=kid,
        school=session.school,
        status=status,
        late_minutes=minutes if status == "late" else None,
        source=source,
        marked_by=session.teacher,
    )


def test_an_unconfirmed_teacher_tap_is_hidden_from_the_attendance_summary(
    school, kid, today_session
):
    _row(today_session, kid, "teacher_late")
    summary = ParentService.get_student_attendance(kid, school)
    assert summary["late"] == 0
    assert summary["total"] == 0
    assert summary["flagged_days"] == []
    assert summary["days_list"] == []


def test_the_same_late_shows_after_the_supervisor_confirms(school, kid, today_session):
    """التثبيتُ يكتب فوق النقرة بمصدر supervisor — فيراه وليُّ الأمر."""
    _row(today_session, kid, "supervisor")
    summary = ParentService.get_student_attendance(kid, school)
    assert summary["late"] == 1
    assert len(summary["flagged_days"]) == 1


def test_an_absence_is_never_hidden_by_this_rule(school, kid, today_session):
    """الإخفاءُ لنقرة التأخّر وحدَها: غيابٌ بمصدرٍ آخر يظهر كما كان."""
    _row(today_session, kid, "supervisor", status="absent")
    summary = ParentService.get_student_attendance(kid, school)
    assert summary["absent"] == 1


def test_the_monthly_counters_skip_an_unconfirmed_tap(school, parent, kid, today_session):
    _row(today_session, kid, "teacher_late")
    (child,) = ParentService.get_children_data(parent, school)
    assert child["late_30"] == 0


def test_the_monthly_counters_count_a_confirmed_late(school, parent, kid, today_session):
    _row(today_session, kid, "supervisor")
    (child,) = ParentService.get_children_data(parent, school)
    assert child["late_30"] == 1


def test_the_dashboard_attendance_rate_and_week_skip_an_unconfirmed_tap(
    school, parent, kid, today_session
):
    _row(today_session, kid, "teacher_late")
    children = ParentService.get_children_data(parent, school)
    enriched = ParentService.enrich_children_dashboard(children, school)
    (child,) = enriched
    # لا رصدَ معروضٌ لوليّ الأمر بعد: لا نسبةَ حضورٍ تُحسب من نقرةٍ لم تُثبَّت، ولا يومَ في اتّجاه الأسبوع.
    assert child["attendance_pct"] is None
    assert child["week_attendance"] == []


def test_other_readers_still_see_the_tap(school, kid, today_session):
    """القرارُ خاصٌّ بوليّ الأمر: القارئُ العامُّ للجدول يرى النقرةَ كما كان."""
    _row(today_session, kid, "teacher_late")
    assert StudentAttendance.objects.filter(student=kid, status="late").count() == 1


def test_a_second_parent_view_of_another_child_is_unaffected(school, parent, kid, today_session):
    other = UserFactory(full_name="طالبٌ آخر", national_id="29000005002")
    ParentStudentLink.objects.create(parent=parent, student=other, school=school)
    _row(today_session, kid, "teacher_late")
    summary = ParentService.get_student_attendance(other, school)
    assert summary["total"] == 0
