"""[PDPPL] المرحلة 1 من محو عمود `phone` الصريح: لا شاشةَ ولا بحثَ يقرأه — فيمكن تفريغُه في المرحلة 2.

الحارسُ: كلُّ اختبارٍ هنا يُفرِّغ العمودَ الصريحَ بـ`update()` (يتجاوز `save()`) ويُبقي النسخةَ المشفَّرة، ثمّ
يثبت أنّ الشاشةَ أو البحثَ يعمل كما كان. وحارسٌ نصّيٌّ يمنع أن يعود قارئٌ خامٌّ.
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from core.models import CustomUser, ParentStudentLink
from core.phone_search import phone_holder_ids
from student_affairs.selectors import guardian_ids_by_phone, guardian_phones
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

ROOT = Path(__file__).resolve().parent.parent
PHONE = "55001234"


def _retire_plaintext(user):
    """الحالُ بعد المرحلة 2: الصريحُ فارغٌ والمشفَّرُ قائم."""
    assert user.phone_encrypted, "الفرضيّةُ: النسخةُ المشفَّرةُ مملوءةٌ بـ save()"
    CustomUser.objects.filter(pk=user.pk).update(phone="")
    user.refresh_from_db()
    assert user.phone == ""


@pytest.fixture
def guardian(db):
    parent = UserFactory(full_name="وليُّ أمرٍ للهاتف", phone=PHONE)
    _retire_plaintext(parent)
    return parent


@pytest.fixture
def pupil(school, guardian):
    kid = UserFactory(full_name="طالبٌ للهاتف")
    MembershipFactory(user=kid, school=school, role=RoleFactory(school=school, name="student"))
    StudentEnrollmentFactory(student=kid, class_group=ClassGroupFactory(school=school))
    ParentStudentLink.objects.create(
        parent=guardian, student=kid, school=school, relationship="father", is_primary=True
    )
    return kid


# ── النموذجُ والبحثُ ─────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_accessor_reads_the_encrypted_copy_once_plaintext_is_retired(guardian):
    assert guardian.get_phone_decrypted() == PHONE


@pytest.mark.django_db
def test_an_unsaved_assignment_wins_over_the_stale_encrypted_copy(guardian):
    guardian.phone = "66009999"
    assert guardian.get_phone_decrypted() == "66009999"


@pytest.mark.django_db
def test_a_user_without_any_phone_gets_an_empty_string():
    assert UserFactory(phone="").get_phone_decrypted() == ""


@pytest.mark.django_db
def test_the_in_memory_search_finds_a_retired_plaintext_holder(guardian):
    assert set(phone_holder_ids(CustomUser.objects.all(), "5500")) == {guardian.pk}


@pytest.mark.django_db
def test_the_in_memory_search_still_finds_a_legacy_row_with_no_encrypted_copy():
    legacy = UserFactory(phone="+97466778899")
    CustomUser.objects.filter(pk=legacy.pk).update(phone_encrypted="", phone_hmac="")
    assert set(phone_holder_ids(CustomUser.objects.all(), "6677")) == {legacy.pk}


@pytest.mark.django_db
def test_guardian_selectors_work_without_the_plaintext(school, pupil, guardian):
    assert guardian_ids_by_phone(school, "5500") == [guardian.pk]
    assert guardian_phones([guardian.pk, None]) == {guardian.pk: PHONE}


# ── الشاشات ──────────────────────────────────────────────────────────────────


@pytest.mark.django_db
def test_the_student_list_shows_and_searches_the_guardian_phone(client_as, principal_user, pupil):
    client = client_as(principal_user)
    url = reverse("student_affairs:student_list")

    shown = client.get(url, {"status": "all"}).content.decode()
    found = client.get(url, {"q": "5500", "status": "all"}).content.decode()
    missed = client.get(url, {"q": "99887766", "status": "all"}).content.decode()

    assert PHONE in shown
    assert "طالبٌ للهاتف" in found
    assert "طالبٌ للهاتف" not in missed


@pytest.mark.django_db
def test_the_parent_links_screen_shows_and_searches_the_phone(client_as, principal_user, pupil):
    client = client_as(principal_user)
    url = reverse("manage_parent_links")

    shown = client.get(url, {"status": "all"}).content.decode()
    found = client.get(url, {"search": "5500", "status": "all"}).content.decode()

    assert PHONE in shown
    assert PHONE in found


# ── الحارس النصّيّ ───────────────────────────────────────────────────────────

_SKIP = ("migrations", "tests", ".claude", "scripts", "node_modules", "staticfiles", ".venv")
#: استعلامٌ على العمود الصريح — لا يعمل بعد تفريغه.
_ORM_PLAIN_PHONE = re.compile(
    r"\b(?:parent|user|student|guardian)__phone\b|\bphone__(?:i?contains|i?exact|istartswith|startswith|in)\b"
)
#: قراءةُ الصريح في قالبٍ من كائن مستخدمٍ لا من قاموسٍ جهّزه العرض.
_TEMPLATE_PLAIN_PHONE = re.compile(r"\b(?:parent|student|sender|user|request\.user)\.phone\b")


def _files(suffix):
    for path in ROOT.rglob(f"*{suffix}"):
        rel = path.relative_to(ROOT).parts
        if any(part in _SKIP for part in rel):
            continue
        yield path


def test_no_query_targets_the_plaintext_phone_column():
    offenders = [
        f"{p.relative_to(ROOT)}:{i}"
        for p in _files(".py")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _ORM_PLAIN_PHONE.search(line) and "management/commands" not in p.as_posix()
    ]
    assert not offenders, (
        "استعلامٌ على `phone` الصريح لا يعمل بعد المرحلة 2 — استعمل `core.phone_search.phone_holder_ids`: "
        + ", ".join(offenders)
    )


def test_no_template_reads_the_plaintext_phone_of_a_user():
    offenders = [
        f"{p.relative_to(ROOT)}:{i}"
        for p in _files(".html")
        for i, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1)
        if _TEMPLATE_PLAIN_PHONE.search(line)
    ]
    assert not offenders, "اقرأ `x.get_phone_decrypted` لا `x.phone`: " + ", ".join(offenders)
