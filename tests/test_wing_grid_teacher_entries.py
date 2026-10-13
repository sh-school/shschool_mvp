"""[W-20261004-014] شبكةُ المشرف تعرض إدخالَ المعلّم المبدئيّ كما تعرضه صفحةُ المعلّم، ويعتمده الحاملُ في مكانه.

كانت الشبكةُ (`wings:record_section`) تقرأ ما رصده المشرفُ وحدَه (`source=supervisor`) فلا ترى إدخالاً معلَّقاً ولا ما اعتُمد من إدخال المعلّم،
واعتمادُه في صفحةٍ منفصلة. الآن: علامةٌ بحالة الإدخال في خليّة الطالب/الحصّة (معلَّق، معتمَد، لم يُعتمد، تصحيح دون معاينة)، وزرُّ اعتمادٍ
لمن يملك `can_approve` وحدَه، ورفضٌ يبقى في صفحة الاعتماد لأنّ الرفضَ يلزمه سبب. ولا تغييرَ لكتابة الحامل المباشرة (`confirm_period`).
"""

import pytest
from django.urls import reverse
from django.utils import timezone

from operations.attendance_entries import submit_entry
from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

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


def test_the_teacher_has_no_access_to_the_wing_grid(
    client_as, now_0730, klass, session, teacher, kid
):
    _entry(teacher, session, kid)
    response = _grid(client_as, teacher, klass)
    assert response.status_code in (302, 403)
    assert kid.full_name not in response.content.decode()


def test_the_grid_is_unchanged_when_no_teacher_entered_anything(
    client_as, now_0730, klass, session, holder, kid
):
    html = _grid(client_as, holder, klass).content.decode()
    assert "rec-entry" not in html
    assert "ينتظر اعتمادك" not in html
