"""قراءةُ سياسة تخفيف التلاصق من مصدرٍ واحد — يقرؤها المولّدُ والمُقيِّمُ وفحصُ الجدوى (D-382م، W-20261011-007).

يوم 10-09 رفض المُقيِّمُ ما يسمح به النموذجُ لأنّ كلًّا منهما كان يقرأ تخفيفاً غيرَ الآخر. فهذه الوحدةُ هي المصدرُ
الوحيد: لا ثابتَ تخفيفٍ يُكتب في موضعٍ ثانٍ، ولا معرّفَ معلّمٍ حقيقيّ في الشيفرة.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from .models.schedule_policy import RELAXED_RUN_CAP, ScheduleRelaxationPolicy

#: سقفُ التتابع بلا تخفيف: HC5 صلب (لا تلاصق)، أي أقصى حصّةٍ واحدة في المجموعة المتلاصقة.
STRICT_RUN_CAP = 1


def school_policy(school: Any) -> ScheduleRelaxationPolicy:
    """سياسةُ المدرسة المحفوظة، أو القيمُ الافتراضيّةُ (= قاعدةُ الجدول الحيّ) لمدرسةٍ لم يُحفظ لها صفّ.

    الكائنُ الافتراضيّ غيرُ محفوظ: لا كتابةَ في قراءة، فتبقى قراءةُ المُقيِّم بلا أثرٍ جانبيّ.
    """
    saved = ScheduleRelaxationPolicy.objects.filter(school=school).first()
    return saved if saved is not None else ScheduleRelaxationPolicy(school=school)


def relaxed_run_cap(school: Any) -> int:
    """أقصى حصصٍ متلاصقةٍ يقبلها HC5 لمعلّمٍ في هذه المدرسة: 1 صارمٌ، أو سقفُ التخفيف للجميع."""
    policy = school_policy(school)
    return policy.touch_run_cap if policy.relax_touch_for_all else STRICT_RUN_CAP


def run_caps_for_tasks(
    school: Any, tasks: Iterable[Any], explicit: dict[str, int] | None = None
) -> dict[str, int]:
    """{معلّم ← سقف التتابع المخفَّف} لكلّ معلّمٍ في المهامّ، فارغٌ حين لا تخفيفَ للجميع؛ والمُمرَّرُ صراحةً يعلو.

    هذا ما يمرّره المُقيِّمُ إلى `_ease_runs` ليحكم بالقاعدة التي وُلّد بها الجدول لا بأشدّ منها.
    """
    cap = relaxed_run_cap(school)
    if cap <= STRICT_RUN_CAP:
        return dict(explicit or {})
    return {**{m.teacher_id: cap for task in tasks for m in task.members}, **(explicit or {})}


def rule_sentence(spec: dict[str, Any]) -> str:
    """جملةٌ عربيّةٌ بالقاعدة السارية في تشغيلٍ بعينه (للرسائل)، أو «بلا تخفيفات» حين لا شيء مفعَّل."""
    parts: list[str] = []
    if spec.get("touch_relaxed_all"):
        parts.append(
            f"تلاصقُ حتى {int(spec.get('run_cap') or RELAXED_RUN_CAP)} حصصٍ متتاليةٍ لكلّ المعلّمين"
        )
    elif spec.get("touch_relaxed"):
        parts.append(f"تلاصقٌ مخفَّفٌ لـ{len(spec['touch_relaxed'])} معلّماً مسمّى")
    if spec.get("no_6_7"):
        parts.append("منعُ السادسة مع السابعة")
    if spec.get("triples_by_number"):
        parts.append("منعُ ثلاثِ حصصٍ بأرقامٍ متتالية")
    if not parts:
        return "القاعدة السارية: بلا تخفيفات"
    return "القاعدة السارية (إعداد المدرسة): " + "، ".join(parts)


__all__ = [
    "RELAXED_RUN_CAP",
    "STRICT_RUN_CAP",
    "rule_sentence",
    "relaxed_run_cap",
    "run_caps_for_tasks",
    "school_policy",
]
