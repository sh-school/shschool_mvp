"""قراءاتُ الأجنحة التي تعرضها العروض — دوالُّ تُرجع ولا تكتب شيئاً."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from django.db.models import F, Q

from core.models import School, StudentEnrollment
from core.models.academic import Wing
from core.sorting import arabic_key, normalise_arabic

if TYPE_CHECKING:
    from .scope import StudentScope


def students_in_wings_matching(
    school: School,
    wings: Iterable[Wing],
    query: str,
    limit: int,
    scope: StudentScope | None = None,
) -> list[StudentEnrollment]:
    """قيودُ طلاب هذه الأجنحة بالاسم (بلا تشكيلٍ ولا همزات) أو أوّلِ الرقم الشخصيّ.

    مرتّبةً بالاسم، وأوّلُ `limit` منها — والمستدعي يطلب واحداً زائداً ليعرف أنّ وراءها المزيد.
    والطالبُ من قيدُه الجاري في جناحي — لا من بقي له قيدٌ قديمٌ نشطٌ في شعبةٍ منه: للمقيَّد
    بجناحه طلبةُ نطاقه، ولغيره لا تضييقَ فوق أجنحته (القيادةُ ترى الخمسة).
    """
    shaped = normalise_arabic(query)
    if scope is not None and scope.is_wing_bound:
        in_scope: object = scope.student_ids()
    else:
        in_scope = StudentEnrollment.objects.filter(is_active=True).values_list(
            "student_id", flat=True
        )
    return list(
        StudentEnrollment.objects.filter(
            is_active=True,
            class_group__school=school,
            class_group__wing__in=wings,
        )
        .annotate(name_key=arabic_key(F("student__full_name")))  # type: ignore[no-untyped-call]
        .filter(Q(name_key__icontains=shaped) | Q(student__national_id__startswith=query))
        .filter(student_id__in=in_scope)
        .select_related("student", "class_group")
        .order_by("student__full_name")[:limit]
    )
