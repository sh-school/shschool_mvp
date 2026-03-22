"""
analytics/tasks.py
━━━━━━━━━━━━━━━━━━
Celery tasks لوحدة التحليلات

المهام:
  - send_monthly_kpi_report: إرسال تقرير KPIs شهري PDF للمدير
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="analytics.send_monthly_kpi_report",
    bind=True,
    max_retries=3,
    default_retry_delay=300,  # 5 دقائق بين المحاولات
)
def send_monthly_kpi_report(self, school_id=None):
    """
    يولّد تقرير KPIs PDF ويرسله بالبريد لمدير المدرسة.
    إذا لم يُحدَّد school_id يُرسَل لكل المدارس.
    """
    try:
        from django.conf import settings
        from django.core.mail import EmailMessage
        from django.template.loader import render_to_string

        from analytics.services import KPIService
        from core.models import School
        from core.pdf_utils import render_pdf_bytes
        from quality.models import OperationalDomain

        schools = (
            [School.objects.get(id=school_id)]
            if school_id
            else School.objects.filter(is_active=True)
        )

        for school in schools:
            logger.info("إنشاء تقرير KPIs لـ %s", school.name)

            # ── حساب المؤشرات ─────────────────────────────────────────
            data = KPIService.compute(school)

            # ── تقدم الخطة التشغيلية ──────────────────────────────────
            plan_domains = OperationalDomain.objects.filter(
                school=school, academic_year=data["year"]
            ).order_by("order")

            # ── المؤشرات الحمراء للتوصيات ─────────────────────────────
            red_kpis = [
                kpi
                for kpi in data["kpis"].values()
                if kpi.get("traffic") == "red" and kpi.get("value") is not None
            ]

            ctx = {
                **data,
                "plan_domains": plan_domains,
                "red_kpis": red_kpis,
            }

            # ── توليد PDF ─────────────────────────────────────────────
            html = render_to_string("analytics/kpi_monthly_report.html", ctx)
            pdf_bytes = render_pdf_bytes(html)

            # ── إيجاد مدير المدرسة ────────────────────────────────────
            from core.models import Membership

            director = (
                Membership.objects.filter(school=school, is_active=True, role__name="director")
                .select_related("user")
                .first()
            )

            if not director or not director.user.email:
                logger.warning("لا يوجد مدير بريد إلكتروني للمدرسة %s — تخطي", school.name)
                continue

            # ── إرسال البريد ──────────────────────────────────────────
            subject = f"[SchoolOS] تقرير KPIs الشهري — {data['month_label']} — {school.name}"
            body = (
                f"السلام عليكم،\n\n"
                f"مرفق تقرير المؤشرات الكمية الشهري لمدرسة {school.name}.\n\n"
                f"ملخص سريع:\n"
                f"  ✅ مؤشرات خضراء : {data['summary']['green']}\n"
                f"  ⚠️  تحتاج متابعة : {data['summary']['yellow']}\n"
                f"  🔴 تحت الهدف    : {data['summary']['red']}\n\n"
                f"SchoolOS v6 — تقرير آلي"
            )
            email = EmailMessage(
                subject=subject,
                body=body,
                from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "noreply@schoolos.qa"),
                to=[director.user.email],
            )
            email.attach(
                filename=f"kpi_{school.code}_{data['month_label']}.pdf",
                content=pdf_bytes,
                mimetype="application/pdf",
            )
            email.send(fail_silently=False)
            logger.info(
                "✅ تقرير KPIs أُرسل إلى %s للمدرسة %s",
                director.user.email,
                school.name,
            )

    except Exception as exc:
        logger.exception("فشل إرسال تقرير KPIs: %s", exc)
        raise self.retry(exc=exc)
