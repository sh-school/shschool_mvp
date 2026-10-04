"""[W-20261004-014] رصدُ المعلّم في شُعب الأجنحة بالسهولة نفسِها التي كانت للمشرف في شبكته: ضغطةٌ واحدةٌ للطالب و«الكلُّ حاضر».

كانت خليّةُ المعلّم قائمةً منسدلةً ثمّ زرَّ «إدخال» (ثلاثُ حركاتٍ لكلّ طالب)، فصارت ثلاثةَ أزرارٍ (حاضر · غائب · متأخّر) تُدخل فوراً. وللحصّة «الكلُّ حاضر»
لمن لم يُدخَل له شيء. والإدخالُ مبدئيٌّ يعتمده حاملُ الجناح كما قرّر المالك (D-125م): لا يصل `StudentAttendance` إلّا المعتمَد.
"""

import datetime as dt
import uuid

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.attendance_entries import decide_entry, submit_entry
from operations.models import AttendanceEntry, Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, at
from tests.conftest import StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


@pytest.fixture
def now_1500(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(15, 0))


@pytest.fixture
def second_kid(school, klass):
    student = UserFactory(full_name="طالبٌ ثانٍ", national_id="29000001002")
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
    return student


def _page(client_as, user, session):
    return client_as(user).get(reverse("attendance", args=[session.id]))


def test_the_teacher_page_offers_one_tap_buttons_not_a_select(
    client_as, now_0730, session, teacher, kid
):
    html = _page(client_as, teacher, session).content.decode()
    assert html.count('class="att-btn is-present') >= 1
    for status in ("present", "absent", "late"):
        assert f'"status": "{status}"' in html
    assert 'name="status"' not in html  # لا قائمةَ منسدلةً لمن لم يُعتمد رصدُه
    assert reverse("attendance_entry_all", args=[session.id]) in html
    assert "الكلُّ حاضر" in html


def test_one_tap_enters_a_pending_entry_without_touching_the_effective_row(
    client_as, now_0730, session, teacher, kid
):
    response = client_as(teacher).post(
        reverse("attendance_entry", args=[session.id]),
        {"student_id": str(kid.id), "status": "absent"},
    )
    assert response.status_code == 200
    assert "بانتظار الاعتماد" in response.content.decode()
    assert AttendanceEntry.objects.get(session=session, student=kid).status == "absent"
    assert not StudentAttendance.objects.filter(session=session, student=kid).exists()


def test_all_present_enters_pending_entries_for_everyone_without_one(
    client_as, now_0730, session, teacher, kid, second_kid
):
    response = client_as(teacher).post(reverse("attendance_entry_all", args=[session.id]))
    assert response.status_code == 302
    assert response.url == reverse("attendance", args=[session.id])
    entries = AttendanceEntry.objects.filter(session=session)
    assert {e.student_id for e in entries} == {kid.id, second_kid.id}
    assert {e.status for e in entries} == {"present"}
    assert not StudentAttendance.objects.filter(session=session).exists()  # مبدئيٌّ حتى الاعتماد


def test_all_present_never_overwrites_an_existing_entry_or_an_approved_row(
    client_as, now_0730, session, teacher, holder, kid, second_kid
):
    mine = submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    done = submit_entry(teacher, session, second_kid, "late", tardiness_minutes=5, now=at(7, 30))
    decide_entry(holder, done, True, now=at(7, 40))
    client_as(teacher).post(reverse("attendance_entry_all", args=[session.id]))
    assert AttendanceEntry.objects.filter(session=session).count() == 2
    assert AttendanceEntry.objects.get(pk=mine.pk).status == "absent"
    assert StudentAttendance.objects.get(session=session, student=second_kid).status == "late"


def test_all_present_is_refused_to_another_teacher_and_writes_nothing(
    client_as, now_0730, session, other_teacher, kid
):
    response = client_as(other_teacher).post(reverse("attendance_entry_all", args=[session.id]))
    assert response.status_code == 403
    assert not AttendanceEntry.objects.exists()


def test_all_present_is_refused_after_the_school_day_window(
    client_as, now_1500, session, teacher, kid
):
    response = client_as(teacher).post(reverse("attendance_entry_all", args=[session.id]))
    assert response.status_code == 403
    assert not AttendanceEntry.objects.exists()


def test_all_present_needs_post_and_an_existing_session(client_as, now_0730, session, teacher, kid):
    assert (
        client_as(teacher).get(reverse("attendance_entry_all", args=[session.id])).status_code
        == 405
    )
    missing = reverse("attendance_entry_all", args=[uuid.uuid4()])
    assert client_as(teacher).post(missing).status_code == 404


def test_an_approved_row_keeps_the_correction_form_with_a_required_reason(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    decide_entry(holder, entry, True, now=at(7, 40))
    html = _page(client_as, teacher, session).content.decode()
    assert 'name="reason"' in html and "required" in html
    assert 'name="status"' in html


# ── صفحةُ المعلّم هي شبكةُ الكشف نفسُها (طلابٌ صفوفاً وحصصُه أعمدةً) ─────────────────────────


def test_the_teacher_page_is_the_grid_with_only_his_own_sessions_as_columns(
    client_as, now_0730, session, teacher, other_teacher, kid, second_kid
):
    later = Session.objects.create(
        school=session.school,
        class_group=session.class_group,
        teacher=teacher,
        date=session.date,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    Session.objects.create(  # حصّةُ زميله للشعبة نفسِها: ليست من أعمدته
        school=session.school,
        class_group=session.class_group,
        teacher=other_teacher,
        date=session.date,
        start_time=dt.time(9, 0),
        end_time=dt.time(9, 45),
        status="scheduled",
    )
    html = _page(client_as, teacher, session).content.decode()
    assert 'class="per-grid"' in html and "tch-list" not in html
    assert html.count('<th scope="col" class="per-col') == 3  # حصّتان له + عمودُ الأدوات
    assert reverse("attendance", args=[later.id]) in html
    assert "09:00" not in html
    assert html.count('class="rec-row"') == 2  # صفٌّ لكلّ طالب


def test_pending_is_a_small_symbol_not_a_sentence_in_every_row(
    client_as, now_0730, session, teacher, kid, second_kid
):
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    submit_entry(teacher, session, second_kid, "present", now=at(7, 30))
    html = _page(client_as, teacher, session).content.decode()
    assert html.count("◔") == 2
    assert "badge--neutral" not in html  # لا شارةَ نصّيّةً في كلّ صفّ
    assert "2 بانتظار الاعتماد" in html  # سطرٌ واحدٌ أعلى الصفحة يلخّص المعلّق
    assert "لم يُرصد</span>" not in html  # لا «لم يُرصد» مكرَّرة


def test_another_sessions_cell_shows_its_state_as_a_symbol(
    client_as, now_0730, session, teacher, kid
):
    later = Session.objects.create(
        school=session.school,
        class_group=session.class_group,
        teacher=teacher,
        date=session.date,
        start_time=dt.time(8, 0),
        end_time=dt.time(8, 45),
        status="scheduled",
    )
    submit_entry(teacher, later, kid, "late", now=at(8, 5))
    html = _page(client_as, teacher, session).content.decode()
    assert 'class="per-cell is-late"' in html
    assert ">م</span>" in html
