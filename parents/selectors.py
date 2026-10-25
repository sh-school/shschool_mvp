"""قراءاتُ تطبيق الأولياء — بلا ORM في العروض (سقّاطة الطبقات)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from django.db.models import OuterRef, Subquery

from core.models import Membership, ParentStudentLink, StudentEnrollment
from core.models.user import CustomUser
from core.phone_search import phone_holder_ids


def parent_ids_by_phone(links: Any, term: str) -> list:
    """معرّفاتُ أولياء الأمر في هذه الروابط ممّن يحوي جوّالُه الأرقامَ المكتوبة (بلا العمود الصريح)."""
    parents = CustomUser.objects.filter(pk__in=links.values("parent_id"))
    return list(phone_holder_ids(parents, term))


def _this_year_seat(student_id: Any, school: Any, year: str):
    """قيدُ الطالب الفعّال في هذا العام — الأحدثُ أوّلاً."""
    return StudentEnrollment.objects.filter(
        student_id=student_id,
        class_group__school=school,
        class_group__academic_year=year,
        is_active=True,
    ).order_by("-enrolled_at")


def link_form_students(school: Any, year: str):
    """طلابُ هذا العام لقائمة الربط، لكلٍّ صفُّه وشعبتُه (`grade_code`/`section_code`).

    الرقمُ الشخصيّ لا يُعرض في القائمة، فطالبان بالاسم نفسه يُميَّزان بصفّ كلٍّ منهما وشعبته (W-20261012-006).
    """
    seat = _this_year_seat(OuterRef("pk"), school, year)
    student_ids = StudentEnrollment.objects.filter(
        class_group__school=school, class_group__academic_year=year, is_active=True
    ).values_list("student_id", flat=True)
    return (
        CustomUser.objects.filter(id__in=student_ids)
        .annotate(
            grade_code=Subquery(seat.values("class_group__grade")[:1]),
            section_code=Subquery(seat.values("class_group__section")[:1]),
        )
        .order_by("full_name")
    )


def link_form_parents(school: Any, year: str) -> list:
    """أولياءُ المدرسة لقائمة الربط. وليّان بالاسم نفسه يُميَّزان باسم أحد أبنائهما وصفّه (`has_namesake`).

    استعلامٌ واحدٌ يحمل ابنَ كلٍّ منهما (`child_name`/`child_grade`/`child_section`) فلا استعلامَ لكلّ صف.
    """
    parent_ids = Membership.objects.filter(
        school=school, is_active=True, role__name="parent"
    ).values_list("user_id", flat=True)
    first_link = ParentStudentLink.objects.filter(school=school, parent_id=OuterRef("pk")).order_by(
        "student__full_name"
    )
    child_seat = _this_year_seat(OuterRef("child_id"), school, year)
    parents = list(
        CustomUser.objects.filter(id__in=parent_ids)
        .annotate(
            child_id=Subquery(first_link.values("student_id")[:1]),
            child_name=Subquery(first_link.values("student__full_name")[:1]),
        )
        .annotate(
            child_grade=Subquery(child_seat.values("class_group__grade")[:1]),
            child_section=Subquery(child_seat.values("class_group__section")[:1]),
        )
        .order_by("full_name")
    )
    name_counts = Counter(parent.full_name for parent in parents)
    for parent in parents:
        setattr(parent, "has_namesake", name_counts[parent.full_name] > 1)  # noqa: B010 — وسمٌ للقالب لا حقلُ نموذج
    return parents
