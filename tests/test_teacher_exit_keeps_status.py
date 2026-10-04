"""[W-20261004-015] خروجُ الطالب بإذن المعلّم **ليس غياباً** في كشف المعلّم — ملاحظةُ المالك على المعاينة: «الطالب عند اختيار خروج يعتمد غائب؟».

في كشف المشرف (`record_period`) اختيارُ وجهةٍ يجعل الطالبَ غائباً بوجهته. وللمعلّم الخروجُ سطرُ `ClassExit` يُسجَّل **فوراً بلحظته** (`mark_exit`/`mark_return`)
ويبقى حالُ الطالب كما هو؛ والمشرفُ يرى «غائباً بإذن المعلّم» مشتقّاً من الخروج في كشفه لا من اختيار المعلّم.
"""

from pathlib import Path

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.models import AttendanceEntry, ClassExit
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at

pytestmark = pytest.mark.django_db

JS = Path(__file__).resolve().parent.parent / "static" / "js" / "period-register.js"


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


@pytest.fixture
def now_1500(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(15, 0))


def test_the_exit_button_is_disabled_when_entry_is_closed_so_no_403_toast(
    client_as, now_0730, now_1500, session, teacher, kid
):
    """لقطةُ المالك: «تعذّر تسجيلُ الخروج» مرّتين — الزرُّ كان عاملاً والإدخالُ مغلقٌ فيردّ الخادمُ 403."""
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert "الإدخالُ مغلق: انتهت نافذةُ الإدخال" in html  # سطرٌ ظاهرٌ نصّاً لا أيقونةً فحسب
    assert 'class="per-head__note">الإدخالُ مغلق' in html
    assert (
        'data-exit-open aria-haspopup="true" aria-expanded="false" title="خروجُ الطالب — أين هو؟" disabled'
        in html
    )


def test_the_exit_button_is_enabled_when_entry_is_open(client_as, now_0730, session, teacher, kid):
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert 'title="خروجُ الطالب — أين هو؟" disabled' not in html
    assert "عاد إلى الفصل" in html  # العودةُ بمفتاحٍ باسمها للمعلّم


def test_the_supervisor_keeps_his_popup_label(client_as, now_0730, klass, session, holder, kid):
    response = client_as(holder).get(
        reverse("wings:record_section", args=[klass.id]), {"date": session.date.isoformat()}
    )
    html = response.content.decode()
    assert ">في فصله<" in html and "عاد إلى الفصل" not in html


def test_the_teacher_form_carries_the_exit_and_return_endpoints(
    client_as, now_0730, session, teacher, kid
):
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert f'data-exit-url="{reverse("mark_exit", args=[session.id])}"' in html
    assert f'data-return-url="{reverse("mark_return", args=[session.id])}"' in html


def test_the_supervisor_form_has_no_exit_endpoints_so_his_behaviour_is_unchanged(
    client_as, now_0730, klass, session, holder, kid
):
    response = client_as(holder).get(
        reverse("wings:record_section", args=[klass.id]), {"date": session.date.isoformat()}
    )
    assert "data-exit-url" not in response.content.decode()


def test_the_script_does_not_switch_the_student_to_absent_when_the_teacher_exits_him():
    source = JS.read_text(encoding="utf-8")
    assert "if (exitUrl) {" in source and "sendExit(cell, value);" in source
    # التحويلُ إلى «غائب» لوجهة المشرف وحدَه: فرعٌ `else if` بعد فرع المعلّم
    assert "} else if (value) {" in source


def test_the_exit_endpoint_records_a_class_exit_and_no_absence(
    client_as, now_0730, session, teacher, kid
):
    response = client_as(teacher).post(
        reverse("mark_exit", args=[session.id]),
        {"student_id": str(kid.id), "destination": "clinic"},
    )
    assert response.status_code == 200
    assert ClassExit.objects.filter(session=session, student=kid, destination="clinic").exists()
    assert not AttendanceEntry.objects.filter(session=session, student=kid).exists()


def test_a_student_already_out_is_preselected_without_an_extra_badge_line(
    client_as, now_0730, session, teacher, kid
):
    """لقطةُ المالك: سطرُ «خرج · …» كان يُطيل بطاقاتٍ دون غيرها وزرُّ الوجهة يغطّي أزرارَ الحالة — الآن الوجهةُ مختارةٌ في القائمة فيحمرّ الزرُّ بلا سطرٍ إضافيّ."""
    ClassExit.objects.create(
        school=session.school,
        session=session,
        student=kid,
        destination="clinic",
        left_at=at(7, 20),
        allowed_by=teacher,
    )
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert '<option value="clinic" selected>' in html
    assert "rec-row__flags" not in html and "خرج · " not in html


def test_the_teachers_exit_button_keeps_its_short_label_so_it_cannot_cover_the_status_buttons():
    source = JS.read_text(encoding="utf-8")
    assert "label.textContent = set && !exitUrl ? option.textContent : 'خروج';" in source
    assert "if (exitUrl) button.title" in source  # اسمُ الوجهة في التلميح
    assert "label.textContent = 'خروج · ' + times;" in source  # عددُ مرّات اليوم على الزرّ نفسه


def test_marking_absent_closes_the_open_exit_and_records_the_absence(
    client_as, now_0730, session, teacher, kid
):
    """أمرُ المالك 2026-10-04: غائبٌ وخروجٌ لا يجتمعان — وسمُ الغياب يُغلق الخروجَ المفتوح ويُدخَل الغياب."""
    ClassExit.objects.create(
        school=session.school,
        session=session,
        student=kid,
        destination="clinic",
        left_at=at(7, 20),
        allowed_by=teacher,
    )
    client_as(teacher).post(
        reverse("attendance_period_entries", args=[session.id]), {f"s-{kid.id}": "absent"}
    )
    assert ClassExit.objects.get(session=session, student=kid).returned_at == at(7, 30)
    assert AttendanceEntry.objects.get(session=session, student=kid).status == "absent"


def test_the_row_of_a_student_out_carries_his_exit_moment_for_the_timer(
    client_as, now_0730, session, teacher, kid
):
    left = at(7, 20)
    ClassExit.objects.create(
        school=session.school,
        session=session,
        student=kid,
        destination="restroom",
        left_at=left,
        allowed_by=teacher,
    )
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert f'data-out-since="{int(left.timestamp())}"' in html
    assert f'data-entry-url="{reverse("attendance_entry", args=[session.id])}"' in html
    assert 'data-start-epoch="' in html


def test_pressing_late_saves_at_once_with_minutes_from_the_session_start(
    client_as, now_0730, session, teacher, kid
):
    """«متأخّر»: وقتُ الدخول من لحظة الضغط ودقائقُه من بدء الحصّة (07:10) آلياً ويُحفظ — الدقائقُ لا يكتبها المعلّم."""
    response = client_as(teacher).post(
        reverse("attendance_entry", args=[session.id]),
        {"student_id": str(kid.id), "status": "late", "tapped_at": str(int(at(7, 22).timestamp()))},
    )
    assert response.status_code == 200
    entry = AttendanceEntry.objects.get(session=session, student=kid)
    assert (entry.status, entry.tardiness_minutes) == ("late", 12)


def test_the_script_has_the_exclusion_the_stopwatch_and_the_immediate_late_save():
    source = JS.read_text(encoding="utf-8")
    for needle in (
        "function syncExclusive(row)",
        "function outTick()",
        "function saveLate(radio)",
        "data-out-since",
    ):
        assert needle in source, needle


def test_the_exit_button_is_a_toggle_and_the_stopwatch_is_continuous_across_periods():
    """الضغطةُ التالية تُوقف العدّاد ويعود المفتاحُ «خروج»؛ ومن لم يعد ينتقل عدّادُه المتّصلُ إلى الحصص التالية (لا قصَّ عند نهاية الحصّة)."""
    source = JS.read_text(encoding="utf-8")
    assert "var outRow = exitUrl ? cell.closest('tr[data-out-since]') : null;" in source
    assert "endEpoch" not in source
    assert "var text = stopwatch(Math.max(0, now - since));" in source


def test_the_row_carries_the_day_count_and_the_closed_total_for_the_tooltip(
    client_as, now_0730, session, teacher, kid
):
    from operations.class_exit import come_back, leave

    leave(session, kid, "restroom", by=teacher, now=at(7, 12))
    come_back(session, kid, now=at(7, 17))
    leave(session, kid, "clinic", by=teacher, now=at(7, 20))
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert 'data-exit-count="2"' in html
    assert 'data-exit-base="300"' in html  # الجزءُ المغلق وحدَه 5 د؛ والمفتوحُ يُضاف في المتصفّح
    assert f'data-exit-open-at="{int(at(7, 20).timestamp())}"' in html
