"""حراسُ تدقيق الـAPI الأمنيّ (2026-11-20) — أربعُ ثغراتٍ لا تعود.

1. المعلّمُ لطلبته: قائمتا الطلبة والحضور ونتائجُ الشعبة كانت بحصر المدرسة وحدَه.
2. الرقمُ الشخصيُّ لا يُستخرج بالبحث الجزئيّ من `students/?search=`.
3. المحوُ للطالب وحدَه: لا يُطلب ولا يُنفَّذ على حساب كادر.
4. عنوانُ اشتراك Push لمزوّدٍ معروف: لا يُخزَّن ولا يُنادى مضيفٌ داخليّ (SSRF).
"""

from __future__ import annotations

import datetime as dt
import json
from unittest.mock import patch

import pytest
from django.test import Client
from rest_framework.test import APIClient

from assessments.models import SubjectClassSetup
from core.academic_calendar import academic_year_for_school
from core.models import ErasureRequest
from governance.erasure_service import ErasureService
from notifications.models import NotificationDelivery, NotificationDispatch, PushSubscription
from notifications.push_endpoints import is_allowed_push_endpoint
from notifications.push_subscriptions import PushEndpointRejectedError, register_subscription
from notifications.tasks import send_push_task
from operations.models import ScheduleSlot, Session, StudentAttendance, Subject

from .conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

OWN_ID = "28712345678"
OTHER_ID = "28798765432"


def _api(user) -> APIClient:
    client = APIClient()
    client.force_login(user)
    return client


def _rows(resp):
    return resp.data["results"] if isinstance(resp.data, dict) else resp.data


def _student(school, name, national_id):
    user = UserFactory(full_name=name, national_id=national_id)
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="student"))
    return user


@pytest.fixture
def world(db, school, teacher_user, principal_user):
    """شعبتان: المعلّمُ يدرّس الأولى وحدَها، وفي كلٍّ طالبٌ له صفُّ حضور."""
    year = academic_year_for_school(school)
    subject = Subject.objects.create(school=school, name_ar="العلوم", code="SCI")
    own_class = ClassGroupFactory(school=school, academic_year=year)
    other_class = ClassGroupFactory(school=school, academic_year=year)
    own = _student(school, "طالب الشعبة الأولى", OWN_ID)
    other = _student(school, "طالب الشعبة الثانية", OTHER_ID)
    StudentEnrollmentFactory(student=own, class_group=own_class)
    StudentEnrollmentFactory(student=other, class_group=other_class)

    ScheduleSlot.objects.create(
        school=school,
        teacher=teacher_user,
        class_group=own_class,
        subject=subject,
        day_of_week=0,
        period_number=1,
        start_time=dt.time(7, 0),
        end_time=dt.time(7, 45),
        academic_year=year,
    )
    SubjectClassSetup.objects.create(
        school=school,
        subject=subject,
        class_group=own_class,
        teacher=teacher_user,
        academic_year=year,
    )
    # حصّةُ الشعبة الثانية لمعلّمٍ آخر: لا يُدرّسها صاحبُ الطلب ولا يُشغلها.
    colleague = UserFactory(full_name="معلّم الشعبة الثانية")
    MembershipFactory(
        user=colleague, school=school, role=RoleFactory(school=school, name="teacher")
    )
    for klass, student, teacher in (
        (own_class, own, teacher_user),
        (other_class, other, colleague),
    ):
        session = Session.objects.create(
            school=school,
            class_group=klass,
            teacher=teacher,
            subject=subject,
            date=dt.date(2026, 11, 15),
            start_time=dt.time(8, 0),
            end_time=dt.time(8, 45),
            status="scheduled",
        )
        StudentAttendance.objects.create(
            session=session, student=student, school=school, status="absent", excuse_type=""
        )
    return {
        "school": school,
        "teacher": teacher_user,
        "principal": principal_user,
        "own": own,
        "other": other,
        "own_class": own_class,
        "other_class": other_class,
    }


# ═══════════════════════════════════════════════════════════════════
#  1. المعلّمُ لطلبته
# ═══════════════════════════════════════════════════════════════════


def _student_ids(resp):
    return {str(row["student"]["id"]) for row in _rows(resp)}


def test_teacher_lists_only_the_students_he_teaches(world):
    resp = _api(world["teacher"]).get("/api/v1/students/")

    assert resp.status_code == 200
    assert _student_ids(resp) == {str(world["own"].id)}


def test_principal_still_lists_the_whole_school(world):
    resp = _api(world["principal"]).get("/api/v1/students/")

    assert _student_ids(resp) == {str(world["own"].id), str(world["other"].id)}


def test_teacher_cannot_read_attendance_of_a_student_he_does_not_teach(world):
    client = _api(world["teacher"])

    foreign = client.get(f"/api/v1/attendance/?student_id={world['other'].id}")
    mine = client.get(f"/api/v1/attendance/?student_id={world['own'].id}")
    everything = client.get("/api/v1/attendance/")

    assert foreign.status_code == 200
    assert _rows(foreign) == []
    assert len(_rows(mine)) == 1
    assert {str(row["student_id"]) for row in _rows(everything)} == {str(world["own"].id)}


def test_principal_reads_attendance_of_any_student(world):
    resp = _api(world["principal"]).get(f"/api/v1/attendance/?student_id={world['other'].id}")

    assert len(_rows(resp)) == 1


def test_teacher_cannot_read_results_of_a_class_he_does_not_teach(world):
    client = _api(world["teacher"])

    foreign = client.get(f"/api/v1/classes/{world['other_class'].id}/results/")
    mine = client.get(f"/api/v1/classes/{world['own_class'].id}/results/")

    assert foreign.status_code == 403
    assert mine.status_code == 200


def test_principal_reads_results_of_any_class(world):
    resp = _api(world["principal"]).get(f"/api/v1/classes/{world['other_class'].id}/results/")

    assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════
#  2. الرقمُ الشخصيُّ لا يُستخرج بالبحث الجزئيّ
# ═══════════════════════════════════════════════════════════════════


def test_teacher_partial_national_id_search_matches_nothing(world):
    """كلُّ خانةٍ كانت تضيّق النتيجةَ والاسمُ يظهر — فيُستخرج الرقمُ خانةً خانةً."""
    client = _api(world["teacher"])

    for fragment in (OWN_ID[:4], OWN_ID[3:8], OWN_ID[:-1]):
        assert _rows(client.get(f"/api/v1/students/?search={fragment}")) == []


def test_teacher_exact_national_id_and_name_search_still_work(world):
    client = _api(world["teacher"])

    assert _student_ids(client.get(f"/api/v1/students/?search={OWN_ID}")) == {str(world["own"].id)}
    assert _student_ids(client.get("/api/v1/students/?search=الأولى")) == {str(world["own"].id)}


def test_principal_may_search_national_id_partially(world):
    resp = _api(world["principal"]).get(f"/api/v1/students/?search={OTHER_ID[3:8]}")

    assert _student_ids(resp) == {str(world["other"].id)}


# ═══════════════════════════════════════════════════════════════════
#  3. المحوُ للطالب وحدَه
# ═══════════════════════════════════════════════════════════════════


def test_principal_cannot_request_erasure_of_a_staff_account(school, principal_user, teacher_user):
    resp = _api(principal_user).post(
        "/api/v1/erasure/request/",
        format="json",
        data={"student_id": str(teacher_user.id), "reason": "طلبٌ على حساب معلّمٍ لا طالب"},
    )

    assert resp.status_code == 404
    assert not ErasureRequest.objects.filter(student=teacher_user).exists()


def test_approving_a_request_that_targets_staff_erases_nothing(
    school, principal_user, teacher_user
):
    """دفاعٌ في العمق: طلبٌ بلغ القاعدةَ من غير طريق الـAPI لا يُنفَّذ على كادر."""
    original_name = teacher_user.full_name
    req = ErasureRequest.objects.create(
        school=school, student=teacher_user, requested_by=principal_user, reason="طلبٌ مدسوس"
    )

    resp = _api(principal_user).post(
        f"/api/v1/erasure/requests/{req.id}/approve/", format="json", data={}
    )

    assert resp.status_code == 409
    teacher_user.refresh_from_db()
    assert teacher_user.is_active is True
    assert teacher_user.full_name == original_name


def test_only_a_student_membership_makes_an_erasure_target(school, student_user, teacher_user):
    assert ErasureService.student_in_school(student_user, school) is True
    assert ErasureService.student_in_school(teacher_user, school) is False

    # دورُ طالبٍ يُضاف إلى حساب كادرٍ لا يفتح الباب: الحسابُ واحدٌ عبر المدارس.
    MembershipFactory(
        user=teacher_user, school=school, role=RoleFactory(school=school, name="student")
    )
    assert ErasureService.student_in_school(teacher_user, school) is False

    student_user.is_superuser = True
    assert ErasureService.student_in_school(student_user, school) is False


# ═══════════════════════════════════════════════════════════════════
#  4. عنوانُ اشتراك Push لمزوّدٍ معروف
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
        "https://web.push.apple.com/abc",
        "https://FCM.googleapis.com:443/fcm/send/abc",
    ],
)
def test_known_push_providers_are_accepted(endpoint):
    assert is_allowed_push_endpoint(endpoint) is True


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",  # بلا TLS
        "https://10.0.0.5/hook",  # عنوانٌ داخليّ
        "http://169.254.169.254/latest/meta-data/",  # بياناتُ السحابة
        "https://redis.railway.internal:6379/",
        "https://localhost/x",
        "https://[::1]/x",
        "https://fcm.googleapis.com.evil.example/x",  # لاحقةٌ مزوّرة
        "https://evilfcm.googleapis.com.attacker.test/x",
        "https://notfcm.googleapis.com/x",  # ليس تحت المضيف المسمّى
        "https://fcm.googleapis.com:8443/x",  # منفذٌ غيرُ 443
        "https://user:pass@fcm.googleapis.com/x",  # بياناتُ دخولٍ في العنوان  # pragma: allowlist secret
        "https://fcm.googleapis.com@10.0.0.5/x",
        "ftp://fcm.googleapis.com/x",
        "https://[not-an-ip/x",
        "",
    ],
)
def test_everything_else_is_rejected(endpoint):
    assert is_allowed_push_endpoint(endpoint) is False


def _subscribe(user, endpoint):
    client = Client()
    client.force_login(user)
    return client.post(
        "/parents/push/subscribe/",
        data=json.dumps({"endpoint": endpoint, "keys": {"p256dh": "k" * 32, "auth": "a" * 16}}),
        content_type="application/json",
    )


def test_subscribing_with_an_internal_endpoint_is_refused_and_not_stored(parent_user):
    resp = _subscribe(parent_user, "http://10.0.0.5:8080/internal")

    assert resp.status_code == 400
    assert not PushSubscription.objects.filter(user=parent_user).exists()


def test_registering_a_provider_endpoint_still_works(school, parent_user):
    """على مالك التسجيل لا على العرض: العرضُ يمرّر `request.user` الكسول فيسقط عند قفل صفّ
    المستخدم (`type(user).objects`) قبل هذا التعديل وبعده — عيبٌ قائمٌ خارج هذا الإصلاح."""
    _, created, _ = register_subscription(
        user=parent_user,
        school=school,
        endpoint="https://fcm.googleapis.com/fcm/send/abc",
        p256dh="k" * 32,
        auth="a" * 16,
    )

    assert created is True
    assert PushSubscription.objects.filter(user=parent_user, is_active=True).count() == 1


def test_registering_an_internal_endpoint_raises_before_any_write(school, parent_user):
    with pytest.raises(PushEndpointRejectedError):
        register_subscription(
            user=parent_user,
            school=school,
            endpoint="https://10.0.0.5/hook",
            p256dh="k" * 32,
            auth="a" * 16,
        )

    assert not PushSubscription.objects.filter(user=parent_user).exists()


def test_a_stored_internal_endpoint_is_disabled_and_never_called(school, parent_user):
    """اشتراكٌ خُزّن قبل الفحص: العاملُ يعطّله ولا يطرق عنوانَه."""
    sub = PushSubscription.objects.create(
        user=parent_user,
        school=school,
        endpoint="http://10.0.0.5:8080/internal",
        p256dh="k" * 32,
        auth="a" * 16,
        is_active=True,
    )
    dispatch = NotificationDispatch.objects.create(school=school, event_type="general")
    delivery = NotificationDelivery.objects.create(
        dispatch=dispatch, school=school, recipient=parent_user, channel="push"
    )

    with patch("pywebpush.webpush") as provider:
        send_push_task(
            str(parent_user.id),
            "عنوان",
            "نصّ",
            "/",
            school_id=str(school.id),
            delivery_id=str(delivery.id),
        )

    assert provider.call_count == 0
    sub.refresh_from_db()
    assert sub.is_active is False
