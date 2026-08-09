"""
behavior/tasks.py
━━━━━━━━━━━━━━━━━
Celery tasks لوحدة السلوك الطلابي.

المهام:
  - weekly_risk_check: فحص أسبوعي للطلاب المعرّضين للخطر السلوكي
    يستخدم .iterator(chunk_size=200) لتجنب تحميل كل الطلاب في الذاكرة.
"""

import logging

from celery import shared_task

from core.celery_tasks import school_rls_scope

logger = logging.getLogger(__name__)


@shared_task(
    name="behavior.weekly_risk_check",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def weekly_risk_check(self, school_id=None):
    """Check behavioral risk inside one school scope at a time."""
    try:
        from django.db.models import Count

        from behavior.models import BehaviorInfraction
        from core.models import Membership, School

        risk_count_threshold = 5

        schools = School.objects.filter(is_active=True)

        if school_id:
            schools = schools.filter(id=school_id)

        total_flagged = 0

        for school in schools.iterator(chunk_size=100):
            with school_rls_scope(school.id):
                at_risk = (
                    BehaviorInfraction.objects.filter(school=school)
                    .values(
                        "student_id",
                        "student__full_name",
                    )
                    .annotate(count=Count("id"))
                    .filter(count__gte=risk_count_threshold)
                    .order_by("-count")
                )

                risk_list = list(at_risk)

                if not risk_list:
                    continue

                total_flagged += len(risk_list)

                try:
                    from notifications.hub import NotificationHub

                    leadership = (
                        Membership.objects.filter(
                            school=school,
                            is_active=True,
                            role__name__in=[
                                "principal",
                                "vice_admin",
                                "social_worker",
                            ],
                        )
                        .select_related("user")
                        .iterator(chunk_size=200)
                    )

                    student_names = ", ".join(row["student__full_name"] for row in risk_list[:5])

                    extra = f" و{len(risk_list) - 5} آخرين" if len(risk_list) > 5 else ""

                    recipients = [member.user for member in leadership]

                    if recipients:
                        NotificationHub.dispatch(
                            event_type="behavior_risk",
                            school=school,
                            recipients=recipients,
                            title=("تنبيه سلوكي: " f"{len(risk_list)} طالب في خطر"),
                            body=(
                                "الطلاب التالية أسماؤهم تجاوزوا "
                                f"حد {risk_count_threshold} مخالفات:\n"
                                f"{student_names}{extra}"
                            ),
                        )

                except Exception as exc:
                    logger.warning(
                        "weekly_risk_check: notification " "failed for school %s: %s",
                        school.name,
                        exc,
                    )

                logger.info(
                    "weekly_risk_check: school %s — " "%d students at risk",
                    school.name,
                    len(risk_list),
                )

        logger.info(
            "weekly_risk_check complete: " "%d students flagged across all schools",
            total_flagged,
        )

        return {"total_flagged": total_flagged}

    except Exception as exc:
        logger.exception(
            "weekly_risk_check error: %s",
            exc,
        )
        raise self.retry(exc=exc)
