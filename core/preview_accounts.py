"""حساباتُ المعاينة الدائمة على 8500 — التعريفُ الواحد، ومصيدةُ الإنتاج (W-20261003-023، قرارُ المالك D-167م، حكمُ 0105).

«الحساباتُ كلُّها على المحلّيّ ولا تُحقن في الإنتاج» (المالك، 2026-10-03). فهذا الملفُّ يجمع في موضعٍ واحدٍ:

1. **القائمةُ المغلقة** `ROLES`: تسعةُ أدوارٍ بأسمائها وأرقامِ دخولِها `PV-…` — لا platform_developer ولا superuser ولا is_staff، ويفشل
   الاختبارُ إن ظهر دورٌ خارجها (حكمُ 0105 ج).
2. **الوسمُ المركَّب** `is_preview_account`: بادئةُ الاسم «[وهميّ» **و**بادئةُ الرقم `PV-` معاً — فاسمٌ يبدأ بالبادئة وحدَها أو رقمٌ يبدؤها وحدَه
   لا يُحجب (لا يُسقط موظّفاً حقيقيّاً بمصادفة).
3. **المصيدةُ**: حسابٌ موسومٌ خارج إعداد المعاينة (`shschool.settings.preview`) لا يدخل ولا تبقى جلستُه (انظر `core/backends.py`)، ويُبلَّغ
   عن **حدث المنع نفسِه** (سجلّ + Sentry) بمعرّف الحساب لا اسمِه ولا رقمِه — لا من استعلامِ إقلاعٍ على قاعدة الإنتاج.
4. **استثناءُ الحقن 8500→الإنتاج**: `exclude_from_injection`/`injection_violations` (انظر `academic_management/preview_reconciliation.py`).

كلمةُ المرور ليست هنا ولا في أيّ كودٍ أو اختبار: من `PREVIEW_ACCOUNTS_PASSWORD` في `.env` غير المتتبَّع (انظر الأمر `preview_accounts`).
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings
from django.db.models import Q

logger = logging.getLogger("core.preview_accounts")

PREVIEW_SETTINGS_MODULE = "shschool.settings.preview"

#: الوسمُ المركَّب — لا يكفي أحدُ شقَّيه (حكمُ 0105 ب-٢).
NAME_PREFIX = "[وهميّ"
ID_PREFIX = "PV-"
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
}
#: أدوارٌ محظورةٌ على هذه الحسابات مهما كان السبب.
FORBIDDEN_ROLES = frozenset({"platform_developer"})


def in_preview_environment() -> bool:
    """أهذا إعدادُ المعاينة؟ — بالإعداد الفعليّ للعمليّة لا بمتغيّرٍ يُضبط في مكانٍ آخر."""
    return str(getattr(settings, "SETTINGS_MODULE", "")) == PREVIEW_SETTINGS_MODULE


def is_preview_account(user: Any) -> bool:
    """الوسمُ المركَّب: بادئةُ الاسم **و**بادئةُ رقم الدخول معاً."""
    if user is None:
        return False
    name = str(getattr(user, "full_name", "") or "")
    national_id = str(getattr(user, "national_id", "") or "")
    return name.startswith(NAME_PREFIX) and national_id.startswith(ID_PREFIX)


def preview_accounts_q(prefix: str = "") -> Q:
    """الوسمُ المركَّب كشرطِ استعلام (`prefix` مثل `teacher__` لعلاقةٍ)."""
    return Q(**{f"{prefix}full_name__startswith": NAME_PREFIX}) & Q(
        **{f"{prefix}national_id__startswith": ID_PREFIX}
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
