"""رسائلُ المطوّر الصادرة (مطوّر ← مستخدمين) — فردٌ/قسمٌ أكاديميّ/دورٌ وظيفيّ/الجميع.

التسليمُ عبر `notifications.InAppNotification` القائم — هذه الاختباراتُ تتحقّق
من أنّ البثّ يصل العدد الصحيح من المستخدمين بالنوع الصحيح، وأنّ الحواجز
(`developer_only`، استبعادُ المرسِل نفسِه) تعمل.
"""

import pytest
from django.urls import reverse

from developer_feedback.models import OutboundMessage
from developer_feedback.services.audience import AudienceError, resolve_recipients
from notifications.models import InAppNotification


@pytest.fixture
def department_math(db, school):
    from core.models import Department

    return Department.objects.create(school=school, name="الرياضيات", code="math")


@pytest.fixture
def teacher_in_math(db, school, department_math, teacher_user):
    teacher_user.memberships.update(department_obj=department_math)
    return teacher_user


@pytest.mark.django_db
class TestResolveRecipients:
    def test_individual_user_returns_that_user_only(self, school, developer_user, teacher_user):
        qs = resolve_recipients(school, developer_user, "user", str(teacher_user.id))
        assert list(qs) == [teacher_user]

    def test_department_returns_its_teachers(
        self, school, developer_user, teacher_in_math, department_math
    ):
        qs = resolve_recipients(school, developer_user, "department", str(department_math.id))
        assert teacher_in_math in qs

    def test_role_returns_every_member_with_that_role(self, school, developer_user, teacher_user):
        qs = resolve_recipients(school, developer_user, "role", "teacher")
        assert teacher_user in qs

    def test_all_returns_every_active_member_except_the_sender(
        self, school, developer_user, teacher_user
    ):
        qs = resolve_recipients(school, developer_user, "all", "")
        assert teacher_user in qs
        assert developer_user not in qs

    def test_sender_is_always_excluded(self, school, developer_user):
        qs = resolve_recipients(school, developer_user, "all", "")
        assert developer_user not in qs

    def test_unknown_role_raises_audience_error(self, school, developer_user):
        with pytest.raises(AudienceError):
            resolve_recipients(school, developer_user, "role", "not-a-real-role")

    def test_unknown_target_kind_raises_audience_error(self, school, developer_user):
        with pytest.raises(AudienceError):
            resolve_recipients(school, developer_user, "spaceship", "")


@pytest.mark.django_db
class TestBroadcastCreateView:
    def test_developer_can_broadcast_to_a_role(self, client, school, developer_user, teacher_user):
        client.force_login(developer_user)
        url = reverse("developer_feedback:broadcast_create")
        resp = client.post(
            url,
            {
                "subject": "اختبارٌ تجريبيّ",
                "body": "نصُّ رسالةٍ تجريبيّة لأغراض الاختبار الآليّ.",
                "target_kind": "role",
                "target_value": "teacher",
            },
        )
        assert resp.status_code == 302

        outbound = OutboundMessage.objects.get(sent_by=developer_user)
        assert outbound.recipient_count == 1
        assert "معلم" in outbound.audience_label or "teacher" in outbound.audience_label.lower()

        notif = InAppNotification.objects.get(user=teacher_user)
        assert notif.event_type == "developer_message"
        assert notif.title == "اختبارٌ تجريبيّ"
        assert notif.is_read is False

    def test_non_developer_is_forbidden(self, client, teacher_user):
        client.force_login(teacher_user)
        resp = client.get(reverse("developer_feedback:broadcast_create"))
        assert resp.status_code == 403

    def test_empty_audience_shows_form_error_and_creates_nothing(
        self, client, school, developer_user
    ):
        client.force_login(developer_user)
        url = reverse("developer_feedback:broadcast_create")
        resp = client.post(
            url,
            {
                "subject": "لا أحد يستلمها",
                "body": "دورٌ لا يملكه أحدٌ في هذه المدرسة بعدُ.",
                "target_kind": "role",
                "target_value": "psychologist",
            },
        )
        assert resp.status_code == 200
        assert OutboundMessage.objects.count() == 0
        assert InAppNotification.objects.count() == 0

    def test_recipient_count_endpoint_matches_resolve_recipients(
        self, client, school, developer_user, teacher_user
    ):
        client.force_login(developer_user)
        url = reverse("developer_feedback:broadcast_recipient_count")
        resp = client.get(url, {"target_kind": "role", "target_value": "teacher"})
        assert resp.status_code == 200
        assert resp.json()["count"] == 1
