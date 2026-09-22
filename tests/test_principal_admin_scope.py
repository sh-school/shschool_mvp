"""[SECURITY] المدير `is_staff` بصلاحيّاتٍ صريحة لا `is_superuser` — قرارُ المالك 2026-09-22.

كان `full_seed.py` يمنح المدير `is_superuser`: يتجاوز نظامَ الصلاحيّات بالكامل،
فيقدر أن يعدّل درجةً أو سجلّاً صحّيّاً مباشرةً في الجدول متجاوزاً كلَّ حارسٍ في
`services.py`، ويدخل `roadmap/` المخصّصة للمطوّر (`is_platform_developer` تُرجع
True لأيّ superuser)، ويمنح نفسَه صلاحيّاتٍ أخرى عبر تعديل CustomUser الخام.
"""

from io import StringIO

import pytest
from django.contrib.auth.models import Group
from django.core.management import call_command

from core.admin_access import (
    FULL_ACCESS_MODELS,
    PRINCIPAL_GROUP_NAME,
    VIEW_ONLY_MODELS,
    sync_principal_admin_group,
)
from core.models import CustomUser
from core.models.access import Membership, Role


def _run(*args):
    out = StringIO()
    call_command("scope_principal_admin_access", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def principal(db, school):
    user = CustomUser.objects.create(
        must_change_password=False,
        national_id="9990009999",
        full_name="مدير الاختبار",
        is_superuser=True,
        is_staff=True,
    )
    role, _ = Role.objects.get_or_create(school=school, name="principal")
    Membership.objects.create(user=user, school=school, role=role, is_active=True)
    return user


def test_the_group_grants_exactly_the_documented_permissions(db):
    group = sync_principal_admin_group()
    codenames = {
        (p.content_type.app_label, p.content_type.model, p.codename.split("_", 1)[0])
        for p in group.permissions.select_related("content_type")
    }
    for app_label, model in FULL_ACCESS_MODELS:
        for action in ("view", "add", "change", "delete"):
            assert (app_label, model, action) in codenames, (app_label, model, action)
    for app_label, model in VIEW_ONLY_MODELS:
        assert (app_label, model, "view") in codenames
        assert (app_label, model, "change") not in codenames
        assert (app_label, model, "delete") not in codenames


def test_customuser_is_view_only_never_change_or_delete(db):
    """منحُ change على CustomUser يسمح نظريّاً بإعادة is_superuser يدويّاً — ممنوعٌ عمداً."""
    group = sync_principal_admin_group()
    codenames = {p.codename for p in group.permissions.all()}
    assert "view_customuser" in codenames
    assert "change_customuser" not in codenames
    assert "delete_customuser" not in codenames


def test_apply_converts_the_principal_account(db, principal):
    _run("--apply")

    principal.refresh_from_db()
    assert principal.is_superuser is False
    assert principal.is_staff is True
    assert principal.groups.filter(name=PRINCIPAL_GROUP_NAME).exists()


def test_without_apply_nothing_changes(db, principal):
    out = _run()

    principal.refresh_from_db()
    assert principal.is_superuser is True
    assert "عرضٌ فقط" in out


def test_a_superuser_who_is_not_principal_is_left_alone(db, school):
    user = CustomUser.objects.create(
        must_change_password=False,
        national_id="9990008888",
        full_name="مطوّر الاختبار",
        is_superuser=True,
    )
    role, _ = Role.objects.get_or_create(school=school, name="platform_developer")
    Membership.objects.create(user=user, school=school, role=role, is_active=True)

    _run("--apply")

    user.refresh_from_db()
    assert user.is_superuser is True


def test_syncing_again_drops_a_permission_removed_from_the_lists(db, monkeypatch):
    """إعادةُ المزامنة تُصلح الانجراف — لا تتراكم صلاحيّاتٌ سُحبت من القوائم."""
    import core.admin_access as mod

    group = sync_principal_admin_group()
    assert group.permissions.filter(codename="view_school").exists()

    monkeypatch.setattr(mod, "FULL_ACCESS_MODELS", frozenset())
    group = sync_principal_admin_group()

    assert not group.permissions.filter(codename="view_school").exists()


def test_sync_is_idempotent_and_returns_the_same_group(db):
    first = sync_principal_admin_group()
    second = sync_principal_admin_group()
    assert first.pk == second.pk
    assert Group.objects.filter(name=PRINCIPAL_GROUP_NAME).count() == 1
