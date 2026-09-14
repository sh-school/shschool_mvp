"""
من يكتب في مركز معلومات الطلبة، ومن يقرأ.

**قرارُ المدرسة في القراءة:** كلُّ من يُدرّس الطالب يرى كلَّ ملاحظاته — بما
فيها ملاحظاتُ الأخصائيَّين. عُرض على المدير أنّ هذا يوصل ملاحظةً نفسيّةً عن
قاصرٍ إلى عشرة معلّمين، فاعتُمد على حاله. وهو منفَّذٌ هنا كما اعتُمد، ومعه
أثرٌ لا يُمحى: كلُّ فتحِ ملفٍّ يحمل ملاحظةَ أخصائيٍّ يُسجَّل في `AuditLog`
باسم من فتحه (المادّة ١٩ من قانون حماية البيانات الشخصيّة).

**الكتابة أضيقُ من القراءة:** لا يكتب في خانةِ جهةٍ إلّا أهلُها. فملاحظةُ
الأخصائيّ النفسيّ يكتبها الأخصائيُّ النفسيُّ وحده، ولا يكتبها معلّمٌ ولو
كان يقرؤها.

**المشرفُ الإداريُّ لشُعب أجنحته (قرار 2026-09-14):** يقرأ ملفّاتِ طلبة جناحه
وحدهم — ومن كان خارجه يعود له 404. ولا يقرأ ملاحظاتِ الأخصائيَّين ولا الدرجاتِ
وإن كان الطالبُ من جناحه (قرار 2026-09-15). والنطاقُ لا يُحسب هنا بل في
`wings/scope.py` وحدَه، فلا يُسأل «ما جناحُه؟» في موضعين.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from core.models.academic import ClassGroup, StudentEnrollment

if TYPE_CHECKING:
    from wings.scope import StudentScope

#: من يكتب في كلّ خانة. القيادةُ تُضاف لكلّ خانةٍ في `can_write` — لا هنا،
#: كي يبقى الجدولُ قراءةً في «صاحبِ الاختصاص» لا في «من يستطيع».
NOTE_AUTHORS = {
    "teacher": {
        "teacher",
        "ese_teacher",
        "teacher_assistant",
        "ese_assistant",
        "e_projects_coordinator",
    },
    "social_worker": {"social_worker"},
    "psychologist": {"psychologist"},
    "nurse": {"nurse"},
    "student_affairs": {"admin_supervisor", "coordinator", "activities_coordinator"},
}

#: قيادةُ المدرسة تكتب في كلّ خانةٍ وتقرأ كلَّ ملفّ.
LEADERSHIP = {"principal", "vice_academic", "vice_admin", "platform_developer"}

#: من يقرأ ملفّ أيِّ طالبٍ في المدرسة بلا شرطِ تدريس: القيادةُ ومن وظيفتُه
#: رعايةُ الطلاب جميعاً. والمشرفُ الإداريُّ ليس منهم: كان هنا فرأى المدرسةَ كلَّها،
#: وصار لجناحه وحدَه (قرار 2026-09-14).
SCHOOL_WIDE_READERS = LEADERSHIP | {
    "social_worker",
    "psychologist",
    "nurse",
    "academic_advisor",
    "coordinator",
    "activities_coordinator",
}

#: من يدخل المركزَ أصلاً. المعلّمُ داخلٌ، لكنّ ما يراه محدودٌ بمن يُدرّسهم؛
#: والمشرفُ الإداريُّ داخلٌ، وما يراه محدودٌ بشُعب أجنحته.
MODULE_ROLES = SCHOOL_WIDE_READERS | {
    "admin_supervisor",
    "teacher",
    "ese_teacher",
    "teacher_assistant",
    "ese_assistant",
    "e_projects_coordinator",
}


def can_write(user, category):
    """هل لهذا المستخدم أن يكتب في هذه الخانة؟"""
    role = user.get_role()
    if user.is_superuser or role in LEADERSHIP:
        return True
    return role in NOTE_AUTHORS.get(category, set())


def writable_categories(user):
    """الخاناتُ التي يفتح له فيها زرُّ الإضافة — لا تُعرض أداةٌ لا تعمل."""
    return [c for c in NOTE_AUTHORS if can_write(user, c)]


def taught_class_ids(user, year):
    """معرّفاتُ الشُّعب التي يُدرّسها هذا المعلّم في هذا العام.

    المصدرُ جدولُ الحصص لا توزيعُ المواد: التوزيعُ قد يتأخّر، والحصّةُ هي
    ما يقف المعلّمُ أمامه فعلاً.
    """
    from operations.models import ScheduleSlot

    return set(
        ScheduleSlot.objects.filter(teacher=user, academic_year=year)
        .values_list("class_group_id", flat=True)
        .distinct()
    )


def sees_whole_school(user: Any) -> bool:
    """أيقرأ هذا المستخدمُ المدرسةَ كلَّها بلا شرطِ تدريسٍ ولا جناح؟"""
    return bool(user.is_superuser) or user.get_role() in SCHOOL_WIDE_READERS


def _wing_scope(user: Any, school: Any, scope: StudentScope | None) -> StudentScope | None:
    """نطاقُ الجناح لمن يدخل المركز — ومن لا يدخله لا يُسأل عن جناحه أصلاً.

    `WING_BOUND_ROLES` تضمّ البديلَين (ملاحظَ الطلبة وعاملَ الخدمات)، وهما خارج
    `MODULE_ROLES` بقرار 2026-09-15: فلا يفتح لهما نطاقُ جناحٍ ما لم يفتحه الدور.
    """
    if user.get_role() not in MODULE_ROLES:
        return None
    if scope is None:
        # كسولاً: `core.capabilities` يستورد هذه الوحدةَ عند بناء سجلّه.
        from wings.scope import student_scope

        scope = student_scope(user, school)
    return scope if scope.is_wing_bound else None


def visible_class_groups(user, school, year, scope=None):
    """الشُّعبُ التي تظهر لهذا المستخدم في صفحة الشُّعب.

    والمقيَّدُ بجناحه: شُعبُ أجنحته في العام الجاري، ولا يوسّعها `year`.
    """
    groups = ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
    if sees_whole_school(user):
        return groups.in_school_order()
    wing = _wing_scope(user, school, scope)
    if wing is not None:
        # مديرُ `ClassGroup` يرتّب ترتيبَ المدرسة افتراضاً — فالشُّعبُ من 7/1 إلى 12/4 هنا أيضاً.
        return wing.class_groups()
    return groups.filter(id__in=taught_class_ids(user, year)).in_school_order()


def can_read_student(user, student, school, year, scope=None):
    """هل يرى هذا المستخدمُ ملفَّ هذا الطالب؟

    القيادةُ وأهلُ الرعاية: كلُّ طالبٍ في المدرسة. والمشرفُ الإداريُّ: طلبةُ
    جناحه بقيدهم الجاري في العام الجاري، لا بـ`year` القادم من الطلب. والمعلّمُ:
    من يُدرّسه — أي من كان مسجَّلاً في شعبةٍ من شُعبه في هذا العام.
    """
    role = user.get_role()
    if sees_whole_school(user):
        return True
    if role not in MODULE_ROLES:
        return False
    wing = _wing_scope(user, school, scope)
    if wing is not None:
        return wing.covers_student(student.id)
    return StudentEnrollment.objects.filter(
        student=student,
        is_active=True,
        class_group_id__in=taught_class_ids(user, year),
        class_group__school=school,
    ).exists()
