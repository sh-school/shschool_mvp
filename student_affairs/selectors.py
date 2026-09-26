"""قراءاتُ شؤون الطلبة التي يشترك فيها أكثرُ من مسار — بلا `request` فتعمل في العامل كما في الطلب."""

from __future__ import annotations

from typing import Any

from django.db.models import Exists, OuterRef, Q

from core.models.academic import StudentEnrollment
from core.models.access import Membership


def student_register(school: Any, year: str, params: Any) -> tuple[Any, dict[int, dict[str, Any]]]:
    """الاستعلامُ المشترَك بين تصديرَي سجلّ الطلاب — Excel وPDF: `(الطلبة، القيدُ لكلّ طالب)`.

    نفس فلترة `student_list`، بما فيها الإصلاحُ الذي أخذته الشاشةُ في #191 ولم
    يكن قد بلغ أيَّ تصدير: المقيَّدُ أوّلاً، ومن لا قيدَ له هذا العامَ يخرج
    بترشيحٍ صريحٍ (`status=unenrolled` أو `all`) لا بعدٍّ يُساوي به العضويّةَ
    بالقيد.

    `params` هو `QueryDict` الرابط (`request.GET`)؛ والعامُ يُمرَّر لا يُشتقّ هنا كي يبقى النداءُ نقيّاً.
    """
    q = params.get("q", "").strip()
    grade_filter = params.get("grade", "")
    section_filter = params.get("section", "")

    students = (
        Membership.objects.filter(
            school=school,
            role__name="student",
            is_active=True,
        )
        .select_related("user")
        .order_by("user__full_name")
    )

    if q:
        students = students.filter(
            Q(user__full_name__icontains=q) | Q(user__national_id__icontains=q)
        )

    status = params.get("status") or "enrolled"
    is_enrolled = Exists(
        StudentEnrollment.objects.filter(
            student_id=OuterRef("user_id"),
            class_group__school=school,
            class_group__academic_year=year,
            is_active=True,
        )
    )
    if status == "enrolled":
        students = students.filter(is_enrolled)
    elif status == "unenrolled":
        students = students.exclude(is_enrolled)

    enrollment_data: dict[int, dict[str, Any]] = {}
    for enr in StudentEnrollment.objects.filter(
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    ).values("student_id", "class_group__grade", "class_group__section"):
        enrollment_data[enr["student_id"]] = enr

    if grade_filter:
        enrolled_ids = [
            sid
            for sid, data in enrollment_data.items()
            if data["class_group__grade"] == grade_filter
        ]
        students = students.filter(user_id__in=enrolled_ids)
    if section_filter:
        enrolled_ids = [
            sid
            for sid, data in enrollment_data.items()
            if data.get("class_group__section") == section_filter
        ]
        students = students.filter(user_id__in=enrolled_ids)

    return students, enrollment_data
