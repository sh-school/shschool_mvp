"""[STAFF] إكمالُ الفارغ من كشف الكادر عند القائمين — ولا كتابةَ فوق ممتلئ.

كان `import_staff_register` يُدخل الجديدَ ويترك القائمَ كما هو: معلّمٌ في
القاعدة بلا رقمٍ وظيفيٍّ يبقى بلا رقمٍ ولو كان في الكشف. فصار `--complete-existing`
يملأ الفارغَ وحدَه، و`--rows-b64` يحمل الكشفَ إلى قاعدةٍ لا يصلها الملفّ.
"""

from io import StringIO

import pytest
from django.core.management import call_command

from core.management.commands.import_staff_register import _pack
from core.models import CustomUser, Membership
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


def _teacher(school, national_id, **fields):
    role = RoleFactory(school=school, name="teacher")
    user = UserFactory(national_id=national_id, full_name="معلّمٌ قائم", **fields)
    membership = MembershipFactory(user=user, school=school, role=role)
    return user, membership


def _run(rows, *flags):
    out = StringIO()
    call_command(
        "import_staff_register",
        "--rows-b64",
        _pack(rows),
        "--include-teaching",
        "--complete-existing",
        "--no-create",
        *flags,
        stdout=out,
        stderr=StringIO(),
    )
    return out.getvalue()


def test_empty_fields_are_filled_from_the_register_and_phone_gets_its_derivatives(school):
    user, membership = _teacher(school, "29000000001", phone="", email="", employee_number="")
    membership.job_title = ""
    membership.save(update_fields=["job_title"])
    rows = [
        {
            "national_id": "29000000001",
            "name": "معلّمٌ قائم",
            "title": "معلم رياضيات",
            "employee_number": "70123",
            "email": "t@example.qa",
            "phone": "+97455000001",
        }
    ]

    report = _run(rows)
    assert "يُكمَل عند القائمين" in report and "تقريرٌ فقط" in report
    assert CustomUser.objects.get(pk=user.pk).employee_number == "", "العرضُ لا يكتب"

    _run(rows, "--apply")

    user.refresh_from_db()
    membership.refresh_from_db()
    assert user.employee_number == "70123"
    assert user.email == "t@example.qa"
    assert user.phone == "+97455000001"
    assert user.phone_hmac and user.phone_encrypted, "الجوّالُ يُحفظ مع بصمته وتشفيره لا عارياً"
    assert membership.job_title == "معلم رياضيات"
    assert membership.appointment_reference.startswith("كشف الكادر")


def test_filled_fields_are_never_overwritten(school):
    user, membership = _teacher(
        school, "29000000002", phone="+97455999999", email="mine@example.qa", employee_number="1"
    )
    membership.job_title = "منسق الرياضيات"
    membership.appointment_reference = "قرار 5"
    membership.save(update_fields=["job_title", "appointment_reference"])
    rows = [
        {
            "national_id": "29000000002",
            "name": "معلّمٌ قائم",
            "title": "معلم رياضيات",
            "employee_number": "70999",
            "email": "register@example.qa",
            "phone": "+97455000002",
        }
    ]

    report = _run(rows, "--apply")

    user.refresh_from_db()
    membership.refresh_from_db()
    assert (user.phone, user.email, user.employee_number) == (
        "+97455999999",
        "mine@example.qa",
        "1",
    )
    assert (membership.job_title, membership.appointment_reference) == ("منسق الرياضيات", "قرار 5")
    assert "0 حقلاً" in report or "لا شيء" in report


def test_no_create_reports_newcomers_without_creating_them(school):
    RoleFactory(school=school, name="teacher")
    rows = [
        {
            "national_id": "29000000003",
            "name": "قادمٌ جديد",
            "title": "معلم علوم",
            "employee_number": "70003",
            "email": "",
            "phone": "+97455000003",
        }
    ]

    report = _run(rows, "--apply")

    assert "لن يُنشأ (--no-create)" in report
    assert not CustomUser.objects.filter(national_id="29000000003").exists()
    assert not Membership.objects.filter(user__national_id="29000000003").exists()
