"""[CI] كلُّ اختبار متصفّحٍ خارجَ الخطوة الرئيسيّة في `nightly.yml` و`quality.yml`، ومُشغَّلٌ في خطوةٍ منفصلة.

fixture جلسة Playwright تُبقي حلقةَ async قائمةً في العمليّة كلّها، فيسقط كلُّ اختبارٍ يلمس القاعدةَ
بعدها بـ`SynchronousOnlyOperation`. فالخطوةُ الرئيسيّة (المجموعةُ كاملةً متسلسلةً) تستثني ملفّاتِ
المتصفّح بأسمائها، وخطوةٌ بعدها تُشغّلها وحدها. والقائمةُ يدويّةٌ فتُنسى: ملفّان أُضيفا بلا
استثناء (`test_action_cards_fit_narrow_screens.py` في 09-19 و`test_page_nav_htmx_process.py` في 09-22)
فسقطت الليالي أربعاً (09-20..09-23، القضيّة #422) — وما يلزم كان سطرين في الملفّ.
وكان `quality.yml` الأسبوعيُّ بلا استثناءٍ ولا خطوةٍ منفصلة أصلاً (27 تشغيلاً فاشلاً من 27، REP-18)،
والحارسُ لا يراه لأنّه كان يقرأ `nightly.yml` وحدَه — فصار يقرأ الملفّين.

ملفُّ المتصفّح: كلُّ ما في `tests/e2e/`، وكلُّ ملفٍّ يطلب `pytest_playwright` أو `axe_playwright_python`.
"""

import pathlib
import re

import pytest
import yaml

#: ملفُّ الوظيفة ← (علامةٌ تميّز الخطوةَ الرئيسيّة فيه، ملفّاتٌ تُستثنى من الرئيسيّة ولا تُشغَّل في وظيفتها).
#: Lighthouse ليليٌّ فقط: ثلاثُ دقائق للصفحة ودرجةُ الأداء تتذبذب، فلا يُكرَّر أسبوعيّاً.
WORKFLOWS = {
    ".github/workflows/nightly.yml": ("--junit-xml", set()),
    ".github/workflows/quality.yml": (
        "--cov-report=json:coverage.json",
        {"tests/test_lighthouse_mobile.py"},
    ),
}
BROWSER_MARK = re.compile(r'importorskip\("(?:pytest_playwright|axe_playwright_python)"\)')


def _browser_tests() -> list[str]:
    files = sorted(
        str(p.as_posix())
        for p in pathlib.Path("tests").glob("test_*.py")
        if BROWSER_MARK.search(p.read_text(encoding="utf-8"))
    )
    return ["tests/e2e", *files]


def _runs(workflow: str) -> tuple[str, list[str]]:
    """(أمرُ الخطوة الرئيسيّة، أوامرُ الخطوات الأخرى) في الوظيفة."""
    marker, _ = WORKFLOWS[workflow]
    jobs = yaml.safe_load(pathlib.Path(workflow).read_text(encoding="utf-8"))["jobs"]
    steps = [s for job in jobs.values() for s in job.get("steps", []) if "run" in s]
    main = [s["run"] for s in steps if marker in s["run"]]
    assert len(main) == 1, f"خطوةُ المجموعة الكاملة (`{marker}`) غيرُ وحيدةٍ في {workflow}"
    return main[0], [s["run"] for s in steps if marker not in s["run"]]


def test_the_browser_marker_still_finds_the_known_files():
    found = _browser_tests()
    for known in ("tests/test_mobile_audit.py", "tests/test_a11y_axe_ratchet.py"):
        assert known in found, f"العلامةُ لم تعد تجد {known} — راجع BROWSER_MARK"


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_browser_test_is_kept_out_of_the_main_step(workflow):
    main, _ = _runs(workflow)
    missing = [f for f in _browser_tests() if f"--ignore={f}" not in main]
    assert not missing, (
        f"اختبارُ متصفّحٍ في الخطوة الرئيسيّة لـ{workflow} — سيُسقط ما بعده من اختبارات القاعدة. "
        "أضِف `--ignore=…` له:\n  " + "\n  ".join(missing)
    )


@pytest.mark.parametrize("workflow", WORKFLOWS)
def test_every_browser_test_still_runs_in_a_separate_step(workflow):
    _, others = _runs(workflow)
    _, exempt = WORKFLOWS[workflow]
    lost = [f for f in _browser_tests() if f not in exempt and not any(f in run for run in others)]
    assert not lost, (
        f"اختبارُ متصفّحٍ مستثنىً من {workflow} ولا يُشغَّل في أيّ خطوةٍ منه:\n  " + "\n  ".join(lost)
    )
