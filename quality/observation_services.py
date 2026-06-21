"""
quality/observation_services.py
منطق الإشراف على أداء المعلّم (Fat Service / Skinny Views).
"""

from django.db import transaction
from django.utils import timezone

from quality.observation_models import (
    ClassroomObservation,
    ObservationCriterion,
    ObservationScore,
)


class ObservationService:
    @staticmethod
    def criteria_for(school):
        return ObservationCriterion.objects.filter(school=school, is_active=True).order_by(
            "order"
        )

    @staticmethod
    @transaction.atomic
    def save_scores(observation, ratings: dict, recommendations: dict):
        """ratings/recommendations: {criterion_id(str): value}. يُنشئ/يحدّث التقييمات."""
        crits = {
            str(c.id): c
            for c in ObservationService.criteria_for(observation.school)
        }
        for cid, crit in crits.items():
            ObservationScore.objects.update_or_create(
                observation=observation,
                criterion=crit,
                defaults={
                    "rating": (ratings.get(cid) or "")[:15],
                    "recommendation": (recommendations.get(cid) or "").strip(),
                },
            )
        observation.score_percent = observation.compute_score_percent()
        observation.save(update_fields=["score_percent", "updated_at"])

    @staticmethod
    @transaction.atomic
    def submit(observation, by_user):
        """إرسال الزيارة للمعلّم + إشعار."""
        observation.status = "submitted"
        observation.submitted_at = timezone.now()
        observation.score_percent = observation.compute_score_percent()
        observation.save(update_fields=["status", "submitted_at", "score_percent", "updated_at"])
        ObservationService._notify_teacher(observation)
        return observation

    @staticmethod
    def _notify_teacher(observation):
        try:
            from notifications.hub import NotificationHub

            pct = observation.score_percent
            body = f"أجرى {observation.observer.full_name} زيارة إشرافية على أدائك"
            if pct is not None:
                body += f" — النسبة الإجماليّة {pct}%"
            body += ". يُرجى الاطّلاع والإقرار."
            NotificationHub.dispatch(
                event_type="observation",
                school=observation.school,
                recipients=[observation.teacher],
                title="ملاحظة صفّية جديدة على أدائك",
                body=body,
                related_url=f"/quality/observations/{observation.id}/",
                related_object_id=str(observation.id),
            )
        except Exception:  # noqa: BLE001 — الإشعار لا يُسقط العملية الأساسية
            import logging

            logging.getLogger("quality").exception("observation notify failed")

    @staticmethod
    @transaction.atomic
    def acknowledge(observation, comment=""):
        observation.status = "acknowledged"
        observation.teacher_acknowledged_at = timezone.now()
        observation.teacher_comment = (comment or "").strip()
        observation.save(
            update_fields=[
                "status",
                "teacher_acknowledged_at",
                "teacher_comment",
                "updated_at",
            ]
        )
        return observation

    @staticmethod
    def visible_to(user, school):
        """الملاحظات التي يراها المستخدم: القيادة=الكل، الزائر=ما أنشأه، المعلّم=ما تلقّاه."""
        from core.permissions import OBSERVATION_VIEW_ALL

        qs = ClassroomObservation.objects.filter(school=school).select_related(
            "teacher", "observer", "subject", "class_group"
        )
        role = user.get_role()
        if user.is_superuser or role in OBSERVATION_VIEW_ALL:
            return qs
        from django.db.models import Q

        return qs.filter(Q(observer=user) | Q(teacher=user))
