"""[CALENDAR] لا موضعَ يقرأ العام من الثابت المُجمَّد إلّا مصدر الحقيقة نفسه.

المرحلة الثانية نقلت الواجهات التي فيها `request.GET`. وبقي ما هو أخطر منها:
تسعٌ وثلاثون دالّة تُوقَّع هكذا —

    def get_plan_stats(school, year: str = settings.CURRENT_ACADEMIC_YEAR)

والقيمة الافتراضية في بايثون تُقيَّم **مرّةً واحدة عند استيراد الوحدة**. فلو
صحّح أحدٌ الثابت في الإعدادات لَما وصل التصحيح إلى أيٍّ من هذه الدوالّ قبل
إعادة تشغيل العملية. وهي لا تبدو خطأً: التوقيع مقروءٌ ومألوف.

وصارت:

    def get_plan_stats(school, year: str | None = None):
        year = year or academic_year_for_school(school)

فالاشتقاق يقع وقت النداء، ومن مدرسة المستأجر نفسه لا من رايةٍ عامّة.
"""

import ast
import pathlib

import pytest

SKIP = ("/.venv/", "/node_modules/", "/worktrees/", "/migrations/", "/tests/")

#: الثابت مسموحٌ فيها: تعريفه، ومصدر الحقيقة الذي يرتدّ إليه، والنماذج (المرحلة التالية).
ALLOWED = {"shschool/settings/base.py", "core/academic_calendar.py"}


def _sources():
    for f in sorted(pathlib.Path(".").rglob("*.py")):
        if any(x in "/" + f.as_posix() for x in SKIP):
            continue
        yield f, f.read_text(encoding="utf-8", errors="ignore")


def _reads(node):
    return isinstance(node, ast.Attribute) and node.attr == "CURRENT_ACADEMIC_YEAR"


def test_the_sweep_reaches_the_modules_it_claims_to():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    assert sum(1 for _ in _sources()) > 300


def test_no_function_freezes_the_year_in_a_parameter_default():
    """القيمة الافتراضية تُقيَّم عند الاستيراد — فالثابت فيها أسوأ منه في الجسم."""
    frozen = []
    for f, src in _sources():
        if f.as_posix() in ALLOWED:
            continue
        for node in ast.walk(ast.parse(src)):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            a = node.args
            for d in list(a.defaults) + [x for x in a.kw_defaults if x]:
                if _reads(d):
                    frozen.append(f"{f.as_posix()}:{node.lineno} {node.name}")

    assert not frozen, f"قيمٌ افتراضية مُجمَّدة في: {frozen}"


def test_no_module_level_constant_copies_the_year():
    """`_DEFAULT_YEAR = settings.X` يتجمّد كما تتجمّد القيمة الافتراضية."""
    copies = []
    for f, src in _sources():
        if f.as_posix() in ALLOWED:
            continue
        for node in ast.parse(src).body:
            if isinstance(node, ast.Assign) and _reads(node.value):
                copies.append(f"{f.as_posix()}:{node.lineno}")

    assert not copies, f"نسخٌ مُجمَّدة على مستوى الوحدة في: {copies}"


def test_the_constant_survives_only_in_model_field_defaults():
    """ما بقي محصورٌ في `default=` داخل النماذج — ولا يتسرّب إلى غيرها."""
    stray = []
    for f, src in _sources():
        if f.as_posix() in ALLOWED:
            continue
        for i, line in enumerate(src.splitlines(), 1):
            if "CURRENT_ACADEMIC_YEAR" not in line or line.strip().startswith("#"):
                continue
            if "default=settings.CURRENT_ACADEMIC_YEAR" not in line:
                stray.append(f"{f.as_posix()}:{i}")

    assert not stray, f"قراءةٌ للثابت خارج قيم النماذج الافتراضية في: {stray}"


# ── العتبة القانونية للغياب ───────────────────────────────────────────


def test_the_legal_absence_window_is_not_written_in_dates(db, school):
    """كانت النافذة مكتوبةً `date(2025, 9, 1)` إلى `date(2026, 6, 30)`.

    فلمّا بدأ عام ٢٠٢٦-٢٠٢٧ خلت النافذة من كل حصّة: لا حصصَ تُعدّ، ولا غيابَ
    يُحسب، ولا تنبيهَ ينطلق. عطبٌ صامت في التزامٍ بالمادة ٧ من قانون التعليم
    الإلزامي ٢٥/٢٠٠١ — ولا شيء في الشاشة يقول إن التنبيه توقّف.
    """
    import inspect

    from operations.services import AttendanceService

    body = inspect.getsource(AttendanceService.check_absence_threshold)

    assert "date(2025" not in body and "date(2026" not in body
    assert "academic_year_window" in body


def test_the_absence_window_follows_the_seeded_calendar(db, school):
    from django.core.management import call_command

    from core.academic_calendar import academic_year_window

    call_command("seed_academic_calendar", school=school.code, verbosity=0)
    start, end = academic_year_window(school)

    assert start < end
    assert (end - start).days > 250, "عامٌ دراسيّ أقصر من ثمانية أشهر — تحقّق من البذر"


def test_the_window_falls_back_to_september_june_before_seeding(db, school):
    """قبل البذر لا ينكسر الحساب — يرتدّ إلى سبتمبر–يونيو مشتقّين من الاسم."""
    from core.academic_calendar import academic_year_window

    start, end = academic_year_window(school)

    assert (start.month, start.day) == (9, 1)
    assert (end.month, end.day) == (6, 30)
    assert end.year == start.year + 1


# ── الاشتقاق نفسه ─────────────────────────────────────────────────────


def test_the_school_helper_derives_from_the_seeded_calendar(db, school):
    from django.core.management import call_command

    from core.academic_calendar import academic_year_for_school

    call_command("seed_academic_calendar", school=school.code, verbosity=0)

    assert academic_year_for_school(school).count("-") == 1


def test_the_school_helper_tolerates_no_school(db):
    """التصدير قد يجري بلا مدرسةٍ معلومة — ولا يُسقط الصفحة."""
    from core.academic_calendar import academic_year_for_school

    assert academic_year_for_school(None)


def test_the_default_helper_is_not_frozen_at_import(db):
    """الذاكرة المؤقّتة بيوم، لا بعمر العملية."""
    import datetime

    from core.academic_calendar import _by_day, default_academic_year

    _by_day.clear()
    first = default_academic_year()
    assert list(_by_day) == [datetime.date.today()] or _by_day

    _by_day.clear()
    assert default_academic_year() == first


@pytest.mark.parametrize(
    "module,name",
    [
        ("quality.services", "get_plan_stats"),
        ("reports.services", "get_behavior_report"),
        ("analytics.services", "grades_distribution"),
    ],
)
def test_a_sample_of_services_accept_a_missing_year(module, name):
    """التوقيع نفسه يجب أن يقبل الغياب — وإلّا لم يُنقل أصلاً."""
    import importlib
    import inspect

    mod = importlib.import_module(module)
    fn = next(
        getattr(obj, name)
        for _, obj in vars(mod).items()
        if hasattr(obj, name) and not isinstance(obj, str)
    )
    param = inspect.signature(fn).parameters["year"]

    assert param.default is None
