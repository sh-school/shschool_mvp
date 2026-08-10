"""
tests/test_tenant_surface_coverage.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[RLS-PRE0] كل جدول فيزيائي مصنَّف، ولا جدول يسقط في النقطة العمياء.

`DeadLetterMessage` لم يكن استثناءً؛ كان العيّنة الظاهرة من فئة كاملة: جداول
تحمل بيانات مستأجِر بلا عمود `school_id`، فلا تراها حلقة المطابقة في 0037 لأنها
تختار على ذلك العمود بالذات. الجرد الفيزيائي وجد عشرين منها، اثنان منها جدولا
ربط M2M لا يظهران في `apps.get_models()` أصلاً.

حارس الوجود لا يكفي هنا. الحارس الذي يقول "محميّ/غير محميّ" يفشل بصمت أمام
جدول لم يُرَ قط. لذلك يفرض هذا الملف تصنيفاً رباعياً صريحاً: كل جدول في فئة
واحدة، ومن لا فئة له يُسقط CI حتى يكتب أحدهم حكماً وسبباً.

هذه الفحوص ساكنة بالكامل — لا قاعدة بيانات. برهان أن السياسات مُطبَّقة فعلاً
في PostgreSQL في tests/test_parent_derived_rls.py، وهما حارسان لا حارس واحد:
الساكن يُثبت أن التصميم معلَن، والسلوكي يُثبت أن المحرّك نفّذه.
"""

from pathlib import Path

import pytest
from django.apps import apps
from django.db.migrations.loader import MigrationLoader

from core.tenancy import (
    BOOTSTRAP_EXCLUDED,
    GLOBAL_INFRASTRUCTURE,
    PARENT_DERIVED,
    SPECIAL_UNRESOLVED,
    direct_school_tables,
    policy_required_tables,
    tenant_reachable_tables,
)

ROOT = Path(__file__).resolve().parents[1]


def _physical_tables():
    return {model._meta.db_table for model in apps.get_models(include_auto_created=True)}


# ══════════════════════════════════════════════════════════════════
# التصنيف الرباعي
# ══════════════════════════════════════════════════════════════════


def test_every_physical_table_is_classified():
    """
    [RLS-PRE0] لا جدول بلا حكم.

    هذا هو الحارس الذي كان غيابه يكلّفنا: جدول جديد يحمل بيانات مستأجِر يمكن
    أن يُولد بلا سياسة ولا يلاحظه أحد. الآن يسقط CI حتى يُصنَّف.
    """
    classified = (
        direct_school_tables()
        | set(PARENT_DERIVED)
        | set(GLOBAL_INFRASTRUCTURE)
        | set(SPECIAL_UNRESOLVED)
    )
    unclassified = sorted(_physical_tables() - classified)

    assert not unclassified, "غير مصنَّفة — صنّفها في core/tenancy.py قبل الدمج: " + ", ".join(
        unclassified
    )


def test_no_table_is_classified_twice():
    """فئتان لجدول واحد تعني أن إحداهما لا تُقرأ — وقد تكون الفئة الحامية."""
    groups = {
        "DIRECT_SCHOOL": direct_school_tables(),
        "PARENT_DERIVED": set(PARENT_DERIVED),
        "GLOBAL_INFRASTRUCTURE": set(GLOBAL_INFRASTRUCTURE),
        "SPECIAL_UNRESOLVED": set(SPECIAL_UNRESOLVED),
    }

    names = list(groups)
    for index, first in enumerate(names):
        for second in names[index + 1 :]:
            overlap = sorted(groups[first] & groups[second])
            assert not overlap, f"{first} ∩ {second}: {overlap}"


def test_the_inventory_sees_auto_created_join_tables():
    """
    الحارس نفسه يحتاج برهاناً.

    `apps.get_models()` يُسقط جداول M2M الآلية افتراضياً. حارس يمشي عليها بلا
    `include_auto_created=True` يمرّ دائماً لأنه لا يرى الفئة التي يفترض أن
    يحرسها. هذا التأكيد يفشل لحظة عودة الجرد إلى الافتراضي.
    """
    tables = _physical_tables()

    assert "core_busroute_students" in tables
    assert "core_libraryactivity_participants" in tables
    assert len(tables) > len({m._meta.db_table for m in apps.get_models()})


# ══════════════════════════════════════════════════════════════════
# صدق كل فئة
# ══════════════════════════════════════════════════════════════════


@pytest.mark.parametrize("table", sorted(PARENT_DERIVED))
def test_parent_derived_tables_have_no_school_column(table):
    """
    جدول اكتسب `school_id` لم يعد مشتقّاً.

    تركه في الفئة الخطأ يعني سياسة تقرأ الأب بينما التطبيق يكتب العمود —
    مصدرا حقيقة يمكن أن يختلفا، وهو ما اخترنا الاشتقاق أصلاً لتفاديه.
    """
    assert table not in direct_school_tables()


@pytest.mark.parametrize("table", sorted(PARENT_DERIVED))
def test_parent_derived_tables_exist(table):
    """اسم في السجلّ بلا جدول يعني سياسة تحرس لا شيء."""
    assert table in _physical_tables()


@pytest.mark.parametrize("table", sorted(GLOBAL_INFRASTRUCTURE))
def test_global_tables_are_outside_the_tenant_graph(table):
    """
    جدول "عامّ" اكتسب مفتاحاً إلى بيانات مستأجِر لم يعد عامّاً.

    بلا هذا الفحص يبقى التصنيف إعلاناً لا يُراجَع: تكفي إضافة مفتاح أجنبي
    واحد ليصير الجدول مستأجِراً وتبقى الفئة تقول غير ذلك.
    """
    assert table not in tenant_reachable_tables()


def test_special_unresolved_stays_at_two():
    """
    [RLS-PRE0] الفئة الأخيرة ليست allowlist.

    جدول ثالث يدخلها يجب أن يُسقط CI حتى يُكتب سببه ومساره صراحةً — وإلا
    تحوّلت فئة "مؤجَّل" إلى مقبرة ديون صامتة.
    """
    assert set(SPECIAL_UNRESOLVED) == {"core_healthrecord", "core_storedfile"}

    for table, reason in SPECIAL_UNRESOLVED.items():
        assert "TRACK" in reason, f"{table}: يجب أن يسمّي المسار الذي يملكه"


@pytest.mark.parametrize("table", sorted(PARENT_DERIVED))
def test_every_parent_derived_entry_records_its_derivation(table):
    """السجلّ يُقرأ لمراجعة الـSQL؛ قيمة فارغة تجعله زينة."""
    assert "->" in PARENT_DERIVED[table]


# ══════════════════════════════════════════════════════════════════
# السياسة معلَنة في ترحيل — بلا قاعدة بيانات
# ══════════════════════════════════════════════════════════════════


def _declared_policy_sql():
    """كل نصّ SQL في كل RunSQL عبر رسم الترحيلات، بلا اتصال بقاعدة."""
    loader = MigrationLoader(None, ignore_no_migrations=True)
    statements = []

    for migration in loader.disk_migrations.values():
        for operation in migration.operations:
            sql = getattr(operation, "sql", None)
            if isinstance(sql, str):
                statements.append(sql)
            elif isinstance(sql, (list, tuple)):
                statements.extend(item for item in sql if isinstance(item, str))

    return statements


@pytest.mark.parametrize("table", sorted(PARENT_DERIVED))
def test_a_migration_declares_a_policy_for_each_derived_table(table):
    """
    السياسة مكتوبة في ترحيل لا في نيّة.

    0037 واقعة ماضية ولن تُعاد، فالمطابقة لن تلتقط شيئاً بعدها. كل جدول هنا
    يحتاج ترحيله الخاص الذي يقول ذلك صراحةً.
    """
    wanted = f"CREATE POLICY school_isolation ON public.{table}"

    assert any(wanted in sql for sql in _declared_policy_sql()), f"لا ترحيل يُنشئ سياسة على {table}"


@pytest.mark.parametrize("table", sorted(PARENT_DERIVED))
def test_each_derived_policy_is_reversible(table):
    """
    ترحيل أمني بلا تراجع يحجز القاعدة في حالة لا مخرج منها.

    والتراجع يُسقط السياسة ولا يستعيد وضعاً أوسع — لا شيء هنا كان مسموحاً
    قبل الترحيل ويجب أن يعود.
    """
    loader = MigrationLoader(None, ignore_no_migrations=True)
    marker = f"CREATE POLICY school_isolation ON public.{table}"

    for migration in loader.disk_migrations.values():
        for operation in migration.operations:
            sql = getattr(operation, "sql", None)
            if not isinstance(sql, str) or marker not in sql:
                continue

            reverse = getattr(operation, "reverse_sql", None)
            assert isinstance(reverse, str), f"{table}: RunSQL بلا reverse_sql"
            assert f"DROP POLICY IF EXISTS school_isolation ON public.{table}" in reverse
            return

    pytest.fail(f"لم يُعثر على ترحيل السياسة لـ{table}")


def test_the_migration_scanner_finds_real_statements():
    """ماسح لا يجد شيئاً يمرّ دائماً — نُثبت أنه يقرأ الترحيلات فعلاً."""
    statements = _declared_policy_sql()

    assert len(statements) > 10
    assert any("app_rls_school" in sql for sql in statements)


# ══════════════════════════════════════════════════════════════════
# استثناءات الإقلاع
# ══════════════════════════════════════════════════════════════════


def test_bootstrap_exclusions_are_named_and_few():
    """
    الثلاثة المستثناة مستثناة لسبب بنيوي، لا للراحة.

    `core_membership` و`core_role` يُجيبان عن سؤال "أي مدرسة؟" فلا يمكن
    ترشيحهما بالجواب، و`app_rls_role_school` تقرأها الدالة التي ستحرسه —
    فالسياسة عليه استدعاء لنفسها.
    """
    assert BOOTSTRAP_EXCLUDED == {
        "core_membership",
        "core_role",
        "app_rls_role_school",
    }

    required = policy_required_tables()
    for table in BOOTSTRAP_EXCLUDED:
        assert table not in required
