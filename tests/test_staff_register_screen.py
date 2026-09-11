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


def _order_of(body, *names):
    """مواضعُ أسماءٍ بعينها في القائمة — والمديرُ وغيرُه فيها ولا شأنَ لنا بهم."""
    listed = _names(body)
    return [listed.index(n) for n in names]


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


class TestArabicOrder:
    """القاعدةُ ترتّب بالنقطة البرمجيّة، والقارئُ يقرأ بالحرف."""

    def test_the_hamza_alif_sorts_with_the_bare_alif(self, client_as, school, principal):
        """«أكرم» كانت تسبق «ابراهيم» لأنّ همزةَ الألف نقطةٌ أصغرُ من الألف."""
        for name, national_id in (
            ("أكرم رابح", "29000000061"),
            ("ابراهيم محمد", "29000000062"),
            ("بشار محمود", "29000000063"),
        ):
            _staff(school, name, national_id)

        places = _order_of(_body(client_as, principal), "ابراهيم محمد", "أكرم رابح", "بشار محمود")

        assert places == sorted(places), "الألفُ قبل الباء، وهمزةُ الألف ألفٌ"

    def test_the_taa_marbuta_sorts_as_a_haa(self, client_as, school, principal):
        """التاءُ المربوطةُ هاءٌ عند القارئ، والهاءُ قبل الياء."""
        _staff(school, "حمزة سالم", "29000000064")
        _staff(school, "حمزي سالم", "29000000065")

        places = _order_of(_body(client_as, principal), "حمزة سالم", "حمزي سالم")

        assert places == sorted(places)


class TestBlanksLast:
    """الفراغُ ليس قيمةً صغرى — ومن نقر عموداً ليرى قيمَه لا يريد فراغَه."""

    def _one_filled_two_empty(self, school):
        _staff(school, "ألف", "29000000071", residence_area="الوكرة")
        _staff(school, "باء", "29000000072", residence_area="")
        _staff(school, "تاء", "29000000073", residence_area="")

    @pytest.mark.parametrize("direction", ("asc", "desc"))
    def test_the_empty_cell_falls_to_the_tail_in_both_directions(
        self, client_as, school, principal, direction
    ):
        self._one_filled_two_empty(school)

        places = _order_of(
            _body(client_as, principal, f"?sort=residence&dir={direction}"),
            "ألف",
            "باء",
            "تاء",
        )

        assert places[0] == 0, "المملوءةُ وحدَها في الصدارة صعوداً ونزولاً"
        assert min(places[1:]) > places[0], "والفارغتان بعدها في الاتّجاهين"

    def test_a_missing_employee_number_is_not_a_row_of_zeros(self, client_as, school, principal):
        """يُحشى الرقمُ بأصفارٍ ليُفرَز عدداً — فالفارغُ كان يصير أصغرَ الأعداد."""
        numbered = _staff(school, "له رقم", "29000000074")
        numbered.employee_number = "9907"
        numbered.save(update_fields=["employee_number"])
        _staff(school, "بلا رقم", "29000000075")

        assert _names(_body(client_as, principal, "?sort=employee&dir=asc"))[0] == "له رقم"


class TestTheHeaderSortsByWhatItShows:
    def test_the_job_title_column_sorts_by_the_job_title(self, client_as, school, principal):
        """كان يُفرَز بـ`role.name` الإنجليزيّ — ترويسةٌ تَعرض شيئاً وترتّب بغيره."""
        _staff(school, "الأوّل", "29000000081", job_title="امين مخزن")
        _staff(school, "الثاني", "29000000082", job_title="اخصائي نفسي")

        names = _names(_body(client_as, principal, "?sort=title&dir=asc"))

        assert names.index("الثاني") < names.index("الأوّل"), "«اخصائي» قبل «امين»"

    def test_a_person_without_a_title_falls_back_to_the_arabic_role_label(
        self, client_as, school, principal
    ):
        """لا عمودَ لدور المنصّة، لكنّه يبقى ارتدادَ المسمّى لمن لا مسمّى له —
        بعنوانه العربيّ المعروض لا بمفتاحه الإنجليزيّ المخزَّن. والمفتاحُ
        «nurse» يسبق «teacher» بالإنجليزيّة، و«معلم» يسبق «ممرض» بالعربيّة."""
        _staff(school, "واحد", "29000000083", role_name="teacher")
        _staff(school, "اثنان", "29000000084", role_name="nurse")

        body = _body(client_as, principal, "?sort=title&dir=asc")

        assert "ممرض" in body, "عنوانُ الدور بالعربيّة يملأ خانةَ المسمّى"
        names = _names(body)
        assert names.index("واحد") < names.index("اثنان"), "«معلم» قبل «ممرض»"


class TestThePartialReplacesItself:
    """نقرةُ الفرز تُبدّل الجدولَ وحدَه — وما تُبدّله يجب أن يبقى موجوداً."""

    def test_the_swap_target_survives_a_sort_click(self, client_as, school, principal):
        """`hx-swap="outerHTML"` يمحو العنصرَ الذي يستبدله. فلمّا كان المعرّفُ
        في الصفحة الأمّ وحدَها محته أوّلُ نقرةِ فرز، فلم تجد النقرةُ الثانيةُ
        هدفاً — وتوقّف الفرزُ كلُّه على كلّ الأعمدة بعد نقرةٍ واحدة.

        فالجزئيّةُ تحمل غلافَها بمعرّفه: تستبدل نفسَها بنفسها، ويبقى الهدف.
        """
        _staff(school, "المعلّم", "29000000090")
        url = reverse("staff_affairs:staff_list") + "?sort=employee&dir=desc"

        partial = client_as(principal).get(url, HTTP_HX_REQUEST="true").content.decode()

        assert partial.count('id="staff-table-container"') == 1, "غلافٌ واحدٌ — لا صفرَ ولا اثنان"


class TestSearchReachesEveryColumn:
    """من يرى قيمةً في عمودٍ يتوقّع أن يجدها بكتابتها — وإلّا فالعمودُ زينة."""

    @pytest.fixture
    def one(self, school):
        user = _staff(
            school,
            "أحمد المبحوث",
            "29000000101",
            email="target@education.qa",
            phone="55500999",
            nationality="سوداني",
            residence_area="معيذر",
            job_title="منسق كيمياء",
        )
        user.employee_number = "778811"
        user.professional_license_number = "LIC-777"
        user.save(update_fields=["employee_number", "professional_license_number"])
        _staff(school, "سواه", "29000000102")
        return user

    @pytest.mark.parametrize(
        "term",
        [
            "المبحوث",
            "778811",
            "29000000101",
            "منسق كيمياء",
            "55500999",
            "target@education.qa",
            "معيذر",
            "سوداني",
            "LIC-777",
        ],
    )
    def test_every_shown_value_finds_its_owner(self, client_as, school, principal, one, term):
        assert _names(_body(client_as, principal, f"?q={term}")) == ["أحمد المبحوث"]

    def test_the_hamza_is_not_a_wall_between_the_reader_and_the_name(
        self, client_as, school, principal, one
    ):
        """أكثرُ ما يُكتب في صندوق بحثٍ عربيّ ألفٌ مجرّدة — والمخزَّنُ بالهمزة."""
        assert _names(_body(client_as, principal, "?q=احمد")) == ["أحمد المبحوث"]
