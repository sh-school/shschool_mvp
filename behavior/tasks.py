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

logger = logging.getLogger(__name__)


@shared_task(
    name="behavior.weekly_risk_check",
    bind=True,
    max_retries=2,
    default_retry_delay=300,
)
def weekly_risk_check(self, school_id=None):
    """
    فحص أسبوعي — يحدد الطلاب المعرّضين لخطر سلوكي (نقاط >= 80 مخصومة).

    يُشغَّل من Celery Beat أسبوعياً (مثلاً كل أحد صباحاً).
    يستخدم .iterator(chunk_size=200) لتجنب تحميل كل الطلاب في الذاكرة.

    الإجراءات:
      1. يفحص كل المدارس النشطة (أو مدرسة محددة)
      2. يجد الطلاب الذين تجاوزت نقاطهم المخصومة الحد (80 نقطة)
      3. يرسل إشعار in_app للقيادة (المدير + النائب الإداري)
    """
    try:
        from django.db.models import Count

        from behavior.models import BehaviorInfraction
        from core.models import Membership, School

        # نظام النقاط ملغى — RISK = 5 مخالفات فأكثر (أو 2+ من الدرجة 3-4)
        RISK_COUNT_THRESHOLD = 5

        if school_id:
            schools = School.objects.filter(id=school_id, is_active=True)
        else:
            schools = School.objects.filter(is_active=True)

        total_flagged = 0

        for school in schools.iterator(chunk_size=200):
            # ── الطلاب المعرّضين للخطر (حسب عدد المخالفات) ──
            at_risk = (
                BehaviorInfraction.objects.filter(school=school)
                .values("student_id", "student__full_name")
                .annotate(count=Count("id"))
                .filter(count__gte=RISK_COUNT_THRESHOLD)
                .order_by("-count")
            )

            risk_list = list(at_risk)
            if not risk_list:
                continue

            total_flagged += len(risk_list)

            # ── إشعار القيادة ──────────────────────────────────
            try:
                from notifications.hub import NotificationHub

                leadership = (
                    Membership.objects.filter(
                        school=school,
                        is_active=True,
                        role__name__in=["principal", "vice_admin", "social_worker"],
                    )
                    .select_related("user")
                    .iterator(chunk_size=200)
                )

                student_names = ", ".join(r["student__full_name"] for r in risk_list[:5])
                extra = f" و{len(risk_list) - 5} آخرين" if len(risk_list) > 5 else ""

                for member in leadership:
                    NotificationHub.send(
                        user=member.user,
                        school=school,
                        event_type="behavior_risk",
                        title=f"تنبيه سلوكي: {len(risk_list)} طالب في خطر",
                        body=(
                            f"الطلاب التالية أسماؤهم تجاوزوا حد {RISK_THRESHOLD} نقطة مخصومة:\n"
                            f"{student_names}{extra}"
                        ),
                        channels=["in_app"],
                    )

            except Exception as e:
                logger.warning(
                    "weekly_risk_check: notification failed for school %s: %s",
                    school.name,
                    e,
                )

            logger.info(
                "weekly_risk_check: school %s — %d students at risk",
                school.name,
                len(risk_list),
            )

        logger.info(
            "weekly_risk_check complete: %d students flagged across all schools",
            total_flagged,
        )
        return {"total_flagged": total_flagged}

    except Exception as exc:
        logger.exception("weekly_risk_check error: %s", exc)
        raise self.retry(exc=exc)
