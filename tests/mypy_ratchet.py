"""سقّاطةُ الأنواع — أخطاءُ mypy المسجَّلةُ لكلّ ملفٍّ لا تزيد، وما نقص يُثبَّت نقصُه.

كانت وظيفةُ mypy في بوّابة الجودة تُشغّله بـ`| head -50 || true` ثمّ تطبع
`::warning` — فتخضرّ مهما أخرج، والملخّصُ يكتب PASS لفحصٍ لم يحكم قطّ. وإعدادُ
`pyproject.toml` صارمٌ (`disallow_untyped_defs`…) على شيفرةٍ كُتب أكثرُها بلا
أنواع، فالصفرُ لا يُبلَغ في طلب دمجٍ واحد. فالحارسُ هنا كحارس الهويّة البصريّة
(`tests/design_ratchet.py`): لا يطلب الصفرَ بل يمنع الزيادة:

* لكلّ ملفٍّ عددُه المسجَّل من أخطاء mypy. **زاد** → يسقط البناء.
* **نقص** → يسقط كذلك حتّى يُسجَّل العددُ الجديد، فالتحسّنُ لا يبقى هامشاً يُملأ.
* ملفٌّ جديدٌ عددُه المسجَّل صفر — فما يُكتب اليوم يُكتب بأنواعه.
* وmypy إن سقط هو نفسُه (خطأُ إعدادٍ أو انهيار) فالسقّاطةُ تسقط بصوتٍ عالٍ —
  لا «صفرُ أخطاء» لفحصٍ لم يجرِ.

الإعدادُ من `pyproject.toml` (`[tool.mypy]`) بلا أعلامٍ تُخفّفه في CI، والنطاقُ
هو ما كانت البوّابةُ تدّعي فحصَه: `core/` و`shschool/`.

وتسجيلُ الأعداد بعد تحسينٍ مقصود:

    python -m tests.mypy_ratchet --update

والملفُّ الناتج يُراجَع في طلب الدمج كأيّ شيفرة: سطرٌ زاد فيه عددٌ هو قرارٌ
يُسأل عنه، لا ضجيج.
"""

from __future__ import annotations

import json
import pathlib
import re
import subprocess
import sys
from collections import Counter

BASELINE = pathlib.Path("tests/mypy_ratchet_baseline.json")

#: ما تدّعي البوّابةُ فحصَه — وما تفحصه فعلاً.
TARGETS = ("core", "shschool", "governance")

#: `path:line: error: message  [code]` — سطرُ mypy بلا `--pretty`.
ERROR_LINE = re.compile(r"^(?P<path>[^:\n]+):\d+(?::\d+)?: error: ")


def run_mypy(targets: tuple[str, ...] = TARGETS) -> tuple[int, str]:
    """(رمزُ الخروج، المخرَجات) — mypy بإعداد pyproject.toml وحدَه."""
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "mypy",
            *targets,
            "--no-error-summary",
            "--no-pretty",
            "--show-error-codes",
            "--no-color-output",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return proc.returncode, proc.stdout + proc.stderr


def parse(output: str) -> dict[str, int]:
    """الملفُّ ← عددُ أخطائه. المساراتُ بشرطةٍ أماميّة كي يتّفق ويندوز ولينكس."""
    counts: Counter[str] = Counter()
    for line in output.splitlines():
        match = ERROR_LINE.match(line)
        if match:
            counts[match.group("path").replace("\\", "/")] += 1
    return dict(sorted(counts.items()))


def measure() -> dict[str, int]:
    """يُجري mypy ويعدّ. رمزُ خروجٍ غيرُ 0 و1 — انهيارٌ أو إعدادٌ معطوب — يُرفع لا يُبتلع."""
    code, output = run_mypy()
    if code not in (0, 1):
        raise RuntimeError(f"mypy لم يُكمل الفحص (رمز الخروج {code}):\n{output[-4000:]}")
    counts = parse(output)
    if code == 1 and not counts:
        raise RuntimeError(f"mypy أعلن خطأً ولم يُقرأ سطرُ خطأٍ واحد:\n{output[-4000:]}")
    return counts


def compare(baseline: dict[str, int], current: dict[str, int]) -> tuple[list[str], list[str]]:
    """(ما زاد، ما نقص ولم يُسجَّل) — كلٌّ سطرٌ يُقرأ."""
    worse, stale = [], []
    for path in sorted(set(baseline) | set(current)):
        was, is_ = baseline.get(path, 0), current.get(path, 0)
        if is_ > was:
            worse.append(f"{path}: {was} → {is_}")
        elif is_ < was:
            stale.append(f"{path}: {was} → {is_}")
    return worse, stale


def load_baseline() -> dict[str, int]:
    return json.loads(BASELINE.read_text(encoding="utf-8"))["files"]


#: الإصداراتُ الثابتةُ لفاحص الأنواع — مصدرٌ واحدٌ يقرؤه CI وrequirements-dev.txt (OWN-30).
PINS = pathlib.Path("requirements-mypy.txt")
PINNED = ("mypy", "django-stubs", "djangorestframework-stubs")


def pinned_version(name: str) -> str:
    """إصدارُ الحزمة في requirements-mypy.txt (سطرُ `name==x.y.z`)."""
    for line in PINS.read_text(encoding="utf-8").splitlines():
        match = re.match(rf"^{re.escape(name)}==(\S+?)\s*(?:#.*)?$", line.strip())
        if match:
            return match.group(1)
    raise RuntimeError(f"{name} غيرُ مثبَّتٍ بـ`==` في {PINS}")


def installed_version(name: str) -> str:
    """الإصدارُ المثبَّت في هذه البيئة، أو فارغٌ إن غابت الحزمة."""
    from importlib.metadata import PackageNotFoundError, version

    try:
        return version(name)
    except PackageNotFoundError:
        return ""


def version_skew() -> list[str]:
    """أسطرٌ تصف ما يخالف الإصداراتِ الثابتة في هذه البيئة — فارغةٌ إن طابقت (وهذا حالُ CI دائماً)."""
    return [
        f"{name}: الثابتُ {pinned_version(name)}، والمثبَّتُ عندك {installed_version(name) or 'غائب'}"
        for name in PINNED
        if installed_version(name) != pinned_version(name)
    ]


def main(argv: list[str]) -> int:
    skew = version_skew()
    if skew and "--update" in argv:
        # عددٌ يخرج من إصدارٍ لا تحكم به البوّابة يُسجَّل فيُسقط الطلبَ (أو يخضرّ زوراً) — وقد وقع: التطويرُ على
        # mypy 2.3.1 والبوّابةُ على 1.10.0. فلا تسجيلَ إلّا بالإصدارات الثابتة نفسِها.
        print(
            "رُفض --update: إصداراتُ الفاحص عندك غيرُ الثابتة في requirements-mypy.txt (ما تحكم به البوّابة):"
        )
        for line in skew:
            print(f"  {line}")
        print(
            "ثبّتها (pip install -r requirements-mypy.txt) ثمّ أعِد الأمر. لا يُسجَّل عددٌ من إصدارٍ آخر."
        )
        return 2
    for line in skew:
        print(f"تحذير: {line} — قد تخالف الأعدادُ ما تراه البوّابة؛ لا تسجّل بهذه البيئة.")
    current = measure()
    if "--update" in argv:
        BASELINE.write_text(
            json.dumps(
                {"total": sum(current.values()), "files": current},
                ensure_ascii=False,
                indent=1,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )
        print(f"mypy: {sum(current.values())} خطأً في {len(current)} ملفّاً — سُجِّلت.")
        return 0
    worse, stale = compare(load_baseline(), current)
    for line in worse:
        print(f"زاد: {line}")
    for line in stale:
        print(f"نقص ولم يُسجَّل (python -m tests.mypy_ratchet --update): {line}")
    total = sum(current.values())
    print(f"mypy: {total} خطأً في {len(current)} ملفّاً (المسجَّل {sum(load_baseline().values())}).")
    return 1 if worse or stale else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
