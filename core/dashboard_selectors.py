"""قراءاتُ لوحة التحكم الرئيسية — ما تعدّه كلُّ لوحةِ دورٍ من التطبيقات الأخرى.

كانت هذه الاستعلاماتُ في `core/views_dashboard.py` نفسِه: `_get_director_ctx` مئةٌ
وثلاثةَ عشرَ سطراً بستّةٍ وأربعين استدعاءَ ORM، ولا يراه حارسُ الطبقات لأنّ أوّلَ
وسائطه ليس `request`. فالعرضُ الآن يركّب السياقَ ويُسمّي مفاتيحه، والعدُّ هنا.

وقراءاتُ الحصص والحضور والتنبيهات والتبديل في `operations/selectors.py` — تشترك فيها
هذه اللوحةُ وشؤونُ الطلبة. واللوحةُ في النواة تقرأ من تطبيقاتٍ نازلة بطبيعتها؛
وسقّاطةُ الطبقات تعدّ ذلك على النواة كلِّها، فنقلُه من العرض إلى هنا لا يزيده.
"""

from __future__ import annotations

from datetime import date

from django.db.models import Count, Q, QuerySet

from assessments.models import AnnualSubjectResult, SubjectClassSetup
from behavior.models import BehaviorInfraction
from clinic.models import ClinicVisit
from core.models.academic import grade_order
from core.models.school import School
from core.models.user import CustomUser
from library.models import BookBorrowing


def annual_result_counts(school: School, year: str, **filters: object) -> dict[str, int]:
    """النتائجُ السنويّة: الكلّ، والناجح، والراسب — للمدرسة أو لطالبٍ (`student=`)."""
    counts: dict[str, int] = AnnualSubjectResult.objects.filter(
        school=school, academic_year=year, **filters
    ).aggregate(
        total=Count("id"),
        passed=Count("id", filter=Q(status="pass")),
        failed=Count("id", filter=Q(status="fail")),
    )
    return counts


def failing_student_count(school: School, year: str) -> int:
    """الطلبةُ الذين رسبوا في مادّةٍ واحدةٍ على الأقلّ — كلُّ طالبٍ مرّة."""
    count: int = (
        AnnualSubjectResult.objects.filter(school=school, academic_year=year, status="fail")
        .values("student")
        .distinct()
        .count()
    )
    return count


def incomplete_setup_count(school: School, year: str) -> int:
    """إعداداتُ موادّ نشطةٌ بلا باقات تقييم."""
    count: int = (
        SubjectClassSetup.objects.filter(school=school, academic_year=year, is_active=True)
        .exclude(packages__isnull=False)
        .count()
    )
    return count


def teacher_setups(school: School, teacher: CustomUser, year: str) -> QuerySet[SubjectClassSetup]:
    """موادُّ المعلّم وشُعبُه هذا العام — بترتيب الصفّ ثمّ المادّة."""
    setups: QuerySet[SubjectClassSetup] = (
        SubjectClassSetup.objects.filter(
            school=school, teacher=teacher, academic_year=year, is_active=True
        )
        .select_related("subject", "class_group")
        .order_by(grade_order("class_group__grade"), "subject__name_ar")
    )
    return setups


def behaviour_month_and_critical(school: School, today: date) -> dict[str, int]:
    """مخالفاتُ الشهر الميلاديّ الجاري، والجسيمةُ (الدرجة 3 فأعلى) على الإطلاق — استعلامٌ واحد."""
    counts: dict[str, int] = BehaviorInfraction.objects.filter(school=school).aggregate(
        behavior_monthly=Count("id", filter=Q(date__month=today.month, date__year=today.year)),
        behavior_critical=Count("id", filter=Q(level__gte=3)),
    )
    return counts


def infractions_since_count(school: School, since: date) -> int:
    count: int = BehaviorInfraction.objects.filter(school=school, date__gte=since).count()
    return count


def critical_infraction_count(school: School) -> int:
    count: int = BehaviorInfraction.objects.filter(school=school, level__gte=3).count()
    return count


def clinic_counts_on(school: School, day: date) -> dict[str, int]:
    """زياراتُ العيادة يومَ `day`، ومن أُعيد منها إلى البيت."""
    counts: dict[str, int] = ClinicVisit.objects.filter(
        school=school, visit_date__date=day
    ).aggregate(
        clinic_today=Count("id"),
        clinic_sent_home=Count("id", filter=Q(is_sent_home=True)),
    )
    return counts


def loan_count(school: School, **filters: object) -> int:
    """إعاراتُ مكتبة المدرسة المرشَّحة (`status="OVERDUE"`، `borrow_date=`…)."""
    count: int = BookBorrowing.objects.filter(book__school=school, **filters).count()
    return count


def school_user_count(school: School, *, active_only: bool) -> int:
    """حساباتُ المدرسة — كلُّ حسابٍ مرّةً وإن تعدّدت عضويّاتُه."""
    users = CustomUser.objects.filter(memberships__school=school)
    if active_only:
        users = users.filter(is_active=True)
    count: int = users.distinct().count()
    return count
