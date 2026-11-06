"""
tests/test_clinic_health_visibility.py — رؤيةُ الملفّ الصحّيّ (W-20261020-033 / W-20261107-001)

الممرّضُ يرى الكاملَ؛ المدير والنائب مختصراً بلا تشخيصٍ، ولا يُفتح الكاملُ إلا بسببٍ من القائمة المغلقة
يُسجَّل في التدقيق؛ والتعديلُ للممرّض وحدَه؛ والمعلّمُ لا يرى اسمَ حالةٍ إلا بنقرةٍ مسجَّلة لشُعبته.
"""

import re
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse

from clinic.health_access import OPEN_REASONS
from clinic.models import ClinicVisit, HealthRecord
from core.models import AuditLog
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

DIAGNOSIS = "ربو شعبي مزمن"
MEDICINE = "بخاخ فنتولين"


def _client(user):
    c = Client()
    c.force_login(user)
    return c


def _staff(school, role, name):
    user = UserFactory(full_name=name)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def record(student_user):
    return HealthRecord.objects.create(
        student=student_user, chronic_diseases=DIAGNOSIS, medications=MEDICINE, needs_care=True
    )


@pytest.fixture
def manager(school):
    return _staff(school, "principal", "مدير الاختبار")


@pytest.fixture
def deputy(school):
    return _staff(school, "vice_admin", "نائب الاختبار")


def _url(student):
    return reverse("clinic:health_record", args=[student.id])


@pytest.mark.django_db
def test_nurse_sees_full_record(nurse_user, student_user, record):
    body = _client(nurse_user).get(_url(student_user)).content.decode()
    assert DIAGNOSIS in body and MEDICINE in body


@pytest.mark.django_db
@pytest.mark.parametrize("role_fixture", ["manager", "deputy"])
def test_principal_and_deputy_see_brief_without_diagnosis(
    role_fixture, request, student_user, record
):
    user = request.getfixturevalue(role_fixture)
    body = _client(user).get(_url(student_user)).content.decode()
    assert DIAGNOSIS not in body and MEDICINE not in body
    assert "يحتاج مراعاةً" in body and 'name="reason"' in body


@pytest.mark.django_db
def test_teacher_has_no_access_to_health_record_page(teacher_user, student_user, record):
    resp = _client(teacher_user).get(_url(student_user))
    assert resp.status_code in (302, 403, 404)
    assert DIAGNOSIS not in resp.content.decode()
    assert MEDICINE not in resp.content.decode()


@pytest.mark.django_db
def test_open_full_without_reason_is_refused_and_logged(manager, student_user, record):
    resp = _client(manager).post(_url(student_user), {"open_full": "1", "reason": ""})
    body = resp.content.decode()
    assert resp.status_code == 400
    assert DIAGNOSIS not in body and MEDICINE not in body
    assert AuditLog.objects.filter(user=manager, changes__denied="no_reason").exists()
    resp = _client(manager).post(_url(student_user), {"open_full": "1", "reason": "عشوائي"})
    assert resp.status_code == 400


@pytest.mark.django_db
def test_open_full_with_reason_shows_record_and_logs_reason(manager, student_user, record):
    code = OPEN_REASONS[0][0]
    resp = _client(manager).post(
        _url(student_user), {"open_full": "1", "reason": code, "note": "طلبُ الوليّ"}
    )
    body = resp.content.decode()
    assert resp.status_code == 200 and DIAGNOSIS in body
    row = AuditLog.objects.filter(user=manager, changes__reason=code).get()
    assert row.changes["note"] == "طلبُ الوليّ"
    assert DIAGNOSIS not in row.object_repr and DIAGNOSIS not in str(row.changes)
    # القراءةُ التاليةُ مختصرةٌ من جديد: السببُ لكلّ فتحٍ لا للجلسة
    assert DIAGNOSIS not in _client(manager).get(_url(student_user)).content.decode()


@pytest.mark.django_db
def test_only_nurse_can_edit(manager, nurse_user, student_user, record):
    data = {"chronic_diseases": "تغيير", "needs_care": "1"}
    assert _client(manager).post(_url(student_user), data).status_code == 403
    record.refresh_from_db()
    assert record.chronic_diseases == DIAGNOSIS
    assert _client(nurse_user).post(_url(student_user), data).status_code == 302


@pytest.mark.django_db
def test_brief_hides_visit_symptoms_and_treatment(
    manager, nurse_user, student_user, record, school
):
    ClinicVisit.objects.create(
        school=school,
        student=student_user,
        nurse=nurse_user,
        reason="صداع",
        symptoms="دوارٌ شديد",
        treatment="مسكّن",
    )
    brief = _client(manager).get(_url(student_user)).content.decode()
    assert "دوارٌ شديد" not in brief and "مسكّن" not in brief
    full = _client(nurse_user).get(_url(student_user)).content.decode()
    assert "دوارٌ شديد" in full


def test_diagnosis_text_is_read_only_by_the_record_view():
    """حارسُ الأسطح: لا قالبَ غيرُ السجلّ الصحّيّ يعرض تشخيصاً أو دواءً أو حساسيّة."""
    root = Path(__file__).resolve().parent.parent
    pattern = re.compile(r"\b(chronic_diseases|medications|allergies)\b")
    leaks = [
        str(path.relative_to(root))
        for path in (root / "templates").rglob("*.html")
        if path.name != "health_record.html" and pattern.search(path.read_text(encoding="utf-8"))
    ]
    assert leaks == [], f"قوالبُ تعرض حقلاً صحّيّاً خارج السجلّ: {leaks}"


@pytest.mark.django_db
def test_chronic_name_reveal_is_post_only_logged_and_name_only(
    manager, student_user, record, enrolled_student
):
    url = reverse("student_affairs:reveal_chronic", args=[student_user.id])
    c = _client(manager)
    assert c.get(url).status_code == 405
    before = AuditLog.objects.filter(user=manager, action="view").count()
    resp = c.post(url)
    body = resp.content.decode()
    assert resp.status_code == 200 and DIAGNOSIS in body and MEDICINE not in body
    assert AuditLog.objects.filter(user=manager, action="view").count() == before + 1
    line = AuditLog.objects.filter(user=manager, action="view").latest("timestamp")
    assert DIAGNOSIS not in f"{line.object_repr} {line.changes}"


@pytest.mark.django_db
def test_chronic_name_hidden_from_unrelated_roles_and_other_teachers(
    school, student_user, record, enrolled_student
):
    url = reverse("student_affairs:reveal_chronic", args=[student_user.id])
    driver = _staff(school, "driver", "سائق")
    assert _client(driver).post(url).status_code in (302, 403)
    # المعلّمُ خارجُ القدرة: لا كشفَ لاسم الحالة ولو لطالب شُعبته (يرى «يحتاج مراعاةً» فقط)
    teacher = _staff(school, "teacher", "معلم الشعبة")
    for user in (teacher, _staff(school, "teacher", "معلم غريب")):
        resp = _client(user).post(url)
        assert resp.status_code in (302, 403, 404)
        assert DIAGNOSIS not in resp.content.decode()
    assert not AuditLog.objects.filter(user=teacher, action="view").exists()


@pytest.mark.django_db
def test_teacher_profile_page_never_shows_chronic_name_or_reveal_button(
    teacher_user, student_user, record, enrolled_student
):
    resp = _client(teacher_user).get(
        reverse("student_affairs:student_profile", args=[student_user.id])
    )
    body = resp.content.decode()
    assert resp.status_code in (302, 403, 404)
    assert DIAGNOSIS not in body and MEDICINE not in body
    assert "reveal_chronic" not in body and "كشف اسم الحالة" not in body


@pytest.mark.django_db
def test_profile_shows_needs_care_flag_without_name_for_roles_that_can_open_it(
    school, student_user, record, enrolled_student
):
    coordinator = _staff(school, "student_affairs_coordinator", "منسق الطلبة")
    body = (
        _client(coordinator)
        .get(reverse("student_affairs:student_profile", args=[student_user.id]))
        .content.decode()
    )
    assert "يحتاج مراعاةً" in body
    assert DIAGNOSIS not in body and MEDICINE not in body
