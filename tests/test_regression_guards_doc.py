"""[GOVERNANCE] وثيقةُ الحرّاس لا تُحيل إلى ما لا يوجد.

`docs/governance/regression_guards.md` هي المرجعُ الواحدُ للحرّاس؛ فإن أشارت إلى اختبارٍ أُعيدت تسميتُه
أو ملفٍّ نُقل صار المرجعُ نفسُه دَيناً صامتاً — من يقرؤها يبحث عن حارسٍ لا وجودَ له فيظنّ أنّ الشيءَ محروسٌ
وهو ليس كذلك. وجد قياسُ 2026-09-25 (VI-35) في الوثيقة ستّةَ أرقامٍ متقادمة وإحالةً إلى ملفٍّ صار حزمةً
(`operations/models.py`)، ولم يُسقط ذلك شيءٌ.

الحارسُ يفحص **الإحالاتِ** لا الأرقام: كلُّ ما بين علامتَي الاقتباس المائلتين ويشبه اسمَ اختبارٍ (`test_…`
أو `Test…`) أو مسارَ ملفٍّ أو `*_baseline.json` يجب أن يوجد. والأرقامُ لقطةٌ مؤرَّخةٌ في رأس الوثيقة، مصدرُها
الحيُّ ملفُّ خطّ الأساس — وإجبارُ كلّ طلبٍ يغيّر خطَّ أساسٍ على تعديل هذا الملفّ (وهو بؤرةُ تعارضٍ بين
الجلسات المتوازية) ثمنُه أكبرُ من نفعه؛ فإن قرّر المالكُ غيرَ ذلك فهذا الملفّ هو موضعُه.
"""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent
DOC = ROOT / "docs" / "governance" / "regression_guards.md"
TESTS = ROOT / "tests"

SPAN_RE = re.compile(r"`([^`\n]+)`")
NAME_RE = re.compile(r"\b(test_[A-Za-z0-9_]+|Test[A-Z][A-Za-z0-9_]+)\b")
PATH_RE = re.compile(
    r"(?<![\w/.\-])([A-Za-z0-9_.\-]+(?:/[A-Za-z0-9_.\-]+)+\.(?:py|json|md|yml|yaml|css|js|html|svg|toml|txt))"
)
BASELINE_RE = re.compile(r"\b([a-z0-9_]+_baseline\.json)\b")

#: أقلُّ ما يجب أن يراه الحارسُ — قيسَ 121 اسمَ اختبارٍ ومسارٍ وخطَّ أساسٍ يومَ كتابته. إن سقط تحته فقد عطب القارئُ
#: فصار الحارسُ يمرّ بلا أن يفحص شيئاً (الفحصُ الذي لا يستطيع أن يفشل ليس فحصاً).
MIN_REFERENCES = 100


def _test_files(tests: pathlib.Path) -> list[pathlib.Path]:
    """ملفّاتُ الاختبار: `tests/*.py` و`tests/e2e/*.py` — اختباراتُ المتصفّح تُحرس بالوثيقة نفسِها."""
    return sorted(tests.glob("*.py")) + sorted((tests / "e2e").glob("*.py"))


def _sources() -> str:
    """نصُّ كلّ ملفّات الاختبار — للبحث عن `def` و`class`."""
    return "\n".join(p.read_text(encoding="utf-8", errors="ignore") for p in _test_files(TESTS))


def references(doc: str) -> tuple[set[str], set[str], set[str]]:
    """(أسماءُ الاختبارات، مساراتُ الملفّات، ملفّاتُ الأساس) المذكورةُ بين علامتَي اقتباس."""
    names: set[str] = set()
    paths: set[str] = set()
    baselines: set[str] = set()
    for span in SPAN_RE.findall(doc):
        names |= set(NAME_RE.findall(span))
        baselines |= set(BASELINE_RE.findall(span))
        paths |= {p for p in PATH_RE.findall(span) if "*" not in p and "<" not in p}
    return names, paths, baselines


def missing(
    doc: str, root: pathlib.Path = ROOT, tests: pathlib.Path = TESTS, sources: str | None = None
):
    names, paths, baselines = references(doc)
    text = _sources() if sources is None else sources
    stems = {p.stem for p in _test_files(tests)}
    lost_names = sorted(
        n
        for n in names
        if n not in stems and not re.search(rf"\b(?:def|class) {re.escape(n)}\b", text)
    )
    top_level = {p.name for p in root.iterdir() if p.is_dir()}
    lost_paths = sorted(
        p for p in paths if p.split("/", 1)[0] in top_level and not (root / p).exists()
    )
    lost_baselines = sorted(b for b in baselines if not (tests / b).exists())
    return lost_names, lost_paths, lost_baselines


def test_every_reference_in_the_guards_document_exists():
    doc = DOC.read_text(encoding="utf-8")
    lost_names, lost_paths, lost_baselines = missing(doc)
    problems = [f"اختبارٌ غيرُ موجود: {n}" for n in lost_names]
    problems += [f"ملفٌّ غيرُ موجود: {p}" for p in lost_paths]
    problems += [f"خطُّ أساسٍ غيرُ موجود: tests/{b}" for b in lost_baselines]
    assert not problems, (
        "وثيقةُ الحرّاس تُحيل إلى ما لا يوجد — حدِّثها في الطلب الذي غيّر الاسمَ أو المسار:\n  "
        + "\n  ".join(problems)
    )


def test_the_guard_reads_enough_references_to_mean_something():
    names, paths, baselines = references(DOC.read_text(encoding="utf-8"))
    assert len(names) + len(paths) + len(baselines) >= MIN_REFERENCES


def test_the_detector_sees_what_it_claims_to_see(tmp_path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_real.py").write_text(
        "def test_alive():\n    pass\n\nclass TestKept:\n    pass\n"
    )
    (tmp_path / "tests" / "kept_baseline.json").write_text("{}")
    (tmp_path / "tests" / "e2e").mkdir()
    (tmp_path / "tests" / "e2e" / "test_browser_flow.py").write_text(
        "def test_in_browser():\n    pass\n"
    )
    (tmp_path / "core").mkdir()
    (tmp_path / "core" / "real.py").write_text("")
    doc = (
        "`test_real` `test_alive` `TestKept` `test_gone_file` `TestGone` `test_renamed_function`\n"
        "`tests/e2e/test_browser_flow.py` `test_in_browser`\n"
        "`core/real.py` `core/moved.py` `docs/not_a_repo_dir/x.md` `kept_baseline.json` `lost_baseline.json`\n"
        "`tests/test_real.py::test_alive` عبارةٌ خارجَ الاقتباس test_outside_backticks تُتجاهل"
    )
    sources = _sources_of(tmp_path / "tests")
    lost_names, lost_paths, lost_baselines = missing(doc, tmp_path, tmp_path / "tests", sources)
    assert lost_names == ["TestGone", "test_gone_file", "test_renamed_function"]
    assert lost_paths == ["core/moved.py"]
    assert lost_baselines == ["lost_baseline.json"]


def _sources_of(tests_dir: pathlib.Path) -> str:
    return "\n".join(p.read_text(encoding="utf-8") for p in _test_files(tests_dir))
