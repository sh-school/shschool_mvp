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


@pytest.mark.django_db
@pytest.mark.parametrize(
    "table",
    ["core_busroute_students", "core_libraryactivity_participants"],
)
def test_join_table_checks_are_stronger_than_their_using(table):
    """
    [RLS-PRE0] جدول الربط له طرفان، فـWITH CHECK يجب أن يزيد على USING.

    السياسة الأولى فحصت الأب في الاثنين معاً، فبدت خضراء بينما تترك الطرف
    الثاني مفتوحاً. هذا الفحص يُثبت بنيوياً أن مُسنَد الكتابة يسأل جدول
    العضويّات — فإن حذفه أحد يوماً سقط الاختبار بدل أن يمرّ بادعاء أوسع من
    السياسة.
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

    assert "core_membership" in with_check, f"{table}: WITH CHECK لا يفحص الطرف الثاني"
    assert "core_membership" not in qual, (
        f"{table}: USING يفحص العضويّة — وهذا يُخفي صفوفاً مشروعة انتهت عضويّة " f"صاحبها ويمنع تصحيحها"
    )


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


# ── الشكل الثاني: جدولا ربط M2M — طرفان مستأجِران ────────────────────────────
#
# جدول الربط يحمل مرجعين، وكلاهما مستأجِر. فحص الأب وحده يترك الطرف الآخر
# مفتوحاً: مسار مدرستنا يقبل طالب مدرسة أخرى.
#
# والطرف الآخر لا يُفحص بعمود — `core_customuser` بلا `school_id` لأن استئجار
# الشخص علاقة متعدّدة عبر `core_membership`. فالمُسنَد يسأل جدول العضويّات.
#
# ولهذا ثلاثية لكل جدول لا اختباران. اختبارٌ يرفض مستخدماً بلا عضويّة **ومع**
# أبٍ أجنبي لا يُثبت شيئاً عن المستخدم: الرفض منسوب إلى الأب. الحالة الوحيدة
# التي تُثبت الطرف الثاني هي **أبٌ لنا ومستخدم ليس لنا**.

JOIN_TABLE_PARENTS = ("core_busroute", "core_schoolbus", "core_membership")


def _member_of(school):
    """مستخدم يحمل عضويّة في المدرسة — لا مستخدم عشوائي."""
    from tests.conftest import MembershipFactory

    return MembershipFactory(school=school).user


@pytest.mark.django_db
def test_route_membership_for_a_member_succeeds():
    """
    الحالة المشروعة: مسارنا وطالب يحمل عضويّة عندنا.

    كان هذا الاختبار يُنشئ `UserFactory()` بلا عضويّة ويؤكّد النجاح — أي أنه
    كان يُثبت أن أيّ مستخدم في المنصّة يُقبل، وهو نقيض ما تدّعيه السياسة.
    """
    _skip_unless_postgres()

    own = SchoolFactory()
    route = _make_route(own)
    student = _member_of(own)

    with _rls_enforced_as(
        own.id,
        readable=JOIN_TABLE_PARENTS,
        writable=("core_busroute_students",),
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.core_busroute_students "
                "(busroute_id, customuser_id) VALUES (%s, %s)",
                [str(route.id), str(student.id)],
            )


@pytest.mark.django_db
def test_own_route_with_a_foreign_student_is_rejected():
    """
    [RLS-PRE0] الطرف الثاني — وهو ما كانت السياسة الأولى تتركه مفتوحاً.

    المسار مسارنا فيمرّ `USING`، والطالب يحمل عضويّة في مدرسة أخرى وحدها.
    سياسة تفحص الأب فقط كانت ستقبل الصفّ: طالب مدرسة أخرى في حافلة مدرستنا.
    ولا المفتاح الأجنبي يمنعه، لأن فحص السلامة المرجعية يجري خارج RLS.
    """
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    route = _make_route(own)
    foreign_student = _member_of(victim)

    with _rls_enforced_as(
        own.id,
        readable=JOIN_TABLE_PARENTS,
        writable=("core_busroute_students",),
    ):
        _assert_rejected_by_rls(
            "INSERT INTO public.core_busroute_students (busroute_id, customuser_id) "
            "VALUES (%s, %s)",
            [str(route.id), str(foreign_student.id)],
        )


@pytest.mark.django_db
def test_foreign_route_membership_is_rejected():
    """
    [RLS-PRE0] الطرف الأول: جدول الربط الآلي لا يراه جرد النماذج.

    `core_busroute_students` يُنشئه Django لـ`BusRoute.students`، ولا يظهر في
    `apps.get_models()` افتراضياً. المسار هنا أجنبي والطالب عضو عندنا، فالرفض
    منسوب إلى الأب وحده — وهذا ما يجعله مكمّلاً للاختبار السابق لا بديلاً عنه.
    """
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    foreign_route = _make_route(victim)
    student = _member_of(own)

    with _rls_enforced_as(
        own.id,
        readable=JOIN_TABLE_PARENTS,
        writable=("core_busroute_students",),
    ):
        _assert_rejected_by_rls(
            "INSERT INTO public.core_busroute_students (busroute_id, customuser_id) "
            "VALUES (%s, %s)",
            [str(foreign_route.id), str(student.id)],
        )


@pytest.mark.django_db
def test_a_student_of_two_schools_may_ride_in_each():
    """
    شرط العضويّة لا يكسر تعدّد المدارس.

    من يحمل عضويّتين يُقبل في كلٍّ منهما، لأن كل مدرسة تستوفي المُسنَد في
    دورها. المرفوض هو من لا عضويّة له هنا، لا من له عضويّة هناك أيضاً.
    """
    _skip_unless_postgres()

    from tests.conftest import MembershipFactory

    first = SchoolFactory()
    second = SchoolFactory()
    student = _member_of(first)
    MembershipFactory(school=second, user=student)

    for school in (first, second):
        route = _make_route(school)
        with _rls_enforced_as(
            school.id,
            readable=JOIN_TABLE_PARENTS,
            writable=("core_busroute_students",),
        ):
            with connection.cursor() as cursor:
                cursor.execute(
                    "INSERT INTO public.core_busroute_students "
                    "(busroute_id, customuser_id) VALUES (%s, %s)",
                    [str(route.id), str(student.id)],
                )


# ── نفس الثلاثية لمشاركي أنشطة المكتبة ───────────────────────────────────────

ACTIVITY_PARENTS = ("core_libraryactivity", "core_membership")


def _make_activity(school):
    from library.models import LibraryActivity

    return LibraryActivity.objects.create(
        school=school,
        title="نشاط",
        description="وصف",
        date="2026-01-01",
    )


@pytest.mark.django_db
def test_activity_participant_who_is_a_member_succeeds():
    """الحالة المشروعة: نشاطنا ومشارك يحمل عضويّة عندنا."""
    _skip_unless_postgres()

    own = SchoolFactory()
    activity = _make_activity(own)
    participant = _member_of(own)

    with _rls_enforced_as(
        own.id,
        readable=ACTIVITY_PARENTS,
        writable=("core_libraryactivity_participants",),
    ):
        with connection.cursor() as cursor:
            cursor.execute(
                "INSERT INTO public.core_libraryactivity_participants "
                "(libraryactivity_id, customuser_id) VALUES (%s, %s)",
                [str(activity.id), str(participant.id)],
            )


@pytest.mark.django_db
def test_own_activity_with_a_foreign_participant_is_rejected():
    """
    [RLS-PRE0] نشاطنا لا يقبل مشاركاً من مدرسة أخرى.

    وهذا حكم دلالي صريح لا صمت: لا شيء في النموذج يشير إلى ضيف خارجي، وقبوله
    ضمناً كان سيجعل هذا الجدول الموضع الوحيد في المنصّة الذي يُسجَّل فيه شخص
    من مدرسة أخرى على نشاط مدرسة. إن لزم ذلك يوماً فليكن علاقةً معلنة.
    """
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    activity = _make_activity(own)
    foreign_participant = _member_of(victim)

    with _rls_enforced_as(
        own.id,
        readable=ACTIVITY_PARENTS,
        writable=("core_libraryactivity_participants",),
    ):
        _assert_rejected_by_rls(
            "INSERT INTO public.core_libraryactivity_participants "
            "(libraryactivity_id, customuser_id) VALUES (%s, %s)",
            [str(activity.id), str(foreign_participant.id)],
        )


@pytest.mark.django_db
def test_foreign_activity_participation_is_rejected():
    """الطرف الأول: نشاط مدرسة أخرى مرفوض ولو كان المشارك عضواً عندنا."""
    _skip_unless_postgres()

    own = SchoolFactory()
    victim = SchoolFactory()
    foreign_activity = _make_activity(victim)
    participant = _member_of(own)

    with _rls_enforced_as(
        own.id,
        readable=ACTIVITY_PARENTS,
        writable=("core_libraryactivity_participants",),
    ):
        _assert_rejected_by_rls(
            "INSERT INTO public.core_libraryactivity_participants "
            "(libraryactivity_id, customuser_id) VALUES (%s, %s)",
            [str(foreign_activity.id), str(participant.id)],
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
