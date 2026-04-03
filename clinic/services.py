"""
clinic/services.py — Business Logic لوحدة العيادة المدرسية
════════════════════════════════════════════════════════════
Service Layer للعيادة — فصل الـ business logic عن الـ views.

القواعد:
  - transaction.atomic() للعمليات الذرّية
  - كل method يُعيد Model أو dict — ليس HttpResponse
  - الإشعارات منفصلة عن الإنشاء (Single Responsibility)
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School


class ClinicService:
    """خدمات العيادة المدرسية — تسجيل الزيارات + الإشعارات."""

    @staticmethod
    @transaction.atomic
    def record_visit(
        school: "School",
        student: "CustomUser",
        nurse: "CustomUser",
        reason: str,
        symptoms: str = "",
        temperature=None,
        treatment: str = "",
        is_sent_home: bool = False,
    ):
        """
        تسجيل زيارة عيادة جديدة.

        يُنشئ ClinicVisit في transaction ذرّي.
        إذا أُرسل الطالب للمنزل، يُحاوَل إرسال إشعار لولي الأمر.

        Args:
            school: كائن المدرسة
            student: الطالب الزائر
            nurse: الممرض المسجِّل
            reason: سبب الزيارة
            symptoms: الأعراض (اختياري)
            temperature: درجة الحرارة (اختياري)
            treatment: العلاج المُعطى (اختياري)
            is_sent_home: هل أُرسل الطالب للمنزل

        Returns:
            ClinicVisit: سجل الزيارة المنشأ
        """
        from core.models import ClinicVisit

        visit = ClinicVisit.objects.create(
            school=school,
            student=student,
            nurse=nurse,
            reason=reason,
            symptoms=symptoms,
            temperature=temperature,
            treatment=treatment,
            is_sent_home=is_sent_home,
            parent_notified=False,
        )

        if is_sent_home:
            notified = ClinicService._notify_parents_sent_home(visit, school, nurse)
            # update_fields لتجنّب حفظ الكائن كاملاً مرتين
            if notified != visit.parent_notified:
                visit.parent_notified = notified
                visit.save(update_fields=["parent_notified"])

        logger.info(
            "زيارة عيادة جديدة: طالب=%s مدرسة=%s منزل=%s",
            student.full_name, school.code, is_sent_home,
        )
        return visit

    @staticmethod
    def _notify_parents_sent_home(visit, school, nurse) -> bool:
        """
        يُرسل إشعار لأولياء أمور الطالب عند إرساله للمنزل.

        Returns:
            bool: True إذا أُرسل إشعار بنجاح، False إذا فشل
        """
        try:
            from core.models import ParentStudentLink
            from notifications.services import NotificationService

            links = (
                ParentStudentLink.objects
                .filter(student=visit.student, school=school)
                .select_related("parent")
            )
            sent = False
            for link in links:
                parent = link.parent
                if not parent.email:
                    continue
                msg = (
                    f"مدرسة الشحانية: تم إرسال ابنكم/ابنتكم {visit.student.full_name} "
                    f"إلى المنزل من العيادة المدرسية بسبب: {visit.reason}. "
                    f"يُرجى التواصل مع المدرسة للاستفسار."
                )
                NotificationService.send_email(
                    school=school,
                    recipient_email=parent.email,
                    subject=f"إشعار عيادة: {visit.student.full_name}",
                    body_text=msg,
                    student=visit.student,
                    notif_type="custom",
                    sent_by=nurse,
                )
                sent = True
            return sent

        except (ImportError, OSError, RuntimeError, ValueError) as e:
            logger.exception(
                "فشل إرسال إشعار العيادة لولي الأمر [visit=%s]: %s",
                visit.pk, e,
            )
            return False
