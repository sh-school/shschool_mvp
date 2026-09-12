"""شاشةُ ربط أولياء الأمور — عددٌ يُعمَل به، وبابٌ واحدٌ للإضافة.

كان في الشاشة عدّادٌ يقول «742 طالباً مرتبطاً» لمدرسةٍ سجلُّ قيدها 735: مئةٌ
وسبعةٌ منهم غادروا وبقيت ارتباطاتُهم. والرقمُ الذي يُفتح السجلُّ لأجله — **من
بقي بلا وليِّ أمر** — لم يكن معروضاً أصلاً.

وكان للإضافة بابان: استمارةٌ في هذه الصفحة تربط وليّاً قائماً، وشاشةٌ في
القائمة تُنشئ وتربط. فصارا باباً واحداً حيث يُرى العمل.
"""

import re
from urllib.parse import quote

import pytest
from django.urls import NoReverseMatch, reverse

from core.models.academic import ParentStudentLink
from core.models.user import CustomUser
from core.querysets import year_or_current
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def year(school):
    return year_or_current(school)


@pytest.fixture
def admin(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="المدير", national_id="29000000001")
    MembershipFactory(user=user, school=school, role=role)
    return user


def _class(school, year, grade="G7", section="1"):
    from core.models.academic import ClassGroup

    found = ClassGroup.objects.filter(
        school=school, grade=grade, section=section, academic_year=year
    ).first()
    return found or ClassGroupFactory(
        school=school, grade=grade, section=section, academic_year=year
    )


def _student(school, name, national_id, year=None, grade="G7", section="1"):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    if year:
        StudentEnrollmentFactory(student=user, class_group=_class(school, year, grade, section))
    return user


def _parent(school, name, national_id, phone=""):
    user = UserFactory(full_name=name, national_id=national_id, phone=phone)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="parent"))
    return user


def _link(school, parent, student, relationship="father"):
    return ParentStudentLink.objects.create(
        school=school, parent=parent, student=student, relationship=relationship
    )


def _body(client_as, admin, query=""):
    return client_as(admin).get(reverse("manage_parent_links") + query).content.decode()


def _students_in(body):
    """أسماءُ الطلاب في الصفوف وحدَها — لا في قوائم الاستمارة فوقها."""
    return re.findall(r'<td data-label="الطالب">.*?>\s*([^<>]+?)\s*</a>', body, re.S)


class TestTheCountIsTheWorkLeft:
    def test_a_link_whose_student_left_is_not_counted_by_default(
        self, client_as, school, admin, year
    ):
        here = _student(school, "الباقي", "31400000001", year=year)
        gone = _student(school, "المغادر", "31400000002")
        _link(school, _parent(school, "أبو الباقي", "28400000001"), here)
        _link(school, _parent(school, "أبو المغادر", "28400000002"), gone)

        assert _students_in(_body(client_as, admin)) == ["الباقي"], (
            "من أُغلق قيدُه ارتباطُه أثرٌ لا عمل"
        )

    def test_the_departed_are_reachable_by_an_explicit_filter(self, client_as, school, admin, year):
        here = _student(school, "الباقي", "31400000003", year=year)
        gone = _student(school, "المغادر", "31400000004")
        _link(school, _parent(school, "أبو الباقي", "28400000003"), here)
        _link(school, _parent(school, "أبو المغادر", "28400000004"), gone)

        assert _students_in(_body(client_as, admin, "?status=left")) == ["المغادر"]

    def test_the_screen_says_how_many_are_still_without_a_guardian(
        self, client_as, school, admin, year
    ):
        """هذا هو الرقمُ الذي يُفتح السجلُّ لأجله."""
        linked = _student(school, "له وليّ", "31400000005", year=year)
        _student(school, "بلا وليّ", "31400000006", year=year)
        _student(school, "بلا وليٍّ أيضاً", "31400000007", year=year)
        _link(school, _parent(school, "الوليّ", "28400000005"), linked)

        body = _body(client_as, admin)

        assert "بلا وليِّ أمرٍ مرتبط" in body
        assert re.search(r'kpi-mini-value">\s*2\s*<', body), "اثنان بلا وليّ من ثلاثة"

    def test_the_linked_count_is_read_against_the_register_not_alone(
        self, client_as, school, admin, year
    ):
        """«600» وحدَه لا يقول شيئاً — «600 من 735» يقول."""
        linked = _student(school, "له وليّ", "31400000008", year=year)
        _student(school, "بلا وليّ", "31400000009", year=year)
        _link(school, _parent(school, "الوليّ", "28400000006"), linked)

        assert "من 2" in _body(client_as, admin)


class TestTheColumnsAreTheOnesUsed:
    def test_the_class_is_written_as_the_ministry_writes_it(self, client_as, school, admin, year):
        student = _student(school, "الطالب", "31400000010", year=year, grade="G9", section="2")
        _link(school, _parent(school, "الوليّ", "28400000010"), student)

        assert "09/2" in _body(client_as, admin)

    def test_the_guardian_phone_is_a_click_to_call(self, client_as, school, admin, year):
        student = _student(school, "الطالب", "31400000011", year=year)
        _link(school, _parent(school, "الوليّ", "28400000011", phone="55500099"), student)

        assert 'href="tel:55500099"' in _body(client_as, admin)

    def test_the_relationship_is_shown_in_arabic(self, client_as, school, admin, year):
        student = _student(school, "الطالب", "31400000012", year=year)
        _link(school, _parent(school, "الوليّة", "28400000012"), student, relationship="mother")

        body = _body(client_as, admin)

        assert "الأم" in body
        assert ">mother<" not in body

    def test_no_national_id_is_bared(self, client_as, school, admin, year):
        student = _student(school, "الطالب", "31473600538", year=year)
        _link(school, _parent(school, "الوليّ", "28576002649"), student)

        body = _body(client_as, admin)

        assert "*******0538" in body
        assert "31473600538" not in body
        assert "28576002649" not in body

    def test_each_cell_holds_one_value(self, client_as, school, admin, year):
        """كان هذا الجدولُ وحدَه في المنصّة يحشر الاسمَ والرقمَ في خليّةٍ
        واحدة، والرقمُ بـ`dir="ltr"` يرتدّ إلى الحافة المقابلة فيُرى السطرُ
        مفكوكاً. وأخواتُه — سجلُّ الطلاب وسجلُّ الكادر — قيمةٌ لكلّ خليّة."""
        student = _student(school, "الطالب", "31400000013", year=year)
        _link(school, _parent(school, "الوليّ", "28400000013", phone="55500088"), student)

        rows = re.findall(r"<tbody>(.*?)</tbody>", _body(client_as, admin), re.S)

        assert rows, "لا صفوف"
        assert 'dir="ltr"' not in rows[0], "رقمٌ منفلتُ الاتّجاه داخل خليّةِ اسم"

    def test_the_student_name_opens_the_file(self, client_as, school, admin, year):
        """كما في سجلّ الطلاب — الاسمُ بابُ ملفّه."""
        student = _student(school, "الطالب", "31400000014", year=year)
        _link(school, _parent(school, "الوليّ", "28400000014"), student)

        assert f"/student-affairs/profile/{student.id}/" in _body(client_as, admin)


class TestTheSearchReadsEveryColumn:
    @pytest.mark.parametrize(
        ("query", "found"),
        [
            ("الطالب المطلوب", True),
            ("مميَّز", True),
            ("55500077", True),
            ("G8", True),
            ("البتّة", False),
        ],
    )
    def test_the_search_covers_the_columns_it_shows(
        self, client_as, school, admin, year, query, found
    ):
        student = _student(school, "الطالب المطلوب", "31400000020", year=year, grade="G8")
        _link(school, _parent(school, "وليٌّ مميَّز", "28400000020", phone="55500077"), student)

        shown = _students_in(_body(client_as, admin, f"?q={quote(query)}"))

        assert (shown == ["الطالب المطلوب"]) is found


class TestThePagesKeepTheirFilters:
    def test_a_page_link_carries_the_current_filter(self, client_as, school, admin, year):
        """كان الانتقالُ إلى الصفحة الثانية يفتحها على المدرسة كلِّها."""
        for index in range(30):
            student = _student(school, f"طالب {index:02}", f"3140003{index:04}", year=year)
            _link(school, _parent(school, f"وليّ {index:02}", f"2840003{index:04}"), student)

        body = _body(client_as, admin, "?q=" + quote("طالب"))

        assert "q=%D8%B7%D8%A7%D9%84%D8%A8" in body, "رابطُ الصفحة يحمل البحث"


class TestOneDoorAdds:
    """بابان لفعلٍ واحدٍ يُربكان: أحدُهما يربط قائماً والآخرُ يُنشئ ويربط."""

    def test_the_separate_screen_is_gone(self):
        with pytest.raises(NoReverseMatch):
            reverse("student_affairs:parent_add")

    def test_the_menu_no_longer_offers_a_second_door(self, client_as, school, admin, year):
        body = _body(client_as, admin)

        assert "إضافة ولي امر" not in body
        assert "ربط أولياء الأمور بالطلاب" in body

    def test_an_existing_guardian_is_linked_by_id(self, client_as, school, admin, year):
        student = _student(school, "الطالب", "31400000030", year=year)
        parent = _parent(school, "الوليّ", "28400000030")

        client_as(admin).post(
            reverse("add_parent_link"),
            {"parent_id": str(parent.id), "student_id": str(student.id), "relationship": "father"},
        )

        assert ParentStudentLink.objects.filter(parent=parent, student=student).exists()

    def test_a_new_guardian_is_created_and_linked_in_one_go(self, client_as, school, admin, year):
        student = _student(school, "الطالب", "31400000031", year=year)

        client_as(admin).post(
            reverse("add_parent_link"),
            {
                "parent_national_id": "28400000031",
                "parent_full_name": "وليٌّ جديدٌ للطالب",
                "parent_phone": "55500055",
                "student_id": str(student.id),
                "relationship": "father",
            },
        )

        parent = CustomUser.objects.get(national_id="28400000031")
        assert parent.full_name == "وليٌّ جديدٌ للطالب"
        assert ParentStudentLink.objects.filter(parent=parent, student=student).exists()

    def test_the_new_account_has_no_usable_password(self, client_as, school, admin, year):
        """كانت كلمتُه رقمَه الشخصيَّ — وهو رقمٌ في كشوف الوزارة وفي يد المدرسة،
        فمن يعرفه يدخل بحسابه قبل أن يدخل هو. وإلزامُه بالتغيير بعد الدخول لا
        يمنع غيرَه من السبق إليه."""
        student = _student(school, "الطالب", "31400000032", year=year)

        client_as(admin).post(
            reverse("add_parent_link"),
            {
                "parent_national_id": "28400000032",
                "parent_full_name": "وليٌّ بلا كلمة",
                "student_id": str(student.id),
                "relationship": "father",
            },
        )

        parent = CustomUser.objects.get(national_id="28400000032")
        assert not parent.has_usable_password()
        assert not parent.check_password("28400000032"), "الرقمُ الشخصيُّ ليس مفتاحاً"

    def test_the_new_guardian_gets_a_parent_membership(self, client_as, school, admin, year):
        student = _student(school, "الطالب", "31400000033", year=year)

        client_as(admin).post(
            reverse("add_parent_link"),
            {
                "parent_national_id": "28400000033",
                "parent_full_name": "وليٌّ له دور",
                "student_id": str(student.id),
                "relationship": "father",
            },
        )

        parent = CustomUser.objects.get(national_id="28400000033")
        assert parent.memberships.filter(
            school=school, role__name="parent", is_active=True
        ).exists()

    def test_a_known_person_is_reused_not_duplicated(self, client_as, school, admin, year):
        """من كان في النظام موظّفاً أو وليّاً لابنٍ آخر لا يُنشأ له حسابٌ ثانٍ."""
        student = _student(school, "الطالب", "31400000034", year=year)
        known = UserFactory(full_name="معروفٌ سلفاً", national_id="28400000034")

        client_as(admin).post(
            reverse("add_parent_link"),
            {
                "parent_national_id": "28400000034",
                "parent_full_name": "اسمٌ مكتوبٌ خطأً",
                "student_id": str(student.id),
                "relationship": "father",
            },
        )

        assert CustomUser.objects.filter(national_id="28400000034").count() == 1
        known.refresh_from_db()
        assert known.full_name == "معروفٌ سلفاً", "المخزَّنُ لا يُكتب عليه من استمارةٍ عابرة"
        assert ParentStudentLink.objects.filter(parent=known, student=student).exists()

    @pytest.mark.parametrize(
        ("national_id", "full_name"),
        [
            ("", "اسمٌ بلا رقم"),
            ("28400000035", ""),
            ("28abc", "رقمٌ ليس أرقاماً"),
            ("284", "رقمٌ قصيرٌ جدّاً"),
            ("28400000036", "قصر"),
        ],
    )
    def test_a_malformed_identity_creates_nothing(
        self, client_as, school, admin, year, national_id, full_name
    ):
        student = _student(school, "الطالب", "31400000035", year=year)
        before = CustomUser.objects.count()

        client_as(admin).post(
            reverse("add_parent_link"),
            {
                "parent_national_id": national_id,
                "parent_full_name": full_name,
                "student_id": str(student.id),
                "relationship": "father",
            },
        )

        assert CustomUser.objects.count() == before
        assert not ParentStudentLink.objects.filter(student=student).exists()

    def test_the_form_offers_both_modes(self, client_as, school, admin, year):
        body = _body(client_as, admin)

        assert 'id="parent-mode-existing"' in body
        assert 'id="parent-mode-new"' in body
        assert 'name="parent_national_id"' in body
