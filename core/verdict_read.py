"""
core/verdict_read.py
مجموعاتُ حالاتِ نتيجة المادّة التي تقرؤها الشاشاتُ والتقارير — بقاعدةٍ واحدةٍ لكلّ المستهلكين.

الحالتان القديمتان `pass` و`fail` وحدَهما ما تفهمه الشاشاتُ التي كانت تعدّ بـ`status="pass"`.
فإذا رُفعت راية `VERDICT_ENGINE_ENABLED` (محرّكُ الحكم الواحد، `assessments/verdict_engine.py`)
صارت المادّةُ «مُرفَّعة» أو «راسبة — دورٌ ثانٍ» أو «معذور» أو «ملغي»…، فيقرأ كلُّ مستهلكٍ
المجموعاتِ الكاملة من `core.domain.grades`. ومطفأةً تبقى المجموعاتُ القديمةَ حرفيّاً، فلا يتغيّر
عدٌّ ولا نسبةٌ قبل أن تُرفع الراية.

كلُّ مستهلكٍ يكتب `status__in=passing_statuses()` لا `status="pass"` — فلا يحكم أحدٌ بحكمٍ موازٍ.
"""

from __future__ import annotations

from django.conf import settings

from core.domain.grades import (
    FAILING_STATUSES,
    PASSING_STATUSES,
    PENDING_STATUSES,
    RESULT_STATUSES,
)


def verdict_engine_enabled() -> bool:
    """أيُحسب الحكمُ الواحد ويُخزَّن؟ — راية `VERDICT_ENGINE_ENABLED` (مطفأةٌ افتراضاً)."""
    return bool(getattr(settings, "VERDICT_ENGINE_ENABLED", False))


_LEGACY_PASSING: tuple[str, ...] = ("pass",)
_LEGACY_FAILING: tuple[str, ...] = ("fail",)
_LEGACY_PENDING: tuple[str, ...] = ("incomplete",)
#: كلُّ ما كانت `STATUS` القديمةُ تحمله — تُعدّ مادّتُها في «عددِ الموادّ».
_LEGACY_RESULT: tuple[str, ...] = ("pass", "fail", "incomplete", "second_round")


def passing_statuses() -> tuple[str, ...]:
    """حالاتُ النجاح: `pass` و`promoted` بالمحرّك؛ `pass` وحدَها قبله."""
    return PASSING_STATUSES if verdict_engine_enabled() else _LEGACY_PASSING


def failing_statuses() -> tuple[str, ...]:
    """حالاتُ الرسوب: `fail` و`second_round` و`cancelled` بالمحرّك؛ `fail` وحدَها قبله."""
    return FAILING_STATUSES if verdict_engine_enabled() else _LEGACY_FAILING


def pending_statuses() -> tuple[str, ...]:
    """حالاتُ ما لم يُحسم: غيرُ مكتمل، والملحقُ، والمعذورُ والمحرومُ بالمحرّك."""
    return PENDING_STATUSES if verdict_engine_enabled() else _LEGACY_PENDING


def result_statuses() -> tuple[str, ...]:
    """كلُّ حالةٍ تُعدّ مادّتُها نتيجةً (بلا «ليست مادة نجاح ورسوب») — عددُ الموادّ."""
    return RESULT_STATUSES if verdict_engine_enabled() else _LEGACY_RESULT
