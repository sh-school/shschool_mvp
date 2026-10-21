#!/usr/bin/env python3
"""أرقامُ الجودة في سطرٍ واحد (W-20261003-008) — يطبعه CI في آخر وظيفة mypy ويطبعه أمرُ الفحص المحلّيّ، فيقارَن السطران حرفيّاً.

    python scripts/quality_numbers.py [--skip mypy ruff radon]

السطر:  أرقام الجودة: mypy=<أخطاء>/<ملفّات> (مسجَّل <ن>) · ruff=<مخالفات> · CC≥31=<دوالّ>
ما تعذّر قياسُه يُطبع «غير مقيس» ولا يُعدّ صفراً. قراءةٌ فقط: لا يغيّر شيئاً ولا يحكم (الحكمُ للوظائف الأصليّة)، وخروجُه 0 دائماً إلا مع `--strict` (للفحص المحلّيّ).
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys

UNMEASURED = "غير مقيس"
MYPY_RE = re.compile(r"mypy:\s*([\d,]+)\s*خطأً في\s*([\d,]+)\s*ملفّاً(?:\s*\(المسجَّل\s*([\d,]+)\))?")
RADON_EXCLUDE = "*/migrations/*,*/.venv/*,manage.py,scripts/*,*/scripts/*,tests/*,*/tests/*,*/management/commands/*"


def _num(text: str) -> int:
    return int(text.replace(",", ""))


def parse_mypy(out: str) -> str | None:
    """«أخطاء/ملفّات (مسجَّل ن)» من سطر tests.mypy_ratchet؛ None إن لم يوجد السطر."""
    m = MYPY_RE.search(out)
    if not m:
        return None
    base = f" (مسجَّل {_num(m.group(3))})" if m.group(3) else ""
    return f"{_num(m.group(1))}/{_num(m.group(2))}{base}"


def parse_ruff(out: str) -> int | None:
    """عددُ المخالفات من `ruff check --output-format=concise`: سطرٌ لكلّ مخالفة؛ «All checks passed!» ⇒ 0."""
    if "All checks passed" in out:
        return 0
    n = sum(1 for line in out.splitlines() if re.match(r".+:\d+:\d+: ", line))
    return n if n else None


def parse_radon(out: str) -> int:
    """عددُ الدوالّ في الدرجة E فأسوأ من `radon cc --min E` (سطرٌ لكلّ دالّة بمسافة بادئة أو بعلامة F/M/C)."""
    return sum(1 for line in out.splitlines() if re.match(r"\s+[FMC]\s+\d+:\d+\s", line))


def _run(cmd: list[str], timeout: int = 600) -> str | None:
    try:
        p = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout
        )  # noqa: S603 — أوامرُ ثابتة من هذا الملفّ
    except (OSError, subprocess.TimeoutExpired):
        return None
    if "No module named" in p.stderr and p.returncode:
        return None
    return p.stdout + p.stderr


def measure(skip: set[str], run=_run) -> dict[str, str]:
    out: dict[str, str] = {}
    if "mypy" not in skip:
        text = run([sys.executable, "-m", "tests.mypy_ratchet"])
        out["mypy"] = (parse_mypy(text) if text else None) or UNMEASURED
    if "ruff" not in skip:
        text = run([sys.executable, "-m", "ruff", "check", ".", "--output-format=concise"])
        n = parse_ruff(text) if text else None
        out["ruff"] = UNMEASURED if n is None else str(n)
    if "radon" not in skip:
        text = run(
            [sys.executable, "-m", "radon", "cc", ".", "--exclude", RADON_EXCLUDE, "--min", "E"]
        )
        out["CC≥31"] = UNMEASURED if text is None else str(parse_radon(text))
    return out


def line(values: dict[str, str]) -> str:
    return "أرقام الجودة: " + " · ".join(f"{k}={v}" for k, v in values.items())


def breaches(values: dict[str, str]) -> list[str]:
    """ما يخالف حكمَ البوّابة بين القيم المقيسة (غير المقيس لا يُعدّ مخالفة هنا): mypy فوق المسجَّل، ruff أو CC فوق صفر."""
    out = []
    m = re.match(r"(\d+)/\d+(?: \(مسجَّل (\d+)\))?", values.get("mypy", ""))
    if m and m.group(2) and int(m.group(1)) > int(m.group(2)):
        out.append("mypy فوق المسجَّل")
    for key in ("ruff", "CC≥31"):
        if values.get(key, "").isdigit() and int(values[key]) > 0:
            out.append(f"{key} فوق الصفر")
    return out


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--strict", action="store_true", help="خروج 1 إن خالف رقمٌ مقيسٌ حكمَ البوّابة")
    ap.add_argument("--skip", nargs="*", default=[], choices=["mypy", "ruff", "radon"])
    a = ap.parse_args(argv)
    values = measure(set(a.skip))
    print(line(values))
    bad = breaches(values) if a.strict else []
    for b in bad:
        print(f"✘ {b}", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
