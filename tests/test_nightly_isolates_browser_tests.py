"""[CI] كلُّ اختبار متصفّحٍ خارجَ الخطوة الرئيسيّة في السيرَين المجدولَين (`nightly.yml` و`quality.yml`)، ومُشغَّلٌ في خطوةٍ منفصلة.

fixture جلسة Playwright تُبقي حلقةَ async قائمةً في العمليّة كلّها، فيسقط كلُّ اختبارٍ يلمس القاعدةَ
بعدها بـ`SynchronousOnlyOperation`. فالخطوةُ الرئيسيّة (المجموعةُ كاملةً) تستثني ملفّاتِ
المتصفّح بأسمائها، وخطوةٌ بعدها تُشغّلها وحدها بعد أن يُثبَّت المتصفّح. والقائمةُ يدويّةٌ فتُنسى:
ملفّان أُضيفا بلا استثناء (`test_action_cards_fit_narrow_screens.py` في 09-19 و`test_page_nav_htmx_process.py`
في 09-22) فسقطت الليالي أربعاً (09-20..09-23، القضيّة #422) — وما يلزم كان سطرين في الملفّ.

وسيرُ `quality.yml` الأسبوعيّ (وظيفةُ التغطية) كان يشغّل المجموعةَ كاملةً بلا متصفّحٍ ولا عزل: 27 فشلاً و173 خطأً
(`BrowserType.launch` و`SynchronousOnlyOperation`) في 09-20، وحمرةٌ أسبوعيّةٌ منذ 08-23 — فصار الحارسُ يحكم
السيرَين معاً، لا الليليَّ وحدَه.

ملفُّ المتصفّح: كلُّ ما في `tests/e2e/`، وكلُّ ملفٍّ يطلب `pytest_playwright` أو `axe_playwright_python`.
"""

import pathlib
import re

import pytest
import yaml

#: السيرُ ← علامةٌ في أمر الخطوة الرئيسيّة (التي تشغّل المجموعةَ كاملةً) تميّزها عن غيرها.
SCHEDULED_SUITES = {
    ".github/workflows/nightly.yml": "--junit-xml",
    ".github/workflows/quality.yml": "--cov-report=json:coverage.json",
}
BROWSER_MARK = re.compile(r'importorskip\("(?:pytest_playwright|axe_playwright_python)"\)')
ASYNC_UNSAFE = "DJANGO_ALLOW_ASYNC_UNSAFE"


def _browser_tests() -> list[str]:
    files = sorted(
        str(p.as_posix())
        for p in pathlib.Path("tests").glob("test_*.py")
        if BROWSER_MARK.search(p.read_text(encoding="utf-8"))
    )
    return ["tests/e2e", *files]


def _steps(path: str) -> list[tuple[dict, dict]]:
    """[(الوظيفة، الخطوة)] لكلّ خطوةٍ تشغّل أمراً في السير."""
    jobs = yaml.safe_load(pathlib.Path(path).read_text(encoding="utf-8"))["jobs"]
    return [(job, step) for job in jobs.values() for step in job.get("steps", []) if "run" in step]


def _split(path: str) -> tuple[tuple[dict, dict], list[dict]]:
    """((وظيفةُ الخطوة الرئيسيّة، الخطوةُ الرئيسيّة)، الخطواتُ الأخرى في الوظيفة نفسِها).

    الوظيفةُ نفسُها لا السيرُ كلُّه: المتصفّحُ المثبَّت في وظيفةٍ لا يخدم خطوةً في وظيفةٍ أخرى (كلٌّ على مُشغِّلٍ منفصل).
    """
    marker = SCHEDULED_SUITES[path]
    steps = _steps(path)
    main = [(job, step) for job, step in steps if marker in step["run"]]
    assert len(main) == 1, f"لم أجد خطوةَ المجموعة الكاملة (`{marker}`) في {path}"
    job, main_step = main[0]
    return (job, main_step), [s for j, s in steps if j is job and s is not main_step]


def test_the_browser_marker_still_finds_the_known_files():
    found = _browser_tests()
    for known in ("tests/test_mobile_audit.py", "tests/test_a11y_axe_ratchet.py"):
        assert known in found, f"العلامةُ لم تعد تجد {known} — راجع BROWSER_MARK"


@pytest.mark.parametrize("path", SCHEDULED_SUITES)
def test_every_browser_test_is_kept_out_of_the_main_step(path):
    (_, main), _ = _split(path)
    missing = [f for f in _browser_tests() if f"--ignore={f}" not in main["run"]]
    assert not missing, (
        f"اختبارُ متصفّحٍ في الخطوة الرئيسيّة لـ{path} — سيُسقط ما بعده من اختبارات القاعدة. "
        "أضِف `--ignore=…` له:\n  " + "\n  ".join(missing)
    )


@pytest.mark.parametrize("path", SCHEDULED_SUITES)
def test_every_browser_test_still_runs_in_a_separate_step(path):
    _, others = _split(path)
    lost = [f for f in _browser_tests() if not any(f in step["run"] for step in others)]
    assert not lost, f"اختبارُ متصفّحٍ مستثنىً في {path} ولا يُشغَّل في أيّ خطوة:\n  " + "\n  ".join(lost)


@pytest.mark.parametrize("path", SCHEDULED_SUITES)
def test_the_browsers_are_installed_before_the_separate_step(path):
    """كان `quality.yml` يشغّل اختباراتِ المتصفّح بلا `playwright install` فسقطت كلُّها بـ`BrowserType.launch`."""
    _, others = _split(path)
    names = [step["run"] for step in others]
    install = next((i for i, run in enumerate(names) if "playwright install" in run), None)
    browser = next((i for i, run in enumerate(names) if "tests/e2e" in run), None)
    assert install is not None, f"{path}: لا خطوةَ `playwright install`"
    assert browser is not None, f"{path}: لا خطوةَ تشغّل tests/e2e"
    assert install < browser, f"{path}: المتصفّحُ يُثبَّت بعد الخطوة التي تستعمله"


@pytest.mark.parametrize("path", SCHEDULED_SUITES)
def test_the_async_escape_hatch_is_only_on_the_browser_step(path):
    """`DJANGO_ALLOW_ASYNC_UNSAFE` يُطفئ حارسَ Django من الوصول المتزامن للقاعدة داخل حلقة async: مكانُه خطوةُ
    المتصفّح وحدَها. على الخطوة الرئيسيّة يُخفي أعطالاً حقيقيّة (راجع تعليق nightly.yml)."""
    (job, main), others = _split(path)
    assert ASYNC_UNSAFE not in main.get("env", {}), f"{path}: على الخطوة الرئيسيّة"
    assert ASYNC_UNSAFE not in job.get("env", {}), f"{path}: على مستوى الوظيفة كلِّها"
    browser = [step for step in others if "tests/e2e" in step["run"]]
    assert browser and all(
        step.get("env", {}).get(ASYNC_UNSAFE) == "1" for step in browser
    ), f"{path}: خطوةُ المتصفّح بلا {ASYNC_UNSAFE}=1"
