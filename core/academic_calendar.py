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
from typing import TYPE_CHECKING

from django.utils import timezone

if TYPE_CHECKING:  # النماذج تستورد هذه الوحدة لقيمها الافتراضية — فلا نستوردها هنا وقت التشغيل
    from core.models import AcademicYear, Semester


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
        from core.models import AcademicYear

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
        from core.models import CalendarEvent

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
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return _frozen()

    return academic_year_for_school(user.get_school())


def academic_year_for_school(school, on=None) -> str:
    """العام الجاري لمدرسةٍ بعينها — لخدماتٍ تستقبل المدرسة ولا تستقبل طلباً.

    عشرات الخدمات تُوقّع `f(school, year=...)`، وكانت القيمة الافتراضية تُقرأ
    من الثابت **عند استيراد الوحدة** لا عند النداء. فحتى لو صحّ الثابت في
    الإعدادات لم يكن ليصل إليها قبل إعادة تشغيل العملية.
    """
    if school is None:
        return default_academic_year()

    return AcademicCalendar.year_name(school, on) or _frozen()


def academic_year_window(school, on=None):
    """تاريخا بداية العام ونهايته — لا اسمه.

    عتبة الغياب القانونية (المادة ٧ من قانون التعليم الإلزامي ٢٥/٢٠٠١) تُحسب
    على نافذة العام. وكانت النافذة مكتوبةً بالتواريخ: ٢٠٢٥/٩/١ إلى ٢٠٢٦/٦/٣٠.
    فلمّا بدأ عام ٢٠٢٦-٢٠٢٧ صارت النافذة خاليةً من كل حصّة — فلا حصص تُعدّ،
    ولا غيابَ يُحسب، ولا تنبيهَ ينطلق لأيّ طالب. عطبٌ صامت في التزامٍ قانونيّ.

    ويرتدّ إلى سبتمبر–يونيو المشتقّين من اسم العام حين لا يكون التقويم مبذوراً.
    """
    from datetime import date

    now = AcademicCalendar.current(school, on)
    if now.year is not None:
        return now.year.start_date, now.year.end_date

    name = academic_year_for_school(school, on)
    try:
        start, end = (int(part) for part in str(name).split("-"))
    except ValueError:
        return None
    return date(start, 9, 1), date(end, 6, 30)


def default_academic_year() -> str:
    """العام الجاري بلا مدرسةٍ معلومة — لأوامر الإدارة وقيم النماذج الافتراضية.

    وليس هذا تنازلاً عن الفصل بين المستأجرين: أمان الصفوف يُقيّد الاستعلام
    بمدرسة الجلسة تلقائياً، فيُعيد عامَها هي. وخارج الطلب — في أمرٍ إداريّ أو
    هجرة — لا جلسةَ ولا صفوف، فيرتدّ إلى الثابت.

    وتقويم الوزارة وطنيّ: التواريخ واحدة لكل المدارس. فإن اختلف عامان على
    اليوم نفسه فذلك خللٌ في البذر، والارتداد أصدق من اختيارٍ عشوائيّ.

    ولا يُخزَّن الجواب. جرّبتُ ذاكرةً مفتاحها اليومُ وحده فكانت تنقض ما
    تحرسه من وجهين: تُقدّم جوابَ مستأجرٍ لمن بعده في العملية نفسها، وإن وقع
    أوّل نداءٍ خارج طلبٍ — أمرٍ إداريّ أو فحص صحّة — خزّنت الارتدادَ إلى
    الثابت المُجمَّد وقدّمته يوماً كاملاً لكل من جاء بعده. أي أنها تُعيد
    الثابت من البابِ الذي أُغلق. واستعلامٌ واحدٌ مفهرس أرخص من هذا الخطر.
    """
    from django.db import Error

    from core.models import AcademicYear

    day = timezone.localdate()
    try:
        names = set(
            AcademicYear.objects.filter(start_date__lte=day, end_date__gte=day)
            .values_list("name", flat=True)
            .distinct()[:2]
        )
    except Error:
        # الجداول غير موجودة بعد — أثناء هجرةٍ أو قاعدةٍ جديدة.
        return _frozen()

    return names.pop() if len(names) == 1 else _frozen()


def _frozen() -> str:
    """الثابت المُجمَّد — الملاذ الأخير، ولا يُقرأ من موضعٍ آخر."""
    from django.conf import settings

    return settings.CURRENT_ACADEMIC_YEAR


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
