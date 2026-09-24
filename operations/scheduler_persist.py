"""scheduler_persist.py — الشبكةُ صفوفاً في `ScheduleSlot`: كتابةٌ واحدةٌ للتوليد وللسداد.

كانت الكتابةُ حلقةً داخل `generate_schedule`. فلمّا احتاج سدادُ الجدول الحيّ (SCH-06)
أن يكتب مسودّتَه كان أمامه أن ينسخها — ونسختان من الجرس والوسم تفترقان يوماً، فتُعتمد
مسودّةُ السداد بأوقاتٍ أو وسومٍ غيرِ ما يكتبه التوليد، ويردّها القيدُ الفريدُ عند الاعتماد.
فهي هنا مرّةً للاثنين، ولا تحفظ شيئاً: المُنادي يكتب الصفوفَ في معاملته.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .models import ScheduleSlot

if TYPE_CHECKING:
    from core.models import School

    from .models import ScheduleGeneration
    from .scheduler import ScheduleGrid, Task


def _member_labels(task: Task) -> list[str]:
    """وسمُ كلّ ساكنٍ في الخانة — فارغٌ لغير المنقسمة، ومميَّزٌ داخل المنقسمة.

    و`ScheduleSlot.elective_group` جزءٌ من قيد «حصّةٌ واحدةٌ لشعبةٍ في التوقيت
    الواحد»، فتساوي الوسمَين يعني صفّاً مكرَّراً ترفضه القاعدةُ عند الاعتماد.
    """
    if not task.is_split:
        return ["" for _ in task.members]
    names = [m.subject_name for m in task.members]
    if len(set(names)) == len(names):
        return [name[:40] for name in names]
    return [f"{i + 1}·{name}"[:40] for i, name in enumerate(names)]


def slots_from_grid(
    school: School,
    academic_year: str,
    grid: ScheduleGrid,
    generation: ScheduleGeneration | None,
    publish: bool,
) -> list[ScheduleSlot]:
    """صفٌّ لكلّ (خانة × ساكن) من الشبكة — غيرُ محفوظ.

    المزدوجةُ تشغل خانتين، والشعبةُ المنقسمةُ خانةً واحدةً بحصّتين. و`elective_group`
    هو ما يُجيز اجتماعَ الحصّتين في القاعدة — فالقيدُ الفريدُ يشمله. ونصفا الشعبة في
    المادّة نفسها بمعلّمَين اسمُهما واحد، فيسبقه ترتيبُه: «1·الكيمياء» و«2·الكيمياء».
    """
    # `scheduler` يستورد هذه الوحدة، فالجرسُ يُستورد هنا لا في رأسها.
    from .scheduler import bell_lookup

    # وقتُ كلّ حصّةٍ من جرس نطاق شعبتها ليومها — الترتيبُ نفسُه الذي تُصالِح به
    # `resync_slot_times` الحصصَ القائمة.
    get_time = bell_lookup(school)
    rows = []
    for entry in grid.all_entries():
        task, day = entry["task"], entry["day"]
        labels = _member_labels(task)
        for slot in task.slots(entry["period"]):
            start, end = get_time(day, slot, task.band_id)
            for index, member in enumerate(task.members):
                rows.append(
                    ScheduleSlot(
                        school=school,
                        teacher_id=member.teacher_id,
                        class_group_id=task.class_id,
                        subject_id=member.subject_id,
                        day_of_week=day,
                        period_number=slot,
                        start_time=start,
                        end_time=end,
                        academic_year=academic_year,
                        elective_group=labels[index],
                        is_active=publish,
                        generation=generation,
                    )
                )
    return rows
