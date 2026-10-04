"""[W-20261004-015] صفحةُ المعلّم هي كشفُ المشرف نفسُه (القالبُ المشترك `attendance/period_sheet.html`) مقتصراً على حصصه — والفرقُ في الخدمة وحدَها.

المشرفُ: «ثبّتِ الحصّة» ← `StudentAttendance` مباشرةً. المعلّم: النموذجُ نفسُه ← `attendance_period_entries` ← `AttendanceEntry` مبدئيٌّ ينتظر اعتمادَ الحامل (D-125م)،
والخروجُ `ClassExit`. وتطابقُ كشفِ المشرف مع قالبه الأصليّ في `test_period_sheet_parity.py`.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.attendance_entries import decide_entry, submit_entry
from operations.models import AttendanceEntry, ClassExit, Session, StudentAttendance
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import ENROLLED, at
from tests.conftest import StudentEnrollmentFactory, UserFactory

pytestmark = pytest.mark.django_db


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


@pytest.fixture
def now_1500(monkeypatch):
    """بعد نهاية الدوام (13:30): الإدخالُ مغلق."""
    monkeypatch.setattr(timezone, "now", lambda: at(15, 0))


@pytest.fixture
def second_kid(school, klass):
    student = UserFactory(full_name="طالبٌ ثانٍ", national_id="29000001002")
    StudentEnrollmentFactory(student=student, class_group=klass, enrolled_at=ENROLLED)
    return student


def _later(session, teacher, klass=None, start=dt.time(8, 0)):
    return Session.objects.create(
        school=session.school,
        class_group=klass or session.class_group,
        teacher=teacher,
        date=session.date,
        start_time=start,
        end_time=(dt.datetime.combine(session.date, start) + dt.timedelta(minutes=45)).time(),
        status="scheduled",
    )


def _page(client_as, user, session):
    return client_as(user).get(reverse("attendance", args=[session.id]))


def _submit(client_as, user, session, data):
    return client_as(user).post(reverse("attendance_period_entries", args=[session.id]), data)


# ── الصفحةُ هي القالبُ المشترك ─────────────────────────────────────────────


def test_the_teacher_page_is_the_shared_sheet_with_the_supervisors_elements(
    client_as, now_0730, session, teacher, kid
):
    html = _page(client_as, teacher, session).content.decode()
    for marker in (
        'class="per-head"',
        'data-bulk="present"',
        'data-bulk="absent"',
        'data-view="tiles"',
        'data-view="table"',
        'class="per-grid-wrap is-tiles"',
        'class="rec-form"',
        "data-draft-key=",
        "period-register.js",
        f'name="s-{kid.id}"',
        "ثبّتِ الحصّة",
        "data-exit-open",  # «خروج» في البطاقة
    ):
        assert marker in html, marker
    assert reverse("attendance_period_entries", args=[session.id]) in html


def test_supervisor_only_elements_are_absent_for_the_teacher(
    client_as, now_0730, session, teacher, kid, klass
):
    html = _page(client_as, teacher, session).content.decode()
    assert reverse("wings:section_register", args=[klass.id]) not in html  # لا تصدير
    assert reverse("wings:absence_file", args=[kid.id]) not in html  # لا ملفَّ غياب
    assert "rec-row__fix" not in html  # لا «تصحيح» المشرف


def test_columns_are_only_the_teachers_own_sessions(
    client_as, now_0730, session, teacher, other_teacher, kid
):
    later = _later(session, teacher)
    _later(session, other_teacher, start=dt.time(9, 0))  # حصّةُ زميله للشعبة نفسِها
    html = _page(client_as, teacher, session).content.decode()
    assert html.count('class="per-tab ') + html.count('class="per-tab"') == 2
    assert reverse("attendance", args=[later.id]) in html
    assert "09:00" not in html


# ── «ثبّتِ الحصّة»: إدخالاتٌ مبدئيّةٌ لا StudentAttendance ──────────────────────


def test_submit_creates_pending_entries_not_effective_rows(
    client_as, now_0730, session, teacher, kid, second_kid
):
    response = _submit(
        client_as,
        teacher,
        session,
        {f"s-{kid.id}": "absent", f"s-{second_kid.id}": "present", f"m-{kid.id}": ""},
    )
    assert response.status_code == 302
    assert response.url == reverse("attendance", args=[session.id])
    assert {e.status for e in AttendanceEntry.objects.filter(session=session)} == {
        "absent",
        "present",
    }
    assert not StudentAttendance.objects.filter(session=session).exists()  # D-125م


def test_late_minutes_are_computed_automatically_from_the_session_start(
    client_as, now_0730, session, teacher, kid
):
    """ملاحظةُ المالك: «دقائقُ التأخّر حسب ضغط المعلّم وبداية الحصّة من ساعة الجهاز آلياً — المعلّمُ لا يُدخل الوقت».

    داخل وقت الحصّة: الدقائقُ من بدء الحصّة (07:10) إلى لحظة التثبيت (07:30) = 20 ولو كُتب رقمٌ آخر باليد.
    """
    _submit(client_as, teacher, session, {f"s-{kid.id}": "late", f"m-{kid.id}": "7"})
    entry = AttendanceEntry.objects.get(session=session, student=kid)
    assert (entry.status, entry.tardiness_minutes) == ("late", 20)


def test_late_minutes_come_from_the_moment_the_teacher_pressed_late(
    client_as, now_0730, session, teacher, kid
):
    pressed = int(at(7, 22).timestamp())  # لحظةُ الضغط بساعة الجهاز (JS يحفظها في t-<طالب>)
    _submit(client_as, teacher, session, {f"s-{kid.id}": "late", f"t-{kid.id}": str(pressed)})
    assert AttendanceEntry.objects.get(session=session, student=kid).tardiness_minutes == 12


def test_a_press_time_outside_the_session_is_ignored(client_as, now_0730, session, teacher, kid):
    """لحظةٌ قبل بدء الحصّة عبثٌ أو ساعةٌ مختلّة: تُترك ويُحسب من لحظة التثبيت (كما يفعل كشفُ المشرف)."""
    before = int(at(6, 0).timestamp())
    _submit(client_as, teacher, session, {f"s-{kid.id}": "late", f"t-{kid.id}": str(before)})
    assert AttendanceEntry.objects.get(session=session, student=kid).tardiness_minutes == 20


def test_outside_the_session_window_the_minutes_are_typed(
    client_as, monkeypatch, session, teacher, kid
):
    monkeypatch.setattr(
        timezone, "now", lambda: at(10, 0)
    )  # بعد نهاية الحصّة بساعاتٍ وقبل نهاية اليوم
    _submit(client_as, teacher, session, {f"s-{kid.id}": "late", f"m-{kid.id}": "9"})
    assert AttendanceEntry.objects.get(session=session, student=kid).tardiness_minutes == 9


def test_an_exit_destination_opens_a_class_exit_and_no_entry(
    client_as, now_0730, session, teacher, kid
):
    _submit(client_as, teacher, session, {f"s-{kid.id}": "absent", f"w-{kid.id}": "clinic"})
    assert ClassExit.objects.filter(session=session, student=kid, destination="clinic").exists()
    assert not AttendanceEntry.objects.filter(session=session, student=kid).exists()


def test_save_and_move_goes_to_the_following_session(client_as, now_0730, session, teacher, kid):
    later = _later(session, teacher)
    response = _submit(client_as, teacher, session, {f"s-{kid.id}": "present", "next": "1"})
    assert response.url == reverse("attendance", args=[later.id])


def test_an_approved_entry_is_never_overwritten_and_is_counted(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    decide_entry(holder, entry, True, now=at(7, 40))
    _submit(client_as, teacher, session, {f"s-{kid.id}": "present"})
    assert AttendanceEntry.objects.filter(session=session, student=kid).count() == 1
    assert StudentAttendance.objects.get(session=session, student=kid).status == "absent"


def test_an_approved_row_renders_its_buttons_locked(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    decide_entry(holder, entry, True, now=at(7, 40))
    html = _page(client_as, teacher, session).content.decode()
    assert f'name="s-{kid.id}" value="absent" checked disabled' in html


def test_pending_state_is_an_icon_not_a_sentence(client_as, now_0730, session, teacher, kid):
    submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    html = _page(client_as, teacher, session).content.decode()
    assert 'class="per-pend"' in html and "badge--neutral" not in html


def test_the_rejection_shows_its_state_to_the_teacher_without_the_reason(
    client_as, now_0730, session, teacher, holder, kid
):
    entry = submit_entry(teacher, session, kid, "absent", now=at(7, 30))
    decide_entry(holder, entry, False, reason="سببٌ حرٌّ لا يُعرض", now=at(7, 40))
    html = _page(client_as, teacher, session).content.decode()
    assert "لم يُعتمد إدخالُك" in html and "سببٌ حرٌّ لا يُعرض" not in html


# ── المنعُ والنافذة ─────────────────────────────────────────────────────────


def test_another_teacher_cannot_submit_a_colleagues_sheet(
    client_as, now_0730, session, other_teacher, kid
):
    response = _submit(client_as, other_teacher, session, {f"s-{kid.id}": "absent"})
    assert response.status_code == 403
    assert not AttendanceEntry.objects.exists()


def test_a_missing_session_is_404_and_get_is_405(client_as, now_0730, session, teacher, kid):
    import uuid

    assert (
        client_as(teacher).get(reverse("attendance_period_entries", args=[session.id])).status_code
        == 405
    )
    assert (
        client_as(teacher)
        .post(reverse("attendance_period_entries", args=[uuid.uuid4()]), {})
        .status_code
        == 404
    )


def test_a_closed_window_says_why_locks_the_sheet_and_refuses_the_post(
    client_as, now_0730, now_1500, session, teacher, kid
):
    html = _page(client_as, teacher, session).content.decode()
    assert "الإدخالُ مغلق: انتهت نافذةُ الإدخال" in html
    assert f'name="s-{kid.id}" value="present" checked disabled' in html
    assert "per-bar__actions" in html and "ثبّتِ الحصّة" not in html  # لا أزرارَ تثبيتٍ مغلقة
    assert _submit(client_as, teacher, session, {f"s-{kid.id}": "absent"}).status_code == 403
    assert not AttendanceEntry.objects.exists()


def test_in_the_preview_environment_the_window_stays_open_all_day(
    client_as, now_0730, now_1500, session, teacher, kid, monkeypatch
):
    """قرارُ المالك 2026-10-04: المعاينةُ وحدَها تفتح نافذةَ الإدخال حتى آخر اليوم؛ والإنتاجُ بنافذته."""
    monkeypatch.setattr("operations.attendance_policy.in_preview_environment", lambda: True)
    html = _page(client_as, teacher, session).content.decode()
    assert "الإدخالُ مغلق" not in html and "ثبّتِ الحصّة" in html
    assert _submit(client_as, teacher, session, {f"s-{kid.id}": "absent"}).status_code == 302


@pytest.mark.parametrize(
    "module",
    sorted(__import__("core.preview_accounts", fromlist=["x"]).PRODUCTION_SETTINGS_MODULES),
)
def test_production_keeps_its_window_even_if_every_preview_variable_is_set(
    client_as, now_0730, now_1500, session, teacher, kid, monkeypatch, settings, module
):
    """حكمُ 0105: الإنتاجُ بنافذته يُغلق بعد آخر الدوام **حتى لو ضُبطت كلُّ متغيّرات المعاينة خطأً**."""
    from core import preview_accounts as pa

    settings.SETTINGS_MODULE = module
    monkeypatch.setenv("PREVIEW_MODE", "prod")
    monkeypatch.setenv("PREVIEW_DB_NAME", "ss_main_preview_x")
    monkeypatch.setattr(pa, "current_db_name", lambda: "ss_main_preview_x")
    assert pa.in_preview_environment() is False
    html = _page(client_as, teacher, session).content.decode()
    assert "الإدخالُ مغلق" in html and "ثبّتِ الحصّة" not in html
