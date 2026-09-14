"""سياسةُ قفل الدخول (قرار 2026-09-14).

- القفلُ خمسُ دقائق في البابين: عدّادُ المنصّة وaxes.
- axes يقفل الحسابَ **من العنوان نفسه**، لا كلَّ من خلف عنوانٍ مشترك.
- قفلٌ انتهت مدّتُه يبدأ العدُّ بعده من الصفر.
- المعرّفُ بالأرقام اللاتينيّة وحدها، والعربيّةُ تُردّ برسالةٍ تقول ذلك.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from core import views_auth


def _login(client, user, password="wrong", identifier=None):  # pragma: allowlist secret
    return client.post(
        "/auth/login/",
        {"national_id": identifier or user.national_id, "password": password},
    )


def test_both_locks_last_five_minutes():
    assert views_auth.LOCK_MINUTES == 5
    assert settings.AXES_COOLOFF_TIME == timedelta(minutes=5)


def test_axes_locks_the_account_from_that_address_not_everyone_behind_it():
    """القائمةُ المسطّحة تعني «أيّهما» في axes — والمتداخلةُ «كلاهما»."""
    assert settings.AXES_LOCKOUT_PARAMETERS == [["username", "ip_address"]]


def test_an_expired_lock_starts_counting_from_zero(client, teacher_user):
    teacher_user.failed_login_attempts = views_auth.FAILURES_BEFORE_LOCK
    teacher_user.locked_until = timezone.now() - timedelta(seconds=1)
    teacher_user.save(update_fields=["failed_login_attempts", "locked_until"])

    response = _login(client, teacher_user)

    teacher_user.refresh_from_db()
    assert teacher_user.failed_login_attempts == 1
    assert teacher_user.locked_until is None
    assert "قفل" not in response.content.decode()


def test_a_running_lock_still_holds(client, teacher_user):
    teacher_user.locked_until = timezone.now() + timedelta(minutes=3)
    teacher_user.save(update_fields=["locked_until"])

    response = _login(client, teacher_user, password="testpass123")

    assert "مقفل" in response.content.decode()
    assert "_auth_user_id" not in client.session


def test_arabic_digits_are_refused_with_a_reason_and_not_counted(client, teacher_user):
    arabic = teacher_user.national_id.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))

    response = _login(client, teacher_user, password="testpass123", identifier=arabic)

    assert views_auth.LATIN_DIGITS_ONLY in response.content.decode()
    assert "_auth_user_id" not in client.session
    teacher_user.refresh_from_db()
    assert teacher_user.failed_login_attempts == 0


def test_the_form_asks_for_latin_digits(client, db):
    html = client.get("/auth/login/").content.decode()
    assert 'pattern="[0-9]{5,20}"' in html
    assert "الأرقام الإنجليزية" in html
