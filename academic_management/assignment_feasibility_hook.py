"""فحوصُ الجدوى عند إدخال الإسناد (W-20261001-046) — خارجَ `assignment_services`.

تُرجع كلُّ دالّةٍ رسالةَ الاستحالة أو `None`؛ و`None` تعني **لم يُكتشف مانع** لا «الإسنادُ
صالح» (AS-6). والخدمةُ هي التي تحوّل الرسالةَ إلى `Finding` بمستواها ورمزها، فلا استيرادَ دائريّ.
"""

from __future__ import annotations

from typing import Any


def parallel_same_teacher_message(
    school: Any, academic_year: str, class_group: Any, teacher: Any, tag: str, current: Any
) -> str | None:
    """AS-2: معلّمٌ واحدٌ لعضوَين في المجموعة المتوازية نفسِها يقع في خانةٍ واحدةٍ مرّتين.

    `_to_tasks` يدمج أعضاءَ المجموعة في مهمّةٍ واحدة فلا يراه HC1 — فيُرفض هنا.
    """
    if not tag or teacher is None:
        return None
    from operations.models import SubjectClassAssignment

    rivals = SubjectClassAssignment.objects.live(school, year=academic_year).filter(
        class_group=class_group, parallel_group=tag, teacher=teacher
    )
    if current is not None:
        rivals = rivals.exclude(pk=current.pk)
    other = rivals.select_related("subject").first()
    if other is None:
        return None
    return (
        f"{teacher.full_name} مُسنَدٌ أصلاً إلى {other.subject.name_ar} في مجموعة التوازي «{tag}»"
        f" بـ{class_group} — فالمجموعةُ المتوازيةُ تلزمها معلّمون مختلفون."
    )


def band_load_message(
    school: Any,
    academic_year: str,
    teacher: Any,
    class_group: Any,
    projected_teaching: int,
    count_capacity: int,
) -> str | None:
    """AS-1/AS-4/AS-5: نصابٌ فوقَ سقف الجرس الفعليّ أو التفضيل الشخصيّ.

    العجزُ بالعدّ وحدَه (`projected_teaching > count_capacity`) قائمٌ وتحكمه صرامةُ المدرسة
    (OVER_CAPACITY): لا يُكرَّر هنا فيُبطل ذلك القرار. وهذا الفحصُ يضيف ما لا يراه العدُّ.
    """
    if projected_teaching > count_capacity:
        return None
    from operations import schedule_feasibility

    return schedule_feasibility.entry_load_violation(
        school, academic_year, teacher, class_group, projected_teaching
    )
