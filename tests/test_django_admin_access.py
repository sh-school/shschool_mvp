"""[SECURITY] بابُ لوحة إدارة جانغو ليس للجميع.

`is_staff` محورٌ منفصلٌ عن أدوار المنصّة: لا يمنح صلاحيةً على بيانات، بل
يفتح `/admin/` — صفحةَ دخولٍ ثانية خارج تدفّق المنصّة وحرّاسها.

ووُجد في الإنتاج على ١٢٩ حساباً من ١٤٢٥: اثنان وستّون معلّماً، وتسعةُ
أولياء أمور، وأربعةٌ فقط منهم قيادةٌ فعليّة. ومصدرُه `full_seed` الذي
يضعه لكل من يُنشئه من الطاقم.

والضررُ اليوم محدود — ثلاثةُ حساباتٍ فقط تحمل صلاحياتٍ على النماذج —
لكنّ البابَ مفتوح: أيُّ صلاحيةٍ تُمنح لمجموعةٍ يوماً تسري عليهم جميعاً.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from core.management.commands.revoke_django_admin_access import ADMIN_SITE_ROLES
from core.models import CustomUser
from core.models.access import Membership, Role


def _run(*args):
    out = StringIO()
    call_command("revoke_django_admin_access", *args, stdout=out)
    return out.getvalue()


@pytest.fixture
def person(db, school):
    def _make(name, role_name, *, staff=True, superuser=False):
        user = CustomUser.objects.create(
            national_id=f"288{abs(hash(name)) % 10**8:08d}",
            full_name=name,
            is_staff=staff,
            is_superuser=superuser,
        )
        role, _ = Role.objects.get_or_create(school=school, name=role_name)
        Membership.objects.create(user=user, school=school, role=role)
        return user

    return _make


# ── من يُغلق عنه ─────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["teacher", "parent", "coordinator", "specialist"])
def test_the_door_closes_on_everyone_but_leadership(db, person, role):
    user = person(f"شخص {role}", role)

    _run("--apply")

    user.refresh_from_db()
    assert user.is_staff is False


def test_platform_roles_are_untouched(db, person):
    """`is_staff` محورٌ آخر — إطفاؤه لا يمسّ دور المعلّم في المنصّة."""
    user = person("معلّم", "teacher")

    _run("--apply")

    assert user.get_role() == "teacher"
    assert Membership.objects.filter(user=user, is_active=True).count() == 1


# ── من يبقى له الباب ─────────────────────────────────────────────────


@pytest.mark.parametrize("role", ADMIN_SITE_ROLES)
def test_leadership_keeps_the_door(db, person, role):
    user = person(f"قيادة {role}", role)

    _run("--apply")

    user.refresh_from_db()
    assert user.is_staff is True


def test_a_superuser_is_never_locked_out(db, person):
    """إطفاؤه عن superuser يقفل الباب على أهله."""
    user = person("مالك النظام", "teacher", superuser=True)

    _run("--apply")

    user.refresh_from_db()
    assert user.is_staff is True


# ── العرض قبل الكتابة ─────────────────────────────────────────────────


def test_without_apply_nothing_changes(db, person):
    user = person("معلّم", "teacher")

    out = _run()

    user.refresh_from_db()
    assert user.is_staff is True
    assert "عرضٌ فقط" in out


# ── المصدر لا يعود ───────────────────────────────────────────────────


def test_the_seed_does_not_hand_out_the_admin_door():
    """`full_seed` كان يضع `is_staff=True` لكل من يُنشئه من الطاقم —
    وهو مصدرُ المئة والتسعة والعشرين."""
    import pathlib
    import re

    src = pathlib.Path("core/management/commands/full_seed.py").read_text(encoding="utf-8")
    grants = re.findall(r'"is_staff":\s*True|is_staff\s*=\s*True', src)

    assert not grants, "البذور لا تمنح بابَ لوحة الإدارة"
