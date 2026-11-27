"""
tests/test_student_clinic_tab_audit.py — تبويبُ «العيادة» وواجهةُ الزيارات يُدقَّقان (CLN-03).

الصفحةُ الأولى لملفّ الطالب لا تحمل بياناً صحّيّاً، والتبويبُ يُجلب بطلبٍ يترك سطرَ تدقيقٍ واحداً
بمعرّفاتٍ وأعدادٍ فقط، ومثلُه كلُّ طلبٍ ناجحٍ لـ`/api/v1/clinic/visits/`.
"""

import pytest
from django.urls import reverse
from rest_framework.test import APIClient

from core.models import AuditLog
from tests.conftest import ClinicVisitFactory, HealthRecordFactory

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

REASON = "سببٌ طبّيٌّ خاصّ"
API_URL = "/api/v1/clinic/visits/"


def _views(user):
    return AuditLog.objects.filter(user=user, action="view")


def _health_lines(user):
    return _views(user).filter(model_name__in=["HealthRecord", "ClinicVisit"])


def _assert_ids_only(line, student):
    blob = f"{line.object_repr} {line.object_id} {line.changes}"
    for secret in (student.full_name, REASON, "AB-"):
        assert secret not in blob


@pytest.fixture
def health(school, student_user, enrolled_student):
    # اسمٌ لا يتقاطع مع نصّ الشاشة: «طالب 1» يطابق «ملف الطالب» متبوعاً بمعرّفٍ يبدأ بـ1
    student_user.full_name = "زيدون الاصطناعيّ"
    student_user.save(update_fields=["full_name"])
    HealthRecordFactory(student=student_user, blood_type_encrypted="AB-", needs_care=True)
    ClinicVisitFactory(school=school, student=student_user, reason=REASON)


@pytest.fixture
def api_as_principal(principal_user):
    client = APIClient()
    client.force_login(principal_user)
    return client


@pytest.fixture
def api_as_teacher(teacher_user):
    client = APIClient()
    client.force_login(teacher_user)
    return client


def test_the_first_page_carries_no_health_data(client_as, principal_user, student_user, health):
    response = client_as(principal_user).get(
        reverse("student_affairs:student_profile", args=[student_user.id])
    )
    body = response.content.decode()

    assert response.status_code == 200
    for secret in (REASON, "AB-", "فصيلة الدم", "يحتاج مراعاةً", "reveal_chronic", "chronic-reveal"):
        assert secret not in body
    assert "health_record" not in response.context and "clinic_visits" not in response.context
    assert response.context["clinic_visit_count"] == 1
    assert reverse("student_affairs:student_clinic_tab", args=[student_user.id]) in body
    assert "js/student-profile" in body and "clinic-tab-loading" in body
    assert not _health_lines(principal_user).exists()


def test_fetching_the_tab_writes_one_line_without_pii(
    client_as, principal_user, student_user, health
):
    client = client_as(principal_user)
    before = _views(principal_user).count()

    response = client.get(
        reverse("student_affairs:student_clinic_tab", args=[student_user.id]),
        HTTP_HX_REQUEST="true",
    )
    body = response.content.decode()

    assert response.status_code == 200
    assert REASON in body and "AB-" in body and "يحتاج مراعاةً" in body
    assert "data-clinic-loaded" in body
    assert _views(principal_user).count() == before + 1
    line = _health_lines(principal_user).get()
    assert line.object_id == str(student_user.id)
    assert line.changes["rows"] == 1
    _assert_ids_only(line, student_user)


def test_a_tab_without_health_data_writes_nothing(
    client_as, principal_user, student_user, enrolled_student
):
    response = client_as(principal_user).get(
        reverse("student_affairs:student_clinic_tab", args=[student_user.id])
    )

    assert response.status_code == 200
    assert "لا زيارات عيادة" in response.content.decode()
    assert not _health_lines(principal_user).exists()


def test_the_tab_refuses_post_and_outsiders(client_as, principal_user, student_user, health):
    url = reverse("student_affairs:student_clinic_tab", args=[student_user.id])

    assert client_as(principal_user).post(url).status_code == 405
    # الطالبُ بلا قدرة المتابعة: رفضٌ أو تحويلٌ، لا محتوى
    assert client_as(student_user).get(url).status_code in (302, 403, 404)
    assert not _health_lines(student_user).exists()


def test_every_successful_api_request_is_audited(
    api_as_principal, principal_user, student_user, health
):
    before = _health_lines(principal_user).count()

    assert api_as_principal.get(API_URL).status_code == 200
    assert api_as_principal.get(API_URL, {"student_id": str(student_user.id)}).status_code == 200

    lines = _health_lines(principal_user).order_by("timestamp")
    assert lines.count() == before + 2
    last = lines.last()
    assert last.object_id == str(student_user.id)
    assert last.changes["rows"] == 1
    for line in lines:
        _assert_ids_only(line, student_user)


def test_a_refused_api_request_writes_no_line(api_as_teacher, teacher_user, health):
    assert api_as_teacher.get(API_URL).status_code == 403
    assert not _health_lines(teacher_user).exists()
