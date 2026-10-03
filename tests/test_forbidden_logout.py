"""صفحةُ المنع 403 لا تكون فخّاً: فيها زرُّ «تسجيل الخروج» (POST) لمن دخل — W-20261003-024 (P1).

دخل المالكُ بحساب دورٍ بلا لوحة فخرج على «ليس لديك صلاحيات» وزرّا الصفحة («العودة للرئيسية» و«الرجوع للخلف»)
يقودان كلاهما إلى /dashboard/ فيعود المنعُ نفسُه، والخروجُ GET ← 405 (POST فقط) ولا زرَّ له. فصار في الصفحة زرُّ
خروجٍ POST مع csrf لكلّ مستخدمٍ مصادَق، ولا يظهر لزائرٍ لم يدخل (لا حسابَ يُخرَج منه).
"""

from __future__ import annotations

import re

import pytest
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory

from tests.test_staff_register_screen import principal, school  # noqa: F401

pytestmark = pytest.mark.django_db

PAGES = ["403.html", "errors/forbidden.html"]


def _render(template: str, user) -> str:
    request = RequestFactory().get("/dashboard/")
    request.user = user
    request.csp_nonce = "test-nonce"
    return render_to_string(template, {"message": "ممنوع"}, request=request)


@pytest.mark.parametrize("template", PAGES)
def test_a_signed_in_user_gets_a_post_logout_button(template, principal):
    html = _render(template, principal)

    form = re.search(r'<form method="post" action="([^"]+)">(.*?)</form>', html, re.S)
    assert form, f"{template}: لا نموذجَ خروجٍ POST"
    assert form.group(1).rstrip("/").endswith("logout")
    assert "csrfmiddlewaretoken" in form.group(2), f"{template}: النموذجُ بلا csrf"
    assert "تسجيل الخروج" in form.group(2)


@pytest.mark.parametrize("template", PAGES)
def test_an_anonymous_visitor_gets_no_logout_button(template):
    html = _render(template, AnonymousUser())

    assert "تسجيل الخروج" not in html


@pytest.mark.parametrize("template", PAGES)
def test_the_back_links_are_still_there_beside_the_logout(template, principal):
    """الخروجُ إضافةٌ لا بديلٌ: من منعته صفحةٌ واحدةٌ يبقى له رجوعٌ إلى الرئيسيّة."""
    html = _render(template, principal)

    assert "العودة للرئيسية" in html and "الرجوع للخلف" in html
