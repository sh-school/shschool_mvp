"""
quality/observation_services.py
منطق الإشراف على أداء المعلّم (Fat Service / Skinny Views).

سير الحالة (قابل للعكس، مُدقَّق):
    draft ──submit──▶ submitted ──acknowledge──▶ acknowledged
      ▲                  │  ▲                          │
      └──── withdraw ────┘  └────────── reopen ────────┘

الحذف ناعم دائماً (archive) — لا تُفقَد سجلّات التقييم أبداً.
"""

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from quality.observation_models import (
    ClassroomObservation,
    ObservationCriterion,
    ObservationScore,
)

# الحقول القابلة للتعديل في الترويسة (عدا teacher الذي يُعالَج كـFK)
_HEADER_FIELDS = (
    "subject_id",
    "class_group_id",
    "observation_date",
    "period",
    "topic",
    "follow_up_mode",
    "follow_up_scope",
    "broadcast_note",
    "general_notes",
)


class ObservationService:
    # ── المعايير + التقييمات ────────────────────────────────────────
    @staticmethod
    def criteria_for(school):
        return ObservationCriterion.objects.filter(school=school, is_active=True).order_by("order")

    @staticmethod
    @transaction.atomic
    def save_scores(observation, ratings: dict, recommendations: dict):
        """ratings/recommendations: {criterion_id(str): value}. يُنشئ/يحدّث كل المعايير."""
        crits = {str(c.id): c for c in ObservationService.criteria_for(observation.school)}
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

    # ── التعديل ─────────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def update_observation(
        observation, *, header: dict, ratings: dict, recommendations: dict, by_user
    ):
        """
        تعديل زيارة (مسودة أو مُرسَلة). المُقَرّة غير قابلة للتعديل — تُعاد فتحها أولاً.
        تعديل المُرسَلة صامت (المعلّم لم يُقِرّ بعد ويرى أحدث نسخة عند الفتح)؛ الإشعار
        الرسمي بالتحديث يمرّ عبر سحب→تعديل→إعادة إرسال.
        """
        if observation.status == "acknowledged":
            raise ValueError("لا يمكن تعديل ملاحظة مُقَرّة — أعد فتحها أولاً.")
        for field in _HEADER_FIELDS:
            if field in header:
                setattr(observation, field, header[field])
        if header.get("teacher") is not None:
            observation.teacher = header["teacher"]
        observation.updated_by = by_user
        observation.save()
        ObservationService.save_scores(observation, ratings, recommendations)
        return observation

    # ── سير الحالة ──────────────────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def submit(observation, by_user):
        """إرسال الزيارة للمعلّم + إشعار. لا يُرسَل إلا من مسودة."""
        if observation.status != "draft":
            return observation
        observation.status = "submitted"
        observation.submitted_at = timezone.now()
        observation.submission_count = (observation.submission_count or 0) + 1
        observation.score_percent = observation.compute_score_percent()
        observation.updated_by = by_user
        observation.save(
            update_fields=[
                "status",
                "submitted_at",
                "submission_count",
                "score_percent",
                "updated_by",
                "updated_at",
            ]
        )
        # التقييم الذاتي: المعلّم هو المُنشئ — لا إشعار له
        if observation.kind == "supervision":
            ObservationService._notify_teacher(
                observation, updated=observation.submission_count > 1
            )
        return observation

    @staticmethod
    @transaction.atomic
    def withdraw(observation, by_user):
        """سحب: مُرسَلة → مسودة (للتعديل قبل إعادة الإرسال)."""
        if observation.status != "submitted":
            return observation
        observation.status = "draft"
        observation.submitted_at = None
        observation.teacher_acknowledged_at = None
        observation.teacher_comment = ""
        observation.updated_by = by_user
        observation.save(
            update_fields=[
                "status",
                "submitted_at",
                "teacher_acknowledged_at",
                "teacher_comment",
                "updated_by",
                "updated_at",
            ]
        )
        ObservationService._dispatch(
            observation,
            observation.teacher,
            "سُحبت ملاحظة صفّية مؤقتاً",
            f"سحب {observation.observer.full_name} الملاحظة الصفّية على أدائك مؤقتاً للمراجعة.",
        )
        return observation

    @staticmethod
    @transaction.atomic
    def reopen(observation, by_user, reason=""):
        """إعادة فتح: مُقَرّة → مُرسَلة (الطريق المُدقَّق لتعديل سجل موقّع). يُلغي الإقرار السابق."""
        if observation.status != "acknowledged":
            return observation
        observation.status = "submitted"
        observation.teacher_acknowledged_at = None
        observation.teacher_comment = ""
        observation.updated_by = by_user
        observation.save(
            update_fields=[
                "status",
                "teacher_acknowledged_at",
                "teacher_comment",
                "updated_by",
                "updated_at",
            ]
        )
        ObservationService._notify_teacher(observation, updated=True)
        return observation

    @staticmethod
    @transaction.atomic
    def acknowledge(observation, comment=""):
        """إقرار المعلّم بالاطّلاع + إشعار الزائر."""
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
        ObservationService._notify_observer(observation)
        return observation

    # ── الحذف الناعم / الاسترجاع ─────────────────────────────────────
    @staticmethod
    @transaction.atomic
    def archive(observation, by_user, reason=""):
        """حذف ناعم — يحفظ الزيارة وتقييماتها للتدقيق (قابل للاسترجاع)."""
        observation.updated_by = by_user
        observation.save(update_fields=["updated_by", "updated_at"])
        observation.delete()  # soft delete
        return None

    @staticmethod
    @transaction.atomic
    def restore(observation, by_user):
        """استرجاع زيارة مؤرشَفة (تُجلب عبر all_objects)."""
        observation.updated_by = by_user
        observation.save(update_fields=["updated_by", "updated_at"])
        observation.restore()
        return None

    # ── الرؤية ──────────────────────────────────────────────────────
    @staticmethod
    def visible_to(user, school):
        """
        القيادة=الكل، الزائر=ما أنشأه، المعلّم=ما تلقّاه + تقييمه الذاتي.
        المشرفون (OBSERVATION_CREATE) يطّلعون أيضاً على التقييمات الذاتية (قراءة فقط).
        (المؤرشَف مُستبعَد تلقائياً عبر الـmanager الافتراضي.)
        """
        return ObservationService._scoped(ClassroomObservation.objects.filter(school=school), user)

    @staticmethod
    def archived_for(user, school):
        """المؤرشَف بنفس نطاق الرؤية — عبر `all_objects` لأن الافتراضي يستبعده.

        كان `archive()` يُنادى من زرّ الحذف و`restore()` مكتوبةً لا تُنادى، ولا
        مسار يعرض المؤرشَف. فالرسالة تَعِد المستخدم بأن الملاحظة «ستُحفظ في
        الأرشيف» — وهو صادقٌ في القاعدة ولا سبيل إليه من الواجهة، فيتصرّف الحذف
        الناعم كنهائيّ في نظر من يستعمله.
        """
        return ObservationService._scoped(
            ClassroomObservation.all_objects.filter(school=school, is_deleted=True), user
        ).order_by("-deleted_at")

    @staticmethod
    def _scoped(qs, user):
        """نطاق الرؤية نفسه للحيّ والمؤرشَف — مصدرٌ واحد فلا يفترقان."""
        from core.permissions import OBSERVATION_CREATE, OBSERVATION_VIEW_ALL

        qs = qs.select_related("teacher", "observer", "subject", "class_group")
        role = user.get_role()
        if user.is_superuser or role in OBSERVATION_VIEW_ALL:
            return qs
        cond = Q(observer=user) | Q(teacher=user)
        if role in OBSERVATION_CREATE:
            cond |= Q(kind="self")
        return qs.filter(cond)

    # ── إرسال نسخة إلى الجهات الأكاديميّة ───────────────────────────
    @staticmethod
    def recipient_options(observation):
        """المستلمون المرشَّحون الأربعة، بترتيبٍ ثابت ومفاتيح مستقرّة.

        يُعيد قائمة `(key, label, user)`؛ و`user` قد يكون `None` حين لا يوجد
        شاغل للدور — قسمٌ بلا رئيس، أو مدرسةٌ بلا نائبٍ أكاديميّ مسجَّل. تُعرض
        هذه الحالة في الواجهة معطَّلةً بدل إخفائها، لأن غياب المنسّق معلومةٌ
        تخصّ من يُرسل، لا تفصيلٌ داخليّ يُطوى عنه.
        """
        return [
            ("teacher", "المعلّم", observation.teacher),
            ("coordinator", "منسّق المادّة", ObservationService._coordinator_of(observation.teacher)),
            (
                "vice_academic",
                "النائب الأكاديميّ",
                ObservationService._role_holder(observation.school, "vice_academic"),
            ),
            (
                "principal",
                "مدير المدرسة",
                ObservationService._role_holder(observation.school, "principal"),
            ),
        ]

    @staticmethod
    def _coordinator_of(teacher):
        """منسّق المعلّم = رئيس قسمه.

        لا يوجد ربطٌ مباشر معلّم↔منسّق في النموذج؛ الرابط هو القسم:
        عضويّة المعلّم النشطة → `department_obj` → `head`.
        """
        membership = teacher.active_membership
        department = membership.department_obj if membership else None
        return department.head if department else None

    @staticmethod
    def _role_holder(school, role_name):
        """أوّل شاغلٍ نشط للدور في هذه المدرسة."""
        from core.models import CustomUser

        return (
            CustomUser.objects.filter(
                is_active=True,
                memberships__school=school,
                memberships__is_active=True,
                memberships__role__name=role_name,
            )
            .distinct()
            .first()
        )

    @staticmethod
    def send_copy(observation, by_user, keys):
        """يُرسل نسخةً من الزيارة إلى من اختاره المُرسِل.

        لا يمسّ الحالة (`draft`/`submitted`/`acknowledged`) ولا يُعدّ إرسالاً
        في سير العمل: هذا توزيعٌ إداريّ للاطّلاع، وخلطُه بـ`submit` يجعل زرّاً
        للمشاركة يُغيّر حالةً رسميّة بلا أن يقصد المستخدم ذلك.

        يُعيد أسماء من وصلهم الإشعار فعلاً — لا من طُلب إرسالهم. والفرق يظهر
        حين يكون المستلم هو المُرسِل نفسه، أو حين لا يوجد شاغلٌ للدور.
        """
        wanted = set(keys or ())
        sent, seen = [], set()

        for key, label, user in ObservationService.recipient_options(observation):
            if key not in wanted or user is None:
                continue
            if user.id == by_user.id or user.id in seen:
                continue
            seen.add(user.id)
            ObservationService._notify_copy(observation, user, label, by_user)
            sent.append(user.full_name)

        return sent

    @staticmethod
    def _notify_copy(observation, recipient, label, by_user):
        kind = "التقييم الذاتي" if observation.kind == "self" else "الزيارة الصفّية"
        title = f"نسخة من {kind}"
        body = (
            f"شارك {by_user.full_name} معك نسخةً من {kind} "
            f"لـ{observation.teacher.full_name} بتاريخ {observation.observation_date}"
        )
        if observation.score_percent is not None:
            body += f" — النسبة الإجماليّة {observation.score_percent}%"
        body += "."
        ObservationService._dispatch(observation, recipient, title, body)

    # ── الإشعارات (لا تُسقط العملية الأساسية أبداً) ──────────────────
    @staticmethod
    def _dispatch(observation, recipient, title, body):
        try:
            from notifications.hub import NotificationHub

            NotificationHub.dispatch(
                event_type="observation",
                school=observation.school,
                recipients=[recipient],
                title=title,
                body=body,
                related_url=f"/quality/observations/{observation.id}/",
                related_object_id=str(observation.id),
            )
        except Exception:  # noqa: BLE001 — الإشعار لا يُسقط العملية
            import logging

            logging.getLogger("quality").exception("observation notify failed")

    @staticmethod
    def _notify_teacher(observation, updated=False):
        pct = observation.score_percent
        if updated:
            title = "تحديث على ملاحظة صفّية"
            body = f"حدّث {observation.observer.full_name} الملاحظة الصفّية على أدائك"
        else:
            title = "ملاحظة صفّية جديدة على أدائك"
            body = f"أجرى {observation.observer.full_name} زيارة إشرافية على أدائك"
        if pct is not None:
            body += f" — النسبة الإجماليّة {pct}%"
        body += ". يُرجى الاطّلاع والإقرار."
        ObservationService._dispatch(observation, observation.teacher, title, body)

    @staticmethod
    def _notify_observer(observation):
        body = f"أقرّ {observation.teacher.full_name} بالاطّلاع على ملاحظتك الصفّية"
        if observation.teacher_comment:
            body += f" — تعليقه: {observation.teacher_comment}"
        body += "."
        ObservationService._dispatch(
            observation,
            observation.observer,
            "أقرّ المعلّم بالاطّلاع على ملاحظتك",
            body,
        )
