"""قراءاتُ شؤون الطلبة التي يشترك فيها أكثرُ من مسار — بلا `request` فتعمل في العامل كما في الطلب."""

from __future__ import annotations

from typing import Any

from django.db.models import Exists, OuterRef, Q

from core.academic_calendar import academic_year_for_school
from core.models.academic import ClassGroup, ParentStudentLink, StudentEnrollment
from core.models.access import Membership
from core.models.user import CustomUser
from core.phone_search import phone_holder_ids
from core.privacy import national_id_search_q


def student_register(
    school: Any, year: str, params: Any, *, partial_id: bool = False
) -> tuple[Any, dict[int, dict[str, Any]]]:
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
            Q(user__full_name__icontains=q)
            | national_id_search_q("user__national_id", q, partial=partial_id)
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


def guardian_ids_by_phone(school: Any, term: str) -> list:
    """معرّفاتُ أولياء الأمر في المدرسة ممّن يحوي جوّالُه الأرقامَ المكتوبة — بلا قراءةٍ للعمود الصريح."""
    parents = CustomUser.objects.filter(
        pk__in=ParentStudentLink.objects.filter(school=school).values("parent_id")
    )
    return list(phone_holder_ids(parents, term))


def guardian_phones(parent_ids: Any) -> dict:
    """{معرّفُ وليّ الأمر: جوّالُه} لمن في الصفحة وحدَهم."""
    ids = {pk for pk in parent_ids if pk}
    users = CustomUser.objects.filter(pk__in=ids).only("pk", "phone", "phone_encrypted")
    return {u.pk: u.get_phone_decrypted() for u in users}


def attach_guardian_phones(page: Any) -> Any:
    """يضع `guardian_phone` على كلّ صفٍّ في الصفحة من النسخة المشفَّرة، ويُرجع الصفحةَ نفسَها."""
    phones = guardian_phones(m.guardian_parent_id for m in page)
    for m in page:
        m.guardian_phone = phones.get(m.guardian_parent_id, "")
    return page


def transfer_form_options(school: Any) -> tuple[list, Any]:
    """خياراتُ نموذج الانتقال: كلُّ طالبٍ بصفّه وشعبته (استعلامٌ واحدٌ للقيود)، وكلُّ شعبةٍ نشطةٍ هدفاً داخليّاً."""
    students = list(
        Membership.objects.filter(school=school, role__name="student", is_active=True)
        .select_related("user")
        .order_by("user__full_name")
    )
    current: dict = {}
    for enrollment in (
        StudentEnrollment.objects.filter(
            student_id__in=[m.user_id for m in students],
            class_group__school=school,
            is_active=True,
        )
        .select_related("class_group")
        .newest_first()
    ):
        current.setdefault(enrollment.student_id, enrollment.class_group)
    for membership in students:
        klass = current.get(membership.user_id)
        membership.class_grade = klass.grade if klass else ""
        membership.class_id = klass.pk if klass else ""
        membership.class_label = klass.short_label if klass else "بلا شعبة"
    return students, ClassGroup.objects.filter(
        school=school, is_active=True, academic_year=academic_year_for_school(school)
    )


def active_class(school: Any, class_id: Any) -> Any:
    """الشعبةُ النشطة في المدرسة بمعرّفها، أو `None`."""
    return ClassGroup.objects.filter(id=class_id, school=school, is_active=True).first()
