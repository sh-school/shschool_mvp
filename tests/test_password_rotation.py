"""[AUTH] تدويرُ كلمة مرور المنتسبين كلَّ تسعين يوماً — وتغييرُها بالأصول من القائمة.

قرار 2026-09-08: من الكادر من مضت على كلمته مدّةُ التدوير يُجبَر على تغييرها
عند الدخول التالي — بآلة الإجبار القائمة نفسِها — ولا يمسّ ذلك الطلبةَ وأولياءَ
الأمور. ولكلّ مستخدمٍ صفحةٌ يبدّل فيها كلمتَه بشرط الحاليّة.
"""

from datetime import timedelta

import pytest
from django.utils import timezone

from core.views_auth import password_expired

pytestmark = pytest.mark.django_db

STRONG = "Qatar-School#2026-Strong"


def _login(client, user, password="testpass123"):
    return client.post("/auth/login/", {"national_id": user.national_id, "password": password})


def test_a_staff_password_older_than_the_policy_is_forced_at_login(client, teacher_user):
    teacher_user.last_password_change = timezone.now() - timedelta(days=91)
    teacher_user.save(update_fields=["last_password_change"])

    resp = _login(client, teacher_user)

    teacher_user.refresh_from_db()
    assert resp.status_code == 302 and "force_change_password" in resp.url
    assert teacher_user.must_change_password is True


def test_a_recently_changed_staff_password_passes(client, teacher_user):
    teacher_user.last_password_change = timezone.now() - timedelta(days=10)
    teacher_user.save(update_fields=["last_password_change"])

    resp = _login(client, teacher_user)

    assert resp.status_code == 302 and "/dashboard/" in resp.url
    assert password_expired(teacher_user) is False


def test_a_never_changed_password_counts_from_account_creation(teacher_user):
    """كلمةُ البذر التي لم تُبدَّل قطّ: المرجعُ تاريخُ الإنشاء — لا إعفاءَ بغياب السجلّ."""
    teacher_user.last_password_change = None
    teacher_user.date_joined = timezone.now() - timedelta(days=120)
    teacher_user.save(update_fields=["last_password_change", "date_joined"])
    assert password_expired(teacher_user) is True

    teacher_user.date_joined = timezone.now() - timedelta(days=5)
    teacher_user.save(update_fields=["date_joined"])
    assert password_expired(teacher_user) is False


def test_students_and_parents_are_outside_the_policy(client, student_user):
    student_user.last_password_change = timezone.now() - timedelta(days=400)
    student_user.save(update_fields=["last_password_change"])

    assert password_expired(student_user) is False
    resp = _login(client, student_user)
    student_user.refresh_from_db()
    assert student_user.must_change_password is False
    assert "force_change_password" not in (resp.url or "")


def test_the_policy_can_be_switched_off(settings, teacher_user):
    settings.PASSWORD_ROTATION_DAYS = 0
    teacher_user.last_password_change = timezone.now() - timedelta(days=1000)
    teacher_user.save(update_fields=["last_password_change"])
    assert password_expired(teacher_user) is False


def test_changing_the_password_requires_the_current_one(client_as, teacher_user):
    client = client_as(teacher_user)
    before = teacher_user.last_password_change

    resp = client.post(
        "/auth/change-password/",
        {"current_password": "wrong", "password1": STRONG, "password2": STRONG},
    )
    teacher_user.refresh_from_db()
    assert resp.status_code == 200, "خطأٌ يُعرض في الصفحة نفسِها"
    assert teacher_user.check_password("testpass123"), "الكلمةُ لم تتغيّر بحاليّةٍ خاطئة"
    assert teacher_user.last_password_change == before


def test_changing_the_password_properly_resets_the_rotation_clock_and_keeps_the_session(
    client_as, teacher_user
):
    client = client_as(teacher_user)
    teacher_user.last_password_change = timezone.now() - timedelta(days=80)
    teacher_user.save(update_fields=["last_password_change"])

    resp = client.post(
        "/auth/change-password/",
        {"current_password": "testpass123", "password1": STRONG, "password2": STRONG},
    )

    teacher_user.refresh_from_db()
    assert resp.status_code == 302 and "/dashboard/" in resp.url
    assert teacher_user.check_password(STRONG)
    assert teacher_user.last_password_change > timezone.now() - timedelta(minutes=1)
    assert password_expired(teacher_user) is False
    assert client.get("/dashboard/").status_code == 200, "الجلسةُ باقيةٌ بعد التغيير"


def test_the_page_is_linked_from_every_users_menu(client_as, teacher_user):
    client = client_as(teacher_user)
    page = client.get("/auth/change-password/")
    assert page.status_code == 200
    assert "/auth/change-password/" in client.get("/dashboard/").content.decode()
