"""[W-20261004-014] صفحةُ المعلّم بعرضَي كشف المشرف: بطاقاتٌ (شبكة) أصلاً وجدول، ورأسُ الحصّة وتبويبُ حصصه اليوم.

المصدرُ نفسُه الذي يحفظه كشفُ المشرف (`per-view`) فيبقى اختيارُ المستخدم واحداً للصفحتين، والبطاقاتُ بأصناف `per-grid-wrap is-tiles` نفسِها.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.models import Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import at

pytestmark = pytest.mark.django_db


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


@pytest.fixture
def now_1500(monkeypatch):
    """بعد نهاية الدوام (13:30): الإدخالُ مغلق."""
    monkeypatch.setattr(timezone, "now", lambda: at(15, 0))


def test_a_closed_entry_window_says_why_and_shows_each_state_as_a_word_not_an_empty_card(
    client_as, now_0730, now_1500, session, teacher, kid
):
    """لقطةُ المالك: بطاقاتٌ فارغةٌ بلا أزرارٍ ولا تفسير — صار سطرُ سببٍ واحدٌ وحالةُ كلّ طالبٍ كلمةً."""
    from operations.attendance_entries import submit_entry

    submit_entry(teacher, session, kid, "present", now=at(7, 30))
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert "الإدخالُ مغلق: انتهت نافذةُ الإدخال" in html
    assert 'class="att-btn' not in html  # لا أزرارَ مغلقة
    assert "badge--success" in html and ">حاضر<" in html  # كلمةٌ لا نقطةٌ صغيرة


def test_the_name_has_no_tools_padding_when_there_is_no_tools_menu(
    client_as, now_1500, session, teacher, kid
):
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert "tch-has-tools" not in html and 'class="tch-more"' not in html


@pytest.fixture
def now_1030(monkeypatch):
    """بعد نهاية حصّة 07:10 وقبل نهاية اليوم: الإدخالُ والخروجُ مسموحان (بنافذة اليوم)، و«دخل الآن» (بنافذة الحصّة) لا."""
    monkeypatch.setattr(timezone, "now", lambda: at(10, 30))


def test_the_tools_menu_shows_only_where_the_taps_are_accepted_so_no_403_toasts(
    client_as, now_1030, session, teacher, kid
):
    """خارجَ نافذة الحصّة كانت «دخل الآن» تُعرض وتردّ 403 فتتراكم تنبيهاتُ «غير مصرّح» — فلا تُعرض الآن."""
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert 'id="late-tap-' not in html  # «دخل الآن» بنافذة الحصّة نفسِها فلا تُعرض بعدها
    assert 'id="exit-tap-' in html  # و«خرج بإذن» بنافذة اليوم فتبقى
    assert 'class="att-btn is-present' in html  # والإدخالُ (بنافذة اليوم) مسموح


def test_the_tools_menu_shows_inside_the_session_window(client_as, now_0730, session, teacher, kid):
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert 'class="tch-more"' in html
    assert 'id="late-tap-' in html and 'id="exit-tap-' in html


def test_counts_are_one_line_in_the_head_not_a_kpi_strip_and_names_are_single_line(
    client_as, now_0730, session, teacher, kid
):
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert 'class="per-bar__counts"' in html
    assert "الحصّة الآن" not in html  # لا شريطَ مؤشّراتٍ يزيد الارتفاع
    assert 'class="rec-row__name rec-row__file"' in html  # اسمٌ بسطرٍ واحدٍ بنقطتين


def test_the_teacher_page_has_the_supervisors_head_view_toggle_and_session_tabs(
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
    html = client_as(teacher).get(reverse("attendance", args=[session.id])).content.decode()
    assert 'class="per-head"' in html
    assert 'class="per-grid-wrap is-tiles"' in html  # بطاقاتٌ أصلاً كالمشرف
    assert 'data-view="tiles"' in html and 'data-view="table"' in html
    assert (
        html.count('class="per-tab ') + html.count('class="per-tab"') == 2
    )  # حصّتاه فقط (والغلافُ per-tabs لا يُعدّ)
    assert f'href="{reverse("attendance", args=[later.id])}" class="per-tab' in html
    assert "per-view" in html  # مفتاحُ التفضيل نفسُه الذي يحفظه كشفُ المشرف
