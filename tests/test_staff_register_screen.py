"""سجلُّ المنتسبين — كلُّ ما تحمله المنصّةُ عن الموظّف، وفرزٌ من الخادم."""

import re

import pytest
from django.urls import reverse

from core.models import Membership
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

#: كلُّ عمودٍ وعدَ به السجلّ — وغيابُ واحدٍ يُسقط الاختبار.
COLUMNS = (
    "الاسم",
    "الرقم الوظيفي",
    "الرقم الشخصي",
    "المسمّى الوظيفي",
    "دور المنصّة",
    "القسم",
    "الجوال",
    "البريد",
    "السكن",
    "الجنسية",
    "الرخصة المهنية",
    "الالتحاق",
    "الدخول",
)


@pytest.fixture
def school(db):
    from core.models import School

    return School.objects.create(name="مدرسة السجلّ", code="SHH-REG")


@pytest.fixture
def principal(db, school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="المدير", national_id="29000000001")
    MembershipFactory(user=user, school=school, role=role)
    return user


def _staff(school, name, national_id, **fields):
    role_name = fields.pop("role_name", "teacher")
    job_title = fields.pop("job_title", "")
    user = UserFactory(full_name=name, national_id=national_id, **fields)
    MembershipFactory(
        user=user,
        school=school,
        role=RoleFactory(school=school, name=role_name),
        job_title=job_title,
    )
    return user


def _body(client_as, principal, query=""):
    url = reverse("staff_affairs:staff_list") + query
    return client_as(principal).get(url).content.decode()


def _names(body):
    return re.findall(r'class="staff-name"[^>]*>\s*([^<]+?)\s*</a>', body)


class TestColumns:
    @pytest.mark.parametrize("column", COLUMNS)
    def test_every_promised_column_is_there(self, client_as, school, principal, column):
        _staff(school, "المعلّم", "29000000010")
        assert column in _body(client_as, principal)

    def test_the_row_carries_what_the_platform_knows(self, client_as, school, principal):
        user = _staff(
            school,
            "كاملُ البيانات",
            "29000000011",
            email="k@education.qa",
            phone="55500011",
            nationality="قطري",
            residence_area="الريان",
            job_title="معلم رياضيات",
        )
        user.employee_number = "123456"
        user.professional_license_number = "LIC-9"
        user.save(update_fields=["employee_number", "professional_license_number"])

        body = _body(client_as, principal)

        for value in ("123456", "29000000011", "معلم رياضيات", "k@education.qa", "الريان", "قطري"):
            assert value in body, value

    def test_the_departure_column_shows_only_for_those_who_left(self, client_as, school, principal):
        """عمودٌ فارغٌ على رأس العمل حشوٌ — ويُعرض حين يعني شيئاً."""
        import datetime

        gone = _staff(school, "المغادر", "29000000012")
        m = Membership.objects.get(user=gone, school=school)
        m.is_active = False
        m.left_at = datetime.date(2026, 8, 31)
        m.save(update_fields=["is_active", "left_at"])

        assert "المغادرة" not in _body(client_as, principal)

        body = _body(client_as, principal, "?status=left")
        assert "المغادرة" in body
        assert "31/08/2026" in body


class TestSignIn:
    def test_an_account_without_a_password_is_marked(self, client_as, school, principal):
        """الحسابُ الجديدُ يُنشأ بلا كلمةٍ صالحة — ومن يُصدر كلماتِ المرور يحتاج أن يراه."""
        user = _staff(school, "بلا كلمة", "29000000020")
        user.set_unusable_password()
        user.save(update_fields=["password"])

        assert "بلا كلمة مرور" in _body(client_as, principal)

    def test_a_usable_account_is_marked_as_signing_in(self, client_as, school, principal):
        _staff(school, "له كلمة", "29000000021")
        assert "يدخل" in _body(client_as, principal)


class TestSorting:
    def _three(self, school):
        for name, national_id, employee in (
            ("جيم", "29000000031", "9907"),
            ("ألف", "29000000032", "85308"),
            ("باء", "29000000033", "120176"),
        ):
            user = _staff(school, name, national_id)
            user.employee_number = employee
            user.save(update_fields=["employee_number"])

    def test_the_default_order_is_by_name(self, client_as, school, principal):
        self._three(school)
        assert _names(_body(client_as, principal))[:1] == ["ألف"]

    def test_the_employee_number_sorts_as_a_number_not_as_text(self, client_as, school, principal):
        """أطوالُه مختلفة، وفرزُ النصّ يضع «9907» قبل «85308»."""
        self._three(school)

        body = _body(client_as, principal, "?sort=employee&dir=desc")

        assert _names(body)[0] == "باء", "الأكبرُ عدداً أوّلاً — 120176"

    def test_an_undeclared_key_is_ignored(self, client_as, school, principal):
        """`?sort=` نصٌّ من المستخدم — لا يبلغ `order_by` إلّا عبر القائمة المصرَّحة."""
        self._three(school)

        body = _body(client_as, principal, "?sort=password&dir=desc")

        assert _names(body)[:1] == ["ألف"], "يعود إلى ترتيب الشاشة الأصليّ"

    def test_sorting_covers_the_whole_register_not_the_visible_page(
        self, client_as, school, principal
    ):
        """الترتيبُ يقع على الاستعلام قبل التقسيم — وإلّا كذب على قارئه."""
        self._three(school)
        body = _body(client_as, principal, "?sort=employee&dir=asc")
        assert 'aria-sort="ascending"' in body


class TestSearch:
    def test_the_employee_number_is_searchable(self, client_as, school, principal):
        """صار معرّفَ الدخول — فمن يبحث به يجب أن يجد صاحبَه."""
        user = _staff(school, "المطلوب", "29000000040")
        user.employee_number = "778899"
        user.save(update_fields=["employee_number"])
        _staff(school, "غيرُه", "29000000041")

        assert _names(_body(client_as, principal, "?q=778899")) == ["المطلوب"]


class TestOnePersonOneRow:
    def test_two_memberships_are_one_row(self, client_as, school, principal):
        user = _staff(school, "معلّمٌ ومنسّق", "29000000050")
        MembershipFactory(
            user=user, school=school, role=RoleFactory(school=school, name="coordinator")
        )

        assert Membership.objects.filter(user=user, school=school).count() == 2
        assert _names(_body(client_as, principal)).count("معلّمٌ ومنسّق") == 1
