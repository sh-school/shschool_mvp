"""
tests/test_clinic_student_picker.py — مكوّنُ اختيار الطالب في العيادة (W-20261102-001)

ثلاثةُ مداخل (اسمٌ مطبَّع ببداية الكلمة، صفٌّ ثمّ شعبة، رقمُ الطالب)، وتمييزُ المتشابهين، والتأكيدُ
قبل فتح الزيارة، واستعلاماتٌ ثابتة، وصفحةُ النموذج الكامل بلا قائمةٍ منسدلةٍ بكلّ الطلبة.
"""

import datetime as dt

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from clinic.models import ClinicVisit, HealthRecord
from clinic.selectors import MAX_RESULTS, normalize_ar, search_students
from core.models import ClassGroup, Profile
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.pin_clock


def _client(user):
    c = Client()
    c.force_login(user)
    return c


@pytest.fixture
def student_role(school):
    return RoleFactory(school=school, name="student")


def _student(school, role, name, grade="G9", section="1", national_id=None, born=None):
    kwargs = {"national_id": national_id} if national_id else {}
    user = UserFactory(full_name=name, **kwargs)
    MembershipFactory(user=user, school=school, role=role)
    group = ClassGroup.objects.filter(school=school, grade=grade, section=section).first() or (
        ClassGroupFactory(school=school, grade=grade, section=section)
    )
    StudentEnrollmentFactory(student=user, class_group=group)
    if born:
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.date_of_birth = born
        profile.save()
    return user


def test_normalize_unifies_hamza_teh_marbuta_and_yeh():
    assert normalize_ar("أحمد إبراهيم آل ثاني") == normalize_ar("احمد ابراهيم ال ثاني")
    assert normalize_ar("فاطمة") == normalize_ar("فاطمه")
    assert normalize_ar("موسى") == normalize_ar("موسي")


@pytest.mark.django_db
def test_name_search_is_normalized_and_matches_word_starts(school, student_role):
    ahmad = _student(school, student_role, "أحمد خالد المري")
    _student(school, student_role, "سعيد بن أحمد")
    # بلا همزة، وبداية كلمةٍ من الوسط
    found = {c.id for c in search_students(school, "احمد")}
    assert str(ahmad.id) in found and len(found) == 2
    # الاحتواءُ في وسط الكلمة لا يطابق
    assert search_students(school, "حمد") == []
    # كلُّ كلمةٍ بدايةُ كلمة (ترتيبٌ حرّ)
    assert [c.full_name for c in search_students(school, "المري احمد")] == ["أحمد خالد المري"]


@pytest.mark.django_db
def test_id_search_returns_exactly_one_student(school, student_role):
    target = _student(school, student_role, "طالب أ", national_id="29000000011")
    _student(school, student_role, "طالب ب", national_id="29000000022")
    result = search_students(school, "29000000011")
    assert [c.id for c in result] == [str(target.id)]
    assert search_students(school, "29000000099") == []


@pytest.mark.django_db
def test_other_schools_students_never_appear(school, student_role):
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    other_role = RoleFactory(school=other, name="student")
    _student(other, other_role, "أحمد الغريب", national_id="29000000033")
    assert search_students(school, "احمد") == []
    assert search_students(school, "29000000033") == []


@pytest.mark.django_db
def test_class_then_section_lists_that_section_only(school, nurse_user, student_role):
    a = _student(school, student_role, "طالب شعبة أولى", grade="G9", section="1")
    _student(school, student_role, "طالب شعبة ثانية", grade="G9", section="2")
    resp = _client(nurse_user).get(reverse("clinic:quick_class"), {"cls": "G9|1", "mode": "quick"})
    body = resp.content.decode()
    assert resp.status_code == 200
    assert a.full_name in body and "طالب شعبة ثانية" not in body


@pytest.mark.django_db
def test_similar_names_show_section_and_birth_year_and_care_flag(school, nurse_user, student_role):
    first = _student(
        school, student_role, "محمد علي", grade="G9", section="1", born=dt.date(2012, 3, 1)
    )
    _student(school, student_role, "محمد علي", grade="G10", section="2", born=dt.date(2011, 5, 9))
    HealthRecord.objects.create(student=first, needs_care=True)
    body = _client(nurse_user).get(reverse("clinic:quick_search"), {"q": "محمد"}).content.decode()
    assert "9/1" in body and "10/2" in body
    assert "مواليد 2012" in body and "مواليد 2011" in body
    assert body.count("يحتاج مراعاةً") == 1
    # لا رقمَ وطنيّاً ولا تاريخَ ميلادٍ كاملاً في النتائج
    assert first.national_id not in body and "2012-03-01" not in body


@pytest.mark.django_db
def test_unique_names_hide_birth_year(school, nurse_user, student_role):
    _student(school, student_role, "يوسف فريد", born=dt.date(2012, 3, 1))
    body = _client(nurse_user).get(reverse("clinic:quick_search"), {"q": "يوسف"}).content.decode()
    assert "يوسف فريد" in body and "مواليد" not in body


@pytest.mark.django_db
def test_results_capped_at_twelve_with_two_queries(school, student_role):
    for i in range(MAX_RESULTS + 5):
        _student(school, student_role, f"عبدالله {i}", section=str(i % 3))
    with CaptureQueriesContext(connection) as ctx:
        result = search_students(school, "عبدالله")
    assert len(result) == MAX_RESULTS
    assert len(ctx) <= 2


@pytest.mark.django_db
def test_recent_visitors_fill_the_list_before_typing(school, nurse_user, student_role):
    from django.utils import timezone

    seen = _student(school, student_role, "زائر الأسبوع")
    old = _student(school, student_role, "زائر قديم")
    for s, days in ((seen, 3), (old, 9)):
        v = ClinicVisit.objects.create(school=school, student=s, nurse=nurse_user, reason="")
        ClinicVisit.objects.filter(pk=v.pk).update(
            visit_date=timezone.now() - dt.timedelta(days=days)
        )
    body = _client(nurse_user).get(reverse("clinic:quick_entry")).content.decode()
    assert "زائر الأسبوع" in body and "زائر قديم" not in body


@pytest.mark.django_db
def test_picking_confirms_without_opening_a_visit(school, nurse_user, student_role):
    s = _student(school, student_role, "طالب للتأكيد", born=dt.date(2012, 1, 1))
    client = _client(nurse_user)
    resp = client.get(reverse("clinic:quick_pick"), {"student_id": str(s.id)})
    body = resp.content.decode()
    assert resp.status_code == 200 and "تأكيد فتح الزيارة" in body
    assert ClinicVisit.objects.count() == 0
    client.post(reverse("clinic:quick_start"), {"student_id": str(s.id)})
    assert ClinicVisit.objects.count() == 1


@pytest.mark.django_db
def test_pick_rejects_bad_ids_and_other_schools(school, nurse_user, student_role):
    from tests.conftest import SchoolFactory

    other = SchoolFactory()
    stranger = _student(other, RoleFactory(school=other, name="student"), "غريب")
    client = _client(nurse_user)
    assert (
        client.get(reverse("clinic:quick_pick"), {"student_id": str(stranger.id)}).status_code
        == 404
    )
    assert client.get(reverse("clinic:quick_pick"), {"student_id": "ليس-معرّفاً"}).status_code == 404


@pytest.mark.django_db
def test_non_nurse_cannot_use_picker(school, student_role):
    teacher = UserFactory(full_name="معلم")
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    c = _client(teacher)
    for name in ("quick_search", "quick_class", "quick_recent", "quick_pick"):
        assert c.get(reverse(f"clinic:{name}")).status_code in (302, 403)


@pytest.mark.django_db
def test_record_visit_page_has_no_full_student_select(school, nurse_user, student_role):
    for i in range(3):
        _student(school, student_role, f"طالب {i}")
    body = _client(nurse_user).get(reverse("clinic:record_visit")).content.decode()
    assert "data-student-picker" in body
    assert 'name="student_id"' in body and '<select id="f-student_id"' not in body
    assert "طالب 0" not in body


@pytest.mark.django_db
def test_record_visit_post_requires_a_school_student(school, nurse_user, student_role):
    s = _student(school, student_role, "طالب النموذج")
    client = _client(nurse_user)
    resp = client.post(reverse("clinic:record_visit"), {"student_id": str(s.id), "reason": "صداع"})
    assert resp.status_code in (200, 302)
    assert ClinicVisit.objects.filter(student=s).count() == 1
    # غيرُ طالبٍ (الممرّض نفسُه) يُرفض
    resp = client.post(
        reverse("clinic:record_visit"), {"student_id": str(nurse_user.id), "reason": "x"}
    )
    assert resp.status_code == 404
