"""مُنتقي الطالب في شاشة تسجيل المخالفة: الصفُّ والشعبةُ ثمّ الطالب (بلاغ المالك 2026-09-26).

كانت الشاشةُ تعرض كلَّ طلبة المدرسة (أو الجناح) في قائمةٍ واحدةٍ يُبحث فيها بالاسم وحده، ومن أراد طالباً من شعبةٍ بعينها
تصفّح مئاتِ الأسماء. فصار لها قائمتان منسدلتان — الصفُّ والشعبة — تحصران قائمةَ الطالب وبحثَها. والتصفيةُ في المتصفّح على
سمات `data-grade` و`data-section` (القائمةُ كلُّها مرسومةٌ أصلاً)، وهذا الملفُّ يشتقّ لكلّ طالبٍ صفَّه وشعبتَه **الحاليَّين**.

الحاليّان = قيدُ العام الدراسيّ الجاري، والأحدثُ إن تعدّدت قيودُه النشطةُ فيه (`newest_first`). فقيدُ العام الماضي الذي لم
يُغلق بعدُ لا يضع طالباً في صفٍّ غادره (قِيس هذا على بيانات المدرسة: أكثرُ من 200 طالبٍ بقيدَين نشطَين). ومن لا قيدَ حاليَّ له
يبقى في القائمة بلا صفٍّ ولا شعبة: يظهر حين لا يُقيَّد بصفٍّ ولا شعبة، ولا يظهر تحت أيٍّ منهما.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, StudentEnrollment


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
