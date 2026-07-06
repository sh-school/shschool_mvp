"""
اختبارات إصلاحات التدقيق العدائي 2026-07-06.
تتحقّق من البنود المطبَّقة فعلياً وتمنع ارتدادها.
"""
import pytest


def test_customuser_str_has_no_national_id():
    """[PII-02] التمثيل النصّي للمستخدم لا يحوي الرقم الشخصي (كان يتسرّب لـ AuditLog.object_repr)."""
    from core.models import CustomUser

    u = CustomUser(full_name="أحمد محمد", national_id="28912345678")
    assert str(u) == "أحمد محمد"
    assert "28912345678" not in str(u)


def test_dead_letter_message_model_exists():
    """[P0-8] نموذج Dead-Letter Queue موجود بالحقول المطلوبة."""
    from notifications.models import DeadLetterMessage

    fields = {f.name for f in DeadLetterMessage._meta.get_fields()}
    assert {"kind", "payload", "error", "resolved", "created_at"} <= fields


def test_encrypted_field_empty_passthrough():
    """[PII-10] الحقل المشفّر يمرّر القيم الفارغة دون محاولة تشفير أو رفع خطأ."""
    from core.fields import EncryptedTextField

    f = EncryptedTextField()
    assert f.get_prep_value("") == ""
    assert f.get_prep_value(None) in ("", None)


@pytest.mark.django_db
def test_rls_apply_is_safe_on_test_backend():
    """[SEC-01] ضبط سياق RLS لا يرفع خطأً على قاعدة الاختبار (vendor-guard / set_config)."""
    from core.middleware_rls import RLSMiddleware

    mw = RLSMiddleware(get_response=lambda req: None)
    assert mw._apply("") is None


@pytest.mark.django_db
def test_notification_tasks_import_dlq_helper():
    """[P0-8] مسار DLQ متاح في مهام الإشعارات."""
    from notifications import tasks

    assert hasattr(tasks, "_to_dlq")


@pytest.mark.django_db
def test_emergency_contact_encrypted_at_rest(student_user, settings):
    """[PII-04] جهة اتصال الطوارئ: شفّافة عبر ORM ومشفّرة at-rest."""
    from django.db import connection

    from clinic.models import HealthRecord

    hr = HealthRecord.objects.create(
        student=student_user, emergency_contact_phone="0501234567"
    )
    hr.refresh_from_db()
    assert hr.emergency_contact_phone == "0501234567"  # شفّاف دائماً عبر ORM

    if getattr(settings, "FERNET_KEY", ""):
        with connection.cursor() as cur:
            cur.execute(
                f"SELECT emergency_contact_phone FROM {HealthRecord._meta.db_table} "
                f"WHERE {HealthRecord._meta.pk.column} = %s",
                [str(hr.pk)],
            )
            raw = cur.fetchone()[0]
        assert "0501234567" not in (raw or "")  # مخزّن مشفّراً لا صريحاً
