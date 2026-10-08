"""`python manage.py absence_alerts_report [--school CODE] [--day YYYY-MM-DD]` — قراءةٌ فقط (قرارُ المالك D-246م): لا يكتب ولا يرسل.

يطبع لكلّ مدرسة: عدّادَ تنبيهات الغياب بحسب الحالة، وما سيرسله مرسِلُ 07:00 دفعةً واحدةً (المعلَّقة pending)، وعددَ التكرارات القائمة
(مدرسة+طالب+عتبة+فترة) لقرار قيدٍ لاحقاً، وكم تنبيهاً «محجوزاً» سيُنشئه مسحُ اليوم الآن.
"""

import datetime as dt

from django.core.management.base import BaseCommand
from django.db.models import Count, Max, Min
from django.utils import timezone

from core.models import School
from operations.end_of_day import would_create
from operations.models import AbsenceAlert


class Command(BaseCommand):
    help = "تقريرٌ بتنبيهات الغياب (قراءةٌ فقط): الحالات والمعلَّق والتكرارات وما سيُنشئه المسح."

    def add_arguments(self, parser):
        parser.add_argument("--school", help="رمز المدرسة (الكلّ افتراضاً)")
        parser.add_argument("--day", help="يومُ المسح YYYY-MM-DD (اليوم افتراضاً)")

    def handle(self, *args, **options):
        day = dt.date.fromisoformat(options["day"]) if options.get("day") else timezone.localdate()
        schools = School.objects.filter(is_active=True)
        if options.get("school"):
            schools = schools.filter(code=options["school"])
        for school in schools:
            by_status = dict(
                AbsenceAlert.objects.filter(school=school)
                .values_list("status")
                .annotate(n=Count("id"))
                .order_by("status")
            )
            dupes = (
                AbsenceAlert.objects.filter(school=school)
                .values("student_id", "gate", "period_start", "period_end")
                .annotate(n=Count("id"))
                .filter(n__gt=1)
                .count()
            )
            now = timezone.now()
            ages = AbsenceAlert.objects.filter(school=school, status="pending").aggregate(
                oldest=Min("created_at"), newest=Max("created_at")
            )
            mean_age = None
            created = list(
                AbsenceAlert.objects.filter(school=school, status="pending").values_list(
                    "created_at", flat=True
                )
            )
            if created:
                mean_age = round(sum((now - c).days for c in created) / len(created), 1)
            self.stdout.write(
                f"[{school.code}] أعمارُ المعلَّقة (أيّام): أقدمُها "
                f"{(now - ages['oldest']).days if ages['oldest'] else '—'}، أحدثُها "
                f"{(now - ages['newest']).days if ages['newest'] else '—'}، متوسّطُها "
                f"{mean_age if mean_age is not None else '—'}"
            )
            self.stdout.write(
                f"[{school.code}] الحالات: {by_status or {}} | معلَّقةٌ سيرسلها 07:00 دفعةً: "
                f"{by_status.get('pending', 0)} | مجموعاتٌ مكرَّرة: {dupes} | "
                f"سيُنشئ مسحُ {day} تنبيهاتٍ محجوزة: {would_create(school, day)}"
            )
