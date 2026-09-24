"""[PRIVACY] ترحيبُ ترويسة الإدارة باسم المستخدم لا برقمه الشخصيّ (PDPPL م.8).

نصُّ جانغو `firstof user.get_short_name user.get_username` يقع على `get_username` لأنّ `CustomUser` لا يعرّف
`get_short_name` — فكان الرقمُ الشخصيُّ كاملاً في ترويسة كلّ صفحةٍ (وفي لقطة الشاشة وعند المشاركة)، وقد أُخفي من
`__str__` وقوائم المستخدمين وسجلّ الدخول. `templates/admin/base_site.html` يستبدل كتلةَ الترحيب.
"""

import pytest

pytestmark = pytest.mark.django_db


@pytest.fixture
def superuser(developer_user):
    developer_user.full_name = "المطوّرُ صاحبُ الحساب"
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    return developer_user


@pytest.mark.parametrize("path", ["/admin/", "/admin/core/department/", "/admin/auth/group/"])
def test_the_header_greets_by_name_and_never_shows_the_national_id(client_as, superuser, path):
    html = client_as(superuser).get(path).content.decode()

    assert superuser.national_id not in html, f"الرقمُ الشخصيُّ ظاهرٌ في {path}"
    assert 'id="user-tools"' in html
    header = html[html.index('id="user-tools"') :]
    assert "المطوّرُ صاحبُ الحساب" in header[: header.index("</div>")]


def test_the_change_password_link_and_logout_remain(client_as, superuser):
    html = client_as(superuser).get("/admin/").content.decode()
    header = html[html.index('id="user-tools"') :]
    header = header[: header.index("</div>")]

    assert "/admin/password_change/" in header and "logout" in header
