"""operations/services/attendance.py — الحضور وتنبيهات الغياب.

منقولٌ حرفيّاً من `operations/services.py` (البند 8)؛ لا تغيير في المنطق.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from core.academic_calendar import (
    academic_year_window,
)
from core.models import StudentEnrollment
from operations.models import (
    AbsenceAlert,
)

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from core.models import CustomUser, School
    from operations.absence_policy import Gate

NEWLINE = chr(10)


def absence_notice_text(gate: Gate, unexcused_days: int) -> tuple[bool, str, str, str]:
    """نصُّ إنذار العتبة: (تجاوزَ؟، العنوان، التفصيل، المرجع) — واحدٌ للأخصائي وللإخطار الذي يُصدره حاصرُ الغياب."""
    crossed = unexcused_days > gate.max_days
    if crossed:
        headline = f"تجاوز حدّ الغياب لدخول {gate.label}"
        detail = (
            f"بلغ غياب ابنكم بدون عذر {unexcused_days} يوماً، "
            f"والحدّ لدخول {gate.label} هو {gate.max_days} يوماً."
        )
    else:
        remaining = gate.max_days - unexcused_days
        headline = f"اقتراب من حدّ الغياب لدخول {gate.label}"
        detail = (
            f"بلغ غياب ابنكم بدون عذر {unexcused_days} يوماً، "
            f"ويفصله {remaining} يوماً عن حدّ {gate.max_days} "
            f"المقرّر لدخول {gate.label}."
        )
    # المرجعُ يُسمّى في الرسالة لأنّها تصل بيتاً: وليُّ أمرٍ يقرأ رقماً عن ابنه من حقّه أن يعرف من أين جاء.
    source = (
        "المرجع: الدليل التنظيمي لسياسة إدارة سلوك الطلبة 2026 (م 3.4.1.3) — "
        "وزارة التربية والتعليم والتعليم العالي، قسم حماية ورعاية الطلبة."
    )
    return crossed, headline, detail, source


class AttendanceService:
    # ── إعداد السنة الدراسية (المادة 7 من قانون 25/2001 المعدّل) ─
    # عتبةٌ تشغيلية من وضعنا، لا سندَ لها في نصٍّ رسميّ — راجع
    # `check_absence_threshold` و`absence_policy`. والوحدة هنا حصصٌ لا أيام.
    SCHOOL_YEAR_DAYS = 190
    ABSENCE_THRESHOLD_PCT = 0.10

    #: يُنذَر حين يبقى هذا العدد أو أقلّ قبل العتبة — إنذارٌ يسبق الوقوع.
    GATE_WARNING_MARGIN_DAYS = 2

    @staticmethod
    def check_absence_threshold(student: CustomUser, school: School, on=None) -> None:
        """اسمُها القديم لمنادين قدماء (الرصدُ القديم وكشفُ الأجنحة): تُنشئ تنبيهاتٍ «محجوزة» ولا ترسل لوليّ الأمر (D-246م) — انظر `raise_absence_alerts`."""
        AttendanceService.raise_absence_alerts(student, school, on=on)

    @staticmethod
    def raise_absence_alerts(student: CustomUser, school: School, on=None) -> list:
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

        **لا يُرسَل شيءٌ لوليّ الأمر من هنا (قرار المالك D-246م):** يُنشأ التنبيهُ بحالة «محجوز» `held` ويُشعَر الأخصائيُّ الاجتماعيّ داخلياً فقط؛
        والإخطارُ يُصدره حاصرُ الغياب بزرّ «إصدار الإخطار» بعد ح4 (`wings.absence_notice_services`). يعيد التنبيهاتِ المُنشأةَ الآن.
        """
        from operations.absence_policy import gates_for
        from operations.absence_standing import standing_for
        from operations.attendance_policy import is_special_education

        enrollment = StudentEnrollment.objects.current_of(student)
        grade = enrollment.class_group.grade if enrollment else None
        # طلبةُ التربية الخاصّة (شعبةُ …/ESE بلا جناح، مشتقٌّ من الشعبة لا علمٌ على الطالب — D-255م): عتبتا النهاية 8 و15 فقط، بلا منتصف الفصل (5 و11).
        # لا يغيّر هذا حسابَ أيّام الغياب نفسِها.
        ese = bool(enrollment and is_special_education(enrollment.class_group))
        if not gates_for(grade, ese):
            # صفٌّ لا جدولَ له في السياسة — فلا إنذار بجدولٍ لا يخصّه.
            # (ودليلُ 2026 يشمل «من الصف الأول»، فلم يبقَ خارجَه صفٌّ في مدرسةٍ
            # إعداديّةٍ ثانويّة.) وطالبٌ بلا تسجيلٍ نشط يقع هنا أيضاً، فيفقد
            # إنذاراته كلّها — وذاك نقصٌ في البيانات لا حكمٌ من السياسة، فيُسجَّل
            # كي يُرى.
            if enrollment is None:
                logger.warning(
                    "raise_absence_alerts: لا تسجيل نشط للطالب %s — لا إنذار غياب",
                    student.pk,
                )
            return []

        standing = standing_for(student, school, grade=grade, on=on, ese=ese)
        window = academic_year_window(school, on)
        if window is None:
            return []
        year_start, year_end = window

        margin = AttendanceService.GATE_WARNING_MARGIN_DAYS
        due = [
            gate
            for gate in standing.gates
            if standing.unexcused_days > gate.max_days
            or gate.max_days - standing.unexcused_days <= margin
        ]

        created_alerts: list = []
        for gate in due:
            _alert, created = AbsenceAlert.objects.get_or_create(
                school=school,
                student=student,
                gate=gate.key,
                period_start=year_start,
                period_end=year_end,
                defaults={"absence_count": standing.unexcused_days, "status": "held"},
            )
            if not created:
                continue
            created_alerts.append(_alert)

            crossed, headline, detail, source = absence_notice_text(gate, standing.unexcused_days)

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
                    "raise_absence_alerts: social worker notify failed [student=%s]: %s",
                    student.pk,
                    exc,
                )
        return created_alerts
