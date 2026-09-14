"""[CI] سقّاطةُ الأنواع — راجع `tests/mypy_ratchet.py` للسبب والطريقة.

mypy نفسُه لا يُشغَّل هنا (دقيقتان على core/ وshschool/) — تُشغّله وظيفةُ
`mypy` في بوّابة الجودة عبر `python -m tests.mypy_ratchet`. هنا يُختبر أنّ
السقّاطةَ تحرس ما تقول إنّها تحرسه، وأنّ السجلَّ سليمُ الشكل.
"""

import json
import pathlib

import pytest

from tests import mypy_ratchet as ratchet


def _baseline():
    return json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))


def test_the_baseline_exists_and_is_well_formed():
    baseline = _baseline()
    assert set(baseline) == {"total", "files"}
    assert baseline["total"] == sum(baseline["files"].values())
    assert all(isinstance(n, int) and n > 0 for n in baseline["files"].values())
    assert all("\\" not in path for path in baseline["files"]), "مساراتٌ بشرطةٍ أماميّة فقط"


def test_every_recorded_file_still_exists():
    """ملفٌّ حُذف أو نُقل يبقى في السجلّ عدداً لا يقابله شيء — يُزال بـ--update."""
    gone = [path for path in _baseline()["files"] if not pathlib.Path(path).is_file()]
    assert not gone, f"ملفّاتٌ في السجلّ لم تعد موجودة (python -m tests.mypy_ratchet --update): {gone}"


def test_the_baseline_covers_the_declared_targets_and_what_they_import():
    """mypy يتبع الاستيرادات (`follow_imports = normal`) فيحكم على `operations/models.py`
    حين يستوردها `core/` — فالسجلُّ أوسعُ من الهدفين، وهذا مقصود: لا يضيق."""
    files = _baseline()["files"]
    for target in ratchet.TARGETS:
        assert any(path.startswith(f"{target}/") for path in files), f"لا ملفَّ من {target}/ في السجلّ"
    assert all(pathlib.Path(path).suffix == ".py" for path in files)


class TestTheRatchetItself:
    def test_parse_counts_errors_per_file_and_ignores_notes(self):
        output = (
            "core/a.py:10: error: Function is missing a return type annotation  [no-untyped-def]\n"
            'core/a.py:10: note: Use "-> None" if function does not return a value\n'
            "core/a.py:22:5: error: Incompatible types  [assignment]\n"
            "shschool\\celery.py:54: error: Property is read-only  [misc]\n"
            "Found 3 errors in 2 files (checked 40 source files)\n"
        )
        assert ratchet.parse(output) == {"core/a.py": 2, "shschool/celery.py": 1}

    def test_more_errors_in_a_file_is_worse(self):
        worse, stale = ratchet.compare({"core/a.py": 1}, {"core/a.py": 2})
        assert worse == ["core/a.py: 1 → 2"] and not stale

    def test_a_new_file_starts_from_zero(self):
        worse, _ = ratchet.compare({}, {"core/new.py": 1})
        assert worse == ["core/new.py: 0 → 1"]

    def test_an_improvement_must_be_recorded(self):
        worse, stale = ratchet.compare({"core/a.py": 3}, {"core/a.py": 1})
        assert not worse and stale == ["core/a.py: 3 → 1"]

    def test_a_fixed_file_disappears_and_must_be_recorded(self):
        worse, stale = ratchet.compare({"core/a.py": 3}, {})
        assert not worse and stale == ["core/a.py: 3 → 0"]

    def test_a_crash_is_not_zero_errors(self, monkeypatch):
        """رمزُ خروجٍ 2 (إعدادٌ معطوب/انهيار) يُرفع — لا يُقرأ «لا أخطاء»."""
        monkeypatch.setattr(
            ratchet, "run_mypy", lambda targets=ratchet.TARGETS: (2, "mypy: error: bad config")
        )
        with pytest.raises(RuntimeError):
            ratchet.measure()

    def test_an_error_exit_without_parseable_lines_is_loud(self, monkeypatch):
        monkeypatch.setattr(
            ratchet, "run_mypy", lambda targets=ratchet.TARGETS: (1, "something odd")
        )
        with pytest.raises(RuntimeError):
            ratchet.measure()
