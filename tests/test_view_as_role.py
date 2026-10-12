"""[SECURITY] «عرض بصفة دور» — معاينةُ الدور لمطوّر المنصّة (W-20261009-032، D-303م وD-304م).

المعاييرُ المقيسة في البطاقة: كلُّ دورٍ يُبدَّل إليه وتُرى لوحتُه، وغيرُ المطوّر 403 والطالبُ ووليُّ الأمر غيرُ مدرجين،
والكتابةُ بصلاحيّات الدور المعروض والرفضُ لما لا يملكه، والعلامةُ تنتهي بمدّتها وتسقط إن لم يعد صاحبُها مطوّراً،
والتبديلُ بعد الحدّ 429 بسطر، وأنواعُ `view_as_*` بمسارٍ منظَّف وصفةِ الفاعل، والشريطُ الثابتُ بزرّ العودة.
"""

from __future__ import annotations

import pytest
from django.test import RequestFactory
from django.urls import reverse

from core.models import AuditLog, Membership, Role
from core.models.access import TIER_1_LEADERSHIP, TIER_2_DEPUTIES, TIER_3_SUPERVISORS, TIER_4_STAFF
from core.module_registry import get_protected_paths
from core.view_as import policy, state
from core.view_as.masking import mask_user
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

START = "/developer/view-as/start/"
STOP = "/developer/view-as/stop/"
PICKER = "/developer/view-as/"


def _member(school, role, **kwargs):
    user = UserFactory(**kwargs)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def developer(school):
    return _member(school, "platform_developer", full_name="مطوّر المنصّة")


@pytest.fixture
def dev_client(client, developer):
    client.force_login(developer)
    return client


def _rows(action, **filters):
    return AuditLog.objects.filter(action=action, **filters).order_by("timestamp")


def _start(client, role, **headers):
    return client.post(START, {"role": role}, **headers)


def _resign(client, **changes):
    """يعيد توقيعَ علامة المعاينة بحقولٍ معدَّلة — كما لو مضى الوقت."""
    session = client.session
    payload = state.unsign(session[state.ROLE_KEY], state.ROLE_SALT)
    payload.update(changes)
    session[state.ROLE_KEY] = state.sign(payload, state.ROLE_SALT)
    session.save()


def _leadership_only_prefix():
    for prefix, roles in get_protected_paths().items():
        if "principal" in roles and "teacher" not in roles:
            return prefix
    pytest.skip("لا بوّابةَ وحدةٍ للقيادة دون المعلّم")


# ── القائمة ─────────────────────────────────────────────────────


def test_the_viewable_roles_are_the_four_staff_tiers_only():
    staff = TIER_1_LEADERSHIP | TIER_2_DEPUTIES | TIER_3_SUPERVISORS | TIER_4_STAFF
    assert set(policy.VIEWABLE_ROLES) == staff
    for excluded in ("parent", "student", "platform_developer"):
        assert excluded not in policy.VIEWABLE_ROLES


def test_every_viewable_role_sits_in_exactly_one_column():
    columns = [name for group in policy.role_groups() for name, _label in group["roles"]]
    assert sorted(columns) == sorted(policy.VIEWABLE_ROLES)
    assert [group["key"] for group in policy.role_groups()] == [
        "leadership",
        "classroom",
        "support",
        "administrative",
    ]


def test_the_developer_sees_the_picker_with_every_role(dev_client):
    response = dev_client.get(PICKER)
    assert response.status_code == 200
    shown = {name for group in response.context["groups"] for name, _label in group["roles"]}
    assert shown == set(policy.VIEWABLE_ROLES)
    assert 'id="btn-view-as"' in response.content.decode()


# ── الرفض لغير المطوّر ─────────────────────────────────────────


@pytest.mark.parametrize("method,path", [("get", PICKER), ("post", START)])
def test_a_teacher_is_refused_with_403_and_a_row(client, school, method, path):
    teacher = _member(school, "teacher")
    client.force_login(teacher)
    response = getattr(client, method)(path, {"role": "principal"} if method == "post" else None)
    assert response.status_code == 403
    assert _rows("view_as_denied", user=teacher).exists()
    assert state.ROLE_KEY not in client.session


def test_a_superuser_without_the_developer_role_is_refused(client, school):
    root = _member(school, "teacher", is_superuser=True)
    client.force_login(root)
    assert _start(client, "principal").status_code == 403


def test_the_developers_group_alone_is_not_the_developer_role(client, school):
    from django.contrib.auth.models import Group

    member = _member(school, "it_technician")
    member.groups.add(Group.objects.get_or_create(name="developers")[0])
    client.force_login(member)
    assert client.get(PICKER).status_code == 403


def test_a_teacher_does_not_see_the_header_button(client, school):
    client.force_login(_member(school, "teacher"))
    assert 'id="btn-view-as"' not in client.get(reverse("dashboard")).content.decode()


@pytest.mark.parametrize("role", ["parent", "student", "platform_developer", "nonsense"])
def test_a_role_outside_the_list_is_refused(dev_client, developer, role):
    assert _start(dev_client, role).status_code == 403
    assert _rows("view_as_denied", user=developer).last().changes["why"] == "unknown_role"
    assert state.ROLE_KEY not in dev_client.session


# ── كلُّ دورٍ ولوحتُه ─────────────────────────────────────────


@pytest.mark.parametrize("role", policy.VIEWABLE_ROLES)
def test_every_role_can_be_previewed_and_its_dashboard_opens(dev_client, developer, role):
    response = _start(dev_client, role)
    assert response.status_code == 302 and response.url == reverse("dashboard")
    response = dev_client.get(reverse("dashboard"), follow=True)
    assert response.status_code == 200
    request = response.wsgi_request
    assert request.user.pk == developer.pk
    assert request.user.get_role() == role
    assert request.view_as.role == role
    assert "تعاين بصفة" in response.content.decode()


def test_the_start_row_carries_the_actor_and_the_role(dev_client, developer):
    _start(dev_client, "teacher")
    row = _rows("view_as_start", user=developer).get()
    assert row.changes["acting"] == {"actor": str(developer.pk), "as_role": "teacher"}
    assert row.changes["path"] == START


def test_switching_keeps_the_first_start_and_records_the_previous_role(dev_client, developer):
    _start(dev_client, "teacher")
    first = state.unsign(dev_client.session[state.ROLE_KEY], state.ROLE_SALT)["s"]
    _start(dev_client, "principal")
    payload = state.unsign(dev_client.session[state.ROLE_KEY], state.ROLE_SALT)
    assert payload["r"] == "principal" and payload["s"] == first
    switch = _rows("view_as_switch", user=developer).get()
    assert switch.changes["previous"] == "teacher"


def test_htmx_start_redirects_by_header(dev_client):
    response = _start(dev_client, "teacher", HTTP_HX_REQUEST="true")
    assert response.status_code == 204
    assert response["HX-Redirect"] == reverse("dashboard")


# ── الصلاحيّاتُ صلاحيّاتُ الدور المعروض ───────────────────────


def test_the_module_gate_follows_the_shown_role(dev_client):
    prefix = _leadership_only_prefix()
    _start(dev_client, "teacher")
    assert dev_client.get(prefix).status_code == 403
    _start(dev_client, "principal")
    assert dev_client.get(prefix).status_code != 403


def test_the_superuser_flags_are_off_in_the_request_and_kept_in_the_database(dev_client, developer):
    developer.is_superuser = True
    developer.is_staff = True
    developer.save(update_fields=["is_superuser", "is_staff"])
    _start(dev_client, "teacher")
    request = dev_client.get(reverse("dashboard")).wsgi_request
    assert request.user.is_superuser is False and request.user.is_staff is False
    developer.refresh_from_db()
    assert developer.is_superuser is True and developer.is_staff is True


def test_a_write_runs_with_the_role_and_is_logged_with_the_actor(dev_client, developer):
    _start(dev_client, "teacher")
    response = dev_client.post("/notifications/mark-all-read/")
    assert response.status_code == 302
    row = _rows("update", user=developer).last()
    assert row.changes["path"] == "/notifications/mark-all-read/"
    assert row.changes["acting"] == {"actor": str(developer.pk), "as_role": "teacher"}
    assert "معاينةُ مطوّر" in row.changes["capacity"]


def test_a_write_the_role_does_not_own_is_refused_and_not_logged_as_done(dev_client, developer):
    prefix = _leadership_only_prefix()
    _start(dev_client, "teacher")
    assert dev_client.post(prefix).status_code == 403
    assert not _rows("update", user=developer, changes__path=prefix).exists()


def test_view_as_actions_are_not_duplicated_by_the_developer_audit(dev_client, developer):
    _start(dev_client, "teacher")
    dev_client.post(STOP)
    assert not _rows("update", user=developer, changes__path__startswith=PICKER).exists()


# ── أسطرُ الصفحات ─────────────────────────────────────────────


def test_each_page_is_a_row_with_a_clean_path(dev_client, developer):
    _start(dev_client, "teacher")
    dev_client.get(reverse("dashboard") + "?q=secret-term")
    row = _rows("view_as_page", user=developer).last()
    assert row.changes["path"] == reverse("dashboard")
    assert "secret-term" not in str(row.changes) and "secret-term" not in row.object_repr
    assert row.changes["acting"]["as_role"] == "teacher"


def test_audit_rows_written_inside_a_preview_carry_acting():
    from core.middleware import _current_request

    request = RequestFactory().get("/")
    request.view_as = state.ViewAs(kind=state.PREVIEW, actor_id="a1", started=0, role="teacher")
    token = _current_request.set(request)
    try:
        row = AuditLog.log(
            user=None, action="view", model_name="other", object_repr="x", changes={"k": 1}
        )
    finally:
        _current_request.reset(token)
    row = row or AuditLog.objects.order_by("-timestamp").first()
    assert row.changes == {"k": 1, "acting": {"actor": "a1", "as_role": "teacher"}}


@pytest.mark.parametrize(
    ("role", "path"),
    [
        ("teacher", "/auth/change-password/"),
        ("teacher", "/auth/2fa/setup/"),
        ("teacher", "/admin/"),
        ("teacher", "/api/v1/auth/token/"),
        # الدعمُ التقنيّ يملك الصفحةَ بدوره، فحظرُها أثناء المعاينة من المسار لا من الدور (شرط 0104).
        ("it_technician", "/core/it-admin/password-reset/"),
    ],
)
def test_account_pages_are_closed_during_a_preview(dev_client, developer, role, path):
    _start(dev_client, role)
    assert dev_client.get(path).status_code == 403
    row = _rows("view_as_denied", user=developer).last()
    assert row.changes["why"] == "account_page"


# ── الانتهاء ──────────────────────────────────────────────────


def test_stop_returns_the_developer(dev_client, developer):
    _start(dev_client, "teacher")
    response = dev_client.post(STOP)
    assert response.status_code == 302 and response.url == PICKER
    assert _rows("view_as_end", user=developer).get().changes["why"] == "user"
    request = dev_client.get(PICKER).wsgi_request
    assert request.view_as is None and request.user.get_role() == "platform_developer"


@pytest.mark.parametrize(
    "why,shift",
    [
        ("cap", {"s": state.now() - policy.ROLE_CAP_SECONDS - 5}),
        ("idle", None),
    ],
)
def test_the_mark_ends_with_its_duration(dev_client, developer, why, shift):
    _start(dev_client, "teacher")
    if shift:
        _resign(dev_client, **shift)
    else:
        session = dev_client.session
        session[state.ROLE_SEEN_KEY] = state.now() - policy.ROLE_IDLE_SECONDS - 5
        session.save()
    request = dev_client.get(reverse("dashboard")).wsgi_request
    assert request.view_as is None
    assert request.user.get_role() == "platform_developer"
    assert _rows("view_as_end", user=developer).last().changes["why"] == why
    assert state.ROLE_KEY not in dev_client.session


def test_an_expired_mark_does_not_run_a_write(dev_client, developer):
    _start(dev_client, "teacher")
    _resign(dev_client, s=state.now() - policy.ROLE_CAP_SECONDS - 5)
    response = dev_client.post("/notifications/mark-all-read/")
    assert response.status_code == 302 and response.url == reverse("dashboard")
    assert not _rows(
        "update", user=developer, changes__path="/notifications/mark-all-read/"
    ).exists()


def test_the_mark_falls_when_the_account_is_no_longer_a_developer(dev_client, developer, school):
    _start(dev_client, "principal")
    Membership.objects.filter(user=developer).update(
        role=RoleFactory(school=school, name="teacher")
    )
    request = dev_client.get(reverse("dashboard")).wsgi_request
    assert request.view_as is None and request.user.get_role() == "teacher"
    assert _rows("view_as_end", user=developer).last().changes["why"] == "not_developer"


def test_a_forged_mark_is_dropped(dev_client, developer):
    _start(dev_client, "teacher")
    session = dev_client.session
    session[state.ROLE_KEY] = "forged"
    session.save()
    request = dev_client.get(reverse("dashboard")).wsgi_request
    assert request.view_as is None
    assert _rows("view_as_end", user=developer).last().changes["why"] == "bad_token"


def test_a_mark_for_another_actor_is_dropped(dev_client, developer):
    _start(dev_client, "teacher")
    _resign(dev_client, a="someone-else")
    assert dev_client.get(reverse("dashboard")).wsgi_request.view_as is None
    assert _rows("view_as_end", user=developer).last().changes["why"] == "not_developer"


# ── حدُّ التبديل ──────────────────────────────────────────────


def test_switching_past_the_hourly_limit_is_429_and_a_row(dev_client, developer, monkeypatch):
    monkeypatch.setattr("core.view_as.views.ROLE_SWITCHES_PER_HOUR", 2)
    assert _start(dev_client, "teacher").status_code == 302
    assert _start(dev_client, "principal").status_code == 302
    response = _start(dev_client, "nurse")
    assert response.status_code == 429
    assert "بلغ التبديلُ حدَّه" in response.content.decode()
    row = _rows("view_as_limit", user=developer).get()
    assert row.changes["kind"] == state.PREVIEW
    assert row.changes["acting"] == {"actor": str(developer.pk), "as_role": "nurse"}


# ── قيودُ الهويّة لا الدور ──────────────────────────────────────


def _masked(developer, role="teacher"):
    from core.models import CustomUser

    user = CustomUser.objects.get(pk=developer.pk)
    mask_user(user, role)
    return user


def test_a_masked_account_is_never_saved_whole(developer):
    user = _masked(developer)
    with pytest.raises(RuntimeError):
        user.save()
    with pytest.raises(RuntimeError):
        user.save(update_fields=["is_superuser"])
    user.save(update_fields=["last_login"])


def test_the_owner_restrictions_follow_the_identity_not_the_role(developer):
    from api.permissions import NotPlatformDeveloper
    from core.developer_access import is_platform_developer
    from core.unrestricted_role import has_unrestricted_role, is_excluded_developer

    user = _masked(developer, "admin_supervisor")
    assert user.get_role() == "admin_supervisor"
    assert has_unrestricted_role(user) is False
    assert is_platform_developer(user) is False
    assert is_excluded_developer(user, "attendance.mark") is True
    request = RequestFactory().post("/")
    request.user = user
    assert NotPlatformDeveloper().has_permission(request, None) is False


def test_the_masked_role_is_unsaved_and_in_the_real_school(developer, school):
    user = _masked(developer, "nurse")
    membership = user.active_membership
    assert (
        membership.pk is None
        or not Membership.objects.filter(pk=membership.pk, role__name="nurse").exists()
    )
    assert membership.school == school
    assert user.has_role("nurse") and not user.has_role("platform_developer")
    assert Role.objects.filter(school=school, name="nurse").count() <= 1
