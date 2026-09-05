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
"""

from core.models.academic import ClassGroup, StudentEnrollment

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
#: رعايةُ الطلاب جميعاً.
SCHOOL_WIDE_READERS = LEADERSHIP | {
    "social_worker",
    "psychologist",
    "nurse",
    "academic_advisor",
    "coordinator",
    "admin_supervisor",
    "activities_coordinator",
}

#: من يدخل المركزَ أصلاً. المعلّمُ داخلٌ، لكنّ ما يراه محدودٌ بمن يُدرّسهم.
MODULE_ROLES = SCHOOL_WIDE_READERS | {
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


def visible_class_groups(user, school, year):
    """الشُّعبُ التي تظهر لهذا المستخدم في صفحة الشُّعب."""
    groups = ClassGroup.objects.filter(school=school, academic_year=year, is_active=True)
    role = user.get_role()
    if user.is_superuser or role in SCHOOL_WIDE_READERS:
        return groups.in_school_order()
    return groups.filter(id__in=taught_class_ids(user, year)).in_school_order()


def can_read_student(user, student, school, year):
    """هل يرى هذا المستخدمُ ملفَّ هذا الطالب؟

    القيادةُ وأهلُ الرعاية: كلُّ طالبٍ في المدرسة. والمعلّمُ: من يُدرّسه —
    أي من كان مسجَّلاً في شعبةٍ من شُعبه في هذا العام.
    """
    role = user.get_role()
    if user.is_superuser or role in SCHOOL_WIDE_READERS:
        return True
    if role not in MODULE_ROLES:
        return False
    return StudentEnrollment.objects.filter(
        student=student,
        is_active=True,
        class_group_id__in=taught_class_ids(user, year),
        class_group__school=school,
    ).exists()
