"""المدرسةُ الوهميّةُ الثانيةُ على 8500 — التعريفُ الواحدُ والحارس (W-20261004-006، قرارُ المالك D-190م/D-191م).

مدرسةٌ كاملةُ الأدوار تُبذر **على قاعدة المعاينة وحدَها** لتجريب كلّ دورٍ بلا لمس الإنتاج، وبجانب المدرسة الأولى (حساباتُ
`core/preview_accounts.py` العشرةُ). فهذا الملفُّ يجمع ما يتّفق عليه البذرُ والحارسُ والاختبار:

1. **رمزُ المدرسة والوسمُ**: `SCHOOL_CODE` واسمٌ يبدأ بـ«[وهميّ»؛ `is_preview_school` يطلب الشقّين معاً (كالوسم المركَّب للحسابات).
2. **اثنا عشر دوراً** `ROLES`: العشرةُ القائمةُ في `preview_accounts.ROLES` + `social_worker` + `psychologist` (الدوران الإضافيّان
   بقرار التنفيذ، بطاقة 006 افتراضٌ 4: لا platform_developer ولا superuser ولا is_staff).
3. **رقمُ الدخول** `PV-s2-<الدور>` (فيبقى الوسمُ المركَّب فتُحجب الحساباتُ خارج المعاينة)، والرقمُ الوظيفيّ ثمانُ خاناتٍ من نطاقٍ
   مخصَّصٍ `99800001–99800012` يفترق عن نطاق المدرسة الأولى (`99900001–99900010`) وعن الحقيقيّ.
4. **ما يُحجب**: يدخل النطاقُ في `core.preview_accounts.RESERVED_EMPLOYEE_REGEX` فيرفض الحقنُ 8500←الإنتاج كلَّ صفٍّ منه.

كلمةُ المرور من `PREVIEW_ACCOUNTS_PASSWORD` (كحسابات المدرسة الأولى) — لا كلمةَ في كودٍ ولا اختبار.
"""

from __future__ import annotations

from typing import Any

from core.preview_accounts import FULL_NAME_PREFIX, NAME_PREFIX
from core.preview_accounts import ROLES as FIRST_SCHOOL_ROLES

SCHOOL_CODE = "PVS"
SCHOOL_NAME = f"{FULL_NAME_PREFIX}مدرسة المعاينة الثانية"
#: بادئةُ رقم الدخول للمدرسة الثانية — تحمل «PV-» فيبقى الوسمُ المركَّبُ للمصيدة.
ID_PREFIX = "PV-s2-"

#: الدورُ ← رقمُ الدخول. العشرةُ الأولى من قائمة المدرسة الأولى المغلقة، والاثنان الإضافيّان بقرارٍ مسجَّل.
EXTRA_ROLES = ("social_worker", "psychologist")
#: حقلُ national_id حدُّه 20 خانة: «PV-s2-» + رقمُ الدور بخانتين (اسمُ الدور الطويل لا يتّسع).
ROLES: dict[str, str] = {
    role: f"{ID_PREFIX}{index:02d}"
    for index, role in enumerate((*FIRST_SCHOOL_ROLES, *EXTRA_ROLES), start=1)
}
#: الرقمُ الوظيفيّ (ما يُكتب في حقل الدخول): ثمانُ خاناتٍ `99800001–99800012` بترتيب `ROLES`.
EMPLOYEE_NUMBERS: dict[str, str] = {
    role: f"998{index:05d}" for index, role in enumerate(ROLES, start=1)
}
#: أدوارٌ لا يصحّ أن تظهر هنا مهما كان السبب.
FORBIDDEN_ROLES = frozenset({"platform_developer"})

# أساسٌ مقيس: ثلاثةُ صفوفٍ بشعبتين، وستّةُ طلبةٍ في كلّ شعبة، وجناحان.
GRADES = ("G7", "G8", "G9")
SECTIONS = ("1", "2")
STUDENTS_PER_CLASS = 6
WINGS = (("pvn", "جناح الشمال"), ("pvs", "جناح الجنوب"))
SCHOOL_DAYS_BACK = 5


def is_preview_school(school: Any) -> bool:
    """الشقّان معاً: الرمزُ والبادئةُ — رمزٌ مصادفٌ لمدرسةٍ حقيقيّةٍ باسمٍ عاديّ لا يُحجب."""
    if school is None:
        return False
    return str(getattr(school, "code", "")) == SCHOOL_CODE and str(
        getattr(school, "name", "")
    ).startswith(NAME_PREFIX)


def preview_school_in_wrong_environment() -> bool:
    """أتوجد المدرسةُ الوهميّةُ في بيئةٍ ليست معاينة؟ — الحارسُ الذي يفشل (`seed_preview_school --check`) والاختبار."""
    from core.models import School
    from core.preview_accounts import in_preview_environment

    if in_preview_environment():
        return False
    return any(is_preview_school(s) for s in School.objects.filter(code=SCHOOL_CODE))
