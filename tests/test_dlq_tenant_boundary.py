"""
tests/test_dlq_tenant_boundary.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[P2-B1] طابور الرسائل الفاشلة داخل حدّ المستأجر.

كان `DeadLetterMessage` يخزّن المدرسة داخل JSON. سياسات RLS مُسندات على أعمدة
ولا تقرأ داخل JSONField، فحلقة المطابقة في 0037 — التي تختار الجداول ذات عمود
`school_id` — لم ترَ هذا الجدول قط. مقيساً من الإنتاج قبل التغيير:

    HAS_SCHOOL_ID_COLUMN = 0
    RLS_ENABLED          = False
    POLICY_COUNT         = 0

هذه الاختبارات تُثبت إغلاق الفجوتين: العزل، وتقليل البيانات الشخصية.
"""

import inspect
from pathlib import Path

import pytest
from django.db import connection

from notifications import tasks as notification_tasks
from notifications.models import DeadLetterMessage

# لا pytestmark عام: فحوص المخطّط وحدها تحتاج قاعدة بيانات، وفحوص المصدر
# تعمل في أي بيئة. فرضُ django_db على الجميع يجعل جزءاً من الحراسة غير قابل
# للتشغيل حيث لا قاعدة — وحارس لا يعمل ليس حارساً.

ROOT = Path(__file__).resolve().parents[1]
TABLE = "notifications_deadlettermessage"


# ══════════════════════════════════════════════════════════════════
# العزل على مستوى المخطّط
# ══════════════════════════════════════════════════════════════════


def _skip_unless_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL-specific RLS contract")


@pytest.mark.django_db
def test_dlq_table_carries_a_real_school_column():
    """[P2-B1] المدرسة عمود لا مفتاح JSON — وإلا بقيت السياسة مستحيلة."""
    _skip_unless_postgres()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM information_schema.columns
            WHERE table_schema = 'public'
              AND table_name = %s
              AND column_name = 'school_id'
            """,
            [TABLE],
        )
        assert cursor.fetchone()[0] == 1


@pytest.mark.django_db
def test_dlq_table_is_row_level_secured():
    """
    [P2-B1] الترحيل يُفعّل RLS صراحةً.

    0037 طُبِّق بالفعل ولن يُعاد، فإضافة العمود وحدها لا تُنتج سياسة — الاعتماد
    على مطابقة ماضية كان سيترك الجدول مكشوفاً بينما يبدو مغطّى.
    """
    _skip_unless_postgres()

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity FROM pg_class WHERE oid = %s::regclass",
            [f"public.{TABLE}"],
        )
        assert cursor.fetchone()[0] is True

        cursor.execute(
            """
            SELECT qual, with_check
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = %s
              AND policyname = 'school_isolation'
            """,
            [TABLE],
        )
        policy = cursor.fetchone()

    assert policy is not None, "school_isolation policy is missing"

    qual, with_check = policy
    assert qual and "app_rls_school" in qual
    assert with_check and "app_rls_school" in with_check


@pytest.mark.django_db
def test_dlq_policy_matches_the_platform_predicate():
    """السياسة نفسها المستخدمة في بقيّة الجداول — لا صيغة خاصة تنحرف لاحقاً."""
    _skip_unless_postgres()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT count(*)
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = %s
              AND policyname = 'school_isolation'
              AND coalesce(qual, '') LIKE '%%school_id%%'
            """,
            [TABLE],
        )
        assert cursor.fetchone()[0] == 1


# ══════════════════════════════════════════════════════════════════
# تقليل البيانات الشخصية
# ══════════════════════════════════════════════════════════════════

PII_KEYS = ("recipient_email", "phone_number", "message", "subject")


def test_dlq_writer_takes_the_school_explicitly():
    """[P2-B1] تمرير المدرسة ضمناً داخل JSON هو ما أبقى الجدول خارج العزل."""
    signature = inspect.signature(notification_tasks._to_dlq)

    assert list(signature.parameters) == ["kind", "school_id", "payload", "error"]


@pytest.mark.parametrize("key", PII_KEYS)
def test_no_dlq_payload_carries_personal_data(key):
    """
    الـpayload بيانات إعادة تشغيل لا نسخة من الرسالة.

    تخزين الهاتف أو البريد أو نصّ الرسالة يجعل هذا الجدول مستودع PII جديداً —
    وهي المفارقة نفسها التي أصلحناها في السجلّات ثم كادت تتكرّر هنا.
    """
    source = (ROOT / "notifications" / "tasks.py").read_text(encoding="utf-8")

    for block in _dlq_call_blocks(source):
        assert f'"{key}"' not in block, f"{key} must not be stored in the DLQ payload"


def _dlq_call_blocks(source):
    """يستخرج نصّ كل استدعاء لـ_to_dlq حتى قوس الإغلاق."""
    blocks = []
    lines = source.splitlines()

    for index, line in enumerate(lines):
        if "_to_dlq(" not in line or "def _to_dlq" in line:
            continue

        depth = 0
        collected = []
        for candidate in lines[index:]:
            collected.append(candidate)
            depth += candidate.count("(") - candidate.count(")")
            if depth <= 0 and len(collected) > 1:
                break
        blocks.append("\n".join(collected))

    return blocks


def test_the_payload_scanner_sees_the_real_call_sites():
    """الماسح نفسه يحتاج برهاناً — ماسح لا يجد شيئاً يمرّ دائماً."""
    source = (ROOT / "notifications" / "tasks.py").read_text(encoding="utf-8")
    blocks = _dlq_call_blocks(source)

    assert len(blocks) >= 2
    assert any('"email"' in block for block in blocks)
    assert any('"sms"' in block for block in blocks)
    assert all("student_id" in block for block in blocks)


# ══════════════════════════════════════════════════════════════════
# النموذج
# ══════════════════════════════════════════════════════════════════


def test_school_is_required_on_the_model():
    """صفّ بلا مدرسة لا يمكن نسبته لمستأجر، فلا يُسمح بوجوده."""
    field = DeadLetterMessage._meta.get_field("school")

    assert field.null is False
    assert field.related_model.__name__ == "School"
