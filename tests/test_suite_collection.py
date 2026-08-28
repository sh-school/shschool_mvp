"""[CI] كل ملفّ اختباراتٍ على القرص تجمعه البوابة.

كان في المستودع ثمانيةٌ وأربعون اختباراً لا يراها CI:

    pytest tests/          2263   ما تُشغّله البوابة
    pytest                 2306   +43 في developer_feedback/tests/
    student_affairs/tests.py  5   لا يجمعها أحد — لا مجلّد tests/ فيه

سببان متراكبان: `python_files` كانت `tests/*.py` فلا تُطابق `tests.py`، والبوابة
تُشغّل `pytest tests/` فتقصر نفسها على المجلّد الأعلى.

وما لا يُجمع لا يُخفق. فكان ثلاثة عشر اختباراً ميّتاً بـ`TypeError` — ثمانيةٌ
منها أمنية (XSS، تنقية الرموز، منع الطالب، CSRF، عزل الرسائل) — تُحسب
«أخطاءً» لا «إخفاقات»، والمجموعة تقول `2255 passed` ولا أحد يسأل.
"""

import pathlib
import re

import yaml

#: المجلّدات التي لا تُجمع أصلاً (norecursedirs الافتراضية أو مسارات خارجية).
SKIP = ("/.venv/", "/node_modules/", "/.claude/", "/.mypy_cache/", "/build/", "/dist/")

CONFIG = pathlib.Path("pytest.ini")
WORKFLOWS = pathlib.Path(".github/workflows")


def _patterns():
    for line in CONFIG.read_text(encoding="utf-8").splitlines():
        if line.strip().startswith("python_files"):
            return line.split("=", 1)[1].split()
    raise AssertionError("لا `python_files` في pytest.ini")


def _test_files():
    for f in sorted(pathlib.Path(".").rglob("*.py")):
        path = "/" + f.as_posix()
        if any(x in path for x in SKIP):
            continue
        if f.name == "tests.py" or f.name.startswith("test_"):
            yield f


def test_the_sweep_finds_test_files():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    assert len(list(_test_files())) > 100


def test_every_test_file_matches_a_collection_pattern():
    """ملفٌّ لا يُطابق نمطاً لا يُجمع — ولا يُخفق مهما كان فيه."""
    patterns = _patterns()
    orphans = [f.as_posix() for f in _test_files() if not any(f.match(p) for p in patterns)]

    assert not orphans, f"ملفّات اختباراتٍ خارج الجمع: {orphans}"


def test_no_workflow_restricts_pytest_to_a_subdirectory():
    """`pytest tests/` يقصر البوابة على مجلّدٍ واحد ويترك الباقي بلا حارس."""
    narrowed = []
    for f in sorted(WORKFLOWS.glob("*.yml")):
        doc = yaml.safe_load(f.read_text(encoding="utf-8"))
        for name, job in (doc.get("jobs") or {}).items():
            for step in job.get("steps") or []:
                run = step.get("run")
                if not isinstance(run, str):
                    continue
                for m in re.finditer(r"\bpytest\s+([^\s|&;]+)", run):
                    arg = m.group(1)
                    if arg.startswith("-") or arg.startswith("$"):
                        continue
                    if arg.rstrip("/") in ("tests", "."):
                        narrowed.append(f"{f.name}:{name}  pytest {arg}")

    assert not narrowed, f"بوابةٌ مقصورةٌ على مجلّد: {narrowed}"


def test_the_orphaned_files_are_covered_now():
    """الملفّان اللذان كانا خارج البوابة — مذكوران كي لا يُنسيا."""
    patterns = _patterns()

    for name in ("student_affairs/tests.py", "developer_feedback/tests/test_security.py"):
        f = pathlib.Path(name)
        assert f.exists(), name
        assert any(f.match(p) for p in patterns), name
