"""[PII] repair_pii_columns — إعادةُ بناء المشفَّر والبصمة من الصريح، بلا مسّ السليم ولا عرض قيمة.

الإنتاجُ (2026-09-19): 823 رقماً شخصيّاً و130 جوّالاً مشفَّراً لا تُفكّ — صفوفُ 2026-03 بمفتاحٍ
دُوِّر بلا `FERNET_OLD_KEYS`. والصريحُ موجود؛ فالإصلاحُ يُعيد التشفيرَ منه بالمفتاح الحاليّ.
"""

import io

import pytest
from cryptography.fernet import Fernet
from django.core.management import call_command
from django.core.management.base import CommandError

from core.models import CustomUser
from core.models.crypto import decrypt_field, hmac_field
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db

FOREIGN = Fernet(Fernet.generate_key())


def _break(user, *, national_id=False, phone=False):
    """يحاكي صفَّ مارس: مشفَّرٌ بمفتاحٍ آخر وبصمةٌ من مفتاحٍ آخر، والصريحُ سليم."""
    fields = {}
    if national_id:
        fields.update(
            national_id_encrypted=FOREIGN.encrypt(user.national_id.encode()).decode(),
            national_id_hmac="0" * 64,
        )
    if phone:
        fields.update(
            phone_encrypted=FOREIGN.encrypt(user.phone.encode()).decode(),
            phone_hmac="1" * 64,
        )
    CustomUser.objects.filter(pk=user.pk).update(**fields)


def _run(*args):
    out = io.StringIO()
    call_command("repair_pii_columns", *args, stdout=out)
    return out.getvalue()


def _healthy(user):
    fresh = CustomUser.objects.get(pk=user.pk)
    return (
        decrypt_field(fresh.national_id_encrypted) == fresh.national_id
        and fresh.national_id_hmac == hmac_field(fresh.national_id)
        and decrypt_field(fresh.phone_encrypted) == fresh.phone
        and fresh.phone_hmac == hmac_field(fresh.phone)
    )


def test_a_healthy_database_reports_nothing_to_repair():
    UserFactory()

    out = _run()

    assert "معطوب 0" in out
    assert "لا شيء يحتاج إصلاحاً" in out


def test_the_default_run_is_a_preview_and_writes_nothing():
    user = UserFactory()
    _break(user, national_id=True, phone=True)
    before = CustomUser.objects.get(pk=user.pk)

    out = _run()

    after = CustomUser.objects.get(pk=user.pk)
    assert (after.national_id_encrypted, after.phone_hmac) == (
        before.national_id_encrypted,
        before.phone_hmac,
    )
    assert "معاينة" in out
    assert not _healthy(user)


def test_apply_rebuilds_both_fields_from_the_plaintext():
    user = UserFactory()
    _break(user, national_id=True, phone=True)
    assert not _healthy(user)

    _run("--apply")

    assert _healthy(user)
    fresh = CustomUser.objects.get(pk=user.pk)
    assert fresh.national_id == user.national_id, "الصريحُ لا يُمسّ"
    assert fresh.phone == user.phone


def test_only_the_broken_field_is_rewritten():
    user = UserFactory()
    _break(user, phone=True)
    good_nid = CustomUser.objects.get(pk=user.pk).national_id_encrypted

    _run("--apply")

    fresh = CustomUser.objects.get(pk=user.pk)
    assert fresh.national_id_encrypted == good_nid, "الحقلُ السليم لا يُعاد تشفيرُه"
    assert _healthy(user)


def test_a_healthy_row_is_never_touched():
    healthy, broken = UserFactory(), UserFactory()
    _break(broken, national_id=True)
    before = CustomUser.objects.get(pk=healthy.pk)

    _run("--apply")

    after = CustomUser.objects.get(pk=healthy.pk)
    assert after.national_id_encrypted == before.national_id_encrypted
    assert after.phone_encrypted == before.phone_encrypted


def test_a_second_run_finds_nothing():
    user = UserFactory()
    _break(user, national_id=True, phone=True)
    _run("--apply")

    out = _run()

    assert "معطوب 0" in out
    assert "لا شيء يحتاج إصلاحاً" in out


def test_a_wrong_hmac_alone_is_enough_to_repair():
    user = UserFactory()
    CustomUser.objects.filter(pk=user.pk).update(national_id_hmac="f" * 64)

    _run("--apply")

    assert _healthy(user)


def test_an_orphan_is_reported_and_left_alone():
    """مشفَّرٌ بلا صريح: لا مصدرَ يُبنى منه — يُبلَّغ عنه ولا يُلمس."""
    user = UserFactory()
    CustomUser.objects.filter(pk=user.pk).update(phone="")
    before = CustomUser.objects.get(pk=user.pk).phone_encrypted

    out = _run("--apply")

    assert CustomUser.objects.get(pk=user.pk).phone_encrypted == before
    assert "يتيم (مشفَّر بلا صريح) 1" in out


def test_check_fails_when_a_row_is_broken_and_passes_when_healthy():
    user = UserFactory()
    _break(user, phone=True)

    with pytest.raises(CommandError):
        _run("--check")

    _run("--apply")
    assert "سليم" in _run("--check")


def test_the_output_never_carries_a_value():
    user = UserFactory()
    _break(user, national_id=True, phone=True)

    out = _run("--apply") + _run()

    assert user.national_id not in out
    assert user.phone not in out


def test_many_rows_in_small_batches():
    users = [UserFactory() for _ in range(5)]
    for user in users:
        _break(user, national_id=True, phone=True)

    _run("--apply", "--batch-size", "2")

    assert all(_healthy(user) for user in users)
