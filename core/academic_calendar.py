"""
core/academic_calendar.py — مصدر الحقيقة الوحيد للزمن الأكاديمي.

كان العام الدراسي ثابتاً في الإعدادات (`CURRENT_ACADEMIC_YEAR`) يُستعمل في
عشرات المواضع. وثابتٌ كهذا يتجاوزه الزمن بصمت: في ٢٧ أغسطس ٢٠٢٦ كانت المنصّة
ما تزال تقول «2025-2026» بينما المدارس في «2026-2027» — ولا شيء يكشف ذلك،
لأن الرقم صحيحٌ نحوياً في كل موضع.

والتقويم عندنا **تاريخيّ**: الوزارة تُصدر تواريخ الفصول لثلاثة أعوامٍ مقدَّماً.
فالعام والفصل يُشتقّان من التاريخ، ولا يُعلنان برايةٍ يُنسى تبديلها.
"""

from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone

from core.models import AcademicYear, CalendarEvent, Semester


@dataclass(frozen=True)
class AcademicNow:
    """الزمن الأكاديمي لمدرسةٍ في يومٍ بعينه."""

    year: AcademicYear | None
    semester: Semester | None

    @property
    def year_name(self) -> str:
        return self.year.name if self.year else ""

    @property
    def semester_code(self) -> str:
        return self.semester.code if self.semester else ""


class AcademicCalendar:
    """يُجيب عن «أيّ عامٍ وأيّ فصلٍ لهذه المدرسة الآن» — ومنه وحده يقرأ الجميع."""

    @staticmethod
    def current(school, on=None) -> AcademicNow:
        """يُشتقّ العام والفصل من التاريخ.

        `on` للاختبار وللتقارير بأثرٍ رجعيّ — لا يُمرَّر في الاستعمال العاديّ.
        """
        day = on or timezone.localdate()

        year = (
            AcademicYear.objects.filter(school=school, start_date__lte=day, end_date__gte=day)
            .order_by("-start_date")
            .first()
        )
        if year is None:
            # لا عامَ يغطّي اليوم — تُستعمل الرايةُ احتياطاً لا أصلاً.
            year = AcademicYear.objects.filter(school=school, is_current=True).first()

        semester = None
        if year is not None:
            semester = year.semesters.filter(start_date__lte=day, end_date__gte=day).first()

        return AcademicNow(year=year, semester=semester)

    @staticmethod
    def year_name(school, on=None) -> str:
        """اسم العام الجاري — البديل المباشر لـ`settings.CURRENT_ACADEMIC_YEAR`."""
        return AcademicCalendar.current(school, on).year_name

    @staticmethod
    def events(school, *, grade=None, audience=None, on=None, upcoming=False):
        """أحداث تقويم العام الجاري، مُرشَّحة بنطاق الصفّ والجمهور.

        نوافذ الاختبارات تختلف بين الصفوف ١–٩ و١٠–١١ و١٢، فحدثٌ بلا نطاقٍ
        يُعرض لمن لا يعنيه.
        """
        day = on or timezone.localdate()
        now = AcademicCalendar.current(school, day)
        if now.year is None:
            return CalendarEvent.objects.none()

        qs = now.year.calendar_events.all()
        if grade:
            qs = qs.filter(grade_scope__in=("all", _scope_for(grade)))
        if audience:
            qs = qs.filter(audience__in=("both", audience))
        if upcoming:
            qs = qs.filter(end_date__gte=day)
        return qs


def academic_year_for(request) -> str:
    """العام الجاري لمدرسة الطلب — البديل المباشر لـ`settings.CURRENT_ACADEMIC_YEAR`.

    يرتدّ إلى الثابت حين لا تقويمَ مبذوراً بعد أو لا مدرسةَ للمستخدم، كي لا
    تنكسر شاشةٌ قبل أن تمتلئ الجداول. والارتداد مؤقّت: متى بُذر التقويم صار
    الاشتقاق هو المسار الوحيد.
    """
    from django.conf import settings

    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return settings.CURRENT_ACADEMIC_YEAR

    school = user.get_school()
    if school is None:
        return settings.CURRENT_ACADEMIC_YEAR

    return AcademicCalendar.year_name(school) or settings.CURRENT_ACADEMIC_YEAR


#: الصفوف كما تُصنّفها نوافذ اختبارات الوزارة.
_GRADE_BANDS = (
    (range(1, 10), "g1_9"),
    (range(10, 12), "g10_11"),
    (range(12, 13), "g12"),
)


def _scope_for(grade) -> str:
    """يُحوّل رقم الصفّ (أو «G10») إلى نطاق الوزارة."""
    digits = "".join(ch for ch in str(grade) if ch.isdigit())
    if not digits:
        return "all"
    number = int(digits)
    for band, scope in _GRADE_BANDS:
        if number in band:
            return scope
    return "all"
