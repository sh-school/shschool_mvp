"""سقوفُ الأولى والسابعة المقرَّرةُ إدارياً (الأدمن) تُضمّ إلى إعداد الحلّال.

نُقلت من `runner.py` حين تجاوز حدَّ حجم الملفّ (اختبار `test_file_size`)؛ والمسؤوليّةُ واحدة: ما قرّرته
الإدارةُ في تفضيلات المعلّمين يدخل خيارات النموذج قبل الحلّ فلا يولَّد جدولٌ بقاعدةٍ لا يقرؤها المُقيِّم.
`runner` يعيد تصديرهما بالاسم نفسه فلا يتغيّر موضعُ الاستيراد لأحد.
"""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from operations.scheduler_v2.runner import SolverConfig


def _with_spec(config: SolverConfig, spec: dict[str, Any]) -> SolverConfig:
    return replace(config, relaxations=tuple(sorted(spec.items(), key=lambda kv: kv[0])))


def with_admin_first_caps(config: SolverConfig, school: Any, academic_year: str) -> SolverConfig:
    """يضمّ سقوفَ الأولى المقرَّرةَ إدارياً (الأدمن) إلى `first_cap_override`؛ والأعلى يغلب ملفَّ التخفيف.

    المصدرُ بعد W-20261010-033 هو الحقل `TeacherPreference.max_first_periods`؛ وملفُّ `--relaxations` يبقى
    خياراً لتشغيلٍ بعينه فوق الأساس لا بديلاً عنه.
    """
    from operations.schedule_evaluator import admin_first_caps

    stored = admin_first_caps(school, academic_year)
    if not stored:
        return config
    spec = dict(config.relaxations)
    merged = dict(spec.get("first_cap_override") or {})
    for teacher, cap in stored.items():
        merged[teacher] = max(cap, merged.get(teacher, 0))
    spec["first_cap_override"] = merged
    return _with_spec(config, spec)


def with_admin_last_caps(config: SolverConfig, school: Any, academic_year: str) -> SolverConfig:
    """يضمّ سقوفَ السابعة المقرَّرةَ إدارياً (الأدمن) إلى `last_cap_override`، ومنها الصفرُ (منعُ السابعة).

    على عكس سقف الأولى لا يُرفع هنا الأعلى فوق الملف: القرارُ الإداريّ المحفوظ في حقّ المعلّم هو الحاكم
    (يضيّق بالصفر ويوسّع إلى خمس)، وملفُّ التخفيف يبقى لتشغيلٍ بعينه لمن لم يُقرَّ له سقفٌ محفوظ.
    """
    from operations.last_period_cap import admin_last_caps

    stored = admin_last_caps(school, academic_year)
    if not stored:
        return config
    spec = dict(config.relaxations)
    merged = dict(spec.get("last_cap_override") or {})
    merged.update(stored)
    spec["last_cap_override"] = merged
    return _with_spec(config, spec)
