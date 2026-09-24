"""[I18N] صفحتا كلمة المرور في إدارة المستخدمين عربيّتان (OWN-19).

كان جانغو 5.2 يرسم في «تعديل مستخدم» نصوصاً إنجليزيّةً لا ترجمةَ لها في كتالوجه («Reset password»،
«Raw passwords are not stored…»، و«salt» و«hash»)، وفي «تغيير كلمة المرور» «Password-based authentication:
Enabled/Disabled» وجملةً حرفيّةً بلا gettext. والتعريبُ في `core/admin_password_forms.py`.

يُختبر الرسمُ نفسُه لا القاموسُ: إن أعاد جانغو صياغةَ نصٍّ فبقي إنجليزيّاً سقط الاختبارُ وسمّاه.
"""

import pytest
from django.urls import reverse

from core.admin_password_forms import ARABIC, arabic
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db

#: ما كان يظهر بالإنجليزيّة في الصفحتين (2026-09-24) — كلُّه يجب أن يغيب.
ENGLISH_ON_CHANGE_PAGE = (
    "Reset password",
    "Raw passwords are not stored",
    ">salt<",
    ">hash<",
)
ENGLISH_ON_PASSWORD_PAGE = (
    "Password-based authentication",
    "Enabled",
    "Disabled",
    "Whether the user will be able",
    "If disabled",
)


@pytest.fixture
def superuser(developer_user):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    return developer_user


def _get(client_as, superuser, name, target):
    response = client_as(superuser).get(reverse(name, args=[target.pk]))
    assert response.status_code == 200
    return response.content.decode()


def test_the_change_page_shows_the_password_summary_in_arabic(client_as, superuser):
    target = UserFactory(full_name="مستخدمٌ بكلمة مرور")
    html = _get(client_as, superuser, "admin:core_customuser_change", target)

    for english in ENGLISH_ON_CHANGE_PAGE:
        assert english not in html, f"بقي «{english}» في صفحة تعديل المستخدم"
    for arabic_text in ("إعادة تعيين كلمة المرور", "الملح", "التجزئة", "لا تُخزَّن كلمات المرور"):
        assert arabic_text in html, arabic_text


def test_a_user_without_a_password_gets_the_arabic_set_button(client_as, superuser):
    target = UserFactory(full_name="مستخدمٌ بلا كلمة مرور")
    target.set_unusable_password()
    target.save()
    html = _get(client_as, superuser, "admin:core_customuser_change", target)

    for english in ("Set password", "No password set", "Enable password-based authentication"):
        assert english not in html, english
    for arabic_text in ("تعيين كلمة المرور", "فعِّل الدخول بكلمة مرور"):
        assert arabic_text in html, arabic_text


def test_the_password_change_page_is_arabic(client_as, superuser):
    target = UserFactory(full_name="مستخدمٌ يغيّر كلمته")
    response = client_as(superuser).get(f"/admin/core/customuser/{target.pk}/password/")
    assert response.status_code == 200
    html = response.content.decode()

    for english in ENGLISH_ON_PASSWORD_PAGE:
        assert english not in html, f"بقي «{english}» في صفحة تغيير كلمة المرور"
    for arabic_text in ("الدخول بكلمة مرور", "مفعّل", "معطّل", "إن عُطّل فستُفقد"):
        assert arabic_text in html, arabic_text


def test_a_django_translation_wins_over_ours():
    """لا نكتب فوق ما ترجمه جانغو: النصُّ الذي ليس مفتاحَ القاموس يُعاد كما هو."""
    assert arabic("خوارزمية") == "خوارزمية"
    assert arabic("Reset password") == ARABIC["Reset password"]
