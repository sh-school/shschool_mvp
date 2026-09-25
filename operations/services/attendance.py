"""operations/services/attendance.py — الحضور وتنبيهات الغياب.

منقولٌ حرفيّاً من `operations/services.py` (البند 8)؛ لا تغيير في المنطق.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from django.db import transaction
from django.urls import reverse

from core.academic_calendar import (
    academic_year_window,
)
from core.domain.attendance import attendance_rate
from core.models import StudentEnrollment
from operations.models import (
    AbsenceAlert,
    Session,
    StudentAttendance,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School

NEWLINE = chr(10)


class AttendanceService:
    @staticmethod
    @transaction.atomic
    def mark_attendance(
        session: Session,
        student: CustomUser,
        status: str,
        excuse_type: str = "",
        excuse_notes: str = "",
        marked_by: CustomUser | None = None,
    ) -> tuple:
        att, created = StudentAttendance.objects.update_or_create(
            session=session,
            student=student,
            defaults={
                "school": session.school,
                "status": status,
                "excuse_type": excuse_type,
                "excuse_notes": excuse_notes,
                "marked_by": marked_by,
            },
        )
        # Check absence threshold
        if status == "absent":
            AttendanceService.check_absence_threshold(student, session.school)
        return att, created

    @staticmethod
    @transaction.atomic
    def bulk_mark_all_present(session: Session, marked_by: CustomUser | None = None) -> int:
        students = StudentEnrollment.objects.filter(
            class_group=session.class_group, is_active=True
        ).select_related("student")

        records = []
        for enrollment in students:
            records.append(
                StudentAttendance(
                    session=session,
                    student=enrollment.student,
                    school=session.school,
                    status="present",
                    marked_by=marked_by,
                )
            )
        if not records:
            # شعبةٌ بلا طالبٍ نشطٍ — غالباً جلسةٌ يتيمة من عامٍ منقضٍ لم تُنظَّف
            # بعد. رفعُ الحالة إلى "in_progress" هنا كان يُبقي أثراً بلا حضورٍ
            # يحميه `ScheduleService._untouched` من التنظيف الآليّ إلى الأبد.
            return 0
        StudentAttendance.objects.bulk_create(records, ignore_conflicts=True)
        session.status = "in_progress"
        session.save(update_fields=["status"])
        return len(records)

    @staticmethod
    @transaction.atomic
    def complete_session(session: Session) -> None:
        session.status = "completed"
        session.save(update_fields=["status"])

    # ── إعداد السنة الدراسية (المادة 7 من قانون 25/2001 المعدّل) ─
    # عتبةٌ تشغيلية من وضعنا، لا سندَ لها في نصٍّ رسميّ — راجع
    # `check_absence_threshold` و`absence_policy`. والوحدة هنا حصصٌ لا أيام.
    SCHOOL_YEAR_DAYS = 190
    ABSENCE_THRESHOLD_PCT = 0.10

    #: يُنذَر حين يبقى هذا العدد أو أقلّ قبل العتبة — إنذارٌ يسبق الوقوع.
    GATE_WARNING_MARGIN_DAYS = 2

    @staticmethod
    def check_absence_threshold(student: CustomUser, school: School, on=None) -> None:
        """يُنذر عند اقتراب كلّ عتبةٍ من عتبات الدليل التنظيميّ 2026.

        كانت هذه الدالّة تُنذر عند «10٪ من أيام الدراسة» وتنسبها إلى المادة 7
        من قانون التعليم الإلزامي 25/2001. ونصّ القانون لا يذكر نسبةً ولا عدد
        أيام. وكانت الرسالة تقول لوليّ الأمر «تجاوز ابنكم **العتبة القانونية**»
        — ادّعاءٌ يصل إلى بيتٍ حقيقيّ.

        ثمّ صُحّحت إلى «سياسة تقييم الطلبة 2018» (7·10·13·15)، وقد نسختها
        **«سياسة إدارة سلوك الطلبة 2026»** م 3.4.1.3: خمسةٌ ثمّ ثمانيةٌ ثمّ
        إحدى عشرةَ ثمّ خمسةَ عشر للصفوف 1–11، وثمانيةٌ ثمّ خمسةَ عشر للثاني
        عشر وذوي الإعاقة. والأرقامُ في `absence_policy` لا هنا.

        وثلاثة فروقٍ عمليّة عن الأقدم:

        - تُعدّ **أيام تمدرس** لا حصصاً — والفرق سبعة أضعاف بسبع حصصٍ في اليوم.
        - تنبيهٌ **لكل عتبة**. وكان التنبيه واحداً للعام كلّه، فمن تجاوز الأولى
          لم يُنذَر عند التي بعدها قطّ.
        - **إنذارٌ قبل الوقوع** بيومين، لا إعلامٌ بعده.

        ولا تحجب هذه الدالّة شيئاً. قرار الحرمان **لفريق إدارة سلوك الطلبة**
        بنصّ الدليل.

        `on` للاختبار وللمعالجة بأثرٍ رجعيّ — لا يُمرَّر في الاستعمال العاديّ.
        """
        from core.models import StudentEnrollment
        from operations.absence_policy import gates_for
        from operations.absence_standing import standing_for

        enrollment = StudentEnrollment.objects.current_of(student)
        grade = enrollment.class_group.grade if enrollment else None
        if not gates_for(grade):
            # صفٌّ لا جدولَ له في السياسة — فلا إنذار بجدولٍ لا يخصّه.
            # (ودليلُ 2026 يشمل «من الصف الأول»، فلم يبقَ خارجَه صفٌّ في مدرسةٍ
            # إعداديّةٍ ثانويّة.) وطالبٌ بلا تسجيلٍ نشط يقع هنا أيضاً، فيفقد
            # إنذاراته كلّها — وذاك نقصٌ في البيانات لا حكمٌ من السياسة، فيُسجَّل
            # كي يُرى.
            if enrollment is None:
                logger.warning(
                    "check_absence_threshold: لا تسجيل نشط للطالب %s — لا إنذار غياب",
                    student.pk,
                )
            return

        standing = standing_for(student, school, grade=grade, on=on)
        window = academic_year_window(school, on)
        if window is None:
            return
        year_start, year_end = window

        margin = AttendanceService.GATE_WARNING_MARGIN_DAYS
        due = [
            gate
            for gate in standing.gates
            if standing.unexcused_days > gate.max_days
            or gate.max_days - standing.unexcused_days <= margin
        ]

        for gate in due:
            _alert, created = AbsenceAlert.objects.get_or_create(
                school=school,
                student=student,
                gate=gate.key,
                period_start=year_start,
                period_end=year_end,
                defaults={"absence_count": standing.unexcused_days, "status": "pending"},
            )
            if not created:
                continue

            crossed = standing.unexcused_days > gate.max_days
            if crossed:
                headline = f"تجاوز حدّ الغياب لدخول {gate.label}"
                detail = (
                    f"بلغ غياب ابنكم بدون عذر {standing.unexcused_days} يوماً، "
                    f"والحدّ لدخول {gate.label} هو {gate.max_days} يوماً."
                )
            else:
                remaining = gate.max_days - standing.unexcused_days
                headline = f"اقتراب من حدّ الغياب لدخول {gate.label}"
                detail = (
                    f"بلغ غياب ابنكم بدون عذر {standing.unexcused_days} يوماً، "
                    f"ويفصله {remaining} يوماً عن حدّ {gate.max_days} "
                    f"المقرّر لدخول {gate.label}."
                )
            # المرجعُ يُسمّى في الرسالة لأنّها تصل بيتاً: وليُّ أمرٍ يقرأ رقماً
            # عن ابنه من حقّه أن يعرف من أين جاء.
            source = (
                "المرجع: الدليل التنظيمي لسياسة إدارة سلوك الطلبة 2026 (م 3.4.1.3) — "
                "وزارة التربية والتعليم والتعليم العالي، قسم حماية ورعاية الطلبة."
            )

            try:
                from notifications.hub import NotificationHub

                NotificationHub.dispatch_to_parents(
                    event_type="absence",
                    school=school,
                    student=student,
                    title=f"⚠️ {headline} — {student.full_name}",
                    body=NEWLINE.join([detail, source, "يُرجى التواصل مع المدرسة."]),
                    context={"student": student, "absence_count": standing.unexcused_days},
                    related_url=reverse("student_affairs:student_profile", args=[student.pk]),
                )
            except Exception as exc:
                logger.warning(
                    "check_absence_threshold: Hub dispatch failed [student=%s gate=%s]: %s",
                    student.pk,
                    gate.key,
                    exc,
                )

            try:
                from core.models import Membership
                from notifications.models import InAppNotification

                sw_user_ids = list(
                    Membership.objects.filter(
                        school=school, is_active=True, role__name="social_worker"
                    ).values_list("user_id", flat=True)
                )
                for sw_id in sw_user_ids:
                    InAppNotification.objects.create(
                        user_id=sw_id,
                        school=school,
                        title=f"{headline}: {student.full_name}",
                        body=f"{detail} {source}",
                        event_type="absence",
                        priority="high" if crossed else "normal",
                        related_url=f"/student-affairs/student/{student.pk}/",
                    )
            except Exception as exc:
                logger.warning(
                    "check_absence_threshold: social worker notify failed [student=%s]: %s",
                    student.pk,
                    exc,
                )

    @staticmethod
    def get_session_summary(session: Session) -> dict:
        att = StudentAttendance.objects.filter(session=session)
        total = att.count()
        present = att.filter(status="present").count()
        absent = att.filter(status="absent").count()
        late = att.filter(status="late").count()
        excused = att.filter(status="excused").count()
        pct = attendance_rate(present, total)
        return {
            "total": total,
            "present": present,
            "absent": absent,
            "late": late,
            "excused": excused,
            "percentage": pct,
            # نصُّ البطاقة جاهزاً — لا سلسلةَ مرشِّحاتٍ في القالب تلصق «%».
            "percentage_label": f"{pct}%",
        }
