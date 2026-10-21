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
        school: School,
        student: CustomUser,
        nurse: CustomUser,
        reason: str,
        symptoms: str = "",
        temperature=None,
        treatment: str = "",
        is_sent_home: bool = False,
        service_code: str = "",
        complaint_code: str = "",
        draft_started_at=None,
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
            service_code: رمز الخدمة من `clinic.choices` (اختياري)
            complaint_code: رمز الشكوى من `clinic.choices` (اختياري)
            draft_started_at: لحظة اختيار الطالب (بدء المسودة) لقياس زمن التسجيل (اختياري، وقتٌ فقط)

        Raises:
            ValueError: رمزُ خدمةٍ أو شكوى خارج القائمة المعتمدة

        Returns:
            ClinicVisit: سجل الزيارة المنشأ
        """
        from django.utils import timezone

        from clinic.choices import group_of_service, is_valid_complaint, is_valid_service
        from clinic.models import ClinicVisit

        if service_code and not is_valid_service(service_code):
            raise ValueError(f"رمز خدمة غير معتمد: {service_code}")
        if complaint_code and not is_valid_complaint(complaint_code):
            raise ValueError(f"رمز شكوى غير معتمد: {complaint_code}")

        visit = ClinicVisit.objects.create(
            school=school,
            student=student,
            nurse=nurse,
            service_code=service_code,
            service_group=group_of_service(service_code),
            complaint_code=complaint_code,
            draft_started_at=draft_started_at,
            period_number=ClinicService.derive_period_number(school, student, timezone.now()),
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
            student.pk,
            school.code,
            is_sent_home,
        )
        return visit

    @staticmethod
    def derive_period_number(school: School, student: CustomUser, moment) -> int | None:
        """
        رقمُ الحصة التي يقع فيها `moment` لشعبة الطالب — قراءةً من ScheduleSlot فقط.

        لا يُدخلها الممرّض ولا تُغيَّر بها الجدولُ ولا الحضور؛ وإن لم يُسجَّل الطالبُ في شعبةٍ
        أو وقع الوقتُ خارج الحصص (الفسحة، قبل الدوام) أُعيد None.
        """
        from django.utils import timezone

        from core.models import StudentEnrollment
        from operations.models import ScheduleSlot

        class_group_id = (
            StudentEnrollment.objects.filter(
                student=student, is_active=True, class_group__school=school
            )
            .values_list("class_group_id", flat=True)
            .first()
        )
        if class_group_id is None:
            return None
        local = timezone.localtime(moment)
        # يوم الأسبوع في الجدول: الأحد 0 (Python: الاثنين 0)
        qatar_day = (local.weekday() + 1) % 7
        return (
            ScheduleSlot.objects.live(school, on=local.date())
            .filter(
                class_group_id=class_group_id,
                day_of_week=qatar_day,
                start_time__lte=local.time(),
                end_time__gt=local.time(),
            )
            .order_by("period_number")
            .values_list("period_number", flat=True)
            .first()
        )

    @staticmethod
    @transaction.atomic
    def close_visit(visit, outcome: str):
        """
        إغلاقُ الزيارة بحالة خروج (عودة للصف / استئذان / إحالة) ووقتِ إغلاقٍ للمدّة.

        الاستئذانُ يضبط `is_sent_home` فقط؛ إشعارُ الوليّ يبقى كما في `record_visit`
        ولا يُرسَل هنا (قرارٌ مستقلّ للمالك).

        Raises:
            ValueError: حالةُ خروج خارج القائمة، أو زيارةٌ مُغلقةٌ سلفاً
        """
        from django.utils import timezone

        from clinic.choices import OUTCOME_LEAVE, is_valid_outcome

        if not is_valid_outcome(outcome):
            raise ValueError(f"حالة خروج غير معتمدة: {outcome}")
        if visit.closed_at is not None:
            raise ValueError("الزيارة مُغلقة سلفاً")
        visit.outcome = outcome
        visit.closed_at = timezone.now()
        fields = ["outcome", "closed_at"]
        if outcome == OUTCOME_LEAVE and not visit.is_sent_home:
            visit.is_sent_home = True
            fields.append("is_sent_home")
        visit.save(update_fields=fields)
        return visit

    @staticmethod
    def get_dashboard_stats(school, today=None) -> dict:
        """
        إحصائيات لوحة العيادة — 7 استعلامات في service layer.

        Args:
            school: كائن المدرسة
            today: تاريخ اليوم (افتراضي: اليوم الفعلي)

        Returns:
            dict يحتوي: visits_today, sent_home_today, recent_visits,
                        follow_up_visits, weekly_visits, peak_hours,
                        frequent, month_total
        """
        from datetime import timedelta

        from django.db.models import Count, Q
        from django.db.models.functions import ExtractHour, TruncDate
        from django.utils import timezone

        from clinic.models import ClinicVisit

        today = today or timezone.now().date()
        week_ago = today - timedelta(days=7)

        visits_today = ClinicVisit.objects.filter(
            school=school,
            visit_date__date=today,
        ).count()

        sent_home_today = ClinicVisit.objects.filter(
            school=school,
            visit_date__date=today,
            is_sent_home=True,
        ).count()

        recent_visits = list(
            ClinicVisit.objects.filter(school=school)
            .select_related("student")
            .order_by("-visit_date")[:10]
        )

        follow_up_visits = list(
            ClinicVisit.objects.filter(
                school=school, is_sent_home=True, visit_date__date=today
            ).select_related("student")
        )

        weekly_visits = list(
            ClinicVisit.objects.filter(school=school, visit_date__date__gte=week_ago)
            .values(day=TruncDate("visit_date"))
            .annotate(
                total=Count("id"),
                sent_home=Count("id", filter=Q(is_sent_home=True)),
            )
            .order_by("day")
        )

        peak_hours = list(
            ClinicVisit.objects.filter(school=school, visit_date__date__gte=week_ago)
            .values(hour=ExtractHour("visit_date"))
            .annotate(count=Count("id"))
            .order_by("-count")[:5]
        )

        frequent = list(
            ClinicVisit.objects.filter(
                school=school,
                visit_date__month=today.month,
                visit_date__year=today.year,
            )
            .values("student__id", "student__full_name")
            .annotate(visit_count=Count("id"))
            .filter(visit_count__gte=3)
            .order_by("-visit_count")[:10]
        )

        month_total = ClinicVisit.objects.filter(
            school=school,
            visit_date__month=today.month,
            visit_date__year=today.year,
        ).count()

        return {
            "visits_today": visits_today,
            "sent_home_today": sent_home_today,
            "recent_visits": recent_visits,
            "follow_up_visits": follow_up_visits,
            "weekly_visits": weekly_visits,
            "peak_hours": peak_hours,
            "frequent": frequent,
            "month_total": month_total,
        }

    @staticmethod
    def get_chart_data(school, days: int = 30) -> dict:
        """
        بيانات الرسوم البيانية للعيادة — استعلام واحد بدل N×2 استعلامات.

        ✅ v5.4: يستبدل loop يعمل 60 استعلام (2 × 30 يوم) بـ TruncDate aggregation.

        Args:
            school: كائن المدرسة
            days: عدد الأيام (افتراضي: 30)

        Returns:
            dict يحتوي: labels (قائمة تواريخ), visits (أعداد), sent_home (أعداد)
        """
        from datetime import timedelta

        from django.db.models import Count, Q
        from django.db.models.functions import TruncDate
        from django.utils import timezone

        from clinic.models import ClinicVisit

        today = timezone.now().date()
        start_date = today - timedelta(days=days - 1)

        # استعلام واحد يُجمّع كل الأيام في نفس الوقت
        rows = (
            ClinicVisit.objects.filter(school=school, visit_date__date__gte=start_date)
            .values(day=TruncDate("visit_date"))
            .annotate(
                visits=Count("id"),
                sent_home=Count("id", filter=Q(is_sent_home=True)),
            )
            .order_by("day")
        )

        # بناء lookup سريع من الاستعلام الواحد
        rows_by_date = {r["day"]: r for r in rows}

        labels, visits_data, sent_home_data = [], [], []
        for i in range(days - 1, -1, -1):
            d = today - timedelta(days=i)
            row = rows_by_date.get(d, {})
            labels.append(d.strftime("%d/%m"))
            visits_data.append(row.get("visits", 0))
            sent_home_data.append(row.get("sent_home", 0))

        return {
            "labels": labels,
            "visits": visits_data,
            "sent_home": sent_home_data,
        }

    @staticmethod
    def get_health_statistics(school) -> dict:
        """
        إحصائيات صحية للمدرسة — 4 استعلامات في service layer.

        Args:
            school: كائن المدرسة

        Returns:
            dict يحتوي: health_records_count, allergies_count,
                        visits_count, visits_this_month
        """
        from django.utils import timezone

        from clinic.models import ClinicVisit, HealthRecord

        now = timezone.now()

        health_records_count = (
            HealthRecord.objects.filter(student__memberships__school=school)
            .filter(chronic_diseases__isnull=False)
            .exclude(chronic_diseases="")
            .count()
        )

        allergies_count = (
            HealthRecord.objects.filter(student__memberships__school=school)
            .filter(allergies__isnull=False)
            .exclude(allergies="")
            .count()
        )

        visits_count = ClinicVisit.objects.filter(school=school).count()

        visits_this_month = ClinicVisit.objects.filter(
            school=school,
            visit_date__month=now.month,
            visit_date__year=now.year,
        ).count()

        return {
            "health_records_count": health_records_count,
            "allergies_count": allergies_count,
            "visits_count": visits_count,
            "visits_this_month": visits_this_month,
        }

    @staticmethod
    def _notify_parents_sent_home(visit, school, nurse) -> bool:
        """
        يُرسل إشعار لأولياء أمور الطالب عند إرساله للمنزل.

        Returns:
            bool: True إذا أُرسل إشعار بنجاح، False إذا فشل
        """
        from core.parents_freeze import parents_frozen

        if parents_frozen():
            return False

        try:
            from core.models import ParentStudentLink
            from notifications.services import NotificationService

            links = ParentStudentLink.objects.filter(
                student=visit.student, school=school
            ).select_related("parent")
            sent = False
            for link in links:
                parent = link.parent
                if not parent.email:
                    continue
                msg = (
                    f"{school.name}: تم إرسال ابنكم/ابنتكم {visit.student.full_name} "
                    f"إلى المنزل من العيادة المدرسية بسبب: {visit.reason}. "
                    f"يُرجى التواصل مع المدرسة للاستفسار."
                )
                NotificationService.deliver_email(
                    user=parent,
                    school=school,
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
                visit.pk,
                e,
            )
            return False
