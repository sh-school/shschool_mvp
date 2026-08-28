"""[CALENDAR] لا حقلَ يخزّن العام المُجمَّد في قيمته الافتراضية.

`default=settings.CURRENT_ACADEMIC_YEAR` أسوأ من كل ما سبقه: القيمة لا تُقيَّم
عند الاستيراد فحسب، بل **تُخبَز في ملفّ الهجرة** — فتبقى في تاريخ المشروع نصّاً
لا يتغيّر ولو صُحّح الثابت. وأيّ صفٍّ يُنشأ بلا عامٍ صريح يأخذ ذلك النصّ.

    academic_year = models.CharField(default=settings.CURRENT_ACADEMIC_YEAR)
    academic_year = models.CharField(default=default_academic_year)

والفرق أن جانغو يُسلسل الدالّة **بالمرجع** لا بالقيمة، فلا نصَّ يُخبَز، والنداء
يقع وقت إنشاء الصفّ. والهجرات الناتجة تعديلُ حالةٍ محض — `sqlmigrate` يُخرج
`(no-op)` لكلٍّ منها، لأن جانغو لا يضع القيم الافتراضية في القاعدة أصلاً.
"""

import ast
import pathlib

from django.apps import apps

SKIP = ("/.venv/", "/node_modules/", "/worktrees/", "/tests/")

#: الثابت مسموحٌ فيها: تعريفه، ومصدر الحقيقة، والهجرات التاريخية التي خُبز فيها.
ALLOWED = {"shschool/settings/base.py", "core/academic_calendar.py"}


def _sources():
    for f in sorted(pathlib.Path(".").rglob("*.py")):
        path = "/" + f.as_posix()
        if any(x in path for x in SKIP):
            continue
        yield f, f.read_text(encoding="utf-8", errors="ignore")


def test_the_sweep_reaches_the_model_modules():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    names = {f.as_posix() for f, _ in _sources()}

    assert "quality/models.py" in names and "operations/models.py" in names


def test_no_model_field_bakes_the_constant_into_its_default():
    """ما بقي من الثابت بعد المرحلة الثالثة كان محصوراً هنا — ولم يعد."""
    baked = []
    for f, src in _sources():
        if f.as_posix() in ALLOWED or "/migrations/" in "/" + f.as_posix():
            continue
        for i, line in enumerate(src.splitlines(), 1):
            if "default=settings.CURRENT_ACADEMIC_YEAR" in line:
                baked.append(f"{f.as_posix()}:{i}")

    assert not baked, f"قيمٌ افتراضية مخبوزة في: {baked}"


def test_the_constant_is_read_nowhere_but_its_own_source():
    """آخر خطوة: لا موضعَ في المنصّة كلّها يقرأه إلّا مصدر الحقيقة."""
    readers = []
    for f, src in _sources():
        if f.as_posix() in ALLOWED or "/migrations/" in "/" + f.as_posix():
            continue
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Attribute) and node.attr == "CURRENT_ACADEMIC_YEAR":
                readers.append(f"{f.as_posix()}:{node.lineno}")

    assert not readers, f"ما زال الثابت يُقرأ في: {readers}"


def test_every_year_field_defaults_to_the_callable():
    """الفحص من طرف جانغو نفسه لا من النصّ — الحقول المسجَّلة، لا ما كُتب."""
    from core.academic_calendar import default_academic_year

    wrong = []
    for model in apps.get_models():
        for field in model._meta.local_fields:
            if field.name != "academic_year" or not field.has_default():
                continue
            if field.default is not default_academic_year:
                wrong.append(f"{model._meta.label}.{field.name} = {field.default!r}")

    assert not wrong, f"حقولٌ لا تشتقّ عامها: {wrong}"


#: الهجرات التي نقلت الحقول الواحدَ والعشرين إلى الاشتقاق.
MIGRATIONS = (
    "assessments/migrations/0010_alter_annualsubjectresult_academic_year_and_more.py",
    "core/migrations/0042_alter_classgroup_academic_year.py",
    "exam_control/migrations/0005_alter_examsession_academic_year.py",
    "operations/migrations/0018_alter_freeslotregistry_academic_year_and_more.py",
    "quality/migrations/0016_alter_employeeevaluation_academic_year_and_more.py",
    "staff_affairs/migrations/0002_alter_leavebalance_academic_year_and_more.py",
    "student_affairs/migrations/0002_alter_studentactivity_academic_year_and_more.py",
)


def test_the_new_migrations_serialize_the_callable_by_reference():
    """لو سُلسلت بالقيمة لعاد النصّ المخبوز من حيث خرج.

    والهجرات الأقدم تحمل النصّ المخبوز وتبقى كما هي — فهي سجلّ ما جرى، لا
    وصفٌ لما هو قائم. والقائمُ تحرسه `test_every_year_field_defaults_to_the_callable`
    من طرف جانغو نفسه.
    """
    for name in MIGRATIONS:
        f = pathlib.Path(name)
        assert f.exists(), f"هجرةٌ مفقودة: {name}"
        body = f.read_text(encoding="utf-8")

        assert "core.academic_calendar.default_academic_year" in body, name
        assert "CURRENT_ACADEMIC_YEAR" not in body, name
        assert 'default="20' not in body, name


def test_a_row_created_without_a_year_takes_the_derived_one(db, school):
    """الإثبات الحيّ: صفٌّ يُنشأ بلا عامٍ صريح يأخذ ما يقوله التقويم."""
    from django.core.management import call_command

    from core.academic_calendar import default_academic_year
    from core.models import ClassGroup

    call_command("seed_academic_calendar", school=school.code, verbosity=0)
    expected = default_academic_year()

    group = ClassGroup.objects.create(school=school, grade="G7", section="9")

    assert group.academic_year == expected
