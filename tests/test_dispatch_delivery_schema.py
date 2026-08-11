"""
tests/test_dispatch_delivery_schema.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[B4-0] البنية الخامدة — القيود وحدها، فلا كاتب بعد.

لا شيء يكتب في `NotificationDispatch` ولا `NotificationDelivery` في هذه المرحلة،
فلا سلوك تشغيلياً يُختبَر. المُختبَر هو ما ستعتمد عليه الكتابة لاحقاً: هل تمنع
قاعدة البيانات فعلاً ما اتّفقنا أنه ممنوع؟

وثلاثة من هذه القيود لا يعرفها Django — مفاتيح مركّبة مكتوبة بـ`RunSQL` — أي أن
لا شيء في طبقة النماذج يحرسها. اختبار يمارسها على PostgreSQL هو الطريقة الوحيدة
لمعرفة أنها وصلت.
"""

import os
from contextlib import contextmanager

import pytest
from django.db import DatabaseError, IntegrityError, connection, transaction

from notifications.models import (
    DeadLetterMessage,
    NotificationDelivery,
    NotificationDispatch,
    NotificationLog,
)
from tests.conftest import SchoolFactory, UserFactory

# لا pytestmark عام: حارسا المصدر يعملان بلا قاعدة بيانات، وفرضُ django_db
# عليهما يجعل جزءاً من الحراسة غير قابل للتشغيل حيث لا قاعدة — وحارس لا
# يعمل ليس حارساً.

RLS_TEST_ROLE = "b40_rls_probe_" + os.environ.get("PYTEST_XDIST_WORKER", "solo")

DISPATCH_TABLE = "notifications_notificationdispatch"
DELIVERY_TABLE = "notifications_notificationdelivery"


def _skip_unless_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL-specific schema contract")


def _dispatch(school, **kwargs):
    return NotificationDispatch.objects.create(
        school=school, event_type=kwargs.pop("event_type", "absence_alert"), **kwargs
    )


def _delivery(dispatch, recipient, channel="email", school=None):
    return NotificationDelivery.objects.create(
        dispatch=dispatch,
        school=school or dispatch.school,
        recipient=recipient,
        channel=channel,
    )


@contextmanager
def _expect_integrity_error():
    """قيد قاعدة البيانات يُنقض — داخل savepoint كي تنجو المعاملة."""
    with pytest.raises(IntegrityError), transaction.atomic():
        yield


# ══════════════════════════════════════════════════════════════════
# الحالة المشروعة
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_a_dispatch_and_a_matching_delivery_are_accepted():
    """البنية تعمل في الاتجاه الصحيح — وإلا كانت القيود تعطيلاً لا حماية."""
    school = SchoolFactory()
    dispatch = _dispatch(school)
    delivery = _delivery(dispatch, UserFactory())

    assert delivery.school_id == dispatch.school_id
    assert delivery.status == "pending"
    assert dispatch.deliveries.count() == 1


@pytest.mark.django_db
def test_the_same_dispatch_may_reach_one_user_on_several_channels():
    """القيد على الثلاثية لا على الزوج — قناتان لنفس الشخص تسليمان."""
    school = SchoolFactory()
    dispatch = _dispatch(school)
    recipient = UserFactory()

    _delivery(dispatch, recipient, channel="email")
    _delivery(dispatch, recipient, channel="sms")

    assert dispatch.deliveries.count() == 2


@pytest.mark.django_db
def test_two_dispatches_may_repeat_the_same_business_object():
    """
    [B4-A] `related_object_id` سياق لا هوية.

    تذكير الغد لنفس الإجراء واقعة جديدة مقصودة. قيدُ فرادة عليه كان سيمنع
    إشعاراً مشروعاً — ولهذا لا قيد على الواقعة إطلاقاً.
    """
    school = SchoolFactory()

    _dispatch(school, event_type="deadline_reminder", related_object_id="proc-1")
    _dispatch(school, event_type="deadline_reminder", related_object_id="proc-1")

    assert NotificationDispatch.objects.count() == 2


# ══════════════════════════════════════════════════════════════════
# هوية التسليم
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_a_duplicate_delivery_is_rejected():
    """
    [B4-A] `(dispatch, recipient, channel)` هوية التسليم.

    بدونها لا يمكن تمييز إعادة الإرسال عن إرسال جديد: تسليمان متطابقان
    لواقعة واحدة لا يفرّق بينهما شيء.
    """
    school = SchoolFactory()
    dispatch = _dispatch(school)
    recipient = UserFactory()
    _delivery(dispatch, recipient, channel="email")

    with _expect_integrity_error():
        _delivery(dispatch, recipient, channel="email")


@pytest.mark.django_db
def test_the_identity_does_not_promise_exactly_once():
    """
    القيد يمنع تسليمين، لا محاولتين على تسليم واحد.

    هذا توثيق تنفيذي لا تجميل: عاملٌ يموت بعد قبول المزوّد وقبل الكتابة يُعيد
    الإرسال، والقيد لا يراه لأننا داخل التسليم نفسه. الضمان at-least-once.
    """
    school = SchoolFactory()
    dispatch = _dispatch(school)
    delivery = _delivery(dispatch, UserFactory())

    first = NotificationLog.objects.create(
        school=school, delivery=delivery, recipient="a@example.com", channel="email"
    )
    second = NotificationLog.objects.create(
        school=school, delivery=delivery, recipient="a@example.com", channel="email"
    )

    assert first.id != second.id
    assert delivery.attempts.count() == 2


# ══════════════════════════════════════════════════════════════════
# اتساق المستأجر — المفاتيح المركّبة
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_a_delivery_may_not_carry_a_school_other_than_its_dispatch():
    """
    [B4-0] النسخة المكرّرة لا يُسمح لها بالانحراف.

    `school_id` مكرَّر على التسليم لأن الشاشات تستعلم به مباشرةً. وهذا يعني
    مصدرَي حقيقة — والمفتاح المركّب هو ما يجعل اختلافهما مستحيلاً بدل أن
    يكون مجرّد شيء لا يفعله التطبيق.
    """
    _skip_unless_postgres()

    school = SchoolFactory()
    other = SchoolFactory()
    dispatch = _dispatch(school)

    with _expect_integrity_error():
        _delivery(dispatch, UserFactory(), school=other)


@pytest.mark.django_db
def test_an_attempt_may_not_point_at_a_delivery_from_another_school():
    """محاولة مدرسةٍ لا تُنسب إلى تسليم مدرسة أخرى."""
    _skip_unless_postgres()

    school = SchoolFactory()
    other = SchoolFactory()
    foreign_delivery = _delivery(_dispatch(other), UserFactory())

    with _expect_integrity_error():
        NotificationLog.objects.create(
            school=school,
            delivery=foreign_delivery,
            recipient="a@example.com",
            channel="email",
        )


@pytest.mark.django_db
def test_a_dead_letter_may_not_point_at_a_delivery_from_another_school():
    """وشهادة فشل مدرسةٍ لا تُنسب إلى تسليم مدرسة أخرى."""
    _skip_unless_postgres()

    school = SchoolFactory()
    other = SchoolFactory()
    foreign_delivery = _delivery(_dispatch(other), UserFactory())

    with _expect_integrity_error():
        DeadLetterMessage.objects.create(
            school=school, delivery=foreign_delivery, kind="email", payload={}
        )


@pytest.mark.django_db
@pytest.mark.parametrize(
    "constraint",
    [
        "delivery_tenant_matches_dispatch",
        "notificationlog_tenant_matches_delivery",
        "dlq_tenant_matches_delivery",
    ],
)
def test_the_composite_constraints_exist_in_the_database(constraint):
    """
    Django لا يرى قيود `RunSQL`، فلا شيء في طبقة النماذج يُخبرنا أنها وصلت.

    وفحص السلوك وحده قد يمرّ لسبب آخر — قيد فرادة، أو مفتاح أجنبي عادي —
    فيُثبت المنع بلا أن يُثبت أن الآلية التي قصدناها هي التي منعت.
    """
    _skip_unless_postgres()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT contype
            FROM pg_constraint
            WHERE conname = %s
            """,
            [constraint],
        )
        row = cursor.fetchone()

    assert row is not None, f"{constraint}: القيد المركّب غير موجود"
    assert row[0] == "f", f"{constraint}: ليس مفتاحاً أجنبياً"


# ══════════════════════════════════════════════════════════════════
# الصفوف السابقة للخطّ
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_an_attempt_without_a_delivery_is_still_valid():
    """
    [B4-0] `delivery IS NULL` تعني "سابق للخطّ" — لا صفّاً معطوباً.

    والمفتاح المركّب بدلالة MATCH SIMPLE يقبله: عمودٌ فارغ يُسقط الفحص. ولا
    backfill: اختلاق واقعة إطلاق لم نشهدها هو ما نتجنّبه لا ما ننقصه.
    """
    school = SchoolFactory()

    log = NotificationLog.objects.create(school=school, recipient="a@example.com", channel="email")

    assert log.delivery_id is None


@pytest.mark.django_db
def test_a_dead_letter_without_a_delivery_is_still_valid():
    school = SchoolFactory()

    row = DeadLetterMessage.objects.create(school=school, kind="email", payload={})

    assert row.delivery_id is None


@pytest.mark.django_db
def test_many_legacy_rows_may_all_have_no_delivery():
    """`unique=True` على مفتاح قابل للفراغ لا يمنع تعدّد الفراغات في PostgreSQL."""
    school = SchoolFactory()

    DeadLetterMessage.objects.create(school=school, kind="email", payload={})
    DeadLetterMessage.objects.create(school=school, kind="sms", payload={})

    assert DeadLetterMessage.objects.filter(delivery__isnull=True).count() == 2


# ══════════════════════════════════════════════════════════════════
# الدليل لا يُمحى
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_a_delivery_carries_at_most_one_dead_letter():
    """تسليم واحد ⇒ شهادة فشل واحدة. صفّان لنفس الفشل يجعلان العدّ كذباً."""
    school = SchoolFactory()
    delivery = _delivery(_dispatch(school), UserFactory())
    DeadLetterMessage.objects.create(school=school, delivery=delivery, kind="email", payload={})

    with _expect_integrity_error():
        DeadLetterMessage.objects.create(school=school, delivery=delivery, kind="sms", payload={})


@pytest.mark.django_db
def test_deleting_a_delivery_that_has_attempts_is_refused():
    """
    [B4-0] `PROTECT` لا `CASCADE`.

    السجلّ صار دليلاً على محاولة جرت. حذف التسليم يجب ألّا يمحو تاريخ ما حدث،
    وإخفاء الهوية لاحقاً — إن لزم — سياسةُ احتفاظ صريحة لا أثرٌ جانبي للحذف.
    """
    from django.db.models import ProtectedError

    school = SchoolFactory()
    delivery = _delivery(_dispatch(school), UserFactory())
    NotificationLog.objects.create(
        school=school, delivery=delivery, recipient="a@example.com", channel="email"
    )

    with pytest.raises(ProtectedError), transaction.atomic():
        delivery.delete()


@pytest.mark.django_db
def test_deleting_a_delivery_that_has_a_dead_letter_is_refused():
    from django.db.models import ProtectedError

    school = SchoolFactory()
    delivery = _delivery(_dispatch(school), UserFactory())
    DeadLetterMessage.objects.create(school=school, delivery=delivery, kind="email", payload={})

    with pytest.raises(ProtectedError), transaction.atomic():
        delivery.delete()


@pytest.mark.django_db
def test_deleting_a_recipient_that_has_a_delivery_is_refused():
    """حذف مستخدم لا يمحو سجلّ تشغيل الإشعارات."""
    from django.db.models import ProtectedError

    school = SchoolFactory()
    recipient = UserFactory()
    _delivery(_dispatch(school), recipient)

    with pytest.raises(ProtectedError), transaction.atomic():
        recipient.delete()


# ══════════════════════════════════════════════════════════════════
# العزل — سلوكياً بدور غير متميّز
# ══════════════════════════════════════════════════════════════════


@contextmanager
def _rls_enforced_as(school_id, readable=(), writable=()):
    with connection.cursor() as cursor:
        cursor.execute(
            f"""
            DO $$
            BEGIN
                CREATE ROLE {RLS_TEST_ROLE} NOSUPERUSER NOBYPASSRLS NOINHERIT;
            EXCEPTION WHEN duplicate_object THEN
                NULL;
            END $$;
            """
        )
        cursor.execute(f"GRANT USAGE ON SCHEMA public TO {RLS_TEST_ROLE}")
        cursor.execute(f"GRANT SELECT ON public.app_rls_role_school TO {RLS_TEST_ROLE}")

        for table in readable:
            cursor.execute(f"GRANT SELECT ON public.{table} TO {RLS_TEST_ROLE}")
        for table in writable:
            cursor.execute(f"GRANT SELECT, INSERT ON public.{table} TO {RLS_TEST_ROLE}")

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


def _assert_rejected_by_rls(statement, params):
    with pytest.raises(DatabaseError) as caught:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute(statement, params)

    cause = caught.value.__cause__
    assert getattr(cause, "pgcode", None) == "42501", f"رُفض لسبب آخر: {caught.value}"


def _visible_ids(table):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT id FROM public.{table}")
        return {row[0] for row in cursor.fetchall()}


@pytest.mark.django_db
def test_own_dispatch_is_visible_and_foreign_is_not():
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    mine = _dispatch(own)
    theirs = _dispatch(victim)

    with _rls_enforced_as(own.id, readable=(DISPATCH_TABLE,)):
        visible = _visible_ids(DISPATCH_TABLE)

    assert mine.id in visible
    assert theirs.id not in visible


@pytest.mark.django_db
def test_own_delivery_is_visible_and_foreign_is_not():
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    mine = _delivery(_dispatch(own), UserFactory())
    theirs = _delivery(_dispatch(victim), UserFactory())

    with _rls_enforced_as(own.id, readable=(DELIVERY_TABLE,)):
        visible = _visible_ids(DELIVERY_TABLE)

    assert mine.id in visible
    assert theirs.id not in visible


@pytest.mark.django_db
def test_writing_a_dispatch_for_our_school_succeeds_under_the_restricted_role():
    """
    نُثبت القدرة على الكتابة المشروعة أولاً.

    بلا ذلك يصير رفض الصفّ الأجنبي بلا دلالة: قد ينجح لأن الدور لا يملك
    INSERT أصلاً.
    """
    _skip_unless_postgres()

    own = SchoolFactory()

    with _rls_enforced_as(own.id, writable=(DISPATCH_TABLE,)):
        with connection.cursor() as cursor:
            cursor.execute(
                f"INSERT INTO public.{DISPATCH_TABLE} "
                "(id, school_id, event_type, related_object_id, related_url, created_at) "
                "VALUES (gen_random_uuid(), %s, 'absence_alert', '', '', now())",
                [str(own.id)],
            )


@pytest.mark.django_db
def test_writing_a_dispatch_for_another_school_is_rejected():
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()

    with _rls_enforced_as(own.id, writable=(DISPATCH_TABLE,)):
        _assert_rejected_by_rls(
            f"INSERT INTO public.{DISPATCH_TABLE} "
            "(id, school_id, event_type, related_object_id, related_url, created_at) "
            "VALUES (gen_random_uuid(), %s, 'absence_alert', '', '', now())",
            [str(victim.id)],
        )


@pytest.mark.django_db
def test_writing_a_delivery_for_another_school_is_rejected():
    """
    الرفض من السياسة لا من المفتاح المركّب.

    الواقعة والتسليم كلاهما لمدرسة الضحيّة، فالمفتاح المركّب مُستوفى تماماً —
    وحده العزل يمنع. ولولا ذلك لمرّ الاختبار وهو يقيس شيئاً آخر.
    """
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    foreign_dispatch = _dispatch(victim)
    recipient = UserFactory()

    with _rls_enforced_as(own.id, writable=(DELIVERY_TABLE,)):
        _assert_rejected_by_rls(
            f"INSERT INTO public.{DELIVERY_TABLE} "
            "(id, dispatch_id, school_id, recipient_id, channel, status, created_at) "
            "VALUES (gen_random_uuid(), %s, %s, %s, 'email', 'pending', now())",
            [str(foreign_dispatch.id), str(victim.id), str(recipient.id)],
        )


# ══════════════════════════════════════════════════════════════════
# النموذج
# ══════════════════════════════════════════════════════════════════


def test_delivery_channels_exclude_in_app():
    """
    `InAppNotification` هي الكيان المُرسَل والمخزَّن، لا تسليم خارجي.

    إدخالها كان سيُنتج صفّ Delivery بحالة `sent` دائماً بجانب الإشعار نفسه —
    تمثيلان لعملية قاعدة بيانات واحدة.
    """
    codes = {code for code, _ in NotificationDelivery.CHANNEL}

    assert codes == {"email", "sms", "whatsapp", "push"}


def test_delivery_statuses_do_not_yet_include_unknown():
    """
    [B4-0] `unknown_outcome` تنتظر الاستئجار في B4-3.

    حالة لا يُنتجها انتقال هي دلالة ميتة، وإضافتها الآن تدّعي أننا نميّز
    النتيجة المجهولة ونحن لا نملك بعد ما يكتشفها.
    """
    codes = {code for code, _ in NotificationDelivery.STATUS}

    assert "unknown_outcome" not in codes
    assert codes == {"pending", "in_progress", "sent", "retry_wait", "dead_lettered"}


DORMANT_MODELS = ("NotificationDispatch", "NotificationDelivery")

SKIPPED_DIRS = {
    ".venv",
    ".git",
    ".claude",
    "migrations",
    "tests",
    "staticfiles",
    "htmlcov",
    "_archive",
    "node_modules",
    "__pycache__",
}


def _application_sources():
    """كل ملفّ Python في شيفرة التطبيق — لا الترحيلات ولا الاختبارات."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]

    for path in root.rglob("*.py"):
        if SKIPPED_DIRS & set(path.relative_to(root).parts):
            continue
        yield path, path.read_text(encoding="utf-8")


#: أنماط الإنشاء وحدها. القراءة ليست كتابة — و[B4-1] يقرأ هذه الجداول عمداً
#: ليمرّر التسليم إلى مهمّته، فحارسٌ يمنع كل استعمال كان سيمنع الاستهلاك نفسه
#: الذي بُني من أجله الإصدار.
CREATION_PATTERNS = (
    ".objects.create(",
    ".objects.get_or_create(",
    ".objects.update_or_create(",
    ".objects.bulk_create(",
)


#: [B4-2B] الكاتب الوحيد المسموح له. تُرقّي هذه القاعدة حظر B4-0 المطلق ولا
#: تُلغيه: كان "لا كاتب إطلاقاً" لأن البنية خامدة، فصار "موضع واحد مسمّى" خلف
#: راية مُطفأة افتراضياً.
TRACKED_WRITER = ("notifications/hub.py", "_create_dispatch")


def _writers_of(models):
    """مواضع إنشاء صفوف لهذه النماذج، مع الدالّة الحاوية لكلٍّ منها."""
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    found = []

    for path, text in _application_sources():
        # تعريف النموذج نفسه ليس كتابةً فيه.
        if path.name == "models.py" and path.parent.name == "notifications":
            continue

        try:
            tree = ast.parse(text)
        except SyntaxError:
            continue

        def _visit(node, enclosing, path=path, text=text):
            if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                enclosing = node.name

            if isinstance(node, ast.Call):
                segment = ast.get_source_segment(text, node) or ""
                for model in models:
                    if any(f"{model}{pattern}" in segment for pattern in CREATION_PATTERNS):
                        found.append(
                            (
                                str(path.relative_to(root)).replace("\\", "/"),
                                enclosing,
                                model,
                            )
                        )

            for child in ast.iter_child_nodes(node):
                _visit(child, enclosing)

        _visit(tree, None)

    return found


def test_only_the_tracked_writer_creates_a_dispatch_or_delivery():
    """
    [B4-2B] الحظر المطلق صار حصراً مسمّى.

    كان B4-0 يمنع كل كاتب لأن البنية خامدة. وقد دخل الكاتب المتتبَّع خلف راية
    مُطفأة افتراضياً، فصار المسموح موضعاً واحداً بعينه — وأي كاتب آخر يُسقط CI
    كما كان.
    """
    offenders = [
        f"{path}::{enclosing or '<module>'} → {model}"
        for path, enclosing, model in _writers_of(DORMANT_MODELS)
        if (path, enclosing) != TRACKED_WRITER
    ]

    assert not offenders, "كاتب غير مصرَّح به: " + ", ".join(offenders)


def test_the_tracked_writer_exists_where_the_exception_names_it():
    """
    استثناء يحرس موضعاً غير موجود لا يُثبت شيئاً.

    لو انتقل الكاتب إلى دالّة أخرى لبقي الحارس أخضر بينما صار الاستثناء يشير
    إلى فراغ، ومرّ الكاتب الجديد بلا حراسة.
    """
    written = {(path, enclosing) for path, enclosing, _ in _writers_of(DORMANT_MODELS)}

    assert TRACKED_WRITER in written, "الكاتب المتتبَّع ليس حيث يسمّيه الاستثناء"


def test_the_writer_scanner_reads_real_application_code():
    """
    ماسح لا يقرأ شيئاً يمرّ دائماً.

    الصيغة الأولى لهذا الحارس كانت `root.glob("*/[!m]*.py")` — تتخطّى كل ملفّ
    يبدأ بحرف m وكل ملفّ أعمق من مستوى واحد، فتُبقيه أخضر بلا أن يرى معظم
    الشيفرة. نُثبت هنا أنه يقرأ فعلاً، وأنه يكتشف نموذجاً معروفاً أن له كتّاباً.
    """
    sources = dict(_application_sources())

    assert len(sources) > 100
    assert any(path.name == "tasks.py" for path in sources)
    assert _writers_of(("NotificationLog",)), "الماسح لا يرى كتّاب NotificationLog المعروفين"


def test_the_writer_scanner_distinguishes_reading_from_creating():
    """
    الحارس يفصل القراءة عن الإنشاء.

    صيغته الأولى كانت تُمسك `Model.objects` بأي شكل، فأسقطت [B4-1] لحظة أن قرأ
    التسليمَ ليمرّره — أي أنها كانت ستمنع الاستهلاك الذي بُني الإصدار من أجله،
    لا الإنشاء الذي قصدنا منعه.
    """
    assert any(
        "NotificationDelivery.objects.filter(" in text for _, text in _application_sources()
    ), "القراءة المشروعة اختفت — الاختبار يقيس شيئاً لم يعد موجوداً"

    readers_only = [
        (path, enclosing)
        for path, enclosing, _ in _writers_of(("NotificationDelivery",))
        if (path, enclosing) != TRACKED_WRITER
    ]

    assert not readers_only, f"قراءةٌ حُسبت إنشاءً: {readers_only}"
