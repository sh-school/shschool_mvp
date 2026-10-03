"""يدمق ما تغيّر منذ لحظةٍ في هذه القاعدة — لنقله لاحقاً إلى قاعدةٍ أخرى بالمفتاح الطبيعيّ.

    8500(هذه القاعدة) → dump → ملفّ JSON محليّ

يُشغَّل في بيئة المعاينة (8500) حيث وقع العملُ الفعليّ فعلاً — لا في الإنتاج. يقرأ فقط،
ولا يكتب في أيّ قاعدة. الملفُّ الناتجُ يُطبَّق لاحقاً بـ`apply_preview_workload_changes`
على قاعدةٍ أخرى (الإنتاج عادةً)، عبر Railway shell بيد المالك.

PDPPL: لا يُكتب `national_id` ولا نسخُه المشفّرة في الملفّ — الـHMAC والرقمُ الوظيفيّ وحدَهما.

    python manage.py dump_preview_workload_changes --since "2026-09-27T20:24:00+03:00" --out changes.json
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils.dateparse import parse_datetime

from academic_management import preview_reconciliation as recon
from academic_management.models import TeacherWorkloadPlan
from operations.models import SubjectClassAssignment


class Command(BaseCommand):
    help = "يدمق إسناداتٍ وخططَ أنصبةٍ تغيّرت منذ لحظةٍ في هذه القاعدة إلى ملفّ JSON — بلا كتابة."

    def add_arguments(self, parser):
        parser.add_argument(
            "--since", required=True, help="لحظةٌ بصيغة ISO 8601، مثل 2026-09-27T20:24:00+03:00"
        )
        parser.add_argument("--out", required=True, help="مسارُ ملفّ JSON الناتج")
        parser.add_argument(
            "--school", default="", help="رمزُ مدرسةٍ يحصر الدمقَ بها — وفراغُه كلُّ المدارس"
        )

    def handle(self, *args, **options):
        since = parse_datetime(options["since"])
        if since is None:
            raise CommandError(
                "صيغةُ --since غيرُ صالحة — استعمل ISO 8601، مثل 2026-09-27T20:24:00+03:00"
            )

        assignments = SubjectClassAssignment.objects.filter(updated_at__gte=since).select_related(
            "school", "class_group", "subject", "teacher"
        )
        plans = TeacherWorkloadPlan.objects.filter(updated_at__gte=since).select_related(
            "school", "teacher"
        )
        if options["school"]:
            assignments = assignments.filter(school__code=options["school"])
            plans = plans.filter(school__code=options["school"])
        # حساباتُ المعاينة الوهميّةُ تبقى على 8500 (D-167م): صفوفُ معلّمٍ موسومٍ لا تُدمق أبداً.
        assignments = recon.exclude_preview_teachers(assignments)
        plans = recon.exclude_preview_teachers(plans)

        payload = {
            "since": since.isoformat(),
            "assignments": [recon.dump_assignment(row) for row in assignments],
            "workload_plans": [recon.dump_workload_plan(row) for row in plans],
        }

        with open(options["out"], "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=1, sort_keys=True)

        self.stdout.write(
            f"دُمق {len(payload['assignments'])} إسناداً و{len(payload['workload_plans'])} خطّةَ نصابٍ "
            f"منذ {since.isoformat()} إلى {options['out']}"
        )
        self.stdout.write("لا بياناتٍ شخصيّةً في الملفّ — الـHMAC والرقمُ الوظيفيّ للمطابقة وحدَها.")
