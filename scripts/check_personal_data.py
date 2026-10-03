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

ما تغيّر يوم 2026-10-03 (W-20261003-005، قرارُ المالك D-158م): `docs/` وملفّاتُ `.md` داخلةٌ في الفحص — وهي تدخل
صورةَ الإنتاج وتُنشر مع المستودع العامّ، وكان استثناؤُها ثغرةً بلا حارس. (المقيس يومها: 245 ملفّاً md/docs ← صفرُ التقاط.)
  · **وضعُ تحذير** حتى `WARN_UNTIL` (2026-10-10): الالتقاطُ في md/docs وحدَها يطبع `::warning::` ويخرج 0؛ أمّا الكودُ
    والاختباراتُ فتبقى فشلاً كما كانت. وبعد التاريخ فشلٌ في كلّ شيء (والتاريخُ يُحقَن في الاختبار).
  · **استثناءٌ مسمّى** `EXCEPT_MD`: مسارٌ ← سببٌ مكتوب (فارغةٌ اليوم) — لا استثناءَ بلا سبب.
  · **استثناءٌ سياقيّ:** رقمٌ من 11 خانةً يسبقه «run» أو «runs/» أو «job» أو «jobs/» معرّفُ CI لا هويّة، فيُعفى بالسياق
    لا بقائمة أرقام (نمطٌ حقيقيٌّ يظهر في الوثائق).
  · **حدٌّ معروف:** الاستثناءُ السياقيّ يُتجاوز بكتابة «job» قبل رقمٍ حقيقيّ (يمنع الحوادثَ لا الخصمَ المتعمّد). والحارسُ لا يغطّي **الأسماء** — قائمةُ الأسماء الحقيقيّة بياناتٌ شخصيّةٌ لا تُودَع في مستودعٍ عامّ؛
    فحصُ الأسماء محلّيٌّ عند جلستَي الخصوصيّة (0105/0412) لا هنا.
  · ملفٌّ فوق `MAX_BYTES` أو ثنائيٌّ **يُسمّى في المخرج** (لا يُتخطّى صامتاً) ليُقرَّر إدراجُه أو استثناؤُه بسبب.

الاستعمال:  python scripts/check_personal_data.py [--root .]      (يخرج بـ1 إن وُجد رمزٌ خارج السماح)
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from datetime import date
from pathlib import Path
from typing import NamedTuple

ID_RE = re.compile(r"(?<![0-9A-Za-z_])[23][0-9]{10}(?![0-9A-Za-z_])")
PHONE_RE = re.compile(r"\+974[0-9]{8}(?![0-9])")

#: ما لا يُفحص: محتوًى ثابتٌ ومُولَّد (وtests/ وdocs/ و`.md` داخلةٌ في الفحص منذ W-20261003-005).
EXCLUDED = re.compile(r"^static/|/migrations/|\.lock$|(^|/)package-lock\.json$")

#: ما يُعَدّ «وثيقةً» لوضع التحذير: ملفُّ md أو أيُّ ملفٍّ تحت docs/ (بأيّ امتداد).
DOCS = re.compile(r"^docs/|\.md$")

#: آخرُ يومٍ بوضع التحذير للوثائق؛ بعده فشلٌ (يُحقَن في الاختبار).
WARN_UNTIL = date(2026, 10, 10)

#: استثناءاتٌ مسمّاةٌ للوثائق: مسارٌ ← سببٌ مكتوب (فارغةٌ اليوم — لا استثناءَ بلا سبب).
EXCEPT_MD: dict[str, str] = {}

#: معرّفُ تشغيلٍ أو مهمّةٍ في CI لا هويّةٌ: يسبق الرقمَ «run» أو «runs/» أو «job» أو «jobs/» (فراغٌ أو `#` اختياريّ).
CI_ID_CONTEXT = re.compile(r"(?:\brun|\bruns/|\bjob|\bjobs/)[ \t#]*$", re.IGNORECASE)

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


def is_ci_identifier(line: str, start: int) -> bool:
    """الرقمُ يسبقه مباشرةً «run»/«job»… ⇒ معرّفُ CI لا هويّةٌ (يُعفى بالسياق)."""
    return bool(CI_ID_CONTEXT.search(line[:start]))


def is_allowed(token: str) -> bool:
    if token in ALLOWED or is_synthetic(token):
        return True
    return any(rng.fullmatch(token) for rng in ALLOWED_RANGES)


def scan_text(path: str, text: str) -> list[Violation]:
    """الرموزُ المخالِفة في نصٍّ واحد (الحكمُ على كلّ رمزٍ لا على السطر)."""
    found: list[Violation] = []
    for number, line in enumerate(text.splitlines(), 1):
        for match in list(ID_RE.finditer(line)) + list(PHONE_RE.finditer(line)):
            token = match.group()
            if is_allowed(token) or is_ci_identifier(line, match.start()):
                continue
            found.append(Violation(path, number, token))
    return found


def is_excluded(path: str) -> bool:
    return bool(EXCLUDED.search(path)) or path in EXCEPT_MD


def is_document(path: str) -> bool:
    return bool(DOCS.search(path))


def tracked_files(root: Path) -> list[str]:
    # أمرُ git ثابتٌ بلا مدخلٍ خارجيّ
    result = subprocess.run(
        ["git", "ls-files", "-z"],  # noqa: S603, S607
        cwd=root,
        capture_output=True,
        check=True,
    )
    return [p.decode("utf-8", "replace") for p in result.stdout.split(b"\0") if p]


def scan_repo(root: Path, skipped: list[str] | None = None) -> list[Violation]:
    """المخالفاتُ في المتتبَّع؛ وما تُخطّي لحجمه أو لأنّه ثنائيٌّ يُضاف إلى `skipped` ليُسمّى."""
    found: list[Violation] = []
    for rel in tracked_files(root):
        if is_excluded(rel):
            continue
        try:
            data = (root / rel).read_bytes()
        except OSError:
            continue
        if len(data) > MAX_BYTES:
            if skipped is not None:
                skipped.append(rel)
            continue
        if b"\0" in data[:4096]:
            continue
        found.extend(scan_text(rel, data.decode("utf-8", "replace")))
    return found


def main(argv: list[str] | None = None, today: date | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", default=".", type=Path)
    args = parser.parse_args(argv)
    today = today or date.today()
    skipped: list[str] = []
    found = scan_repo(args.root, skipped)
    for rel in skipped:
        print(
            f"::notice::تُخطّي {rel} (فوق {MAX_BYTES} بايت) — يُقرَّر إدراجُه أو استثناؤُه بسبب في EXCEPT_MD."
        )
    if not found:
        print("لا أرقامَ شخصيّةً ولا جوّالاتٍ بهيئة الحقيقيّ في الملفّات المتتبَّعة.")
        return 0
    warn_window = today <= WARN_UNTIL
    # في نافذة التحذير تُحذَّر الوثائقُ وحدَها؛ والكودُ والاختباراتُ فشلٌ كما كانت.
    failing = [v for v in found if not (warn_window and is_document(v.path))]
    warning = [v for v in found if v not in failing]
    if warning:
        print(
            f"::warning::أرقامٌ تشبه الحقيقيّة في وثائق (md/docs) — فشلٌ بعد {WARN_UNTIL.isoformat()}، فأزِلها أو اجعلها اصطناعيّةً:"
        )
        for violation in warning:
            print(f"  {violation}")
    if not failing:
        return 0
    print("::error::أرقامٌ شخصيّةٌ أو جوّالاتٌ تشبه الحقيقيّة في ملفّاتٍ متتبَّعة — لا تُودَع في مستودعٍ عامّ:")
    for violation in failing:
        print(f"  {violation}")
    print(
        "في الاختبارات والوثائق اكتب رقماً اصطناعيّاً بأصفارٍ في وسطه (مثل 29000000031)، أو أضِف العيّنةَ إلى ALLOWED هنا."
    )
    return 1


if __name__ == "__main__":
    sys.exit(main())
