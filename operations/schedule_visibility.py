"""operations/schedule_visibility.py — من يرى جدولَ من (W-20261013-022، قرار المالك D-432م).

المعلّمُ المقيَّد يرى الجدولَ العامَّ كاملاً، وجداولَ: زملاءِ مادّته، ومن يدرّس شُعبَه،
وشُعبِه هو. أمّا من يتصفّح غيره (`SCHEDULE_BROWSE` والمطلقو الصلاحيّة) فيرى الكلّ.
يوم التفريغ المفضّل لا يخرج من هنا أصلاً: لا يُقرأ في هذه الوحدة (D-341م).
قراءةٌ فقط من `ScheduleSlot` الحيّ، لا كتابةَ ولا مساسَ بالجدول المعتمد (D-381م).
"""

from core.academic_calendar import academic_year_for_school
from core.permissions import SCHEDULE_BROWSE
from core.unrestricted_role import has_unrestricted_role

from .models import ScheduleSlot


def may_browse_all(user) -> bool:
    """من يتصفّح كلَّ الجداول: القيادةُ والمنسّقون ومن لا قيدَ عليه."""
    return bool(
        user.is_admin() or has_unrestricted_role(user) or user.get_role() in SCHEDULE_BROWSE
    )


def _own_slots(school, user, year=None):
    year = year or academic_year_for_school(school)
    return ScheduleSlot.objects.live(school, year=year).filter(teacher=user)


def visible_class_ids(school, user, year=None) -> set:
    """شُعبُ المعلّم نفسِه."""
    return set(_own_slots(school, user, year).values_list("class_group_id", flat=True))


def visible_teacher_ids(school, user, year=None) -> set:
    """المعلّم نفسُه وزملاءُ مادّته ومن يدرّس شُعبَه."""
    year = year or academic_year_for_school(school)
    own = _own_slots(school, user, year)
    classes = set(own.values_list("class_group_id", flat=True))
    subjects = set(own.values_list("subject_id", flat=True))
    live = ScheduleSlot.objects.live(school, year=year)
    by_class = live.filter(class_group_id__in=classes).values_list("teacher_id", flat=True)
    by_subject = live.filter(subject_id__in=subjects).values_list("teacher_id", flat=True)
    return {user.pk, *by_class, *by_subject} - {None}


def may_view_teacher(school, user, teacher_id, year=None) -> bool:
    if may_browse_all(user):
        return True
    return str(teacher_id) in {str(i) for i in visible_teacher_ids(school, user, year)}


def may_view_class(school, user, class_id, year=None) -> bool:
    if may_browse_all(user):
        return True
    return str(class_id) in {str(i) for i in visible_class_ids(school, user, year)}
