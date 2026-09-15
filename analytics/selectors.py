"""قراءاتُ لوحة الإحصاءات المتقدّمة — مؤشّراتُ المدرسة الستّةَ عشرَ في دالّةٍ واحدة.

كانت في `analytics_dashboard` نفسِه: تسعةٌ وثمانون سطراً بواحدٍ وثلاثين استدعاءَ ORM
بين `request` و`render`. فالعرضُ الآن يقرأ الطلبَ ويعرض، والعدُّ هنا يُختبر بلا
طلب (`tests/test_analytics_selectors.py`). ونسبةُ الحضور من `core.domain.attendance`.
"""

from __future__ import annotations

from datetime import date

from django.db.models import Count, Q

from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit, HealthRecord
from core.domain.attendance import attendance_rate
from core.models.academic import StudentEnrollment
from core.models.access import Membership
from core.models.school import School
from library.models import BookBorrowing, LibraryBook
from operations.models import Session, StudentAttendance
from quality.models import OperationalProcedure
from transport.models import SchoolBus


def school_overview_kpis(school: School, year: str, today: date) -> dict[str, int]:
    """المؤشّراتُ بمفاتيح القالب (`kpis.*`): الطلبة، والكادر، والحضور، والعيادة، والسلوك،
    والنقل، والمكتبة، والخطّةُ التشغيليّة."""
    # الحضورُ على حصص المدرسة اليوم — عدّادان في استعلامٍ واحد.
    attendance = StudentAttendance.objects.filter(
        session__in=Session.objects.filter(school=school, date=today)
    ).aggregate(total=Count("id"), present=Count("id", filter=Q(status="present")))
    loans = BookBorrowing.objects.filter(book__school=school).aggregate(
        active=Count("id", filter=Q(status="BORROWED")),
        overdue=Count("id", filter=Q(status="OVERDUE")),
    )
    procedures = OperationalProcedure.objects.filter(school=school, academic_year=year).aggregate(
        total=Count("id"), completed=Count("id", filter=Q(status="Completed"))
    )
    infractions = BehaviorInfraction.objects.filter(school=school).aggregate(
        month=Count("id", filter=Q(date__month=today.month, date__year=today.year)),
        critical=Count("id", filter=Q(level__in=[3, 4], is_resolved=False)),
    )

    return {
        "total_students": StudentEnrollment.objects.filter(
            class_group__school=school, class_group__academic_year=year, is_active=True
        ).count(),
        "total_teachers": Membership.objects.filter(
            school=school, is_active=True, role__name__in=["teacher", "coordinator"]
        ).count(),
        "att_pct_today": attendance_rate(attendance["present"], attendance["total"]),
        "present_today": attendance["present"],
        "clinic_today": ClinicVisit.objects.filter(school=school, visit_date__date=today).count(),
        "chronic_cases": HealthRecord.objects.filter(student__memberships__school=school)
        .exclude(chronic_diseases="")
        .distinct()
        .count(),
        "behavior_month": infractions["month"],
        "critical_issues": infractions["critical"],
        "total_buses": SchoolBus.objects.filter(school=school).count(),
        "bus_students": StudentEnrollment.objects.filter(
            student__bus_routes__bus__school=school, is_active=True
        )
        .distinct()
        .count(),
        "library_books": LibraryBook.objects.filter(school=school).count(),
        "active_loans": loans["active"],
        "overdue_books": loans["overdue"],
        # بصيغة العرض قبل الترحيل — `percent` تُقرّب الأنصافَ غيرَها (109 من 200: 55 لا 54).
        "plan_pct": (
            round(procedures["completed"] / procedures["total"] * 100) if procedures["total"] else 0
        ),
        "completed_procs": procedures["completed"],
        "total_procs": procedures["total"],
    }
