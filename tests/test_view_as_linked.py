"""[SECURITY] الحسابُ المرتبط بمطوّر المنصّة — تبديلُ هويّةٍ بشروط 0104 (W-20261009-032، D-305م وD-306م).

المعاييرُ المقيسة: جدولُ الربط بقدرةٍ منفصلة، ورفضُ الهدف superuser أو المطوّر أو الإدارة العليا أو الربط السلسليّ،
والتبديلُ إلى المعلّم وعودتُه، وإعادةُ تأكيد هويّة المطوّر، وتدويرُ مفتاح الجلسة دخولاً وخروجاً، وحظرُ صفحات الحساب،
و`acting` في كلّ سطر، والعودةُ لا الإخراجُ إلّا إن لم يعد المطوّرُ كما كان.
"""

from __future__ import annotations

import pyotp
import pytest
import redis
from django.contrib.auth import SESSION_KEY
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.test import RequestFactory
from django.urls import reverse

from core.admin_linked_account import LinkedAccountAdmin, _eligible_targets
from core.models import AuditLog, CustomUser, LinkedAccount, Membership
from core.models.crypto import encrypt_field
from core.view_as import linked, policy, state
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory

pytestmark = pytest.mark.django_db

PASSWORD = "testpass123"  # pragma: allowlist secret — كلمةُ مصنع الاختبار الافتراضيّة
EXIT = "/developer/view-as/linked/exit/"
PICKER = "/developer/view-as/"

#: الفحصُ الحقيقيّ قبل أن يستبدله المثبِّتُ أدناه — تقيسه اختباراتُ الذاكرة المشتركة وحدَها.
_LOCK_STORE_SHARED = linked.lock_store_shared


@pytest.fixture(autouse=True)
def _shared_lock_store(monkeypatch):
    """الاختباراتُ بذاكرة locmem وDEBUG مطفأ، والإنتاجُ بـRedis: فتُعدّ الذاكرةُ مشتركةً هنا إلّا حيث تُقاس."""
    monkeypatch.setattr(linked, "lock_store_shared", lambda: True)


def _member(school, role, **kwargs):
    user = UserFactory(**kwargs)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def developer(school):
    return _member(school, "platform_developer", full_name="مطوّر المنصّة")


@pytest.fixture
def target(school):
    return _member(school, "teacher", full_name="حسابُ المطوّر معلّماً")


@pytest.fixture
def link(developer, target):
    return LinkedAccount.objects.create(developer=developer, target=target, created_by=developer)


@pytest.fixture
def dev_client(client, developer):
    client.force_login(developer)
    return client


def _switch_url(link):
    return reverse("view_as_linked_switch", args=[link.pk])


def _confirm_url(link):
    return reverse("view_as_linked_confirm", args=[link.pk])


def _rows(action, **filters):
    return AuditLog.objects.filter(action=action, **filters).order_by("timestamp")


def _session_user(client):
    return str(client.session.get(SESSION_KEY) or "")


def _enter(client, link):
    """تبديلٌ كاملٌ بتأكيد كلمة مرور المطوّر — يعيد مفتاحَ الجلسة قبله."""
    before = client.session.session_key
    response = client.post(_confirm_url(link), {"secret": PASSWORD})
    assert response.status_code == 302 and response.url == reverse("dashboard")
    return before


# ── قواعدُ الربط ─────────────────────────────────────────────


def test_an_eligible_teacher_has_no_problems(developer, target):
    assert linked.link_problems(developer, target) == []


@pytest.mark.parametrize("role", ["coordinator", "nurse", "admin_supervisor", "secretary"])
def test_staff_below_top_leadership_are_eligible(developer, school, role):
    assert linked.link_problems(developer, _member(school, role)) == []


@pytest.mark.parametrize("role", ["principal", "vice_admin", "vice_academic", "student", "parent"])
def test_top_leadership_students_and_parents_are_refused(developer, school, role):
    assert linked.link_problems(developer, _member(school, role))


@pytest.mark.parametrize("flag", ["is_superuser", "is_staff"])
def test_an_elevated_target_is_refused(developer, school, flag):
    assert linked.link_problems(developer, _member(school, "teacher", **{flag: True}))


def test_a_developer_target_is_refused(developer, school):
    assert linked.link_problems(developer, _member(school, "platform_developer"))
    grouped = _member(school, "teacher")
    grouped.groups.add(Group.objects.get_or_create(name="developers")[0])
    assert linked.link_problems(developer, grouped)


def test_a_target_in_another_school_is_refused(developer):
    other = SchoolFactory()
    assert linked.link_problems(developer, _member(other, "teacher"))


def test_an_inactive_target_and_self_are_refused(developer, school):
    assert linked.link_problems(developer, _member(school, "teacher", is_active=False))
    assert linked.link_problems(developer, developer)


def test_a_non_developer_cannot_own_a_link(school, target):
    assert linked.link_problems(_member(school, "teacher"), target)


def test_chained_links_are_refused(developer, target, school):
    other = _member(school, "teacher")
    LinkedAccount.objects.create(developer=target, target=other)
    assert any("سلسليّ" in p for p in linked.link_problems(developer, target))
    second_developer = _member(school, "platform_developer")
    LinkedAccount.objects.create(developer=second_developer, target=developer)
    assert any("سلسليّ" in p for p in linked.link_problems(developer, other))


def test_a_duplicate_link_fails_clean(link, developer, target):
    with pytest.raises(ValidationError) as caught:
        LinkedAccount(developer=developer, target=target).clean()
    assert "هذا الربطُ قائمٌ من قبل." in caught.value.messages
    link.clean()  # الصفُّ نفسُه لا يُعدّ تكراراً لنفسه


# ── لوحةُ الإدارة بقدرتها ─────────────────────────────────────


def _admin_request(user):
    request = RequestFactory().get("/admin/core/linkedaccount/")
    request.user = user
    return request


def test_the_admin_is_the_developers_capability_only(developer, school):
    from django.contrib import admin

    model_admin = LinkedAccountAdmin(LinkedAccount, admin.site)
    assert model_admin.has_module_permission(_admin_request(developer))
    assert model_admin.has_add_permission(_admin_request(developer))
    for role in ("teacher", "principal", "it_technician"):
        other = _member(school, role)
        assert not model_admin.has_module_permission(_admin_request(other))
        assert not model_admin.has_add_permission(_admin_request(other))


def test_the_admin_lists_only_the_developers_own_links(developer, link, school):
    from django.contrib import admin

    second = _member(school, "platform_developer")
    LinkedAccount.objects.create(developer=second, target=_member(school, "nurse"))
    model_admin = LinkedAccountAdmin(LinkedAccount, admin.site)
    assert list(model_admin.get_queryset(_admin_request(developer))) == [link]


def test_the_admin_offers_only_eligible_targets(developer, target, school):
    _member(school, "principal")
    _member(school, "teacher", is_superuser=True)
    _member(SchoolFactory(), "teacher")
    assert list(_eligible_targets(developer)) == [target]


def test_saving_in_the_admin_sets_the_developer_and_logs_both_sides(developer, target):
    from django.contrib import admin

    model_admin = LinkedAccountAdmin(LinkedAccount, admin.site)
    obj = LinkedAccount(target=target)
    model_admin.save_model(_admin_request(developer), obj, form=None, change=False)
    assert obj.developer_id == developer.pk and obj.created_by_id == developer.pk
    row = _rows("create", model_name="LinkedAccount").get()
    assert row.changes["developer"] == str(developer.pk) and row.changes["target"] == str(target.pk)


# ── التبديلُ والتأكيد ─────────────────────────────────────────


def test_a_teacher_cannot_switch(client, school, link):
    client.force_login(_member(school, "teacher"))
    assert client.post(_switch_url(link)).status_code == 403


def test_another_developers_link_is_404(client, school, link):
    client.force_login(_member(school, "platform_developer"))
    assert client.post(_switch_url(link)).status_code == 404


def test_the_first_switch_asks_for_the_developers_own_password(dev_client, link):
    response = dev_client.post(_switch_url(link))
    assert response.status_code == 302 and response.url == _confirm_url(link)
    page = dev_client.get(_confirm_url(link))
    assert page.status_code == 200
    assert 'type="password"' in page.content.decode()


def test_the_targets_password_does_not_confirm(dev_client, link, developer, target):
    target.set_password("TargetOnly-987")
    target.save()
    response = dev_client.post(_confirm_url(link), {"secret": "TargetOnly-987"})
    assert response.status_code == 400
    assert _session_user(dev_client) == str(developer.pk)
    assert _rows("view_as_denied", user=developer).last().changes["why"] == "reauth_failed"


def _with_second_factor(user):
    secret = pyotp.random_base32()
    user.totp_secret = encrypt_field(secret) or secret
    user.totp_enabled = True
    user.save(update_fields=["totp_secret", "totp_enabled"])
    return secret


def test_a_developer_with_a_second_factor_confirms_with_the_code(
    dev_client, link, developer, target
):
    secret = _with_second_factor(developer)
    assert 'autocomplete="one-time-code"' in dev_client.get(_confirm_url(link)).content.decode()
    assert dev_client.post(_confirm_url(link), {"secret": PASSWORD}).status_code == 400
    response = dev_client.post(_confirm_url(link), {"secret": pyotp.TOTP(secret).now()})
    assert response.status_code == 302
    assert _session_user(dev_client) == str(target.pk)


def test_entering_rotates_the_key_and_records_the_actor(dev_client, link, developer, target):
    before = _enter(dev_client, link)
    assert dev_client.session.session_key != before
    assert _session_user(dev_client) == str(target.pk)
    link.refresh_from_db()
    assert link.confirmed_at is not None
    row = _rows("view_as_linked_in", user=developer).get()
    assert row.changes["acting"] == {"actor": str(developer.pk), "as_user": str(target.pk)}


def test_inside_the_linked_account_the_session_is_the_teachers(dev_client, link, developer, target):
    _enter(dev_client, link)
    response = dev_client.get(reverse("dashboard"))
    assert response.status_code == 200
    request = response.wsgi_request
    assert request.user.pk == target.pk and request.view_as.is_linked
    content = response.content.decode()
    assert "في حسابك المرتبط" in content
    assert 'id="btn-view-as"' not in content  # القائمةُ للمطوّر لا للمعلّم
    page = _rows("view_as_page", user=developer).last()
    assert page.changes["acting"] == {"actor": str(developer.pk), "as_user": str(target.pk)}


def test_a_write_in_the_linked_account_is_logged_to_the_developer(
    dev_client, link, developer, target
):
    _enter(dev_client, link)
    assert dev_client.post("/notifications/mark-all-read/").status_code == 302
    row = _rows("update", user=developer, changes__path="/notifications/mark-all-read/").get()
    assert row.changes["acting"] == {"actor": str(developer.pk), "as_user": str(target.pk)}


def test_a_used_code_does_not_confirm_again(developer):
    """شرطُ 0104: رمزٌ صحَّ مرّةً لا يصحّ ثانيةً في نوافذه الثلاث."""
    code = pyotp.TOTP(_with_second_factor(developer)).now()
    assert linked.verify_reauth(developer, code)
    assert not linked.verify_reauth(developer, code)


def test_a_code_used_at_login_does_not_confirm(developer):
    """الحجزُ مشتركٌ مع باب الدخول (`core/views_auth.py`، VULN-001) فرمزُ الدخول لا يؤكّد هنا."""
    code = pyotp.TOTP(_with_second_factor(developer)).now()
    linked.cache.set(f"totp_used:{developer.id}:{code}", True, timeout=90)
    assert not linked.verify_reauth(developer, code)


@pytest.mark.parametrize(
    "path",
    [
        "/auth/change-password/",
        "/auth/2fa/setup/",
        "/notifications/settings/",
        "/admin/",
        "/api/v1/auth/token/",
        "/api/v1/auth/token/refresh/",
        "/core/it-admin/password-reset/",
    ],
)
def test_account_pages_are_closed_in_the_linked_account(dev_client, link, developer, path):
    _enter(dev_client, link)
    assert dev_client.get(path).status_code == 403
    assert _rows("view_as_denied", user=developer).last().changes["why"] == "account_page"


def test_exit_returns_the_developer_with_a_new_key(dev_client, link, developer, target):
    _enter(dev_client, link)
    before = dev_client.session.session_key
    response = dev_client.post(EXIT)
    assert response.status_code == 302 and response.url == PICKER
    assert dev_client.session.session_key != before
    assert _session_user(dev_client) == str(developer.pk)
    row = _rows("view_as_linked_out", user=developer).get()
    assert row.changes["why"] == "user"
    assert row.changes["acting"] == {"actor": str(developer.pk), "as_user": str(target.pk)}
    assert dev_client.get(PICKER).status_code == 200


def test_the_second_switch_in_a_session_needs_no_new_confirmation(dev_client, link, target):
    _enter(dev_client, link)
    dev_client.post(EXIT)
    response = dev_client.post(_switch_url(link))
    assert response.status_code == 302 and response.url == reverse("dashboard")
    assert _session_user(dev_client) == str(target.pk)


def test_entering_ends_a_running_preview(dev_client, link, developer):
    dev_client.post("/developer/view-as/start/", {"role": "nurse"})
    _enter(dev_client, link)
    assert _rows("view_as_end", user=developer).last().changes["why"] == "linked"
    assert state.ROLE_KEY not in dev_client.session


def test_a_target_that_became_elevated_is_refused_at_switch(dev_client, link, developer, target):
    target.is_superuser = True
    target.save(update_fields=["is_superuser"])
    response = dev_client.post(_switch_url(link))
    assert response.status_code == 302 and response.url == PICKER
    assert _session_user(dev_client) == str(developer.pk)
    assert _rows("view_as_denied", user=developer).last().changes["why"] == "link_problems"


# ── القفلُ والحدّ ──────────────────────────────────────────────


def test_five_wrong_confirmations_lock_it(dev_client, link, developer):
    wrong = {"secret": "wrong"}  # pragma: allowlist secret
    for _ in range(policy.REAUTH_FAILURES):
        assert dev_client.post(_confirm_url(link), wrong).status_code == 400
    response = dev_client.post(_confirm_url(link), {"secret": PASSWORD})
    assert response.status_code == 429
    assert "أُوقف التأكيدُ مؤقّتاً" in response.content.decode()
    assert _rows("view_as_limit", user=developer).get().changes["kind"] == "reauth"
    assert _session_user(dev_client) == str(developer.pk)


class _FallenCache:
    """ذاكرةٌ سقطت: كلُّ استدعاءٍ يرفع ما يرفعه Redis المنقطع."""

    def __getattr__(self, name):
        def fallen(*args, **kwargs):
            raise redis.exceptions.ConnectionError("Redis down")

        return fallen


def test_a_fallen_store_locks_the_confirmation(dev_client, link, developer, monkeypatch):
    """شرطُ 0104: لا يُفتح التأكيدُ بلا عدٍّ يراه كلُّ العمّال — يُقفل ولا يسقط 500."""
    monkeypatch.setattr(linked, "cache", _FallenCache())
    assert linked.reauth_locked(developer)
    linked.note_reauth_failure(developer)
    linked.clear_reauth_failures(developer)
    response = dev_client.post(_confirm_url(link), {"secret": PASSWORD})
    assert response.status_code == 429
    assert _session_user(dev_client) == str(developer.pk)


def test_a_fallen_store_refuses_a_correct_code(developer, monkeypatch):
    code = pyotp.TOTP(_with_second_factor(developer)).now()
    monkeypatch.setattr(linked, "cache", _FallenCache())
    assert not linked.verify_reauth(developer, code)


def test_a_fallen_switch_limit_refuses_entry_without_500(dev_client, link, developer, monkeypatch):
    """ملاحظةُ 0104: حدُّ التبديل في `state` يرفض عند السقوط (429) ولا يسقط 500 — والتأكيدُ نفسُه صحيح."""
    monkeypatch.setattr(state, "cache", _FallenCache())
    response = dev_client.post(_confirm_url(link), {"secret": PASSWORD})
    assert response.status_code == 429
    assert _rows("view_as_limit", user=developer).get().changes["kind"] == state.LINKED
    assert _session_user(dev_client) == str(developer.pk)


def test_a_process_local_store_is_not_shared(settings):
    """اختباراتُ المنصّة بـlocmem وDEBUG مطفأ — كالإنتاج بلا REDIS_URL."""
    assert settings.CACHES["default"]["BACKEND"].endswith("LocMemCache") and not settings.DEBUG
    assert not _LOCK_STORE_SHARED()
    settings.CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": "redis://127.0.0.1:6379/0",
        }
    }
    assert _LOCK_STORE_SHARED()


def test_without_a_shared_store_the_linked_account_is_stopped(
    dev_client, link, developer, monkeypatch
):
    monkeypatch.setattr(linked, "lock_store_shared", _LOCK_STORE_SHARED)
    assert linked.reauth_locked(developer)
    response = dev_client.post(_confirm_url(link), {"secret": PASSWORD})
    assert response.status_code == 302 and response.url == PICKER
    assert _session_user(dev_client) == str(developer.pk)
    row = _rows("view_as_denied", user=developer).last()
    assert row.changes["why"] == "link_problems"
    assert any("Redis" in problem for problem in row.changes["problems"])


def test_switching_past_the_hourly_limit_is_429(dev_client, link, developer, monkeypatch):
    monkeypatch.setattr("core.view_as.views.LINKED_SWITCHES_PER_HOUR", 1)
    _enter(dev_client, link)
    dev_client.post(EXIT)
    assert dev_client.post(_switch_url(link)).status_code == 429
    assert _rows("view_as_limit", user=developer).get().changes["kind"] == state.LINKED


# ── السقوطُ والعودة ───────────────────────────────────────────


def _resign(client, **changes):
    session = client.session
    payload = state.unsign(session[state.LINKED_KEY], state.LINKED_SALT)
    payload.update(changes)
    session[state.LINKED_KEY] = state.sign(payload, state.LINKED_SALT)
    session.save()


def test_a_revoked_link_returns_the_developer(dev_client, link, developer):
    _enter(dev_client, link)
    LinkedAccount.objects.filter(pk=link.pk).update(is_active=False)
    response = dev_client.get(reverse("dashboard"))
    assert response.status_code == 302 and response.url == PICKER
    assert _session_user(dev_client) == str(developer.pk)
    assert _rows("view_as_linked_out", user=developer).get().changes["why"] == "link_revoked"


def test_the_cap_returns_the_developer(dev_client, link, developer):
    _enter(dev_client, link)
    _resign(dev_client, s=state.now() - policy.LINKED_CAP_SECONDS - 5)
    assert dev_client.get(reverse("dashboard")).url == PICKER
    assert _rows("view_as_linked_out", user=developer).get().changes["why"] == "cap"


def test_idleness_returns_the_developer(dev_client, link, developer):
    _enter(dev_client, link)
    session = dev_client.session
    session[state.LINKED_SEEN_KEY] = state.now() - policy.LINKED_IDLE_SECONDS - 5
    session.save()
    assert dev_client.get(reverse("dashboard")).url == PICKER
    assert _rows("view_as_linked_out", user=developer).get().changes["why"] == "idle"


def test_a_changed_developer_password_closes_the_whole_session(dev_client, link, developer):
    _enter(dev_client, link)
    fresh = CustomUser.objects.get(pk=developer.pk)
    fresh.set_password("Changed-Elsewhere-1")
    fresh.save()
    response = dev_client.get(reverse("dashboard"))
    assert response.status_code == 302 and response.url.startswith(reverse("login"))
    assert _session_user(dev_client) == ""
    assert _rows("view_as_denied", user=developer).last().changes["why"] == "linked_session_invalid"


def test_a_developer_who_lost_the_role_is_logged_out(dev_client, link, developer, school):
    _enter(dev_client, link)
    Membership.objects.filter(user=developer).update(role=RoleFactory(school=school, name="nurse"))
    response = dev_client.get(reverse("dashboard"))
    assert response.url.startswith(reverse("login"))
    assert _session_user(dev_client) == ""


def test_a_forged_mark_closes_the_session(dev_client, link):
    _enter(dev_client, link)
    session = dev_client.session
    session[state.LINKED_KEY] = "forged"
    session.save()
    assert dev_client.get(reverse("dashboard")).url.startswith(reverse("login"))
    assert _session_user(dev_client) == ""
