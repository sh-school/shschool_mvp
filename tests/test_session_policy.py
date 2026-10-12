"""مُهَلُ الجلسة بحسب الدور (W-20261005-004، س٢ — قرارا المالك D-222م وD-223م).

الخمولُ والمطلقةُ لكلّ دور، وفرضُهما في الميدلوير، وتجديدُ الخمول مخنوقاً (لا كتابةَ على كلّ طلب)،
وجهازٌ مشترك 10 دقائق، وإعادةُ توليد مفتاح الجلسة عند تغيّر الدور، وألّا تنتهي الجلسةُ بإغلاق المتصفّح.
الجانبُ العميليّ (التحذيرُ والنافذة) في tests/test_session_expiry.py وtests/e2e/test_session_guard.py.
"""

import ast
import pathlib
import time
from unittest import mock

import pytest
from django.contrib.sessions.backends.db import SessionStore
from django.test import Client
from django.urls import reverse

from core import session_policy
from core.session_policy import HOUR, MINUTE, limits_for
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

STATUS = "/auth/session/status/"


def _page():
    return reverse("dashboard")


def _user_with_role(school, role_name):
    user = UserFactory()
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


def _age(client, *, idle_for=0, logged_in_for=0):
    """يُقدّم ختمَي الجلسة كأنّ المستخدم خامدٌ `idle_for` ثانية ومسجَّلٌ منذ `logged_in_for`."""
    session = client.session
    session["_last_touch"] -= idle_for
    session["_login_at"] -= max(logged_in_for, idle_for)
    session.save()


class TestTheRoleTable:
    """الجدولُ كما قرّره المالك — في مكانٍ واحد."""

    @pytest.mark.parametrize(
        ("role", "idle_minutes", "absolute_hours"),
        [
            ("teacher", 60, 8),
            ("coordinator", 60, 8),  # مشرف
            ("admin_supervisor", 60, 8),
            ("secretary", 60, 8),  # بقيّة الموظّفين
            ("vice_admin", 60, 8),  # النائبُ الإداريّ ليس الأكاديميّ
            ("vice_academic", 120, 8),
            ("principal", 20, 8),
            ("parent", 15, 2),
        ],
    )
    def test_idle_and_absolute_per_role(self, role, idle_minutes, absolute_hours):
        limits = limits_for(role)
        assert limits.idle == idle_minutes * MINUTE
        assert limits.absolute == absolute_hours * HOUR

    @pytest.mark.parametrize("role", ["", "platform_developer", "some_future_role"])
    def test_an_undefined_role_gets_the_safe_default(self, role):
        limits = limits_for(role)
        assert limits.idle == session_policy.DEFAULT_IDLE == 3600
        assert limits.absolute == 8 * HOUR

    def test_a_student_is_a_beneficiary_with_the_two_hour_absolute(self):
        limits = limits_for("student")
        assert limits.absolute == 2 * HOUR and limits.idle == 60 * MINUTE

    @pytest.mark.parametrize("role", ["teacher", "vice_academic", "principal", "parent"])
    def test_a_shared_device_cuts_idle_to_ten_minutes_and_leaves_the_absolute(self, role):
        normal, shared = limits_for(role), limits_for(role, shared_device=True)
        assert shared.idle == min(normal.idle, 10 * MINUTE)
        assert shared.absolute == normal.absolute

    def test_idle_never_exceeds_the_absolute(self, settings):
        settings.SESSION_ABSOLUTE_AGE = 30 * MINUTE
        assert limits_for("vice_academic").idle == 30 * MINUTE

    def test_the_absolute_can_be_overridden_by_a_setting(self, settings):
        settings.SESSION_ABSOLUTE_AGE = 3 * HOUR
        assert limits_for("teacher").absolute == 3 * HOUR


@pytest.mark.django_db
class TestIdleIsEnforcedPerRole:
    @pytest.mark.parametrize(
        ("role", "idle_minutes"),
        [("teacher", 60), ("vice_academic", 120), ("principal", 20), ("parent", 15)],
    )
    def test_alive_just_inside_the_idle_limit_and_ended_just_past_it(
        self, school, role, idle_minutes
    ):
        inside, outside = Client(), Client()
        for client, offset in ((inside, -MINUTE), (outside, +MINUTE)):
            client.force_login(_user_with_role(school, role))
            _age(client, idle_for=idle_minutes * MINUTE + offset)
        assert inside.get(STATUS).status_code == 200
        assert outside.get(STATUS).status_code == 401

    def test_an_ended_session_is_a_401_for_a_page_request_and_a_302_for_navigation(self, school):
        for headers, expected in (({"HTTP_HX_REQUEST": "true"}, 401), ({}, 302)):
            client = Client()
            client.force_login(_user_with_role(school, "principal"))
            _age(client, idle_for=21 * MINUTE)
            assert client.get(_page(), **headers).status_code == expected

    def test_the_session_is_really_gone_after_the_idle_end(self, school):
        client = Client()
        client.force_login(_user_with_role(school, "principal"))
        _age(client, idle_for=21 * MINUTE)
        client.get(_page())
        assert client.get(STATUS).status_code == 401

    def test_the_absolute_ends_a_session_even_if_it_was_just_renewed(self, school):
        client = Client()
        client.force_login(_user_with_role(school, "parent"))
        _age(client, logged_in_for=2 * HOUR + MINUTE)
        session = client.session
        session["_last_touch"] += 2 * HOUR  # نشِطٌ الآن — والمطلقةُ مع ذلك تحكم
        session.save()
        assert client.get(STATUS).status_code == 401

    def test_the_status_reports_the_roles_own_limits(self, school):
        client = Client()
        client.force_login(_user_with_role(school, "vice_academic"))
        body = client.get(STATUS).json()
        assert body["idle_limit"] == 120 * MINUTE and body["absolute_limit"] == 8 * HOUR

    def test_an_undefined_role_is_ended_after_the_default(self, school):
        client = Client()
        client.force_login(_user_with_role(school, "platform_developer"))
        _age(client, idle_for=session_policy.DEFAULT_IDLE + MINUTE)
        assert client.get(STATUS).status_code == 401


@pytest.mark.django_db
class TestSharedDevice:
    def test_a_listed_network_gets_ten_minutes(self, school, settings):
        settings.SESSION_SHARED_DEVICE_NETWORKS = ["127.0.0.0/8"]
        inside, outside = Client(), Client()
        for client, minutes in ((inside, 9), (outside, 11)):
            client.force_login(_user_with_role(school, "teacher"))
            _age(client, idle_for=minutes * MINUTE)
        assert inside.get(STATUS).status_code == 200
        assert outside.get(STATUS).status_code == 401

    def test_with_no_list_nobody_is_shared(self, school, settings):
        settings.SESSION_SHARED_DEVICE_NETWORKS = []
        client = Client()
        client.force_login(_user_with_role(school, "teacher"))
        _age(client, idle_for=11 * MINUTE)
        assert client.get(STATUS).status_code == 200

    def test_a_malformed_entry_is_ignored_not_fatal(self, school, settings):
        settings.SESSION_SHARED_DEVICE_NETWORKS = ["not-an-ip", "10.9.8.0/24"]
        client = Client()
        client.force_login(_user_with_role(school, "teacher"))
        _age(client, idle_for=11 * MINUTE)
        assert client.get(STATUS).status_code == 200


@pytest.mark.django_db
class TestIdleRenewalIsThrottled:
    """الخمولُ ينزلق، لكنّ الكتابةَ في الجلسة لا تزيد على واحدةٍ كلَّ 5 دقائق (MTG-2026-005)."""

    def test_page_loads_inside_five_minutes_write_nothing(self, teacher_user):
        client = Client()
        client.force_login(teacher_user)
        _age(client, idle_for=4 * MINUTE)
        stamp = client.session["_last_touch"]
        with mock.patch.object(SessionStore, "save", autospec=True) as save:
            for _ in range(10):
                client.get(_page())
        assert save.call_count == 0
        assert client.session["_last_touch"] == stamp

    def test_a_page_load_after_five_minutes_renews_once(self, teacher_user):
        client = Client()
        client.force_login(teacher_user)
        _age(client, idle_for=6 * MINUTE)
        client.get(_page())
        renewed = client.session["_last_touch"]
        assert time.time() - renewed < 5
        with mock.patch.object(SessionStore, "save", autospec=True) as save:
            client.get(_page())
            client.get(_page())
        assert save.call_count == 0

    def test_a_background_poll_never_keeps_the_session_alive(self, teacher_user):
        client = Client()
        client.force_login(teacher_user)
        _age(client, idle_for=6 * MINUTE)
        stamp = client.session["_last_touch"]
        client.get(_page(), HTTP_HX_REQUEST="true")
        client.get(_page(), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        client.get(STATUS)
        assert client.session["_last_touch"] == stamp

    def test_a_submitted_form_counts_as_activity(self, teacher_user):
        client = Client()
        client.force_login(teacher_user)
        _age(client, idle_for=6 * MINUTE)
        client.post(_page(), {"x": "1"})
        assert time.time() - client.session["_last_touch"] < 5


@pytest.mark.django_db
class TestRoleChangeRegeneratesTheSession:
    def test_a_different_role_gets_a_new_session_key_and_a_fresh_idle_window(self, teacher_user):
        client = Client()
        client.force_login(teacher_user)
        _age(client, idle_for=10 * MINUTE)
        session = client.session
        session["_session_role"] = "student"  # كان دورُه غيرَ هذا حين ختمنا الجلسة
        session.save()
        old_key, login_at = client.session.session_key, client.session["_login_at"]

        client.get(_page())

        assert client.session.session_key != old_key
        assert client.session["_session_role"] == "teacher"
        assert client.session["_login_at"] == login_at  # المطلقةُ لا يمدّدها تغيّرُ الدور
        assert time.time() - client.session["_last_touch"] < 5

    def test_an_unchanged_role_keeps_its_key(self, teacher_user):
        client = Client()
        client.force_login(teacher_user)
        key = client.session.session_key
        client.get(_page())
        assert client.session.session_key == key


class TestTheBrowserCloseSetting:
    """`SESSION_EXPIRE_AT_BROWSER_CLOSE=False` في الإنتاج، وسقفُ الكوكي ليس أقلَّ من أطول مطلقة."""

    @staticmethod
    def _production_setting(name):
        source = pathlib.Path(__file__).resolve().parent.parent / "shschool/settings/production.py"
        for node in ast.parse(source.read_text(encoding="utf-8")).body:
            if isinstance(node, ast.Assign) and any(
                getattr(t, "id", None) == name for t in node.targets
            ):
                return eval(compile(ast.Expression(node.value), "<settings>", "eval"), {})  # noqa: S307
        raise AssertionError(f"{name} غائب عن production.py")

    def test_closing_the_browser_does_not_end_the_session(self):
        assert self._production_setting("SESSION_EXPIRE_AT_BROWSER_CLOSE") is False

    def test_the_cookie_outlives_the_longest_absolute_limit(self):
        assert self._production_setting("SESSION_COOKIE_AGE") >= session_policy.STAFF_ABSOLUTE

    def test_every_request_still_does_not_save_the_session(self):
        assert self._production_setting("SESSION_SAVE_EVERY_REQUEST") is False
