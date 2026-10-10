"""[CLOCK] سقّاطةُ تثبيت الساعة في الاختبارات (W-20261008-021).

اختبارٌ يقرأ «اليوم» بلا تثبيت يفشل بحسب يوم تشغيله بلا أن يتغيّر فيه حرف (مثالُه حارس VI-13: ثماني لقطاتٍ على رأسٍ لم يتغيّر).
هنا يُعدّ بشجرة `ast` عددُ ملفّات الاختبار التي تقرأ الساعة مباشرةً ولا تثبّتها، ويسقط الحارسُ على أيّ زيادةٍ — فالملفّ الجديد
يُكتب مثبَّتاً (`pytestmark = pytest.mark.pin_clock`، المرفق في `tests/conftest.py`) أو لا يقرأ «اليوم».

**المعنى بالأرقام** (يُطبع عند الفشل ويُعاد قياسُه، لا يُنقل):

- `CEILING` = ملفّاتُ اختبارٍ تحت `tests/` تستدعي `timezone.now/localdate/localtime` أو `date.today` أو `datetime.now/today/utcnow`
  (أو اسماً مستورداً من `django.utils.timezone`) **ولا أثرَ في المجموعة** لـ`pin_clock` ولا `frozen_clock` ولا `freeze_time`
  ولا `time_machine` ولا `patch("…timezone.now")`. هي حدٌّ أعلى للحساسيّة لليوم: ملفٌّ يقرأ اليومَ لا يفشل بالضرورة، لكنّه قادر.
- من هذه الملفّات `DIRECT_TODAY` تقرأ `date.today()`/`datetime.now()` المباشرتين، ولا تصل إليهما `frozen_clock` (تثبّت `timezone.now`
  وما يتبعه فقط)؛ فتثبيتُها يحتاج تحويلَ القراءة إلى `timezone` أوّلاً. وهي خارج ما تعالجه العلامة.

لا يعدّ الحارسُ التطبيقَ ولا الحسّاسيّةَ الفعليّة: ما يُقاس أنّ الملفّ **يقرأ** الساعةَ دون تثبيتٍ ظاهر. والحسّاسيّةُ الفعليّة تكشفها
الوظيفةُ الليليّة `clock-sensitivity` في `nightly.yml` (تشغيلُ المجموعة بـ`SCHOOLOS_TEST_NOW` يومَ جمعةٍ ثمّ يومَ خميس، وتُبلغ ولا تحجب).

تثبيتُ النقص: إذا نقص العددُ (ثُبّتَ ملفّ) يسقط الحارسُ كذلك حتى يُخفَّض `CEILING` — فلا يبقى التحسّنُ هامشاً يُملأ بملفٍّ جديد.
"""

from __future__ import annotations

import ast
import datetime as dt
import os
import pathlib
import re

import pytest
from django.utils import timezone

from tests.visual_snapshots import FIXED_NOW

TESTS = pathlib.Path(__file__).resolve().parent

#: اللحظةُ المقيسةُ 2026-10-10 بهذه الأداة على 631 ملفَّ اختبار: 79 تقرأ الساعةَ بلا تثبيت، و69 بعد تثبيت عشرةٍ أخطرها.
CEILING = 69
#: من الـ`CEILING` ما يقرأ `date.today()`/`datetime.now()` المباشرتين (لا تصلهما `frozen_clock`).
DIRECT_TODAY = 21

CLOCK_ATTRS = {"now", "localdate", "localtime", "today", "utcnow"}
CLOCK_RECEIVERS = {"timezone", "date", "datetime", "dt"}
TIMEZONE_NAMES = {"now", "localdate", "localtime"}
PIN_NAMES = {"pin_clock", "frozen_clock", "freeze_time", "time_machine"}
PIN_PATCH = re.compile(r"timezone\.(now|localdate|localtime)$")


def _tree(path: pathlib.Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):
        return None


def _reads_the_clock(tree: ast.AST) -> tuple[bool, bool]:
    """(يقرأ الساعة، يقرأ date.today()/datetime.now() المباشرتين)."""
    imported = {
        alias.asname or alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "django.utils.timezone"
        for alias in node.names
        if alias.name in TIMEZONE_NAMES
    }
    reads = direct = False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Attribute) and func.attr in CLOCK_ATTRS:
            receiver = ast.unparse(func.value).rsplit(".", 1)[-1]
            if receiver in CLOCK_RECEIVERS:
                reads = True
                direct = direct or receiver != "timezone"
        elif isinstance(func, ast.Name) and func.id in imported:
            reads = True
    return reads, direct


def _is_pinned(tree: ast.AST) -> bool:
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in PIN_NAMES:
            return True
        if isinstance(node, ast.Attribute) and node.attr in PIN_NAMES:
            return True
        if (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and PIN_PATCH.search(node.value)
        ):
            return True
    return False


def measure(root: pathlib.Path = TESTS) -> tuple[list[str], list[str]]:
    """(ملفّاتٌ تقرأ الساعة بلا تثبيت، منها ما يقرأ date.today()/datetime.now() مباشرةً) — أسماؤُها نسبةً إلى `root`."""
    unpinned: list[str] = []
    direct_files: list[str] = []
    for path in sorted(root.rglob("test_*.py")):
        tree = _tree(path)
        if tree is None:
            continue
        reads, direct = _reads_the_clock(tree)
        if reads and not _is_pinned(tree):
            name = path.relative_to(root).as_posix()
            unpinned.append(name)
            if direct:
                direct_files.append(name)
    return unpinned, direct_files


def test_no_test_file_reads_the_clock_without_a_pin_beyond_the_ceiling():
    unpinned, _direct = measure()
    assert len(unpinned) <= CEILING, (
        f"زاد عددُ ملفّات الاختبار التي تقرأ «اليوم» بلا تثبيت: {len(unpinned)} > {CEILING}. ثبّت الملفَّ الجديد بـ"
        "`pytestmark = pytest.mark.pin_clock` (tests/conftest.py)، أو اقرأ التاريخَ من الاختبار نفسِه لا من الساعة. "
        "الملفّات:\n  " + "\n  ".join(unpinned)
    )


def test_a_pinned_file_lowers_the_ceiling_so_the_gain_cannot_be_spent_again():
    unpinned, direct = measure()
    assert len(unpinned) >= CEILING and len(direct) >= DIRECT_TODAY, (
        f"نقص العددُ ({len(unpinned)} من {CEILING}؛ مباشرة {len(direct)} من {DIRECT_TODAY}) — أحسنت؛ "
        "اخفض `CEILING` و`DIRECT_TODAY` في tests/test_clock_pin_ratchet.py إلى الرقمين الجديدين."
    )


class TestTheCounter:
    def _count(self, tmp_path, **sources):
        for name, source in sources.items():
            (tmp_path / f"test_{name}.py").write_text(source, encoding="utf-8")
        return measure(tmp_path)

    def test_timezone_and_direct_reads_are_counted_and_the_direct_ones_apart(self, tmp_path):
        unpinned, direct = self._count(
            tmp_path,
            tz="from django.utils import timezone\n\ndef test_a():\n    assert timezone.localdate()\n",
            raw="import datetime as dt\n\ndef test_a():\n    assert dt.date.today()\n",
            imported="from django.utils.timezone import now\n\ndef test_a():\n    assert now()\n",
            clean="def test_a():\n    assert 1\n",
        )
        assert unpinned == ["test_imported.py", "test_raw.py", "test_tz.py"]
        assert direct == ["test_raw.py"]

    def test_every_form_of_pin_is_recognised(self, tmp_path):
        unpinned, _ = self._count(
            tmp_path,
            marker="import pytest\nfrom django.utils import timezone\npytestmark = pytest.mark.pin_clock\n"
            "def test_a():\n    timezone.now()\n",
            frozen="from tests.visual_snapshots import frozen_clock\nfrom django.utils import timezone\n"
            "def test_a():\n    with frozen_clock():\n        timezone.now()\n",
            patched="from unittest import mock\nfrom django.utils import timezone\n"
            "def test_a():\n    with mock.patch('django.utils.timezone.now'):\n        timezone.now()\n",
            freezegun="from freezegun import freeze_time\nfrom django.utils import timezone\n"
            "@freeze_time('2026-10-07')\ndef test_a():\n    timezone.now()\n",
        )
        assert unpinned == []

    def test_a_comment_or_a_string_is_not_a_read(self, tmp_path):
        unpinned, _ = self._count(
            tmp_path,
            text='# timezone.now() يُذكر هنا\nTEXT = "date.today()"\ndef test_a():\n    assert TEXT\n',
        )
        assert unpinned == []


# ── المرفق نفسُه (العلامة pin_clock في tests/conftest.py) ──


@pytest.mark.pin_clock
def test_the_marker_pins_now_and_localdate_to_the_ordinary_wednesday():
    assert timezone.now() == FIXED_NOW
    assert timezone.localdate() == dt.date(2026, 10, 7)
    assert timezone.localtime().weekday() == 2


FRIDAY = FIXED_NOW + dt.timedelta(days=2)


@pytest.mark.pin_clock(FRIDAY)
def test_the_marker_accepts_another_instant():
    assert timezone.localdate() == dt.date(2026, 10, 9)
    assert timezone.localtime().weekday() == 4


@pytest.mark.skipif(
    bool(os.environ.get("SCHOOLOS_TEST_NOW")), reason="الوظيفةُ الليليّة تثبّت كلَّ اختبار"
)
def test_the_clock_is_back_to_the_real_one_after_a_pinned_test():
    assert timezone.now() != FIXED_NOW
    assert abs((timezone.now() - dt.datetime.now(dt.UTC)).total_seconds()) < 60
