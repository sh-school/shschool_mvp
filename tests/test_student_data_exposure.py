"""[SECURITY] «مسجَّلُ الدخول» ليس صلاحيّةً على بيانات طالبٍ آخر.

مراجعةُ الصلاحيّات يومَ 2026-09-13 وجدت أربعةَ مواضعَ تكتفي بتسجيل الدخول، وأكّدتها
بطلبٍ من حساب طالبٍ على الإنتاج نفسِه:

- ن١ ``/api/attendance/``: سجلُّ حضور المدرسة كلِّها — الاسمُ والحالةُ والعذر.
  (ونظيرُه ``/api/sessions/``.) مساران قديمان لا يستعملهما قالبٌ ولا سكربت، ونظيراهما
  في ``/api/v1/`` مغلقان بـ``IsTeacherOrAdmin``.
- ن٢ التقاريرُ الأكاديميّةُ الأربعة وتصديرُها: درجةُ كلّ طالبٍ في الاختبارات القصيرة،
  وتقدّمُه، وسلوكُه الشهريّ — بـ``@login_required`` وحدَه.
- ن٣ البحثُ العامّ: ``if request.user.is_admin:`` بلا قوسين — الدالّةُ نفسُها صادقةٌ
  دائماً، فكتلةُ «للمدير وحدَه» تعرض أسماءَ الكادر وبريدَهم لكلّ مستخدم.
- ن٤ البحثُ العامّ بجزءٍ من الرقم الشخصيّ مفتوحٌ لكلّ حساب: من يعرف الرقمَ يعرف الاسم.

وكلُّ اختبارٍ هنا يطلب ما طلبه الطالبُ على الإنتاج.
"""

import pytest
from django.test import Client

from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

REPORTS = (
    "/academic/reports/",
    "/academic/reports/quiz/",
    "/academic/reports/exam-results/",
    "/academic/reports/exam-results/?export=excel",
    "/academic/reports/progress/",
    "/academic/reports/monthly-behavior-academic/",
)


def _member(school, role_name, **user_fields):
    user = UserFactory(**user_fields)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role_name))
    return user


def _client(user):
    client = Client()
    client.force_login(user)
    return client


@pytest.fixture
def classmate(school):
    """طالبٌ في مدرسة الاختبار — اسمُه ورقمُه الشخصيُّ مما يُبحث عنه."""
    student = _member(school, "student", full_name="زميلٌ مبحوثٌ عنه")
    StudentEnrollmentFactory(student=student, class_group=ClassGroupFactory(school=school))
    return student


# ── ن١ ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/api/attendance/", "/api/sessions/"])
def test_the_legacy_api_routes_are_gone(school, student_user, path):
    """لا مستهلكَ لهما، ونظيراهما في ``/api/v1/`` بالصلاحيّة الصحيحة."""
    assert _client(student_user).get(path).status_code == 404


def test_the_versioned_attendance_api_still_refuses_a_student(school, student_user):
    assert _client(student_user).get("/api/v1/attendance/").status_code == 403


# ── ن٢ ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["student", "services_worker", "teacher", "bus_supervisor"])
@pytest.mark.parametrize("path", REPORTS)
def test_the_academic_reports_refuse_who_does_not_see_the_whole_school(school, role, path):
    """التقاريرُ غيرُ مقيَّدةٍ بشعبةٍ ولا قسم — فهي لمن يرى المدرسةَ كلَّها."""
    response = _client(_member(school, role)).get(path)

    assert response.status_code == 403, f"{role} فتح {path}"


@pytest.mark.parametrize("role", ["principal", "vice_academic", "vice_admin"])
def test_the_academic_reports_open_for_school_wide_leadership(school, role):
    assert _client(_member(school, role)).get("/academic/reports/quiz/").status_code == 200


# ── ن٣ ─────────────────────────────────────────────────────────────


def _results(user, q, kind):
    payload = _client(user).get("/search/", {"q": q}).json()
    return [r for r in payload["results"] if r["type"] == kind]


@pytest.mark.parametrize("role", ["student", "teacher", "vice_admin"])
def test_staff_names_and_emails_are_for_the_principal_only(school, role):
    _member(school, "teacher", full_name="معلمٌ مستهدَفٌ بالبحث")

    assert _results(_member(school, role), "مستهدَف", "teacher") == []


def test_the_principal_still_finds_staff(school, principal_user):
    _member(school, "teacher", full_name="معلمٌ مستهدَفٌ بالبحث")

    assert _results(principal_user, "مستهدَف", "teacher")


# ── ن٤ ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("role", ["student", "parent"])
def test_a_student_or_parent_finds_no_students(school, classmate, role):
    user = _member(school, role)
    if role == "parent":
        from django.utils import timezone

        user.consent_given_at = timezone.now()
        user.save(update_fields=["consent_given_at"])

    assert _results(user, "زميل", "student") == []
    assert _results(user, classmate.national_id[:9], "student") == []


def test_staff_find_a_student_by_name(school, classmate, teacher_user):
    assert _results(teacher_user, "زميل", "student")


@pytest.mark.parametrize("role", ["teacher", "services_worker"])
def test_the_national_id_is_not_a_search_key_for_every_staff_member(school, classmate, role):
    """الرقمُ الشخصيُّ مفتاحٌ لمن يدير سجلَّ الطلبة، لا لكلّ موظّف."""
    assert _results(_member(school, role), classmate.national_id[:9], "student") == []


def test_student_affairs_still_find_a_student_by_national_id(school, classmate):
    user = _member(school, "vice_admin")

    assert _results(user, classmate.national_id[:9], "student")
