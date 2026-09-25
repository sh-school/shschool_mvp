"""[ADMIN] جدولا رموز JWT خارجَ الإدارة ما دام JWT مغلقاً (OWN-19).

الجدولان فارغان دائماً (بابُ JWT مغلقٌ منذ P1-1)، وكانا صفحتين فارغتين باسمَين إنجليزيَّين في كلّ فهرس بحث.
`core/admin_hidden.py` يُلغي تسجيلَهما، و`core/admin_menu.py:JWT_TABLES` يتبع الرايةَ نفسَها.
"""

import pytest
from django.conf import settings
from django.contrib import admin
from django.contrib.admin.sites import site
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from core.admin_hidden import hide_unused_jwt_tables
from core.admin_menu import JWT_TABLES, mapped_keys

pytestmark = pytest.mark.django_db

TOKEN_MODELS = (OutstandingToken, BlacklistedToken)


@pytest.fixture
def superuser(developer_user):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    return developer_user


def test_the_flag_is_off_in_this_environment():
    """الاختباراتُ الآتية تفترض الرايةَ مطفأة كما في الإنتاج — وإلّا فلا معنى لها."""
    assert settings.API_JWT_ENABLED is False


def test_the_token_tables_are_not_registered_in_the_admin():
    for model in TOKEN_MODELS:
        assert not site.is_registered(model), model.__name__


def test_the_menu_does_not_map_them_while_jwt_is_closed():
    assert JWT_TABLES == ()
    assert not [k for k in mapped_keys() if k.startswith("token_blacklist.")]


def test_no_admin_page_links_to_them(client_as, superuser):
    html = client_as(superuser).get("/admin/").content.decode()

    assert "token_blacklist" not in html
    assert "Outstanding Tokens" not in html and "Blacklisted Tokens" not in html


@pytest.mark.parametrize("model", ["outstandingtoken", "blacklistedtoken"])
def test_their_pages_no_longer_exist(client_as, superuser, model):
    assert client_as(superuser).get(f"/admin/token_blacklist/{model}/").status_code == 404


def test_hiding_is_repeatable_and_leaves_the_tables_alone():
    hide_unused_jwt_tables()
    hide_unused_jwt_tables()

    assert OutstandingToken.objects.count() == 0 and BlacklistedToken.objects.count() == 0


def test_an_open_jwt_keeps_the_pages(settings):
    """الرايةُ المفتوحةُ تُبقي التسجيل — وإلّا فقد المطوّرُ رؤيةَ رموزٍ حقيقيّة."""
    settings.API_JWT_ENABLED = True
    try:
        admin.site.register(OutstandingToken)
        hide_unused_jwt_tables()

        assert site.is_registered(OutstandingToken)
    finally:
        if site.is_registered(OutstandingToken):
            admin.site.unregister(OutstandingToken)
