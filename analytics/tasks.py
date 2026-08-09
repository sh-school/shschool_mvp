"""
analytics/tasks.py
━━━━━━━━━━━━━━━━━━
Celery tasks لوحدة التحليلات

المهام:
  - send_monthly_kpi_report: إرسال تقرير KPIs شهري PDF للمدير
"""

import logging

from celery import shared_task

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)


@shared_task(
    name="analytics.send_monthly_kpi_report",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def send_monthly_kpi_report(self, school_id=None):
    """Generate KPI reports school-by-school under RLS."""
    try:
        from django.conf import settings
        from django.core.mail import EmailMessage
        from django.template.loader import render_to_string

        from analytics.services import KPIService
        from core.models import Membership, School
        from core.pdf_utils import render_pdf_bytes
        from quality.models import OperationalDomain

        schools = School.objects.filter(is_active=True)

        if school_id:
            schools = schools.filter(id=school_id)

        for school in schools.iterator(chunk_size=100):
            with school_rls_scope(school.id):
                logger.info(
                    "إنشاء تقرير KPIs لـ %s",
                    school.name,
                )

                data = KPIService.compute(school)

                plan_domains = OperationalDomain.objects.filter(
                    school=school,
                    academic_year=data["year"],
                ).order_by("order")

                red_kpis = [
                    kpi
                    for kpi in data["kpis"].values()
                    if (kpi.get("traffic") == "red" and kpi.get("value") is not None)
                ]

                ctx = {
                    **data,
                    "plan_domains": plan_domains,
                    "red_kpis": red_kpis,
                }

                html = render_to_string(
                    "analytics/kpi_monthly_report.html",
                    ctx,
                )

                pdf_bytes = render_pdf_bytes(html)

                director = (
                    Membership.objects.filter(
                        school=school,
                        is_active=True,
                        role__name="principal",
                    )
                    .select_related("user")
                    .first()
                )

                if not director or not director.user.email:
                    logger.warning(
                        "لا يوجد مدير بريد إلكتروني " "للمدرسة %s — تخطي",
                        school.name,
                    )
                    continue

                subject = "[SchoolOS] تقرير KPIs الشهري — " f"{data['month_label']} — {school.name}"

                body = (
                    "السلام عليكم،\n\n"
                    "مرفق تقرير المؤشرات الكمية الشهري "
                    f"لمدرسة {school.name}.\n\n"
                    "ملخص سريع:\n"
                    f"  ✅ مؤشرات خضراء : "
                    f"{data['summary']['green']}\n"
                    f"  ⚠️  تحتاج متابعة : "
                    f"{data['summary']['yellow']}\n"
                    f"  🔴 تحت الهدف    : "
                    f"{data['summary']['red']}\n\n"
                    "SchoolOS v6 — تقرير آلي"
                )

                email = EmailMessage(
                    subject=subject,
                    body=body,
                    from_email=getattr(
                        settings,
                        "DEFAULT_FROM_EMAIL",
                        "noreply@schoolos.qa",
                    ),
                    to=[director.user.email],
                )

                email.attach(
                    filename=(f"kpi_{school.code}_" f"{data['month_label']}.pdf"),
                    content=pdf_bytes,
                    mimetype="application/pdf",
                )

                email.send(fail_silently=False)

                logger.info(
                    "تقرير KPIs أُرسل إلى %s " "للمدرسة %s",
                    director.user.email,
                    school.name,
                )

    except (
        OSError,
        RuntimeError,
        ValueError,
        KeyError,
    ) as exc:
        logger.exception(
            "فشل إرسال تقرير KPIs: %s",
            exc,
        )
        raise self.retry(exc=exc)
