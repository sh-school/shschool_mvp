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
from contextlib import contextmanager
from pathlib import Path

import pytest
from django.db import DatabaseError, connection, transaction

from notifications import tasks as notification_tasks
from notifications.models import DeadLetterMessage
from tests.conftest import SchoolFactory

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


# ══════════════════════════════════════════════════════════════════
# [P2-B1] العزل سلوكياً — لا تركيباً
# ══════════════════════════════════════════════════════════════════
#
# فحص وجود السياسة يُثبت أنها مُركَّبة، لا أنها تمنع.
#
# وتشغيلها يصطدم بعقبتين، كلتاهما أسقطت المحاولة الأولى في CI:
#
# 1) الدور. قاعدة الاختبار تتصل بـPOSTGRES_USER وهو **superuser**.
#    وFORCE ROW LEVEL SECURITY يُخضع مالك الجدول ولا يُخضع superuser ولا
#    BYPASSRLS — فكانت الاختبارات ستمرّ بلا أن تمارس السياسة إطلاقاً.
#    الحلّ: دور فعلي غير متميّز يُنشأ في الاختبار ونتحوّل إليه بـSET ROLE.
#
# 2) الترتيب. ALTER TABLE بعد INSERT في المعاملة نفسها يصطدم بمشغّلات
#    المفاتيح الأجنبية المؤجّلة: "cannot ALTER TABLE ... pending trigger
#    events". فكل DDL يسبق أي DML.

RLS_TEST_ROLE = "dlq_rls_probe"


@contextmanager
def _rls_enforced_as(school_id):
    """
    يُمارس السياسة بدور غير متميّز — لا بمالك القاعدة.

    SET ROLE يُغيّر current_user فتُطبَّق السياسة، بينما session_user يبقى
    المالك؛ ولهذا يُربط الاثنان في جدول الربط: app_rls_school() تقرأ
    session_user، وقرار تطبيق السياسة يقوم على current_user.
    """
    with connection.cursor() as cursor:
        # DDL أولاً: أي DML قبله يترك مشغّلات مؤجّلة تمنع ALTER TABLE.
        cursor.execute(
            f"""
            DO $$
            BEGIN
                CREATE ROLE {RLS_TEST_ROLE} NOSUPERUSER NOBYPASSRLS NOINHERIT;
            EXCEPTION WHEN duplicate_object THEN
                -- الأدوار على مستوى العنقود لا القاعدة، وعمّال xdist يتشاركونه.
                NULL;
            END $$;
            """
        )
        cursor.execute(f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{TABLE} TO {RLS_TEST_ROLE}")
        cursor.execute(f"GRANT SELECT ON public.app_rls_role_school TO {RLS_TEST_ROLE}")
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_TEST_ROLE}")
        cursor.execute(
            """
            INSERT INTO public.app_rls_role_school (db_role, school_id)
            VALUES (session_user, %s)
            ON CONFLICT (db_role) DO UPDATE SET school_id = EXCLUDED.school_id
            """,
            [str(school_id)],
        )
        cursor.execute(f"SET ROLE {RLS_TEST_ROLE}")

    try:
        yield
    finally:
        with connection.cursor() as cursor:
            cursor.execute("RESET ROLE")


def _make_row(school, kind="email"):
    return DeadLetterMessage.objects.create(
        school=school,
        kind=kind,
        payload={"student_id": None, "notif_type": "custom", "sent_by_id": None},
        error="تعذر الإرسال.",
    )


@pytest.mark.django_db
def test_own_school_rows_are_visible():
    """[P2-B1] الوصول المشروع يعمل — وإلا كان العزل تعطيلاً لا حماية."""
    _skip_unless_postgres()

    own = SchoolFactory()
    row = _make_row(own)

    with _rls_enforced_as(own.id):
        visible = list(DeadLetterMessage.objects.values_list("id", flat=True))

    assert row.id in visible


@pytest.mark.django_db
def test_foreign_school_rows_are_invisible():
    """[P2-B1] هذا ما كان مكشوفاً قبل الترحيل: صفوف مدرسة أخرى."""
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    victim_row = _make_row(victim)
    own_row = _make_row(own)

    with _rls_enforced_as(own.id):
        visible = set(DeadLetterMessage.objects.values_list("id", flat=True))

    assert own_row.id in visible
    assert victim_row.id not in visible


@pytest.mark.django_db
def test_writing_into_a_foreign_school_is_rejected():
    """[P2-B1] WITH CHECK يمنع الكتابة عبر المستأجرين لا القراءة فقط."""
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()

    with _rls_enforced_as(own.id):
        # انتهاك WITH CHECK هو SQLSTATE 42501، وربطه بصنف بعينه هشّ عبر
        # إصدارات psycopg — نُمسك DatabaseError ونؤكّد على الرسالة نفسها.
        with pytest.raises(DatabaseError) as exc:
            with transaction.atomic():
                _make_row(victim)

    assert "row-level security" in str(exc.value).lower()


# ══════════════════════════════════════════════════════════════════
# [P2-B2] حقل error آمن بحكم العقد لا بحكم عادة المُستدعين
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize(
    ("raw", "leaked"),
    [
        ("SMTP refused for parent@school.qa", "parent@school.qa"),
        ("Twilio: invalid number +97455512345", "97455512345"),
        ("push endpoint https://fcm.googleapis.com/fcm/send/xyz gone", "fcm.googleapis.com"),
    ],
)
def test_error_text_is_scrubbed_before_storage(raw, leaked):
    """
    نصّ الاستثناء مسار تسريب مثل الـpayload.

    الخدمات اليوم تُرجع رسائل عامة، لكن `_to_dlq` تقبل أي استثناء من أي مُستدعٍ
    مستقبلي — ورسائل مزوّدي البريد وTwilio تحمل العنوان أو الرقم الذي فشل.
    """
    assert leaked not in notification_tasks._safe_error(raw)


def test_error_scrubbing_keeps_the_diagnosis():
    """التنقية تُزيل الهوية لا المعنى — وإلا صار الحقل بلا فائدة."""
    scrubbed = notification_tasks._safe_error("SMTP refused for parent@school.qa")

    assert "SMTP" in scrubbed
    assert "refused" in scrubbed
    assert "<email>" in scrubbed


def test_error_is_stored_through_the_scrubber():
    """الحارس يفشل لو عاد أحدهم إلى str(error) مباشرةً."""
    source = (ROOT / "notifications" / "tasks.py").read_text(encoding="utf-8")

    assert "error=_safe_error(error)" in source
    assert "error=str(error)" not in source
