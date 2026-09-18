"""معرّفُ الدخول: الرقمُ الوظيفيُّ للكادر وحدَه، والمفتاحُ المعياريُّ للقفل.

الرقمُ الشخصيُّ القطريُّ بياناتٌ شخصيّة، وكان يُكتب في نموذج الدخول كلَّ صباح
ويسكن في سجلّ المحاولات الفاشلة نصّاً صريحاً. فصار الكادرُ يدخل برقمه الوظيفيّ،
وصار ما يُقفل عليه مفتاحاً معياريّاً لا النصَّ المكتوب. وقرارُ المالك 2026-09-18
(ق-10) قطع نافذةَ القبول المزدوج: من له رقمٌ وظيفيّ لا يدخل برقمه الشخصيّ بعد
اليوم — يُعامَل كمعرّفٍ مجهول. الطلبةُ وأولياءُ الأمور بلا رقمٍ وظيفيّ يدخلون
برقمهم الشخصيّ كما هم.
"""

import pytest

from core.auth_identity import axes_username, identifier_kind, lockout_key, resolve_user

pytestmark = pytest.mark.django_db


@pytest.fixture
def staff(teacher_user):
    teacher_user.employee_number = "137032"
    teacher_user.save(update_fields=["employee_number"])
    return teacher_user


class TestResolution:
    def test_employee_number_finds_the_staff_member(self, staff):
        assert resolve_user("137032") == staff

    def test_national_id_is_rejected_for_staff(self, staff):
        assert resolve_user(staff.national_id) is None

    def test_national_id_still_finds_a_student_or_parent(self, student_user):
        assert resolve_user(student_user.national_id) == student_user

    def test_unknown_identifier_is_none(self, db):
        assert resolve_user("00000000000") is None

    def test_blank_is_none(self, db):
        assert resolve_user("   ") is None

    def test_kind_says_which_one_was_typed(self, staff):
        assert identifier_kind(staff, "137032") == "employee_number"
        assert identifier_kind(staff, staff.national_id) == "national_id"
        assert identifier_kind(None, "137032") == "unknown"


class TestLockoutKey:
    def test_the_rejected_national_id_no_longer_shares_the_staff_key(self, staff):
        """قبل ق-10 كانا يتشاركان مفتاحاً واحداً؛ اليوم الرقمُ الشخصيّ مرفوضٌ
        فيسقط على مفتاح المجهول — لا يعود يحمي حسابَ الموظّف من القفل."""
        assert lockout_key("137032") != lockout_key(staff.national_id)

    def test_the_key_never_carries_the_national_id(self, staff):
        for raw in ("137032", staff.national_id):
            assert staff.national_id not in axes_username(None, {"identifier": raw})

    def test_unknown_identifiers_get_a_stable_opaque_key(self, db):
        first = lockout_key("29900000009")
        assert first == lockout_key("29900000009")
        assert "29900000009" not in first
        assert first != lockout_key("29900000008")

    def test_axes_reads_the_post_when_credentials_are_empty(self, rf, staff):
        request = rf.post("/auth/login/", {"identifier": "137032"})
        assert axes_username(request, None) == lockout_key("137032")


class TestLoginScreen:
    def test_staff_logs_in_with_the_employee_number(self, client, staff):
        resp = client.post("/auth/login/", {"identifier": "137032", "password": "testpass123"})
        assert resp.status_code == 302

    def test_national_id_is_rejected_for_staff(self, client, staff):
        resp = client.post(
            "/auth/login/",
            {"identifier": staff.national_id, "password": "testpass123"},
        )
        assert resp.status_code == 200
        assert "المعرّف أو كلمة المرور غير صحيحة" in resp.content.decode()

    def test_the_old_field_name_still_posts_for_a_student(self, client, student_user):
        """نماذجُ المتصفّحات المحفوظة لا تُكسر في يوم النشر — لمن يدخل برقمه
        الشخصيّ أصلاً (لا كادرَ له رقمٌ وظيفيّ)."""
        resp = client.post(
            "/auth/login/",
            {"national_id": student_user.national_id, "password": "testpass123"},
        )
        assert resp.status_code == 302

    def test_the_error_message_does_not_name_a_single_identifier(self, client, db):
        resp = client.post("/auth/login/", {"identifier": "00000000000", "password": "x"})
        assert resp.status_code == 200
        assert "المعرّف أو كلمة المرور غير صحيحة" in resp.content.decode()

    def test_failures_by_employee_number_lock_the_account(self, client, staff):
        for _ in range(5):
            client.post("/auth/login/", {"identifier": "137032", "password": "wrong"})
        staff.refresh_from_db()
        assert staff.failed_login_attempts == 5
        assert staff.locked_until is not None

    def test_failures_by_the_rejected_national_id_do_not_touch_the_staff_account(
        self, client, staff
    ):
        """المعرّفُ مرفوضٌ فلا يُحَلّ إلى الموظّف — فشله لا يُعدّ على حسابه."""
        for _ in range(5):
            client.post("/auth/login/", {"identifier": staff.national_id, "password": "wrong"})
        staff.refresh_from_db()
        assert staff.failed_login_attempts == 0
        assert staff.locked_until is None

    def test_the_audit_log_records_which_identifier_was_used(self, client, staff):
        from core.models import AuditLog

        client.post("/auth/login/", {"identifier": "137032", "password": "testpass123"})
        entry = AuditLog.objects.filter(user=staff, action="login").latest("timestamp")
        assert entry.changes == {"identifier": "employee_number"}
