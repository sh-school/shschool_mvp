"""[PDPPL] سجلُّ التدقيق الدائم لا يحمل جوّالاً ولا بريداً كاملَين (قرارُ المالك 2026-10-05).

`AuditLog` لا يُعدَّل ولا يُحذف (مشغّلُ القاعدة)، فأيُّ قيمةٍ تُكتب فيه تبقى بعد المحو وبعد تفريغ عمود الهاتف الصريح. والمساءلةُ
تكفيها «من غيّر ماذا ومتى» وذيلُ القيمة (م.10 وم.13؛ سابقةُ `core/signals.py` [PII-02]).
"""

import pytest

from core.models import AuditLog
from core.privacy import mask_email, mask_phone
from staff_affairs.profile_services import _lines, save_person
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db

OLD_PHONE, NEW_PHONE = "55001234", "66009876"
OLD_EMAIL, NEW_EMAIL = "ahmad@school.edu.qa", "new.name@school.edu.qa"


def _profile_entry(staff):
    return next(
        e
        for e in AuditLog.objects.filter(action="update", object_id=str(staff.id))
        if "الجوال" in (e.changes or {}) or "البريد الإلكتروني" in (e.changes or {})
    )


@pytest.fixture
def changed(principal_user):
    staff = UserFactory(phone=OLD_PHONE, email=OLD_EMAIL, full_name="موظّفٌ للتدقيق")
    save_person(user=staff, data={"phone": NEW_PHONE, "email": NEW_EMAIL}, by=principal_user)
    return staff


def test_the_real_values_are_saved_on_the_user(changed):
    changed.refresh_from_db()
    assert changed.get_phone_decrypted() == NEW_PHONE
    assert changed.email == NEW_EMAIL


def test_no_full_phone_or_email_reaches_the_permanent_audit_log(changed):
    blob = str(_profile_entry(changed).changes)
    for secret in (OLD_PHONE, NEW_PHONE, OLD_EMAIL, NEW_EMAIL, "new.name", "ahmad"):
        assert secret not in blob, secret


def test_the_log_still_says_what_changed_and_the_tail(changed):
    changes = _profile_entry(changed).changes
    assert changes["الجوال"] == {"من": mask_phone(OLD_PHONE), "إلى": mask_phone(NEW_PHONE)}
    assert changes["الجوال"]["إلى"].endswith("9876")
    assert changes["البريد الإلكتروني"]["إلى"] == "n***@school.edu.qa"


def test_the_history_screen_reads_the_masked_lines(changed):
    lines = _lines(_profile_entry(changed).changes)
    assert any(line.startswith("الجوال:") and "9876" in line for line in lines)
    assert not any(NEW_PHONE in line for line in lines)


def test_other_fields_keep_their_real_values_in_the_log(principal_user):
    staff = UserFactory(employee_number="E-100", full_name="موظّفٌ آخر")
    save_person(user=staff, data={"employee_number": "E-200"}, by=principal_user)
    entry = next(
        e
        for e in AuditLog.objects.filter(action="update", object_id=str(staff.id))
        if "الرقم الوظيفي" in (e.changes or {})
    )
    assert entry.changes["الرقم الوظيفي"] == {"من": "E-100", "إلى": "E-200"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [("55001234", "****1234"), ("1234", "****"), ("", ""), (None, "")],
)
def test_mask_phone(value, expected):
    assert mask_phone(value) == expected


@pytest.mark.parametrize(
    ("value", "expected"),
    [("ahmad@school.edu.qa", "a***@school.edu.qa"), ("nodomain", "********"), ("", ""), (None, "")],
)
def test_mask_email(value, expected):
    assert mask_email(value) == expected
