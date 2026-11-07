"""وسمُ أفعال المُناب في سجلّ التدقيق بـ``acting_for`` (W-20261107-002)."""

from __future__ import annotations

from datetime import datetime

import pytest
from django.contrib import admin
from django.core.signals import request_finished, request_started
from django.db import close_old_connections
from django.test import RequestFactory

import staff_affairs.attendance as attendance_module
from core.admin import ActingForFilter, AuditLogAdmin
from core.capabilities import capability, has_capability
from core.capabilities.registry import registry
from core.models import AuditLog
from core.models.user import CustomUser
from staff_affairs.attendance import AssignmentService
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

NOW = datetime(2026, 2, 15, 12, 0)
TODAY = NOW.date()
PRINCIPAL_ONLY = "workload.approve"


def _send(signal):
    """يرسل إشارةَ الطلب الحقيقيّة دون ``close_old_connections`` كما يفعل عميلُ اختبار Django.

    وإلّا أغلقتْ الإشارةُ اتّصالَ القاعدة داخل معاملة الاختبار فتفشل الاستعلاماتُ اللاحقة.
    """
    request_started.disconnect(close_old_connections)
    request_finished.disconnect(close_old_connections)
    try:
        signal.send(sender=None)
    finally:
        request_started.connect(close_old_connections)
        request_finished.connect(close_old_connections)


@pytest.fixture(autouse=True)
def _clock(monkeypatch):
    from django.utils import timezone

    monkeypatch.setattr(
        attendance_module,
        "_now",
        lambda: timezone.localtime(timezone.make_aware(NOW)),
        raising=False,
    )
    _send(request_started)  # بدايةُ طلبٍ نظيفة لكلّ اختبار


@pytest.fixture
def deputy(school, principal_user):
    user = UserFactory(full_name="نائب اصطناعي", employee_number="T-0951")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="vice_admin"))
    AssignmentService.assign(
        school=school,
        assigner=principal_user,
        assignee=user,
        start=TODAY,
        end=TODAY,
        reason="غيابُ صاحب الوظيفة",
    )
    return user


def _fresh(user):
    return CustomUser.objects.get(pk=user.pk)


def _log(user, school, **kw):
    AuditLog.log(user=user, action="update", model_name="other", school=school, **kw)
    return AuditLog.objects.filter(user=user).latest("timestamp")


def test_an_action_through_a_transferred_capability_carries_the_tag(school, deputy):
    assert has_capability(_fresh(deputy), PRINCIPAL_ONLY)
    row = _log(deputy, school, changes={"field": "x"})
    assert row.changes == {"field": "x", "acting_for": "principal"}


def test_the_tag_is_added_when_changes_is_empty_or_not_an_object(school, deputy):
    assert has_capability(_fresh(deputy), PRINCIPAL_ONLY)
    assert _log(deputy, school).changes == {"acting_for": "principal"}
    assert _log(deputy, school, changes=["a"]).changes == {
        "value": ["a"],
        "acting_for": "principal",
    }


def test_an_original_action_of_the_same_user_has_no_tag(school, deputy):
    own = next(
        cap
        for cap in registry().values()
        if "vice_admin" in cap.expanded_roles and cap.key != PRINCIPAL_ONLY
    )
    # فعلٌ بالدور الأصليّ: يمرّ الفحصُ بالدور قبل الإنابة فلا يُعلَّم السياق.
    assert has_capability(_fresh(deputy), own.key)
    assert _log(deputy, school, changes={"field": "x"}).changes == {"field": "x"}
    assert _log(deputy, school).changes is None


def test_a_principal_action_is_never_tagged(school, principal_user, deputy):
    assert has_capability(_fresh(principal_user), PRINCIPAL_ONLY)
    assert _log(principal_user, school).changes is None


def test_the_navigation_check_does_not_mark_the_context(school, deputy):
    from core.capabilities.acting import _grant_or_acting

    assert _grant_or_acting(capability(PRINCIPAL_ONLY))(_fresh(deputy))
    assert _log(deputy, school).changes is None


@pytest.mark.parametrize("signal", [request_started, request_finished])
def test_the_acting_context_does_not_leak_between_requests(school, deputy, signal):
    assert has_capability(_fresh(deputy), PRINCIPAL_ONLY)
    assert _log(deputy, school).changes == {"acting_for": "principal"}
    _send(signal)  # طلبٌ جديد (أو نهايةُ الطلب) يصفّر السياق
    assert _log(deputy, school).changes is None


def test_the_admin_shows_and_filters_by_the_tag(school, deputy, principal_user):
    assert has_capability(_fresh(deputy), PRINCIPAL_ONLY)
    tagged = _log(deputy, school, changes={"f": 1})
    _send(request_started)
    plain = _log(principal_user, school, changes={"f": 2})

    model_admin = AuditLogAdmin(AuditLog, admin.site)
    assert model_admin.acting_for(tagged) == "principal"
    assert model_admin.acting_for(plain) == ""
    assert "acting_for" in model_admin.list_display
    assert ActingForFilter in model_admin.list_filter

    request = RequestFactory().get("/")

    def run(value):
        params = {"acting": [value]} if value else {}
        flt = ActingForFilter(request, params, AuditLog, model_admin)
        # صفوفٌ أخرى تنشئها الـfixtures بلا وسم، فيُحصر الاستعلام في صفَّي الاختبار.
        base = AuditLog.objects.filter(pk__in=[tagged.pk, plain.pk])
        return set(flt.queryset(request, base).values_list("pk", flat=True))

    assert run("yes") == {tagged.pk}
    assert run("no") == {plain.pk}
    assert run(None) == {tagged.pk, plain.pk}
