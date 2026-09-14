"""`request.school` — مدرسةُ المستخدم تُحسب مرّةً في الوسيط وتُقرأ في العروض.

كان `request.user.get_school()` يُكتب في 248 موضعاً. الوسيطُ `SchoolContextMiddleware`
يضع القيمةَ على الطلب بعد حارس المسارات — الذي حمّل العضويّةَ الحاكمة سلفاً —
فلا استعلامَ يُضاف، والعروضُ الخمسةُ الأكثرُ استدعاءً تقرأ الاسمَ الواحد.
"""

from __future__ import annotations

import pathlib

import pytest
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from django.db import connection
from django.http import HttpResponse
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext

from core.middleware import SchoolContextMiddleware, SchoolPermissionMiddleware

pytestmark = pytest.mark.django_db

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: الملفّاتُ الخمسةُ الأكثرُ استدعاءً لـ`get_school()` قبل الترحيل (30، 21، 16، 13، 12).
MIGRATED_VIEWS = (
    "student_affairs/views.py",
    "operations/views_schedule.py",
    "behavior/views.py",
    "assessments/views.py",
    "staff_affairs/views.py",
)


def _run(request):
    seen = {}

    def view(req):
        seen["school"] = req.school
        return HttpResponse("ok")

    SchoolContextMiddleware(view)(request)
    return seen["school"]


def test_sets_school_of_authenticated_user(teacher_user, school):
    request = RequestFactory().get("/dashboard/")
    request.user = teacher_user
    assert _run(request) == school
    assert request.school == teacher_user.get_school()


def test_anonymous_gets_none():
    request = RequestFactory().get("/auth/login/")
    request.user = AnonymousUser()
    assert _run(request) is None


def test_user_without_membership_gets_none(db):
    from tests.conftest import UserFactory

    request = RequestFactory().get("/dashboard/")
    request.user = UserFactory()
    assert _run(request) is None


def test_adds_no_query_after_permission_middleware(teacher_user):
    """حارسُ المسارات حمّل العضويّة؛ الوسيطُ يقرؤها من الكائن بلا استعلام."""
    request = RequestFactory().get("/dashboard/")
    request.user = teacher_user

    def view(req):
        return HttpResponse("ok")

    stack = SchoolPermissionMiddleware(SchoolContextMiddleware(view))
    stack(request)  # إحماء
    teacher_user.invalidate_active_membership()
    with CaptureQueriesContext(connection) as ctx:
        stack(request)
    membership_queries = [q["sql"] for q in ctx.captured_queries if "core_membership" in q["sql"]]
    assert len(membership_queries) == 1, membership_queries


def test_middleware_is_installed_after_permission_guard():
    order = list(settings.MIDDLEWARE)
    assert order.index("core.middleware.SchoolContextMiddleware") == (
        order.index("core.middleware.SchoolPermissionMiddleware") + 1
    )


@pytest.mark.parametrize("path", MIGRATED_VIEWS)
def test_migrated_views_read_request_school(path):
    source = (ROOT / path).read_text(encoding="utf-8")
    assert "request.user.get_school()" not in source, f"{path} لا يزال يستدعي get_school()"
    assert "request.school" in source
