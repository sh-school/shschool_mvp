"""قراءةُ بحث الطالب عند إنشاء الانتقال واختيارِ هدف التعديل (W-20261114-010).

وحدةٌ مستقلّةٌ عن `selectors.py` حفاظاً على سقف الحجم؛ كلُّ دالّةٍ تُرجع للعرض ما يحتاجه دفعةً واحدة.
"""

from typing import Any
from uuid import UUID

from core.models.academic import ClassGroup, StudentEnrollment
from core.models.user import CustomUser

from .models import StudentTransfer

#: أقلُّ حروف البحث، وأقصى المقترَح — يوافقان طلبَ المدير (حرفٌ واحدٌ لا يبحث).
MIN_QUERY_LENGTH = 2
MAX_SUGGESTIONS = 10


def _current_classes(student_ids: list[Any], school: Any) -> dict[Any, Any]:
    """شعبةُ كلِّ طالبٍ الحاليّة باستعلامٍ واحد."""
    current: dict[Any, Any] = {}
    for enrollment in (
        StudentEnrollment.objects.filter(
            student_id__in=student_ids, class_group__school=school, is_active=True
        )
        .select_related("class_group")
        .newest_first()
    ):
        current.setdefault(enrollment.student_id, enrollment.class_group)
    return current


def _pick_row(student: Any, klass: Any) -> dict[str, Any]:
    """سطرُ اقتراحٍ: ما تحتاجه الشاشةُ لتعبئة الصفّ والشعبة بعد الاختيار."""
    return {
        "id": student.pk,
        "name": student.full_name,
        "grade": klass.grade if klass else "",
        "class_id": klass.pk if klass else "",
        "class_label": klass.short_label if klass else "بلا شعبة",
    }


def search_transfer_students(school: Any, scope: Any, query: str) -> list[dict[str, Any]]:
    """طلبةُ المدرسة بالاسم ضمن نطاق المستخدم (`scope.narrow`)؛ أقلُّ من حرفين لا يبحث، وأقصاها عشرة."""
    query = (query or "").strip()
    if len(query) < MIN_QUERY_LENGTH:
        return []
    students = list(
        scope.narrow(
            CustomUser.objects.filter(
                memberships__school=school,
                memberships__role__name="student",
                memberships__is_active=True,
                full_name__icontains=query,
            ),
            "pk",
        )
        .distinct()
        .order_by("full_name")[:MAX_SUGGESTIONS]
    )
    current = _current_classes([s.pk for s in students], school)
    return [_pick_row(s, current.get(s.pk)) for s in students]


def picked_student(school: Any, scope: Any, raw_id: Any) -> dict[str, Any] | None:
    """الطالبُ المختار (إن وُجد في نطاق المستخدم) لإعادة رسم النموذج بعد خطأ."""
    try:
        student_id = UUID(str(raw_id))
    except ValueError:
        return None
    student = scope.narrow(
        CustomUser.objects.filter(
            pk=student_id,
            memberships__school=school,
            memberships__role__name="student",
            memberships__is_active=True,
        ),
        "pk",
    ).first()
    if student is None:
        return None
    return _pick_row(student, _current_classes([student.pk], school).get(student.pk))


def edit_target_classes(transfer: StudentTransfer) -> list[Any]:
    """الشعبُ التي يُختار منها هدفُ الانتقال الداخليّ: النشطةُ من صفّ الطالب الحاليّ دون شعبته."""
    current = StudentEnrollment.objects.current_of(transfer.student, transfer.school)
    if current is None:
        return []
    source = current.class_group
    return list(
        ClassGroup.objects.filter(
            school=transfer.school,
            is_active=True,
            academic_year=source.academic_year,
            grade=source.grade,
        ).exclude(pk=source.pk)
    )
