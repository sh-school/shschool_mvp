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
