"""حساباتُ المعاينة الدائمة على 8500 — التعريفُ الواحد، ومصيدةُ الإنتاج (W-20261003-023، قرارُ المالك D-167م، حكمُ 0105).

«الحساباتُ كلُّها على المحلّيّ ولا تُحقن في الإنتاج» (المالك، 2026-10-03). فهذا الملفُّ يجمع في موضعٍ واحدٍ:

1. **القائمةُ المغلقة** `ROLES`: عشرةُ أدوارٍ بأسمائها وأرقامِ دخولِها `PV-…` — لا platform_developer ولا superuser ولا is_staff، ويفشل
   الاختبارُ إن ظهر دورٌ خارجها (حكمُ 0105 ج).
2. **الوسمُ المركَّب** `is_preview_account`: بادئةُ الاسم «[وهميّ» **و**بادئةُ الرقم `PV-` معاً — فاسمٌ يبدأ بالبادئة وحدَها أو رقمٌ يبدؤها وحدَه
   لا يُحجب (لا يُسقط موظّفاً حقيقيّاً بمصادفة).
3. **المصيدةُ**: حسابٌ موسومٌ خارج إعداد المعاينة (`shschool.settings.preview`) لا يدخل ولا تبقى جلستُه (انظر `core/backends.py`)، ويُبلَّغ
   عن **حدث المنع نفسِه** (سجلّ + Sentry) بمعرّف الحساب لا اسمِه ولا رقمِه — لا من استعلامِ إقلاعٍ على قاعدة الإنتاج.
4. **استثناءُ الحقن 8500→الإنتاج**: `exclude_from_injection`/`injection_violations` (انظر `academic_management/preview_reconciliation.py`).

**ما يكتبه المالكُ في حقل الدخول** هو الرقمُ الوظيفيُّ `EMPLOYEE_NUMBERS[الدور]` (رقمٌ من ثماني خانات)؛ أمّا `national_id=PV-<الدور>` فوسمُ المصيدة وحدَه.

كلمةُ المرور ليست هنا ولا في أيّ كودٍ أو اختبار: من `PREVIEW_ACCOUNTS_PASSWORD` في `.env` غير المتتبَّع (انظر الأمر `preview_accounts`).
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger("core.preview_accounts")

PREVIEW_SETTINGS_MODULE = "shschool.settings.preview"
#: المعاينةُ المثبَّتةُ على شجرة جلسةٍ تعمل بإعداد التطوير (PREVIEW_MODE=dev في compose المعاينة) — وهي استعمالُ المالك الرئيسيّ.
DEVELOPMENT_SETTINGS_MODULE = "shschool.settings.development"
#: إعداداتُ الإنتاج **صريحةً** لا اشتقاقاً: الحسابُ الموسومُ يُحجب فيها دائماً مهما ضُبطت متغيّراتُ المعاينة (حكمُ 0105 ١).
PRODUCTION_SETTINGS_MODULES = frozenset(
    {"shschool.settings.production", "shschool.settings.staging"}
)
#: قيمُ PREVIEW_MODE المقبولة (يضبطها docker-compose.preview.yml وحدَه) — ولا قيمةَ أخرى ولا فراغ (حكمُ 0105 ٣).
PREVIEW_MODES = frozenset({"prod", "dev"})
#: اسمُ قاعدة المعاينة **يحوي** هذا (فحصٌ إيجابيّ) — فقاعدةُ Railway الافتراضيّةُ «railway» تمرّ من أيّ فحصٍ سلبيّ (حكمُ 0105 ٢).
PREVIEW_DB_MARKER = "preview"

#: الوسمُ المركَّب — لا يكفي أحدُ شقَّيه (حكمُ 0105 ب-٢).
NAME_PREFIX = "[وهميّ"
ID_PREFIX = "PV-"
#: أرقامُ الدخول الاصطناعيّةُ للأداة الخارجيّة السابقة (29000009NNN بنمط الحارس، 2026-10-03) — حساباتٌ مبذورةٌ قبل هذا الكود: تُحجب
#: وتُستثنى من الحقن كالجديدة (بالاسم المركَّب نفسِه)، ويحذفها `preview_accounts --sync` ثمّ يبذر `PV-…` مكانها فلا يتكرّر دورٌ.
LEGACY_ID_REGEX = r"^29000009[0-9]{3}$"
#: البريدُ وسمٌ ثالثٌ للإنشاء لا شرطٌ في الحجب.
EMAIL_PREFIX = "preview_"
FULL_NAME_PREFIX = "[وهميّ] "

#: القائمةُ المغلقة (حكمُ 0105 ج): الدورُ ← رقمُ الدخول. إضافةُ دورٍ هنا قرارٌ يُراجَع (ويفشل `test_preview_accounts` بدونه).
ROLES: dict[str, str] = {
    "principal": "PV-principal",
    "vice_admin": "PV-vice-admin",
    "vice_academic": "PV-vice-academic",
    "admin_supervisor": "PV-admin-supervisor",
    "secretary": "PV-secretary",  # pragma: allowlist secret — اسمُ دورٍ لا سرّ
    "teacher": "PV-teacher",
    "ese_teacher": "PV-ese-teacher",
    "coordinator": "PV-coordinator",
    "specialist": "PV-specialist",
    # منسّقُ شؤون الطلبة — قرارُ المالك 2026-10-05 (W-20261001-020): العاشر في القائمة المغلقة.
    "student_affairs_coordinator": "PV-sa-coordinator",
}
#: الرقمُ الوظيفيّ (**ما يُكتب في حقل الدخول**، فنموذجُ الدخول يفرض `pattern="[0-9]{5,20}"` ولا يقبل `PV-…`): ثمانُ خاناتٍ من نطاقٍ مخصَّصٍ
#: `99900001–99900010` يفترق عن الرقم الوظيفيّ الحقيقيّ (5–6 خاناتٍ) وعن الرقم الشخصيّ (11)؛ وآخرُ خانةٍ تدلّ على الدور. حكمُ 0105 (أ بقيود).
#: **ثابتٌ واحدٌ للنطاق** هنا: `RESERVED_EMPLOYEE_REGEX` — منه يرفض `apply` كلَّ صفٍّ رقمُه فيه، ويرفض البذرُ رقماً محجوزاً لحسابٍ غيرِ موسوم.
EMPLOYEE_NUMBERS: dict[str, str] = {
    "principal": "99900001",
    "vice_admin": "99900002",
    "vice_academic": "99900003",
    "admin_supervisor": "99900004",
    "secretary": "99900005",  # pragma: allowlist secret — رقمٌ وظيفيٌّ اصطناعيٌّ لدورٍ لا سرّ
    "coordinator": "99900006",
    "teacher": "99900007",
    "ese_teacher": "99900008",
    "specialist": "99900009",
    "student_affairs_coordinator": "99900010",
}
#: قسمُ عضويّة كلّ حسابٍ يحتاج نطاقَ قسم (W-20261010-026): المنسّقُ والمعلّمُ في «الرياضيات» ليرى المنسّقُ معلّمَ قسمه،
#: ومعلّمُ التربية الخاصّة في قسمٍ آخر لإثبات الاستبعاد. دائمٌ في البذر لأنّ التعديلَ اليدويَّ يضيع عند إعادة بناء القاعدة.
DEPARTMENT_NAMES = {
    "coordinator": "الرياضيات",
    "teacher": "الرياضيات",
    "ese_teacher": "اللغة العربية",
}
RESERVED_EMPLOYEE_REGEX = r"^(9990000[1-9]|99900010)$"
#: أدوارٌ محظورةٌ على هذه الحسابات مهما كان السبب.
FORBIDDEN_ROLES = frozenset({"platform_developer"})


def is_reserved_employee_number(value: str) -> bool:
    """أرقامٌ وظيفيّةٌ من النطاق المحجوز لحسابات المعاينة (`99900001–99900010`)."""
    return re.match(RESERVED_EMPLOYEE_REGEX, str(value or "")) is not None


def current_db_name() -> str:
    """اسمُ القاعدة الفعليّ للاتّصال الحاليّ."""
    from django.db import connection

    return str(connection.settings_dict.get("NAME") or "")


def preview_db_matches() -> bool:
    """قاعدةُ معاينةٍ بالفحص الإيجابيّ: `PREVIEW_DB_NAME` (يضبطه compose المعاينة وحدَه) يساوي الاسمَ الفعليّ **ويحوي «preview»**."""
    expected = os.environ.get("PREVIEW_DB_NAME", "")
    name = current_db_name()
    return bool(expected) and name == expected and PREVIEW_DB_MARKER in name.lower()


def in_preview_environment() -> bool:
    """أهذه بيئةُ معاينة؟ — لا تُحجب فيها حساباتُ المعاينة.

    1. إعدادُ إنتاجٍ/staging (قائمةٌ صريحة) ⇒ **لا، دائماً** — مهما ضُبطت متغيّراتُ المعاينة (خطأُ تهيئةٍ في Railway لا يفعّلها).
    2. `shschool.settings.preview` ⇒ نعم.
    3. `shschool.settings.development` (المعاينةُ المثبَّتةُ على شجرة جلسة) ⇒ نعم **فقط** إن كان `PREVIEW_MODE ∈ {prod, dev}` وقاعدةٌ
       اسمُها قاعدةُ المعاينة (`preview_db_matches`).
    4. غيرُ ذلك (testing وغيره) ⇒ لا.
    """
    module = str(getattr(settings, "SETTINGS_MODULE", ""))
    if module in PRODUCTION_SETTINGS_MODULES:
        return False
    if module == PREVIEW_SETTINGS_MODULE:
        return True
    return (
        module == DEVELOPMENT_SETTINGS_MODULE
        and os.environ.get("PREVIEW_MODE", "") in PREVIEW_MODES
        and preview_db_matches()
    )


def is_preview_account(user: Any) -> bool:
    """الوسمُ المركَّب: بادئةُ الاسم **و**بادئةُ رقم الدخول معاً."""
    if user is None:
        return False
    name = str(getattr(user, "full_name", "") or "")
    national_id = str(getattr(user, "national_id", "") or "")
    return name.startswith(NAME_PREFIX) and (
        national_id.startswith(ID_PREFIX) or re.match(LEGACY_ID_REGEX, national_id) is not None
    )


def legacy_accounts_q(prefix: str = "") -> Q:
    """حساباتُ الأداة الخارجيّة السابقة: بادئةُ الاسم **و**الرقمُ 29000009NNN."""
    return Q(**{f"{prefix}full_name__startswith": NAME_PREFIX}) & Q(
        **{f"{prefix}national_id__regex": LEGACY_ID_REGEX}
    )


def preview_accounts_q(prefix: str = "") -> Q:
    """الوسمُ المركَّب كشرطِ استعلام (`prefix` مثل `teacher__` لعلاقةٍ): الجديدُ `PV-…` أو السابقُ 29000009NNN."""
    return Q(**{f"{prefix}full_name__startswith": NAME_PREFIX}) & (
        Q(**{f"{prefix}national_id__startswith": ID_PREFIX})
        | Q(**{f"{prefix}national_id__regex": LEGACY_ID_REGEX})
    )


def blocked_outside_preview(user: Any) -> bool:
    """أيُحجب هذا المستخدمُ؟ — موسومٌ وخارجَ إعداد المعاينة."""
    return is_preview_account(user) and not in_preview_environment()


def report_blocked(user: Any, where: str) -> None:
    """حدثُ المنع: سجلٌّ وSentry **بمعرّف الحساب** لا اسمِه ولا رقمِه (PDPPL)، فيُنذَر منه لحظةَ وقوعه."""
    account_id = str(getattr(user, "pk", "") or "")
    message = f"حسابُ معاينةٍ وهميّ حاول الدخول خارجَ المعاينة (id={account_id}، المسار={where})"
    logger.error(message, extra={"preview_account_id": account_id, "where": where})
    try:  # Sentry اختياريٌّ: غيابُه لا يُسقط المنع
        import sentry_sdk

        with sentry_sdk.new_scope() as scope:
            scope.set_tag("preview_account_blocked", "1")
            scope.set_extra("account_id", account_id)
            scope.set_extra("where", where)
            sentry_sdk.capture_message(message, level="error")
    except Exception:  # pragma: no cover — لا يمنع المنعُ بسبب تقرير
        logger.debug("تعذّر إرسال حدث المنع إلى Sentry", exc_info=True)
