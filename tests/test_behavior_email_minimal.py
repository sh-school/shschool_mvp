"""[W-20261012-031] بريدُ المخالفة مقتضبٌ: لا اسمَ طالبٍ ولا مبلِّغَ ولا وصفَ ولا إجراءَ ولا درجةَ.

كان البريدُ يحمل ذلك كلَّه إلى مزوّد بريدٍ خارجيّ (يخالف تقليلَ البيانات في PDPPL)، بينما تقتطع البوابةُ الوصف.
وولي الأمر يرى التفاصيل داخل البوابة بعد الدخول، والرابطُ لا يحمل معرّفَ طالبٍ ولا مخالفة.
"""

import re
from datetime import date
from unittest.mock import patch

import pytest
from django.template.loader import render_to_string

from behavior.services import BehaviorService
from tests.conftest import BehaviorInfractionFactory

pytestmark = pytest.mark.django_db

SECRETS = ["اسم-الطالب-السرّي", "اسم-المبلّغ-السرّي", "وصفٌ-حرٌّ-سرّي", "إجراءٌ-متخذٌ-سرّي"]


def _captured(school, student_user, teacher_user, level=3):
    student_user.full_name = SECRETS[0]
    student_user.save(update_fields=["full_name"])
    teacher_user.full_name = SECRETS[1]
    teacher_user.save(update_fields=["full_name"])
    inf = BehaviorInfractionFactory(
        school=school,
        student=student_user,
        reported_by=teacher_user,
        level=level,
        description=SECRETS[2],
        date=date(2026, 10, 1),
    )
    inf.action_taken = SECRETS[3]
    with patch("notifications.hub.NotificationHub.dispatch_to_parents") as dispatch:
        BehaviorService.notify_parents(inf, school, teacher_user)
    return inf, dispatch.call_args.kwargs


def _render(kwargs, school, name):
    ctx = {**kwargs["context"], "parent_name": "ولي الأمر", "school_name": school.name}
    return render_to_string(kwargs[name], ctx)


def test_email_parts_and_subject_carry_no_personal_content(school, student_user, teacher_user):
    _inf, kwargs = _captured(school, student_user, teacher_user)
    parts = [
        _render(kwargs, school, "email_html_template"),
        _render(kwargs, school, "email_text_template"),
        kwargs["title"],
    ]
    for part in parts:
        visible = re.sub(
            r"<style.*?</style>", "", part, flags=re.S
        )  # تعليقاتُ CSS الأساس ليست محتوى
        for secret in SECRETS:
            assert secret not in visible
        assert "الدرجة" not in visible and "مخالفة" not in visible


def test_email_keeps_school_date_and_portal_link(school, student_user, teacher_user):
    inf, kwargs = _captured(school, student_user, teacher_user)
    for name in ("email_html_template", "email_text_template"):
        out = _render(kwargs, school, name)
        assert school.name in out
        assert inf.date.strftime("%Y/%m/%d") in out
        assert "/parents/behavior/" in out
        assert str(inf.pk) not in out and str(student_user.pk) not in out


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_no_channel_text_carries_points_or_deduction(school, student_user, teacher_user, level):
    """[W-20261013-010] لا قناةَ (تطبيق/push/واتساب/SMS/بريد) تحمل نصَّ حسم درجات أو نقاط."""
    _inf, kwargs = _captured(school, student_user, teacher_user, level=level)
    texts = [
        kwargs["title"],
        kwargs["body"],
        _render(kwargs, school, "email_html_template"),
        _render(kwargs, school, "email_text_template"),
    ]
    for text in texts:
        visible = re.sub(r"<style.*?</style>", "", text, flags=re.S)
        for banned in ("حسم", "خصم", "نقاط", "نقطة", "درجات السلوك"):
            assert banned not in visible, (level, banned)


@pytest.mark.parametrize("level", [1, 2, 3, 4])
def test_push_whatsapp_sms_body_is_neutral(school, student_user, teacher_user, level):
    """جسمُ التطبيق/push/واتساب/SMS محايدٌ: لا درجةَ ولا تاريخَ ولا وصفَ (W-20261012-031)."""
    _inf, kwargs = _captured(school, student_user, teacher_user, level=level)
    body = kwargs["body"]
    assert "الدرجة" not in body and "مخالفة" not in body
    assert not re.search(r"\d", body)
    for secret in SECRETS:
        assert secret not in body
