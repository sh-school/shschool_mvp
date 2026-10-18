"""مُنتقي الطالب في شاشة تسجيل المخالفة: الصفُّ والشعبةُ ثمّ الطالب (بلاغ المالك 2026-09-26).

كانت الشاشةُ تعرض كلَّ طلبة المدرسة (أو الجناح) في قائمةٍ واحدةٍ يُبحث فيها بالاسم وحده، ومن أراد طالباً من شعبةٍ بعينها
تصفّح مئاتِ الأسماء. فصار لها قائمتان منسدلتان — الصفُّ والشعبة — تحصران قائمةَ الطالب وبحثَها. والتصفيةُ في المتصفّح على
سمات `data-grade` و`data-section` (القائمةُ كلُّها مرسومةٌ أصلاً)، وهذا الملفُّ يشتقّ لكلّ طالبٍ صفَّه وشعبتَه **الحاليَّين**.

الحاليّان = قيدُ العام الدراسيّ الجاري، والأحدثُ إن تعدّدت قيودُه النشطةُ فيه (`newest_first`). فقيدُ العام الماضي الذي لم
يُغلق بعدُ لا يضع طالباً في صفٍّ غادره (قِيس هذا على بيانات المدرسة: أكثرُ من 200 طالبٍ بقيدَين نشطَين). ومن لا قيدَ حاليَّ له
يبقى في القائمة بلا صفٍّ ولا شعبة: يظهر حين لا يُقيَّد بصفٍّ ولا شعبة، ولا يظهر تحت أيٍّ منهما.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from typing import Any

from django.http import Http404
from django.shortcuts import get_object_or_404

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, CustomUser, StudentEnrollment
from core.permissions import get_teacher_student_ids, teacher_can_access_student
from wings.scope import student_scope_for


def _section_key(section: str) -> tuple[int, int, str]:
    """الأرقامُ أوّلاً بقيمتها («2» قبل «10»)، ثمّ الحروف — وليس ترتيباً نصّيّاً يضع «10» قبل «2»."""
    return (0, int(section), "") if section.isdigit() else (1, 0, section)


def student_picker(students: Iterable[Any], school) -> dict[str, Any]:
    """سياقُ منتقي الطالب: الطلبةُ بصفّهم وشعبتهم الحاليَّين، وخياراتُ الصفّ والشعبة.

    يُرجع `students` (قائمةً بالعناصر نفسِها وعليها `pick_grade` و`pick_section`)، و`grade_options` (الصفوفُ التي فيها طلبةٌ
    بترتيبها الرسميّ)، و`sections_by_grade` (شُعبُ كلّ صفٍّ)، و`all_sections` (كلُّ الشعب، لمن لم يختر صفّاً).
    والخياراتُ من طلبة نطاق صاحب الطلب وحدَهم: مشرفُ الجناح لا يرى صفّاً ولا شعبةً ليست من جناحه.
    """
    people = list(students)
    current: dict[Any, tuple[str, str]] = {}
    rows = (
        StudentEnrollment.objects.filter(
            student_id__in=[person.pk for person in people],
            is_active=True,
            class_group__school=school,
            class_group__academic_year=academic_year_for_school(school),
        )
        .newest_first()
        .values_list("student_id", "class_group__grade", "class_group__section")
    )
    for student_id, grade, section in rows:
        current.setdefault(student_id, (grade, section))

    sections: dict[str, set[str]] = {}
    for person in people:
        grade, section = current.get(person.pk, ("", ""))
        person.pick_grade, person.pick_section = grade, section
        if grade and section:
            sections.setdefault(grade, set()).add(section)

    labels = dict(ClassGroup.GRADES)
    return {
        "students": people,
        "grade_options": [
            (code, labels[code]) for code, _label in ClassGroup.GRADES if code in sections
        ],
        "sections_by_grade": {
            grade: sorted(found, key=_section_key) for grade, found in sections.items()
        },
        "all_sections": sorted({s for found in sections.values() for s in found}, key=_section_key),
    }


def visible_infractions(user, school):
    """مخالفاتُ المدرسة المرئيةُ لصاحب الطلب — بنطاقِ الويب نفسِه (W-20261012-032).

    المعلّمُ والمنسّقُ ومشرفُ الجناح لطلبتهم، والقيادةُ (None) للمدرسة كلِّها. و`?student_id` و`?class_id`
    تُضيَّقان بعده فتُرجعان قائمةً فارغةً لطالبٍ خارج النطاق لا خطأً يكشف وجوده."""
    from .models import BehaviorInfraction

    qs = BehaviorInfraction.objects.filter(school=school).with_student().order_by("-date")
    visible = get_teacher_student_ids(user)
    if visible is not None:
        qs = qs.filter(student_id__in=visible)
    return qs


def recordable_student(request, school, student_id):
    """الطالبُ الذي يحقّ لصاحب الطلب أن يسجّل عليه مخالفة — وإلّا 404 موحَّد لا يكشف وجودَه.

    يجمع ثلاثةَ شروط في استعلامٍ واحد: عضويةٌ فعّالةٌ في مدرسة الطلب بدور طالب (فمستخدمٌ من مدرسةٍ أخرى
    أو غيرُ طالبٍ لا يُجلب)، ثمّ نطاقُ الدور: المشرفُ المقيَّد بجناحه، والمعلّمُ والمنسّقُ بجدولهما، والقيادةُ
    لمدرستها كلِّها. وتُمرَّر `student.id` (UUID) لا النصُّ الخام: مقارنةُ نصٍّ بمجموعة UUID تُرجع False دائماً.
    يُجلب الطالبُ بنطاقه قبل صحّة النموذج، ومعرّفٌ فارغ يُرجع None. الرفضُ 404 لا صفحةَ منع كي لا يُعرف أنّ الطالبَ موجودٌ في مدرسةٍ أخرى أو خارج جدول المعلّم."""
    if not student_id:
        return None
    try:
        sid = uuid.UUID(str(student_id))
    except ValueError:
        raise Http404("طالبٌ غير موجود") from None
    student = get_object_or_404(
        CustomUser.objects.filter(
            memberships__school=school,
            memberships__is_active=True,
            memberships__role__name="student",
        ).distinct(),
        id=sid,
    )
    scope = student_scope_for(request)
    if scope.is_wing_bound:
        scope.require_student(student.id)
    elif not teacher_can_access_student(request.user, student.id):
        raise Http404("طالبٌ غير موجود")
    return student
