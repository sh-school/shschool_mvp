"""[PII] أعمدةُ الهاتف الثلاثة وحدةٌ واحدة: `phone` و`phone_encrypted` و`phone_hmac`.

القارئون يتحوّلون إلى `get_phone_decrypted()` تمهيداً لإسقاط العمود الصريح (البند 13).
وهذا يكشف ثغرةً قديمة: مسحُ `phone` كان يترك النسخةَ المشفَّرة والبصمةَ، فيبقى الرقمُ
الملغى قابلاً للفكّ — وإشعاراتُ SMS كانت ستصل إليه بعد أن حذفه صاحبُه.
"""

import pytest

from core.models import CustomUser
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db

NUMBER = "+97450000022"


def test_clearing_the_phone_clears_its_encrypted_copy_and_hash():
    user = UserFactory(phone=NUMBER)
    assert user.phone_encrypted and user.phone_hmac

    user.phone = ""
    user.save()

    fresh = CustomUser.objects.get(pk=user.pk)
    assert (fresh.phone, fresh.phone_encrypted, fresh.phone_hmac) == ("", "", "")
    assert fresh.get_phone_decrypted() == ""


def test_update_fields_phone_persists_the_encrypted_copy_too():
    """`save(update_fields=["phone"])` كان يحفظ الصريحَ وحدَه."""
    user = UserFactory(phone="")
    user.phone = NUMBER
    user.save(update_fields=["phone"])

    fresh = CustomUser.objects.get(pk=user.pk)
    assert fresh.phone_encrypted and fresh.phone_hmac
    assert fresh.get_phone_decrypted() == NUMBER


def test_update_fields_phone_cleared_persists_the_clearing():
    user = UserFactory(phone=NUMBER)
    user.phone = ""
    user.save(update_fields=["phone"])

    fresh = CustomUser.objects.get(pk=user.pk)
    assert (fresh.phone_encrypted, fresh.phone_hmac) == ("", "")


def test_changing_the_number_replaces_the_copy():
    user = UserFactory(phone=NUMBER)
    user.phone = "+97450000077"
    user.save()

    fresh = CustomUser.objects.get(pk=user.pk)
    assert fresh.get_phone_decrypted() == "+97450000077"


def test_unrelated_update_fields_do_not_touch_the_phone_columns():
    user = UserFactory(phone=NUMBER)
    before = CustomUser.objects.get(pk=user.pk).phone_encrypted

    user.full_name = "اسمٌ جديد"
    user.save(update_fields=["full_name"])

    assert CustomUser.objects.get(pk=user.pk).phone_encrypted == before
