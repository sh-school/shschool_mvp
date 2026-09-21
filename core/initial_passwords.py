"""كلماتُ المرور الأوّليّةُ للحسابات التي تُنشئها المنصّة — عشوائيّةٌ لا مشتقّةٌ.

قرارُ المالك: كلمةُ المرور الأوّليّةُ **لا تساوي الرقمَ الشخصيّ** ولا أيَّ قيمةٍ
يعرفها غيرُ صاحبها أو يخمّنها. الرقمُ الشخصيُّ يعرفه المعلّمُ والوليُّ والإدارةُ
وأيُّ ورقةٍ في المدرسة، فحسابٌ كلمتُه رقمُه مفتوحٌ لكلّ من يعرف الاسم.

## العقد

- `make_initial_password()` كلمةٌ عشوائيّةٌ من `secrets` (لا `random`)، 14 خانةً
  من أبجديّةٍ بلا ملتبسٍ بصريّاً (لا O ولا 0 ولا l ولا 1 ولا I)، وتُرضي
  `StrongPasswordValidator` بالبناء: حرفٌ من كلّ صنف.
- تُعرض الكلمةُ **مرّةً واحدةً** لمن أنشأ الحساب (ورقةٌ في الاستجابة نفسها) ولا
  تُخزَّن نصّاً في أيّ مكان: لا قاعدةَ ولا جلسةَ ولا سجلَّ تدقيقٍ ولا سجلَّ
  تطبيق. ومن ضاعت منه فلا استرجاع — تُصدَر له أخرى.
- `must_change_password` مرفوعٌ: أوّلُ دخولٍ يُلزمه بتغييرها (سياسةُ التدوير).
"""

from __future__ import annotations

import csv
import secrets
from collections.abc import Iterable
from typing import Any

#: أبجديّةٌ بلا ملتبسٍ بصريّاً: الكلمةُ تُقرأ من ورقةٍ وتُكتب بيدٍ.
LETTERS_UPPER = "ABCDEFGHJKLMNPQRSTUVWXYZ"  # pragma: allowlist secret — أبجديّةٌ لا سرّ
LETTERS_LOWER = "abcdefghijkmnpqrstuvwxyz"  # pragma: allowlist secret — أبجديّةٌ لا سرّ
DIGITS = "23456789"
SYMBOLS = "!@#$%*-+=?"
LENGTH = 14


def make_initial_password() -> str:
    """كلمةٌ تُرضي المدقّق بالبناء لا بالمحاولة: حرفٌ من كلّ صنفٍ ثمّ الباقي."""
    pools = (LETTERS_UPPER, LETTERS_LOWER, DIGITS, SYMBOLS)
    chars = [secrets.choice(pool) for pool in pools]
    everything = "".join(pools)
    chars += [secrets.choice(everything) for _ in range(LENGTH - len(pools))]
    # الخلطُ ضروريّ: بلا مزجٍ يقع الرمزُ رابعاً دائماً فيصير النمطُ معروفاً.
    secrets.SystemRandom().shuffle(chars)
    # لا تبدأ بـ = + - @ (تُقرأ صيغةً في Excel عند فتح الورقة) — فتُبدَّل بأوّل غير رمز.
    if chars[0] in SYMBOLS:
        swap = next(i for i, c in enumerate(chars) if c not in SYMBOLS)
        chars[0], chars[swap] = chars[swap], chars[0]
    return "".join(chars)


def assign_initial_password(user: Any, issued: list, role_label: str) -> str:
    """يضع على حسابٍ **جديدٍ** كلمةً عشوائيّةً ويرفع `must_change_password`.

    لا يحفظ (`save()` على المستدعي)، ويُضيف صفَّ ورقة الاعتماد إلى `issued`
    (الرقمُ مستورٌ). الكلمةُ تبقى في هذه القائمة في الذاكرة وحدَها.
    """
    from core.privacy import mask_national_id

    password = make_initial_password()
    user.set_password(password)
    user.must_change_password = True
    issued.append(
        {
            "role": role_label,
            "nid": mask_national_id(user.national_id),
            "name": user.full_name,
            "password": password,
        }
    )
    return password


def write_credentials_csv(path: str, rows: Iterable[dict]) -> int:
    """يكتب ورقةَ الاعتماد إلى ملفٍّ محلّيٍّ (للأوامر الإداريّة) ويُعيد عددَ الصفوف.

    الملفُّ سرٌّ: يُنشأ بصلاحيةٍ للمالك وحدَه حيث يدعمها النظام، ولا يُستعمل في
    مسارٍ ويبيّ — الويبُ يعرض الورقةَ في استجابته ولا يكتب شيئاً.
    """
    import os

    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    count = 0
    with os.fdopen(fd, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["الدور", "الرقم الشخصي", "الاسم", "كلمة المرور"])
        for row in rows:
            # كلمةُ المرور لا تُعقَّم: لا تبدأ بحرف صيغةٍ بالبناء، وتعقيمُها يفسدها.
            writer.writerow(
                [
                    _safe_cell(row["role"]),
                    _safe_cell(row["nid"]),
                    _safe_cell(row["name"]),
                    row["password"],
                ]
            )
            count += 1
    return count


def _safe_cell(value: str) -> str:
    """يمنع حقنَ الصيغ في Excel: خليّةٌ تبدأ بـ = + - @ تُسبَق بفاصلةٍ عليا."""
    text = str(value)
    return "'" + text if text[:1] in ("=", "+", "-", "@") else text
