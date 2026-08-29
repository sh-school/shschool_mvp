"""[CALENDAR] إحصاءات «هذه السنة» تعني العام الدراسي لا السنة الميلادية.

عثرتُ على هذا النمط أوّلاً في صفحة الطالب: ملخّص الحضور كان يُرشَّح
بـ`session__date__year`، فيعرض شطر العام الواقع في السنة الميلادية وحده.
ثم مسحتُ المنصّة عن أشباهه فوجدت ثلاثة:

    behavior/views.py   توزيع مستويات المخالفات «السنة الحالية»
    behavior/views.py   أعلى فئات المخالفات «السنة الحالية»
    analytics/services  استعارة المكتبة لكل طالب

والعام الدراسي يمتدّ من أغسطس إلى يونيو. فالترشيح الميلاديّ:

    في سبتمبر    يخلط شطر العام الماضي بشطر الحالي
    في يناير     يُسقط الفصل الأول كلّه

وأخبثه أنه لا يبدو خطأً: الرقم صحيحُ الشكل، والنسبة تبدو سليمة لأن مقامها
مقطوعٌ هو الآخر. ومقياس المكتبة ينهار إلى الصفر في يناير فيبدو انهياراً في
استعمالها بينما العام في منتصفه.

وما يقرن `__year` بـ`__month` سليم — فذاك «هذا الشهر» وهو ميلاديٌّ بحقّ،
ولم يُمسّ.
"""

import ast
import pathlib

import pytest

SKIP = ("/.venv/", "/node_modules/", "/.claude/", "/.mypy_cache/", "/migrations/", "/tests/")

#: حقولٌ زمنية يُرشَّح بها. `__year` وحدها تعني «هذه السنة».
YEAR_LOOKUP = "__year"
MONTH_LOOKUP = "__month"


def _sources():
    for f in sorted(pathlib.Path(".").rglob("*.py")):
        if any(x in "/" + f.as_posix() for x in SKIP):
            continue
        yield f, f.read_text(encoding="utf-8", errors="ignore")


def test_the_sweep_reaches_the_modules():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    names = {f.as_posix() for f, _ in _sources()}

    assert "behavior/views.py" in names
    assert "analytics/services.py" in names


def test_no_yearly_statistic_is_scoped_to_the_calendar_year():
    """`__year=` بلا `__month=` في نداءٍ واحد يعني «هذه السنة» — وهي دراسية.

    والفحص على مستوى **نداء الترشيح** لا السطر: فقد يمتدّ النداء أسطراً،
    ويقع `__month` في غير سطر `__year`.
    """
    offenders = []
    for f, src in _sources():
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            keys = [k.arg or "" for k in node.keywords]
            if not any(k.endswith(YEAR_LOOKUP) for k in keys):
                continue
            if any(MONTH_LOOKUP in k for k in keys):
                continue  # «هذا الشهر» — ميلاديٌّ بحقّ
            offenders.append(f"{f.as_posix()}:{node.lineno}  {keys}")

    assert not offenders, "إحصاءٌ سنويّ مقيَّدٌ بالسنة الميلادية:\n" + "\n".join(offenders)


# ── الأثر الحيّ ───────────────────────────────────────────────────────


@pytest.fixture
def year_window(db, school):
    from django.core.management import call_command

    from core.academic_calendar import academic_year_window

    call_command("seed_academic_calendar", school=school.code, verbosity=0)
    return academic_year_window(school)


def test_the_behaviour_window_follows_the_seeded_calendar(db, school, year_window):
    from behavior.views import _behaviour_year_window

    assert _behaviour_year_window(school) == year_window


def test_the_behaviour_window_spans_two_calendar_years(db, school, year_window):
    """وهو بيت الداء: نافذةٌ تعبر رأس السنة لا يحدّها `__year`."""
    start, end = _window(school)

    assert start.year != end.year
    assert (start.month, end.month) == (8, 6)


def test_the_behaviour_window_falls_back_before_seeding(db, school):
    """بلا تقويمٍ لا تنكسر اللوحة — ترتدّ إلى السنة الميلادية."""
    start, end = _window(school)

    assert (start.month, start.day) == (1, 1) or start.month == 8


def _window(school):
    from behavior.views import _behaviour_year_window

    return _behaviour_year_window(school)
