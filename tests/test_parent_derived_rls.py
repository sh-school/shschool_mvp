"""
tests/test_parent_derived_rls.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[RLS-PRE0] العزل مشتقّاً من الأب — سلوكاً في PostgreSQL لا إعلاناً في الكود.

عشرون جدولاً تحمل بيانات مستأجِر بلا عمود `school_id`، فلا يمكن لسياسة أن
تُسنِدها إلى عمود. مصدر المدرسة فيها هو الأب: البرنامج من الحافلة، والتقييم من
الزيارة، والقاعة من جلسة الامتحان. أضفنا سياسات تقرأ الأب بدل أن نضيف عشرين
نسخة ثانية من `school_id` يمكن أن تنحرف عنه.

وهنا فحصان مختلفان قصداً:

  الاستبطان   — كل جدول يجب أن يحمل RLS وسياسة فعليّة في `pg_class`/`pg_policies`.
                 هذا يُثبت أن الترحيل وصل القاعدة، لا أن السياسة تمنع.
  السلوك      — دور غير متميّز يرى صفوفه ولا يرى غيرها ولا يستطيع كتابتها.
                 هذا وحده يُثبت المنع.

الحارس الساكن (tests/test_tenant_surface_coverage.py) يُثبت أن التصميم معلَن؛
هذا الملفّ يُثبت أن المحرّك نفّذه. لا يُغني أحدهما عن الآخر: سياسة مكتوبة في
ترحيل لم يُطبَّق تمرّ في الأول وتسقط هنا.
"""

import os
from contextlib import contextmanager

import pytest
from django.db import DatabaseError, connection, transaction

from core.tenancy import PARENT_DERIVED, policy_required_tables
from tests.conftest import SchoolBusFactory, SchoolFactory, UserFactory

#: الأدوار على مستوى العنقود لا القاعدة، وعمّال xdist يتشاركونه.
RLS_TEST_ROLE = "pre0_rls_probe_" + os.environ.get("PYTEST_XDIST_WORKER", "solo")


def _skip_unless_postgres():
    if connection.vendor != "postgresql":
        pytest.skip("PostgreSQL-specific RLS contract")


# ══════════════════════════════════════════════════════════════════
# الاستبطان — السياسة موجودة فعلاً في القاعدة
# ══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
@pytest.mark.parametrize("table", sorted(policy_required_tables()))
def test_every_tenant_table_is_row_level_secured(table):
    """
    [RLS-PRE0] لا جدول مستأجِر بلا RLS وسياسة.

    يشمل الجداول التي تحمل `school_id` والعشرين المشتقّة معاً. جدول جديد
    يحمل العمود ويُنشأ بعد 0037 لن تلتقطه مطابقة ماضية — وهذا الفحص يقوله
    فوراً بدل أن يُكتشف في تدقيق بعد أشهر.
    """
    _skip_unless_postgres()

    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relrowsecurity FROM pg_class WHERE oid = to_regclass(%s)",
            [f"public.{table}"],
        )
        row = cursor.fetchone()
        assert row is not None, f"{table}: الجدول غير موجود في القاعدة"
        assert row[0] is True, (
            f"{table}: RLS غير مُفعّل. إن كان الجدول جديداً فالسبب أن مطابقة "
            f"0037 وقعت قبل إنشائه — وهي لا تُعاد. أضف ترحيلاً في تطبيق الجدول "
            f"يُفعّل RLS ويُنشئ سياسة school_isolation، ويعتمد صراحةً على "
            f"core/0037."
        )

        cursor.execute(
            """
            SELECT qual, with_check
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = %s
              AND policyname = 'school_isolation'
            """,
            [table],
        )
        policy = cursor.fetchone()

    assert policy is not None, f"{table}: سياسة school_isolation مفقودة"

    qual, with_check = policy
    assert qual and "app_rls_school" in qual, f"{table}: USING لا يقرأ هوية المستأجر"
    assert (
        with_check and "app_rls_school" in with_check
    ), f"{table}: WITH CHECK لا يقرأ هوية المستأجر — القراءة محميّة والكتابة ليست"


@pytest.mark.django_db
@pytest.mark.parametrize("table", sorted(PARENT_DERIVED))
def test_derived_policies_reference_a_parent_table(table):
    """
    السياسة المشتقّة يجب أن تقرأ أباً، لا أن تكون نسخة من الشكل المعتاد.

    مُسنَد يقول `school_id = app_rls_school()` على جدول بلا عمود `school_id`
    لا يُنشأ أصلاً — لكن مُسنَداً يقول `true` يُنشأ ويمرّ فحص الوجود. وجود
    `EXISTS` هو الفرق بين سياسة تحرس وسياسة تُزيّن.
    """
    _skip_unless_postgres()

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT qual, with_check
            FROM pg_policies
            WHERE schemaname = 'public'
              AND tablename = %s
              AND policyname = 'school_isolation'
            """,
            [table],
        )
        qual, with_check = cursor.fetchone()

    assert "EXISTS" in qual.upper()
    assert "EXISTS" in with_check.upper()


# ══════════════════════════════════════════════════════════════════
# السلوك — دور غير متميّز
# ══════════════════════════════════════════════════════════════════
#
# قاعدة الاختبار تتصل بـPOSTGRES_USER وهو superuser، وRLS لا يُخضع superuser
# ولا BYPASSRLS. فحصٌ يعمل بذلك الدور يمرّ بلا أن يمارس السياسة إطلاقاً.
#
# ونقطة تخصّ هذه الجداول تحديداً: مُسنَد السياسة يقرأ جدول الأب، ويُنفَّذ
# بصلاحيات الدور الحالي. فبلا SELECT على الأب يفشل الاستعلام بـ"permission
# denied" — وهو رفض حقيقي لكنه ليس الرفض الذي نختبره. لذلك يُمنَح الأب
# صراحةً، ويبقى الرفض منسوباً إلى السياسة وحدها.


@contextmanager
def _rls_enforced_as(school_id, readable=(), writable=()):
    """يُنشئ دوراً غير متميّز مربوطاً بمدرسة، ويتحوّل إليه."""
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
        cursor.execute(f"GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO {RLS_TEST_ROLE}")

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
    """الرفض يجب أن يكون 42501 — لا أي خطأ يصادف أنه خطأ."""
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


# ── الشكل الأول: أب واحد ─────────────────────────────────────────────────────

BUS_ROUTE_TABLES = ("core_busroute", "core_schoolbus")


def _make_route(school, area="منطقة"):
    from transport.models import BusRoute

    bus = SchoolBusFactory(school=school)
    return BusRoute.objects.create(bus=bus, area_name=area)


@pytest.mark.django_db
def test_own_route_is_visible():
    """الوصول المشروع يعمل — وإلا كان العزل تعطيلاً لا حماية."""
    _skip_unless_postgres()

    own = SchoolFactory()
    route = _make_route(own)

    with _rls_enforced_as(own.id, readable=BUS_ROUTE_TABLES):
        assert route.id in _visible_ids("core_busroute")


@pytest.mark.django_db
def test_foreign_route_is_invisible():
    """[RLS-PRE0] هذا ما كان مكشوفاً: مسارات حافلات مدرسة أخرى."""
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    foreign_route = _make_route(victim)

    with _rls_enforced_as(own.id, readable=BUS_ROUTE_TABLES):
        assert foreign_route.id not in _visible_ids("core_busroute")


@pytest.mark.django_db
def test_own_route_insert_succeeds_under_the_restricted_role():
    """
    نُثبت القدرة على الكتابة المشروعة أولاً.

    بلا هذا يصير رفض الصفّ الأجنبي بلا دلالة: قد ينجح لأن الدور لا يملك
    INSERT أصلاً.
    """
    _skip_unless_postgres()

    own = SchoolFactory()
    bus = SchoolBusFactory(school=own)

    with _rls_enforced_as(own.id, readable=("core_schoolbus",), writable=("core_busroute",)):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.core_busroute (id, bus_id, area_name) "
                "VALUES (gen_random_uuid(), %s, %s)",
                [str(bus.id), "منطقة مشروعة"],
            )


@pytest.mark.django_db
def test_route_on_a_foreign_bus_is_rejected():
    """الكتابة عبر الحدّ ترفضها WITH CHECK، لا المفتاح الأجنبي."""
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    foreign_bus = SchoolBusFactory(school=victim)

    with _rls_enforced_as(own.id, readable=("core_schoolbus",), writable=("core_busroute",)):
        _assert_rejected_by_rls(
            "INSERT INTO public.core_busroute (id, bus_id, area_name) "
            "VALUES (gen_random_uuid(), %s, %s)",
            [str(foreign_bus.id), "منطقة أجنبية"],
        )


# ── الشكل الثاني: قفزتان عبر جدول ربط M2M ────────────────────────────────────


@pytest.mark.django_db
def test_foreign_route_membership_is_rejected():
    """
    [RLS-PRE0] جدول الربط الآلي كان الفجوة التي لا يراها جرد النماذج.

    `core_busroute_students` يُنشئه Django لـ`BusRoute.students`، ولا يظهر في
    `apps.get_models()` افتراضياً. قبل الترحيل لم يكن شيء يمنع ربط مسار مدرسة
    بطالب مدرسة أخرى — والمفتاحان الأجنبيان لا يمنعانه لأن فحص السلامة
    المرجعية يجري خارج RLS.
    """
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    foreign_route = _make_route(victim)
    student = UserFactory()

    with _rls_enforced_as(
        own.id,
        readable=("core_busroute", "core_schoolbus"),
        writable=("core_busroute_students",),
    ):
        _assert_rejected_by_rls(
            "INSERT INTO public.core_busroute_students (busroute_id, customuser_id) "
            "VALUES (%s, %s)",
            [str(foreign_route.id), str(student.id)],
        )


@pytest.mark.django_db
def test_own_route_membership_succeeds():
    """القفزتان تعملان في الاتجاه المشروع أيضاً."""
    _skip_unless_postgres()

    own = SchoolFactory()
    route = _make_route(own)
    student = UserFactory()

    with _rls_enforced_as(
        own.id,
        readable=("core_busroute", "core_schoolbus"),
        writable=("core_busroute_students",),
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.core_busroute_students "
                "(busroute_id, customuser_id) VALUES (%s, %s)",
                [str(route.id), str(student.id)],
            )


# ── الشكل الثالث: علاقتا استئجار في صفّ واحد ─────────────────────────────────

OBSERVATION_TABLES = (
    "quality_classroomobservation",
    "quality_observationcriterion",
)


def _make_observation(school):
    from quality.observation_models import ClassroomObservation

    return ClassroomObservation.objects.create(
        school=school,
        teacher=UserFactory(),
        observer=UserFactory(),
    )


def _make_criterion(school, text):
    from quality.observation_models import ObservationCriterion

    return ObservationCriterion.objects.create(school=school, domain="planning", text=text)


@pytest.mark.django_db
def test_own_observation_score_succeeds():
    """الزيارة والمعيار من المدرسة نفسها — الحالة المشروعة."""
    _skip_unless_postgres()

    own = SchoolFactory()
    observation = _make_observation(own)
    criterion = _make_criterion(own, "معيار داخلي")

    with _rls_enforced_as(
        own.id,
        readable=OBSERVATION_TABLES,
        writable=("quality_observationscore",),
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.quality_observationscore "
                "(id, observation_id, criterion_id, rating, recommendation, "
                " created_at, updated_at) "
                "VALUES (gen_random_uuid(), %s, %s, '', '', now(), now())",
                [str(observation.id), str(criterion.id)],
            )


@pytest.mark.django_db
def test_score_pairing_a_foreign_criterion_is_rejected():
    """
    [RLS-PRE0] الاتساق بين العلاقات — لا ملكية الصفّ وحدها.

    الزيارة من مدرستنا فتمرّ USING، لكن المعيار من مدرسة أخرى. سياسة تفحص
    الأب الأول فقط كانت ستقبل هذا الصفّ: تقييم لزيارتنا مُسنَد إلى معيار
    مدرسة أخرى. ولا مفتاح أجنبي يمنعه — PostgreSQL يُجري فحص السلامة
    المرجعية خارج RLS، فالمفتاح يُستوفى في الحالتين.
    """
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    observation = _make_observation(own)
    foreign_criterion = _make_criterion(victim, "معيار مدرسة أخرى")

    with _rls_enforced_as(
        own.id,
        readable=OBSERVATION_TABLES,
        writable=("quality_observationscore",),
    ):
        _assert_rejected_by_rls(
            "INSERT INTO public.quality_observationscore "
            "(id, observation_id, criterion_id, rating, recommendation, "
            " created_at, updated_at) "
            "VALUES (gen_random_uuid(), %s, %s, '', '', now(), now())",
            [str(observation.id), str(foreign_criterion.id)],
        )


@pytest.mark.django_db
def test_foreign_observation_score_is_invisible():
    """تقييمات زيارة مدرسة أخرى لا تُقرأ."""
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    observation = _make_observation(victim)
    criterion = _make_criterion(victim, "معيار الضحيّة")

    from quality.observation_models import ObservationScore

    foreign_score = ObservationScore.objects.create(
        observation=observation, criterion=criterion, rating="", recommendation=""
    )

    with _rls_enforced_as(
        own.id,
        readable=OBSERVATION_TABLES + ("quality_observationscore",),
    ):
        assert foreign_score.id not in _visible_ids("quality_observationscore")
