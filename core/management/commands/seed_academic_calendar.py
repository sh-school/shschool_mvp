"""
يبذر تقويم الوزارة للأعوام ٢٠٢٥/٢٠٢٦ و٢٠٢٦/٢٠٢٧ و٢٠٢٧/٢٠٢٨.

التواريخ من نشرة «تعدّل التقويم السنوي للأعوام الأكاديمية» الصادرة عن وزارة
التربية والتعليم والتعليم العالي — دولة قطر.

كل عامٍ كيانٌ مستقلّ: فصولُه وأحداثُه مرتبطة به وحده، فيُؤرشَف ويُنسَخ احتياطياً
منفرداً بلا أن يجرّ ما قبله.

    python manage.py seed_academic_calendar [--school <code>]
"""

from datetime import date, timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from core.models import AcademicYear, CalendarEvent, School, Semester

# ── حدود الأعوام ─────────────────────────────────────────────────────
# العام يبدأ بدوام الموظفين وينتهي عشيّة بدء العام التالي: فلا يومَ خارج عام،
# ولا تداخلَ بين عامين. وإجازة الموظفين الصيفية حدثٌ **داخل** العام لا نهايته.
YEARS = {
    "2025-2026": (date(2025, 8, 24), date(2026, 8, 22)),
    "2026-2027": (date(2026, 8, 23), date(2027, 8, 21)),
    "2027-2028": (date(2027, 8, 22), date(2028, 8, 19)),
}

# بدء دوام الطلبة للفصل الثاني — وهو الفاصل بين الفصلين.
# الفصل الأول يبدأ ببداية العام لا ببدء دوام الطلبة، كي لا يبقى أسبوع التحضير
# بلا فصل. وينتهي عشيّة هذا التاريخ، فإجازة منتصف العام تُلحق بالفصل المنتهي
# ولا يأتي يومٌ بلا فصل.
S2_START = {
    "2025-2026": date(2026, 1, 5),
    "2026-2027": date(2027, 1, 4),
    "2027-2028": date(2028, 1, 3),
}

MAX_GRADE = {"S1": 40, "S2": 60}

# ── الأحداث: (النوع، البيان، من، إلى، نطاق الصفوف، الجمهور) ──────────
EVENTS = {
    "2025-2026": [
        ("staff_start", "بدء دوام الموظفين", date(2025, 8, 24), date(2025, 8, 24), "all", "staff"),
        (
            "second_round",
            "اختبارات الدور الثاني للعام ٢٠٢٤/٢٠٢٥",
            date(2025, 8, 24),
            date(2025, 8, 28),
            "all",
            "students",
        ),
        (
            "students_start",
            "بدء دوام الطلبة",
            date(2025, 8, 31),
            date(2025, 8, 31),
            "all",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الأول",
            date(2025, 10, 14),
            date(2025, 10, 23),
            "g10_11",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الأول",
            date(2025, 10, 15),
            date(2025, 10, 23),
            "g1_9",
            "students",
        ),
        ("break", "إجازة منتصف الفصل الأول", date(2025, 10, 26), date(2025, 10, 30), "all", "both"),
        (
            "resume",
            "بدء الدوام بعد إجازة منتصف الفصل الأول",
            date(2025, 11, 2),
            date(2025, 11, 2),
            "all",
            "both",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الأول",
            date(2025, 12, 7),
            date(2025, 12, 16),
            "g12",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الأول",
            date(2025, 12, 7),
            date(2025, 12, 16),
            "g10_11",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الأول",
            date(2025, 12, 8),
            date(2025, 12, 16),
            "g1_9",
            "students",
        ),
        (
            "break",
            "إجازة منتصف العام الأكاديمي",
            date(2025, 12, 21),
            date(2026, 1, 3),
            "all",
            "both",
        ),
        (
            "staff_start",
            "بدء دوام الموظفين للفصل الثاني",
            date(2026, 1, 4),
            date(2026, 1, 4),
            "all",
            "staff",
        ),
        (
            "students_start",
            "بدء دوام الطلبة للفصل الثاني",
            date(2026, 1, 5),
            date(2026, 1, 5),
            "all",
            "students",
        ),
        (
            "makeup_exam",
            "ملحق اختبارات نهاية الفصل الأول",
            date(2026, 1, 18),
            date(2026, 1, 27),
            "all",
            "students",
        ),
        ("break", "إجازة رمضان", date(2026, 3, 15), date(2026, 3, 16), "all", "both"),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الثاني",
            date(2026, 3, 29),
            date(2026, 4, 7),
            "g10_11",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الثاني",
            date(2026, 3, 30),
            date(2026, 4, 7),
            "g1_9",
            "students",
        ),
        ("break", "إجازة نهاية أسبوع مطوّلة", date(2026, 4, 8), date(2026, 4, 9), "all", "both"),
        (
            "resume",
            "بدء الدوام بعد الإجازة المطوّلة",
            date(2026, 4, 12),
            date(2026, 4, 12),
            "all",
            "both",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الثاني",
            date(2026, 6, 4),
            date(2026, 6, 21),
            "g12",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الثاني",
            date(2026, 6, 4),
            date(2026, 6, 16),
            "g10_11",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الثاني",
            date(2026, 6, 4),
            date(2026, 6, 15),
            "g1_9",
            "students",
        ),
        ("break", "إجازة الموظفين", date(2026, 6, 28), date(2026, 8, 20), "all", "staff"),
    ],
    "2026-2027": [
        ("staff_start", "بدء دوام الموظفين", date(2026, 8, 23), date(2026, 8, 23), "all", "staff"),
        (
            "second_round",
            "اختبارات الدور الثاني للعام ٢٠٢٥/٢٠٢٦",
            date(2026, 8, 23),
            date(2026, 8, 27),
            "all",
            "students",
        ),
        (
            "students_start",
            "بدء دوام الطلبة",
            date(2026, 8, 30),
            date(2026, 8, 30),
            "all",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الأول",
            date(2026, 10, 13),
            date(2026, 10, 22),
            "g10_11",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الأول",
            date(2026, 10, 14),
            date(2026, 10, 22),
            "g1_9",
            "students",
        ),
        ("break", "إجازة منتصف الفصل الأول", date(2026, 10, 25), date(2026, 10, 29), "all", "both"),
        (
            "resume",
            "بدء الدوام بعد إجازة منتصف الفصل الأول",
            date(2026, 11, 1),
            date(2026, 11, 1),
            "all",
            "both",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الأول",
            date(2026, 12, 6),
            date(2026, 12, 15),
            "g12",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الأول",
            date(2026, 12, 6),
            date(2026, 12, 15),
            "g10_11",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الأول",
            date(2026, 12, 7),
            date(2026, 12, 15),
            "g1_9",
            "students",
        ),
        (
            "break",
            "إجازة منتصف العام الأكاديمي",
            date(2026, 12, 20),
            date(2027, 1, 2),
            "all",
            "both",
        ),
        (
            "staff_start",
            "بدء دوام الموظفين للفصل الثاني",
            date(2027, 1, 3),
            date(2027, 1, 3),
            "all",
            "staff",
        ),
        (
            "students_start",
            "بدء دوام الطلبة للفصل الثاني",
            date(2027, 1, 4),
            date(2027, 1, 4),
            "all",
            "students",
        ),
        (
            "makeup_exam",
            "ملحق اختبارات نهاية الفصل الأول",
            date(2027, 1, 17),
            date(2027, 1, 26),
            "all",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الثاني",
            date(2027, 3, 21),
            date(2027, 3, 30),
            "g10_11",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الثاني",
            date(2027, 3, 22),
            date(2027, 3, 30),
            "g1_9",
            "students",
        ),
        ("break", "إجازة نهاية أسبوع مطوّلة", date(2027, 3, 31), date(2027, 4, 1), "all", "both"),
        (
            "resume",
            "بدء الدوام بعد الإجازة المطوّلة",
            date(2027, 4, 4),
            date(2027, 4, 4),
            "all",
            "both",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الثاني",
            date(2027, 6, 1),
            date(2027, 6, 17),
            "g12",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الثاني",
            date(2027, 6, 3),
            date(2027, 6, 15),
            "g10_11",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الثاني",
            date(2027, 6, 3),
            date(2027, 6, 14),
            "g1_9",
            "students",
        ),
        ("break", "إجازة الموظفين", date(2027, 6, 27), date(2027, 8, 19), "all", "staff"),
    ],
    "2027-2028": [
        ("staff_start", "بدء دوام الموظفين", date(2027, 8, 22), date(2027, 8, 22), "all", "staff"),
        (
            "second_round",
            "اختبارات الدور الثاني للعام ٢٠٢٦/٢٠٢٧",
            date(2027, 8, 22),
            date(2027, 8, 26),
            "all",
            "students",
        ),
        (
            "students_start",
            "بدء دوام الطلبة",
            date(2027, 8, 29),
            date(2027, 8, 29),
            "all",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الأول",
            date(2027, 10, 12),
            date(2027, 10, 21),
            "g10_11",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الأول",
            date(2027, 10, 13),
            date(2027, 10, 21),
            "g1_9",
            "students",
        ),
        ("break", "إجازة منتصف الفصل الأول", date(2027, 10, 24), date(2027, 10, 28), "all", "both"),
        (
            "resume",
            "بدء الدوام بعد إجازة منتصف الفصل الأول",
            date(2027, 10, 31),
            date(2027, 10, 31),
            "all",
            "both",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الأول",
            date(2027, 12, 5),
            date(2027, 12, 14),
            "g12",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الأول",
            date(2027, 12, 5),
            date(2027, 12, 14),
            "g10_11",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الأول",
            date(2027, 12, 6),
            date(2027, 12, 14),
            "g1_9",
            "students",
        ),
        (
            "break",
            "إجازة منتصف العام الأكاديمي",
            date(2027, 12, 19),
            date(2028, 1, 1),
            "all",
            "both",
        ),
        (
            "staff_start",
            "بدء دوام الموظفين للفصل الثاني",
            date(2028, 1, 2),
            date(2028, 1, 2),
            "all",
            "staff",
        ),
        (
            "students_start",
            "بدء دوام الطلبة للفصل الثاني",
            date(2028, 1, 3),
            date(2028, 1, 3),
            "all",
            "students",
        ),
        (
            "makeup_exam",
            "ملحق اختبارات نهاية الفصل الأول",
            date(2028, 1, 16),
            date(2028, 1, 25),
            "all",
            "students",
        ),
        ("break", "إجازة رمضان", date(2028, 2, 22), date(2028, 2, 23), "all", "both"),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الثاني",
            date(2028, 3, 19),
            date(2028, 3, 28),
            "g10_11",
            "students",
        ),
        (
            "midterm_exam",
            "اختبارات منتصف الفصل الثاني",
            date(2028, 3, 20),
            date(2028, 3, 28),
            "g1_9",
            "students",
        ),
        ("break", "إجازة نهاية أسبوع مطوّلة", date(2028, 3, 29), date(2028, 3, 30), "all", "both"),
        (
            "resume",
            "بدء الدوام بعد الإجازة المطوّلة",
            date(2028, 4, 2),
            date(2028, 4, 2),
            "all",
            "both",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الثاني",
            date(2028, 5, 30),
            date(2028, 6, 15),
            "g12",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الثاني",
            date(2028, 6, 1),
            date(2028, 6, 13),
            "g10_11",
            "students",
        ),
        (
            "final_exam",
            "اختبارات نهاية الفصل الثاني",
            date(2028, 6, 1),
            date(2028, 6, 12),
            "g1_9",
            "students",
        ),
        ("break", "إجازة الموظفين", date(2028, 6, 25), date(2028, 8, 17), "all", "staff"),
    ],
}


class Command(BaseCommand):
    help = "يبذر تقويم الوزارة (٢٠٢٥/٢٠٢٦ — ٢٠٢٧/٢٠٢٨)"

    def add_arguments(self, parser):
        parser.add_argument("--school", help="كود المدرسة — الافتراض: كل المدارس النشطة")

    @transaction.atomic
    def handle(self, *args, **options):
        schools = School.objects.filter(is_active=True)
        if options.get("school"):
            schools = schools.filter(code=options["school"])
        if not schools.exists():
            self.stderr.write("لا مدارس مطابقة.")
            return

        for school in schools:
            for name, (start, end) in YEARS.items():
                year = self._year(school, name, start, end)
                s1, s2 = self._semesters(year, name, start, end)
                self._events(year, name, s1, s2)
                self.stdout.write(f"  {school.code} · {name}: {len(EVENTS[name])} حدثاً")

        self.stdout.write(self.style.SUCCESS("تمّ بذر التقويم."))

    @staticmethod
    def _year(school, name, start, end):
        year, _ = AcademicYear.objects.update_or_create(
            school=school,
            name=name,
            defaults={"start_date": start, "end_date": end},
        )
        return year

    @staticmethod
    def _semesters(year, name, start, end):
        s2_start = S2_START[name]
        s1, _ = Semester.objects.update_or_create(
            academic_year=year,
            code="S1",
            defaults={
                "start_date": start,
                "end_date": s2_start - timedelta(days=1),
                "max_grade": MAX_GRADE["S1"],
            },
        )
        s2, _ = Semester.objects.update_or_create(
            academic_year=year,
            code="S2",
            defaults={"start_date": s2_start, "end_date": end, "max_grade": MAX_GRADE["S2"]},
        )
        return s1, s2

    @staticmethod
    def _events(year, name, s1, s2):
        year.calendar_events.all().delete()
        CalendarEvent.objects.bulk_create(
            [
                CalendarEvent(
                    academic_year=year,
                    semester=s1 if ev_start <= s1.end_date else s2,
                    event_type=kind,
                    name=label,
                    start_date=ev_start,
                    end_date=ev_end,
                    grade_scope=scope,
                    audience=audience,
                )
                for kind, label, ev_start, ev_end, scope, audience in EVENTS[name]
            ]
        )
