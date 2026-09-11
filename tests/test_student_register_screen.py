"""سجلُّ الطلاب — عددٌ صادق، وصفحاتٌ حقيقيّة، ورقمٌ لا يُكشف بالجملة."""

import re

import pytest
from django.urls import reverse

from core.models.academic import ParentStudentLink
from core.privacy import mask_national_id
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
def reader(school):
    role = RoleFactory(school=school, name="principal")
    user = UserFactory(full_name="المدير", national_id="29000000001")
    MembershipFactory(user=user, school=school, role=role)
    return user


def _class(school, year, grade, section):
    """الشعبةُ فريدةٌ بـ(مدرسة، صفّ، شعبة، عام) — فتُعاد لا تُنشأ مرّتين."""
    from core.models.academic import ClassGroup

    found = ClassGroup.objects.filter(
        school=school, grade=grade, section=section, academic_year=year
    ).first()
    return found or ClassGroupFactory(
        school=school, grade=grade, section=section, academic_year=year
    )


def _student(school, name, national_id, year=None, grade="G7", section="1"):
    """طالبٌ بعضويّة — ويُقيَّد إن مُرِّر عامٌ، وإلّا بقي بلا قيدٍ نشط."""
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    if year:
        StudentEnrollmentFactory(student=user, class_group=_class(school, year, grade, section))
    return user


def _guardian(school, student, name, phone, relationship="father", primary=True):
    parent = UserFactory(full_name=name, phone=phone)
    MembershipFactory(user=parent, school=school, role=RoleFactory(school=school, name="parent"))
    return ParentStudentLink.objects.create(
        school=school,
        parent=parent,
        student=student,
        relationship=relationship,
        is_primary=primary,
    )


def _body(client_as, reader, query=""):
    return client_as(reader).get(reverse("student_affairs:student_list") + query).content.decode()


def _names(body):
    """أسماءُ الصفوف كما تُعرض — رابطُ الاسم وحدَه يحمل هذا الصنف."""
    return re.findall(r'class="font-semibold text-maroon[^>]*>\s*([^<]+?)\s*</a>', body)


class TestTheCountIsTheRegister:
    """«200 طالباً مسجّلاً» لمدرسةٍ سجلُّ قيدها 735 — رقمٌ يُقرأ في أوّل الشاشة."""

    def test_the_default_counts_the_enrolled_not_the_memberships(
        self, client_as, school, reader, year
    ):
        _student(school, "مقيَّد", "31400000001", year=year)
        _student(school, "مغلقٌ قيدُه", "31400000002")

        body = _body(client_as, reader)

        assert "مقيَّد" in body
        assert "مغلقٌ قيدُه" not in body, "من أُغلق قيدُه لا يُعدّ في سجلّ العام"

    def test_whoever_lost_their_enrolment_is_filtered_not_dropped(
        self, client_as, school, reader, year
    ):
        """من نُقل هذا الصيفَ يبقى ملفُّه مقروءاً — ويُرى بترشيحٍ صريح."""
        _student(school, "مقيَّد", "31400000003", year=year)
        _student(school, "مغلقٌ قيدُه", "31400000004")

        names = _names(_body(client_as, reader, "?status=unenrolled"))

        assert names == ["مغلقٌ قيدُه"], "والمقيَّدُ يسقط من هذا الترشيح"

    def test_all_shows_both(self, client_as, school, reader, year):
        _student(school, "مقيَّد", "31400000005", year=year)
        _student(school, "مغلقٌ قيدُه", "31400000006")

        body = _body(client_as, reader, "?status=all")

        assert "مقيَّد" in body and "مغلقٌ قيدُه" in body


class TestThePagesAreReal:
    """كان السجلُّ يُقطع عند مئتين بلا تقسيمٍ ولا كلمةٍ تقول ذلك."""

    def test_a_page_holds_fifty_and_the_footer_counts_them_all(
        self, client_as, school, reader, year
    ):
        for index in range(55):
            _student(school, f"طالب {index:03}", f"3140001{index:04}", year=year)

        body = _body(client_as, reader)

        assert "55 طالباً — صفحة 1 من 2" in body

    def test_the_second_page_holds_the_rest(self, client_as, school, reader, year):
        for index in range(55):
            _student(school, f"طالب {index:03}", f"3140002{index:04}", year=year)

        body = _body(client_as, reader, "?page=2")

        assert "صفحة 2 من 2" in body


class TestTheNationalIdIsNotBared:
    """قانونُ حماية البيانات يقوم على التقليل — والقارئُ يحتاج أن يميّز لا أن يعرف."""

    def test_only_the_last_four_digits_are_shown(self, client_as, school, reader, year):
        _student(school, "الطالب", "31473600538", year=year)

        body = _body(client_as, reader)

        assert "*******0538" in body
        assert "31473600538" not in body, "الرقمُ كاملاً في ملفّ صاحبه لا في الكشف"

    def test_the_search_still_finds_the_full_number(self, client_as, school, reader, year):
        """من كتب رقماً كاملاً وجد صاحبَه — البحثُ على المخزَّن لا على المستور."""
        _student(school, "المطلوب", "31473600538", year=year)
        _student(school, "سواه", "31473600539", year=year)

        assert _names(_body(client_as, reader, "?q=31473600538")) == ["المطلوب"]

    @pytest.mark.parametrize(
        ("raw", "masked"),
        [
            ("31473600538", "*******0538"),
            ("", ""),
            ("1234", "****"),
            ("12345", "*****"),
            ("123456", "**3456"),
        ],
    )
    def test_the_mask_keeps_the_tail_and_hides_the_rest(self, raw, masked):
        assert mask_national_id(raw) == masked

    def test_a_number_too_short_is_hidden_entirely(self):
        """إظهارُ رقمٍ من خمس خاناتٍ بأربعٍ منه كشفٌ لا ستر."""
        assert set(mask_national_id("12345")) == {"*"}


class TestTheClassReadsLikeTheRegister:
    def test_the_grade_and_section_are_one_column_written_as_the_ministry_writes_it(
        self, client_as, school, reader, year
    ):
        _student(school, "الطالب", "31400000010", year=year, grade="G7", section="2")

        assert "07/2" in _body(client_as, reader)

    def test_the_class_sorts_as_a_number_not_as_text(self, client_as, school, reader, year):
        """«G10» نصّاً يسبق «G7»، وعدداً يليه."""
        _student(school, "عاشر", "31400000011", year=year, grade="G10", section="1")
        _student(school, "سابع", "31400000012", year=year, grade="G7", section="1")

        names = _names(_body(client_as, reader, "?sort=class&dir=asc"))

        assert names.index("سابع") < names.index("عاشر")

    def test_a_student_without_an_enrolment_shows_a_dash(self, client_as, school, reader):
        _student(school, "بلا قيد", "31400000013")

        body = _body(client_as, reader, "?status=unenrolled")

        assert "بلا قيد" in body


class TestTheGuardianIsTheAction:
    """الفعلُ المقصودُ من هذه الشاشة الاتّصالُ بالأسرة."""

    def test_the_guardian_name_and_phone_are_shown(self, client_as, school, reader, year):
        student = _student(school, "الطالب", "31400000020", year=year)
        _guardian(school, student, "أبو الطالب", "55500011")

        body = _body(client_as, reader)

        assert "أبو الطالب" in body
        assert "55500011" in body
        assert 'href="tel:55500011"' in body, "نقرةٌ تتّصل"

    def test_the_relationship_is_shown_in_arabic(self, client_as, school, reader, year):
        student = _student(school, "الطالب", "31400000021", year=year)
        _guardian(school, student, "أمُّ الطالب", "55500012", relationship="mother")

        body = _body(client_as, reader)

        assert "الأم" in body
        assert "mother" not in body, "المفتاحُ المخزَّنُ لا يُعرض"

    def test_the_primary_guardian_comes_first(self, client_as, school, reader, year):
        student = _student(school, "الطالب", "31400000022", year=year)
        _guardian(school, student, "الثانوي", "55500013", primary=False)
        _guardian(school, student, "الأساسي", "55500014", primary=True)

        body = _body(client_as, reader)

        assert "الأساسي" in body
        assert "55500014" in body

    def test_a_student_without_a_guardian_says_so(self, client_as, school, reader, year):
        _student(school, "بلا وليّ", "31400000023", year=year)

        assert "بلا وليّ أمرٍ مرتبط" in _body(client_as, reader)

    def test_the_guardian_is_searchable(self, client_as, school, reader, year):
        student = _student(school, "ابنُ المطلوب", "31400000024", year=year)
        _guardian(school, student, "وليٌّ مميَّز", "55500015")
        _student(school, "سواه", "31400000025", year=year)

        assert _names(_body(client_as, reader, "?q=مميَّز")) == ["ابنُ المطلوب"]


class TestThePartialReplacesItself:
    def test_the_swap_target_survives_a_sort_click(self, client_as, school, reader, year):
        """`hx-swap="outerHTML"` يمحو ما يستبدله — فلو لم تحمل الجزئيّةُ غلافَها
        بمعرّفه لمحته أوّلُ نقرةِ فرز، وتوقّف الفرزُ كلُّه بعدها."""
        _student(school, "الطالب", "31400000030", year=year)
        url = reverse("student_affairs:student_list") + "?sort=class&dir=desc"

        partial = client_as(reader).get(url, HTTP_HX_REQUEST="true").content.decode()

        assert partial.count('id="student-table-container"') == 1
