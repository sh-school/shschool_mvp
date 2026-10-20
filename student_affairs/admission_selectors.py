"""قراءةُ طلبات الالتحاق (نموذج 07) — طبقةُ المحدِّدات لعروض `admission_views` (W-20261001-033)."""

from typing import Any

from django.shortcuts import get_object_or_404

from core.models.academic import ClassGroup

from .admission_models import AdmissionApplication


def admission_list(school: Any, status: str = "", limit: int = 100) -> list[AdmissionApplication]:
    """أحدثُ طلبات المدرسة، مصفّاةً بالحالة إن وُجدت."""
    applications = AdmissionApplication.objects.filter(school=school)
    if status:
        applications = applications.filter(status=status)
    return list(applications.order_by("-created_at")[:limit])


def admission_or_404(school: Any, pk: Any) -> AdmissionApplication:
    """الطلبُ في مدرسته أو 404 — فلا يصل أحدٌ إلى طلب مدرسةٍ أخرى."""
    return get_object_or_404(AdmissionApplication, pk=pk, school=school)


def placement_classes(application: AdmissionApplication) -> list[ClassGroup]:
    """الشعبُ الفاعلة في صفّ الطلب المطلوب وعامه — خيارات التشعيب."""
    return list(
        ClassGroup.objects.filter(
            school=application.school,
            grade=application.grade,
            academic_year=application.academic_year,
            is_active=True,
        ).order_by("section")
    )


def class_group_in(school: Any, pk: Any) -> ClassGroup | None:
    """الشعبةُ بمعرّفها إن كانت من هذه المدرسة، وإلا None."""
    return ClassGroup.objects.filter(pk=pk, school=school).first()
