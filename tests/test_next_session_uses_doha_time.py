"""«الحصّة التالية» تقارن بساعة الدوحة لا ساعة UTC (W-20261010-047، P0).

كان `timezone.now().time()` يعطي ساعة UTC، والحصّةُ محفوظةٌ بتوقيت المدرسة (Asia/Qatar، +3): فعند 07:54 بالدوحة (04:54 UTC)
تبقى حصّةُ 07:10 «تاليةً» وقد انقضى أكثرُها. والعيبُ نفسُه في ثلاثة مواضع: لوحة المعلّم والمنسّق، ولوحة المعالج، وصفحة جدول الحضور.
الحالاتُ الأربع حول الحدّ (قبل البداية بدقيقة، عند البداية، قبل النهاية بدقيقة، عند النهاية) تُثبَّت بلحظة UTC تقابل الدوحة بفارق ثلاث ساعات:
الأخيرتان تفشلان على القديم.
"""

import datetime as dt

import pytest
from django.utils import timezone

from core.dashboard_selectors import get_teacher_ctx, get_therapist_ctx
from operations.models import Session
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, _staff, at

pytestmark = pytest.mark.django_db

#: (لحظةُ الدوحة، هل الحصّةُ ذاتُ 07:10–07:55 «تاليةٌ»؟) — «تالية» = لم تبدأ بعد (`start_time >= الآن`).
BOUNDARY = [
    pytest.param((7, 9), True, id="a-minute-before-start"),
    pytest.param((7, 10), True, id="at-start"),
    pytest.param((7, 54), False, id="a-minute-before-end"),
    pytest.param((7, 55), False, id="at-end"),
]


def _freeze(monkeypatch, doha_hm):
    """يثبّت `timezone.now()` عند لحظةٍ بتوقيت UTC تقابل ساعةَ الدوحة المعطاة (الفارقُ ثلاثُ ساعات)."""
    moment = at(*doha_hm).astimezone(dt.UTC)
    assert moment.hour == doha_hm[0] - 3, "الفارقُ بين UTC والدوحة ثلاثُ ساعات"
    monkeypatch.setattr(timezone, "now", lambda: moment)


@pytest.mark.parametrize("doha_hm,is_next", BOUNDARY)
def test_teacher_dashboard_next_session_follows_doha_clock(
    monkeypatch, school, session, teacher, doha_hm, is_next
):
    _freeze(monkeypatch, doha_hm)

    ctx = get_teacher_ctx(teacher, school, SUNDAY, "teacher")

    assert (ctx["next_session"] == session) is is_next


@pytest.mark.parametrize("doha_hm,is_next", BOUNDARY)
def test_therapist_dashboard_next_session_follows_doha_clock(
    monkeypatch, school, klass, bells, doha_hm, is_next
):
    therapist = _staff(school, "speech_therapist", "معالج", "29000001040")
    mine = Session.objects.create(
        school=school,
        class_group=klass,
        teacher=therapist,
        date=SUNDAY,
        start_time=dt.time(7, 10),
        end_time=dt.time(7, 55),
        status="scheduled",
    )
    _freeze(monkeypatch, doha_hm)

    ctx = get_therapist_ctx(therapist, school, SUNDAY)

    assert (ctx["next_session"] == mine) is is_next


@pytest.mark.parametrize("doha_hm,is_next", BOUNDARY)
def test_attendance_schedule_page_next_session_follows_doha_clock(
    monkeypatch, client_as, session, teacher, doha_hm, is_next
):
    _freeze(monkeypatch, doha_hm)

    resp = client_as(teacher).get("/teacher/schedule/", {"date": SUNDAY.isoformat()})

    assert resp.status_code == 200
    assert (resp.context["next_session"] == session) is is_next
