"""بحثُ سجلّ الموظفين بالجوّال بعد أن صار مشفَّراً — مطابقةٌ في الذاكرة على الأرقام.

`phone__icontains` لا يعمل على عمودٍ مشفَّر، وحذفُ الصريح (البند 13) يُبطله. فالبحثُ
الجزئيُّ باقٍ بفكّ أرقام قائمةِ مدرسةٍ واحدة ومطابقتِها.
"""

import pytest

from core.models import CustomUser
from staff_affairs.selectors import MIN_PHONE_DIGITS, phone_holder_ids
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db


def _ids(term):
    return set(phone_holder_ids(CustomUser.objects.all(), term))


def test_partial_digits_find_the_holder():
    holder = UserFactory(phone="+97455001122")
    UserFactory(phone="+97466778899")

    assert _ids("0011") == {holder.pk}


def test_spacing_and_plus_sign_do_not_matter():
    holder = UserFactory(phone="+97455001122")

    assert _ids("5500 1122") == {holder.pk}
    assert _ids("+974 5500 1122") == {holder.pk}
    assert _ids("55-00-11-22") == {holder.pk}


def test_too_few_digits_search_nothing():
    UserFactory(phone="+97455001122")

    assert _ids("1" * (MIN_PHONE_DIGITS - 1)) == set()
    assert _ids("ahmad") == set()


def test_a_cleared_phone_is_not_found_any_more():
    """النسخةُ المشفَّرة تُمسح مع الصريح — فلا يبقى الرقمُ الملغى يُعثر عليه."""
    user = UserFactory(phone="+97455001122")
    user.phone = ""
    user.save()

    assert _ids("55001122") == set()


def test_users_without_a_phone_are_ignored():
    UserFactory(phone="")

    assert _ids("55001122") == set()
