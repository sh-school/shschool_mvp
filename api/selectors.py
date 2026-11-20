"""قراءاتُ REST المشتركة — خارج ملفّ العروض كي لا يحمل سقفَ الطبقات (W-20261101-007)."""

from __future__ import annotations

from typing import Any

from django.db.models import Q, QuerySet
from django.shortcuts import get_object_or_404

from core.models import CustomUser, StudentEnrollment
from core.permissions import get_teacher_student_ids
from core.privacy import national_id_search_q


def restrict_to_visible_students(qs: QuerySet, user: Any, field: str = "student_id") -> QuerySet:
    """يحصر الاستعلامَ في طلبة صاحب الطلب — بنطاق الويب نفسِه (`get_teacher_student_ids`).

    المعلّمُ والمنسّقُ ومشرفُ الجناح لطلبتهم، والقيادةُ (None) للمدرسة كلِّها. كانت قائمتا الطلبة
    والحضور بحصر المدرسة وحدَه، فيقرأ أيُّ معلّمٍ حضورَ أيّ طالبٍ بـ`?student_id=` وهو محجوبٌ
    عنه في `students/<id>/attendance/` (VULN-002) — القيدُ يُتجاوز من المسار المجاور.
    """
    visible = get_teacher_student_ids(user)
    if visible is None:
        return qs
    return qs.filter(**{f"{field}__in": visible})


def visible_enrollments(
    user: Any, school: Any, year: str, *, class_id: str = "", search: str = ""
) -> QuerySet:
    """قيودُ العام الجارية المرئيّةُ لصاحب الطلب — قائمةُ `students/` في الـAPI.

    البحثُ بالاسم باحتواء، وبالرقم الشخصيّ بسياسة `core.privacy` (#849): `SearchFilter` كان
    يطبّق `icontains` على الرقم لكلّ من يمرّ، فيُستخرج رقمٌ خانةً خانةً وإن سُتر في الاستجابة.
    الاحتواءُ في الرقم للإدارة وحدَها، ولغيرها التساوي التامّ.
    """
    qs = StudentEnrollment.objects.filter(
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    ).select_related("student", "class_group")
    qs = restrict_to_visible_students(qs, user)
    if class_id:
        qs = qs.filter(class_group_id=class_id)
    if term := search.strip()[:100]:
        qs = qs.filter(
            Q(student__full_name__icontains=term)
            | national_id_search_q("student__national_id", term, user=user)
        )
    return qs


def school_student_or_404(school: Any, student_id: Any) -> CustomUser:
    """طالبٌ من عضويّة مدرسة الطلب النشطة — وإلا 404؛ فلا يُقرأ مستخدمُ مدرسةٍ أخرى بمعرّفه."""
    return get_object_or_404(
        CustomUser.objects.filter(
            memberships__school=school, memberships__is_active=True
        ).distinct(),
        id=student_id,
    )
