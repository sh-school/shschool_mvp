"""[CI] لا ملفَّ شيفرةٍ متتبَّعٌ تُسقطه `.gitignore` — حادثةُ 2026-09-26.

كان `core/models/_crypto.py` متتبَّعاً في git لكنّه يطابق `_*.py` في `.gitignore`. ونشراتُ GitHub تُبنى من
الفهرس فتشمله؛ أمّا `railway up` فيرفع الشجرةَ مطبِّقاً `.gitignore` (وعلمُ `--no-gitignore` يعطّل ذلك) فيُسقطه
— فسقطت نشرةٌ رفعتها جلسةٌ بالـCLI في مرحلة pre-deploy بـ`ModuleNotFoundError: No module named
'core.models._crypto'`. وكلُّ فحصٍ في البوّابة كان أخضرَ لأنّ الاختباراتِ وmypy وruff ترى الملفَّ على القرص.

فالحارسُ يسأل git نفسَه: أيُّ ملفٍّ متتبَّعٍ يطابق قاعدةً في `.gitignore` (بعد الاستثناءات `!`)؟ فإن كان شيفرةً
(`.py` و`.html` و`.js` و`.css` و`.sh`) سقط البناء. وغيرُ الشيفرة (سجلّاتٌ ووثائقُ وبيانات) خارجَ الحكم: لا يحتاجه
التشغيلُ فسقوطُه من رفعٍ لا يكسر شيئاً.

العلاج: غيِّر اسمَ الملفّ كي لا يطابق القاعدة (أُعيدت تسميةُ `_crypto.py` إلى `crypto.py`)، أو أضِف استثناءً
`!المسار` في `.gitignore`.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent

#: ما يُنفَّذ أو يُخدَم — سقوطُ أحدها من رفعٍ يكسر النشرَ أو الصفحة.
CODE_SUFFIXES = (".py", ".html", ".js", ".css", ".sh")


def tracked_but_ignored(repo: pathlib.Path) -> list[str] | None:
    """الملفّاتُ المتتبَّعةُ التي تطابق `.gitignore` — أو `None` إن تعذّر على git قراءةُ المستودع."""
    git = shutil.which("git")
    if git is None:
        return None
    proc = subprocess.run(
        [git, "-C", str(repo), "ls-files", "-ci", "--exclude-standard", "-z"],
        capture_output=True,
        check=False,
    )
    if proc.returncode != 0:
        return None
    return sorted(name for name in proc.stdout.decode("utf-8").split("\0") if name)


def _need_git(found: list[str] | None) -> list[str]:
    """حيث لا غيتَ (أو حاويةُ جلسةٍ ترى الشجرةَ بلا مستودعها) يُتخطّى؛ وفي البوّابة غيابُه عطبٌ لا عذر."""
    if found is None:
        # في متغيّرٍ لا في `assert os.environ.get(...)` مباشرةً: pytest يطبع ما يُقارَن عند الإخفاق
        # و`os.environ` تحمل أسراراً.
        in_ci = bool(os.environ.get("CI"))
        assert not in_ci, "git لا يقرأ المستودع في البوّابة — الفحصُ لا يُتخطّى هنا"
        pytest.skip("git لا يقرأ المستودع في هذه البيئة — الفحصُ يجري في البوّابة")
    return found


def test_no_tracked_code_file_is_dropped_by_gitignore():
    dropped = _need_git(tracked_but_ignored(ROOT))
    code = [name for name in dropped if name.endswith(CODE_SUFFIXES)]

    assert not code, (
        "ملفّاتُ شيفرةٍ متتبَّعةٌ في git وتطابق `.gitignore` — يُسقطها `railway up` فيسقط النشرُ "
        "بـ`ModuleNotFoundError`:\n  "
        + "\n  ".join(code)
        + "\nغيِّر الاسمَ كي لا يطابق القاعدة (كالبادئة `_` في `_*.py`)، أو أضِف استثناءً `!المسار`."
    )


def test_the_check_flags_exactly_the_code_that_gitignore_would_drop(tmp_path):
    """المنطقُ في مستودعٍ مؤقّت: الحادثةُ نفسُها تسقط، وما أُنقذ بـ`!` أو ليس شيفرةً لا يسقط."""
    git = shutil.which("git")
    if git is None:
        _need_git(None)
    assert git is not None

    (tmp_path / ".gitignore").write_text("_*.py\n_*.js\n!**/__init__.py\n*.csv\n", encoding="utf-8")
    files = {
        "pkg/_secret.py": "x = 1\n",  # الحادثةُ نفسُها: وحدةٌ تبدأ بشرطةٍ سفليّة وأُضيفت بـ`add -f`
        "pkg/__init__.py": "",  # يطابق `_*.py` لكنّ `!**/__init__.py` يُنقذه
        "pkg/ok.py": "y = 2\n",  # لا يطابق شيئاً
        "static/_helper.js": "//\n",  # الحكمُ ليس للبايثون وحدَه
        "data.csv": "a,b\n",  # مُسقَطٌ لكنّه ليس شيفرةً
    }
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
    subprocess.run([git, "init", "-q", str(tmp_path)], check=True)
    subprocess.run([git, "-C", str(tmp_path), "add", "-f", "--", ".gitignore", *files], check=True)

    dropped = tracked_but_ignored(tmp_path)

    assert dropped is not None
    assert [n for n in dropped if n.endswith(CODE_SUFFIXES)] == [
        "pkg/_secret.py",
        "static/_helper.js",
    ]
    assert "data.csv" in dropped, "غيرُ الشيفرة يراه git مُسقَطاً لكنّ الحارسَ لا يحكم عليه"
    assert "pkg/__init__.py" not in dropped, "الاستثناءُ `!**/__init__.py` يُنقذ مُهيِّئاتِ الحزم"
    assert "pkg/ok.py" not in dropped
