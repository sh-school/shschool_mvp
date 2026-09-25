#!/usr/bin/env python3
"""حارسُ البيانات الشخصيّة: لا رقمَ شخصيّاً ولا جوّالاً بهيئة الحقيقيّ في ملفٍّ متتبَّع — بما فيه tests/.

المستودعُ عامّ، وخطرُه الحقيقيُّ ليس نسخَ الكود بل أن يتسرّب ملفٌّ فيه أرقامٌ شخصيّةٌ أو جوّالاتٌ حقيقيّةٌ
بغلطةِ إيداع — فيصير حادثةَ PDPPL على الملأ. والبادئةُ `[23]` لا `2` وحدَها (ثغرةٌ سُدّت 2026-09-11): الرقمُ
القطريُّ يبدأ برقم القرن، فمواليدُ الألفيّة يبدأ رقمُهم بـ3 — وهم أكثرُ طلبة المدرسة.

ما تغيّر يوم 2026-09-25 (REP-07)، وسببُه ما وُجد حين فُحص التاريخ كلُّه:

  1. `tests/` داخلُ الفحص. كانت مستثناةً كلُّها، فبقي فيها رقمٌ شخصيٌّ حقيقيٌّ لمعلّم (ومعه اسمُه ورقمُه الوظيفيّ)
     ورقمٌ حقيقيٌّ آخر في اختبارٍ ثانٍ، وثلاثةٌ وعشرون رقماً بهيئة الحقيقيّ لم يرها أحد.
  2. الحكمُ على **الرمز** لا على السطر. كان `grep -v` يُسقط السطرَ كلَّه إن حوى رمزاً مسموحاً، فيمرّ معه رمزٌ حقيقيٌّ
     في السطر نفسه.
  3. لا يطبع رقماً كاملاً. كان يطبع الأسطرَ المخالِفة كما هي في سجلّ Actions — وهو عامٌّ — فيصير الكشفُ نفسُه تسريباً.

ما يُسمَح به (اصطناعيٌّ بنيويّاً، لا يقع في رقمٍ حقيقيّ):
  · عيّناتٌ معروفةٌ بأسمائها (`ALLOWED`).
  · رمزٌ فيه خمسةُ أصفارٍ متتاليةٍ فأكثر، أو ستُّ خاناتٍ متماثلةٍ متتالية: احتمالُ أن يكون رقماً حقيقيّاً ضئيلٌ جدّاً
    (رقمُ الجنسيّة ثلاثُ خاناتٍ لا أصفارَ فيها عادةً، والمتسلسلُ خمسُ خاناتٍ يبدأ بواحدٍ)، والحارسُ يمنع الخطأ لا القصد.
وقاعدةُ الكتابة الجديدة: في اختبارٍ جديد اكتب رقماً بأصفارٍ في وسطه، مثل 29000000031.

الاستعمال:  python scripts/check_personal_data.py [--root .]      (يخرج بـ1 إن وُجد رمزٌ خارج السماح)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path
from typing import NamedTuple

ID_RE = re.compile(r"(?<![0-9A-Za-z_])[23][0-9]{10}(?![0-9A-Za-z_])")
PHONE_RE = re.compile(r"\+974[0-9]{8}(?![0-9])")

#: ما لا يُفحص: وثائقُ ومحتوًى ثابتٌ ومُولَّدٌ (وtests/ داخلةٌ في الفحص).
EXCLUDED = re.compile(r"^(docs/|static/)|/migrations/|\.md$|\.lock$|(^|/)package-lock\.json$")

#: عيّناتٌ اصطناعيّةٌ معروفة (قائمةُ السماح القديمة في بوّابة الجودة) وأنماطٌ كُتبت بها اختباراتٌ قائمة.
ALLOWED = frozenset(
    {
        "29012345678",
        "29099999999",
        "28765432101",
        "28760000001",
        "28001234567",
        "29812345678",
        "28644012345",
        "28812345678",
        "28912345678",
        "29955500011",
        "+97466123456",
        "+97455512345",
        "+97455001122",
        "+97466778899",
    }
)
ALLOWED_RANGES = (re.compile(r"2900000000[0-9]"), re.compile(r"\+9745500000[0-9]"))

MAX_BYTES = 5 * 1024 * 1024


class Violation(NamedTuple):
    path: str
    line: int
    token: str

    @property
    def masked(self) -> str:
        """أوّلُ ثلاث خاناتٍ وآخرُ خانتين فقط — لا يُطبع رقمٌ كاملٌ في أيّ سجلّ."""
        head = 4 if self.token.startswith("+") else 3
        return f"{self.token[:head]}…{self.token[-2:]}"

    def __str__(self) -> str:
        return f"{self.path}:{self.line}: {self.masked}"


def is_synthetic(token: str) -> bool:
    """اصطناعيٌّ بنيويّاً: خمسةُ أصفارٍ متتالية، أو ستُّ خاناتٍ متماثلةٍ متتالية."""
    digits = token.lstrip("+")
    return "00000" in digits or re.search(r"([0-9])\1{5}", digits) is not None


def is_allowed(token: str) -> bool:
    if token in ALLOWED or is_synthetic(token):
        return True
    return any(rng.fullmatch(token) for rng in ALLOWED_RANGES)


def scan_text(path: str, text: str) -> list[Violation]:
    """الرموزُ المخالِفة في نصٍّ واحد (الحكمُ على كلّ رمزٍ لا على السطر)."""
    found: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        for token in ID_RE.findall(line) + PHONE_RE.findall(line):
            if not is_allowed(token):
                found.append(Violation(path, number, token))
    return found


def is_excluded(path: str) -> bool:
    return bool(EXCLUDED.search(path))


def tracked_files(root: Path) -> list[str]:
    # أمرُ git ثابتٌ بلا مدخلٍ خارجيّ
    result = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S603, S607
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [p.decode("utf-8", "replace") for p in result.stdout.split(b"\0") if p]


def scan_repo(root: Path) -> list[Violation]:
    found: list[Violation] = []
    for rel in tracked_files(root):
        if is_excluded(rel):
            continue
        try:
            data = (root / rel).read_bytes()
        except OSError:
            continue
        if len(data) > MAX_BYTES or b"\0" in data[:4096]:
            continue
        found.extend(scan_text(rel, data.decode("utf-8", "replace")))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    args = parser.parse_args(argv)
    found = scan_repo(args.root)
    if not found:
        print("لا أرقامَ شخصيّةً ولا جوّالاتٍ بهيئة الحقيقيّ في الملفّات المتتبَّعة.")
        return 0
    print("::error::أرقامٌ شخصيّةٌ أو جوّالاتٌ تشبه الحقيقيّة في ملفّاتٍ متتبَّعة — لا تُودَع في مستودعٍ عامّ:")
    for violation in found:
        print(f"  {violation}")
    print(
        "في الاختبارات اكتب رقماً اصطناعيّاً بأصفارٍ في وسطه (مثل 29000000031)، أو أضِف العيّنةَ إلى ALLOWED هنا."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
