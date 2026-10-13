"""`python manage.py settlement_diff_report [--since YYYY-MM-DD] [--until YYYY-MM-DD] [--out report.json]` — قراءةٌ فقط (D-271م، S3).

تقريرُ فرق الأرقام للمالك قبل أيّ تطبيق: لو سُوِّي المعلَّقُ في أجنحة الرصد النهائيّ، كم يُضاف إلى `StudentAttendance`، وكم طالباً يتغيّر موقفُه، وكم تنبيهاً «محجوزاً» جديداً
يُنشأ، موزَّعاً بحسب اليوم والجناح. يطبع **سيناريوَين** حين يُعطى `--since`: «كلُّ التواريخ» و«من التاريخ» (مثلاً من 10-07 لأنّ 10-06 يومُ اضطراب الحجز).
لا يكتب في القاعدة ولا يرسل، ولا أسماء ولا معرّفات طلبة في المخرج. يُنفَّذ على الإنتاج بيد 0601 بإذن المالك.
"""

import datetime as dt
import json

from django.core.management.base import BaseCommand, CommandError

from core.celery_tasks import school_rls_scope
from core.models import School
from operations.settlement_diff import diff_report


def _date(raw: str) -> dt.date:
    try:
        return dt.date.fromisoformat(raw)
    except ValueError as exc:
        raise CommandError(f"تاريخٌ غيرُ صالح «{raw}» — الصيغة YYYY-MM-DD") from exc


class Command(BaseCommand):
    help = "تقريرُ فرق الأرقام لو سُوِّي المعلَّق (قراءةٌ فقط)"

    def add_arguments(self, parser):
        parser.add_argument("--since", help="أوّلُ تاريخ حصّة للسيناريو الثاني (YYYY-MM-DD)")
        parser.add_argument("--until", help="آخرُ تاريخ حصّة (YYYY-MM-DD)")
        parser.add_argument("--out", help="ملفُّ JSON يُكتب فيه التقريرُ كاملاً (بلا أسماء)")

    def handle(self, *args, **options):
        since = _date(options["since"]) if options["since"] else None
        until = _date(options["until"]) if options["until"] else None
        scenarios = [("كلُّ التواريخ", None)] + (
            [("من " + since.isoformat(), since)] if since else []
        )
        report: dict = {}
        for label, start in scenarios:
            per_school = {}
            for school in School.objects.filter(is_active=True):
                with school_rls_scope(school.id):
                    per_school[school.code] = diff_report(school, since=start, until=until)
            report[label] = per_school
            for code, data in per_school.items():
                self.stdout.write(
                    f"[{label}] {code}: مؤهَّل {data['eligible']} | متعارضٌ يُتخطّى {data['conflicts_skipped']} | "
                    f"صفوفٌ تُضاف {data['rows_added']} | طلبةٌ يتغيّر موقفُهم {data['students_whose_unexcused_days_change']} | "
                    f"طلبةٌ يبلغون عتبةً {data['students_reaching_a_new_gate']} | تنبيهاتٌ محجوزةٌ جديدة "
                    f"{data['new_held_alerts_by_gate']} (بحسب الجناح {data['new_held_alerts_by_wing']})"
                )
        if options["out"]:
            with open(options["out"], "w", encoding="utf-8") as handle:
                json.dump(report, handle, ensure_ascii=False, indent=2, default=str)
            self.stdout.write(f"التقرير الكامل (بلا أسماء) في {options['out']}")
