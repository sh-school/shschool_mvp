"""clinic/metrics.py — مؤشرات قياس العيادة الخمسة على مستوى العيادة (W-20261020-035).

كلُّ مؤشرٍ عددٌ أو نسبةٌ مجمَّعةٌ للمدرسة في شهرٍ واحد: لا اسمَ طالبٍ ولا ممرّضٍ ولا نصَّ صحيٍّ
(reason/symptoms/treatment مشفّرةٌ ولا تُقرأ هنا أصلاً)، ولا قياسَ على مستوى الفرد.

الصيغ (يطابقها `docs/clinic_metrics.md`):
  1. زمن التسجيل  = visit_date − draft_started_at بالثواني، p50/p90 (أقرب رتبة) على زيارات لها مسودة.
  2. ربط الاستئذان = استئذاناتٌ صحية (reason=medical) لها زيارةٌ لنفس الطالب في اليوم نفسه قبل وقت
     الخروج أو عنده ÷ كلُّ الاستئذانات الصحية. ربطٌ منطقيّ بلا مفتاحٍ أجنبيّ.
  3. تغطية الترميز = زياراتٌ فيها خدمةٌ وشكوى (وحالةُ خروجٍ إن أُغلقت) ÷ كلُّ الزيارات.
  4. تدقيق الفتح  = زياراتٌ لها سطرُ تدقيق إنشاءٍ ÷ كلُّ الزيارات؛ وفتحُ الملف الصحي يُدقَّق داخل
     العرض نفسه (`student_health_record`) ويحرسه اختبار.
  5. التطابق الشهري = أبعادُ التقرير (الخدمة، المجموعة، الشكوى، الحالة) التي يساوي مجموعُها عددَ
     الزيارات ÷ عددُ الأبعاد.
"""

from __future__ import annotations

import datetime as dt
import math
from collections import defaultdict

from django.db.models import Count
from django.utils import timezone

from clinic.models import ClinicVisit

#: الأبعادُ التي يجب أن يساوي مجموعُ كلٍّ منها (مع «غير مرمَّز/مفتوحة») عددَ الزيارات.
_RECONCILED_DIMENSIONS = ("service_code", "service_group", "complaint_code", "outcome")


def month_bounds(year: int, month: int) -> tuple[dt.datetime, dt.datetime]:
    """بدايةُ الشهر (شاملة) ونهايتُه (حصريّة) بالتوقيت المحلّي."""
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(dt.datetime(year, month, 1), tz)
    ny, nm = (year + 1, 1) if month == 12 else (year, month + 1)
    return start, timezone.make_aware(dt.datetime(ny, nm, 1), tz)


def _ratio(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def _percentile(sorted_values: list[int], pct: int) -> int | None:
    """أقربُ رتبة: لا استيفاءَ ولا قيمةً غيرَ مرصودة."""
    if not sorted_values:
        return None
    rank = max(1, math.ceil(pct / 100 * len(sorted_values)))
    return sorted_values[rank - 1]


def registration_time(visits) -> dict:
    deltas = sorted(
        max(0, int((v - d).total_seconds()))
        for v, d in visits.exclude(draft_started_at=None).values_list(
            "visit_date", "draft_started_at"
        )
    )
    return {"n": len(deltas), "p50": _percentile(deltas, 50), "p90": _percentile(deltas, 90)}


def exit_link(school, start: dt.datetime, end: dt.datetime) -> dict:
    from operations.models import ExitPermit

    permits = list(
        ExitPermit.objects.filter(
            school=school, reason="medical", exit_at__gte=start, exit_at__lt=end
        ).values_list("student_id", "exit_at")
    )
    seen: dict = defaultdict(list)
    for student_id, visited_at in ClinicVisit.objects.filter(
        school=school, visit_date__gte=start, visit_date__lt=end
    ).values_list("student_id", "visit_date"):
        seen[(student_id, timezone.localtime(visited_at).date())].append(visited_at)
    linked = sum(
        1
        for student_id, exit_at in permits
        if any(v <= exit_at for v in seen.get((student_id, timezone.localtime(exit_at).date()), []))
    )
    return {"permits": len(permits), "linked": linked, "rate": _ratio(linked, len(permits))}


def coding_coverage(visits) -> dict:
    total = visits.count()
    coded = (
        visits.exclude(service_code="")
        .exclude(complaint_code="")
        .exclude(closed_at__isnull=False, outcome="")
        .count()
    )
    return {"visits": total, "coded": coded, "rate": _ratio(coded, total)}


def audit_coverage(visits) -> dict:
    from core.models import AuditLog

    ids = [str(pk) for pk in visits.values_list("pk", flat=True)]
    audited = (
        AuditLog.objects.filter(model_name="ClinicVisit", action="create", object_id__in=ids)
        .values("object_id")
        .distinct()
        .count()
        if ids
        else 0
    )
    return {"visits": len(ids), "audited": audited, "rate": _ratio(audited, len(ids))}


def monthly_reconciliation(visits) -> dict:
    total = visits.count()
    dims: dict[str, bool] = {}
    for field in _RECONCILED_DIMENSIONS:
        grouped = visits.values(field).annotate(n=Count("pk")).values_list("n", flat=True)
        dims[field] = sum(grouped) == total
    matched = sum(dims.values())
    return {"visits": total, "dimensions": dims, "rate": matched / len(dims)}


def clinic_indicators(school, year: int, month: int) -> dict:
    """المؤشراتُ الخمسة لمدرسةٍ في شهر — أعدادٌ ونسبٌ فقط."""
    start, end = month_bounds(year, month)
    visits = ClinicVisit.objects.filter(school=school, visit_date__gte=start, visit_date__lt=end)
    return {
        "year": year,
        "month": month,
        "registration_time": registration_time(visits),
        "exit_link": exit_link(school, start, end),
        "coding_coverage": coding_coverage(visits),
        "audit_coverage": audit_coverage(visits),
        "reconciliation": monthly_reconciliation(visits),
    }


def _pct(rate: float | None) -> str:
    return "—" if rate is None else f"{rate * 100:.0f}%"


def _secs(value: int | None) -> str:
    return "—" if value is None else f"{value} ث"


def cards(m: dict) -> list[dict]:
    """بطاقاتُ العرض: نصوصٌ جاهزة (لا يُطبع None) مع الهدف لكلّ مؤشر."""
    reg, link = m["registration_time"], m["exit_link"]
    cov, aud, rec = m["coding_coverage"], m["audit_coverage"], m["reconciliation"]
    return [
        {
            "label": "زمن التسجيل (وسيط)",
            "value": _secs(reg["p50"]),
            "sub": f"p90: {_secs(reg['p90'])} — من {reg['n']} زيارة — الهدف أقل من 20 ث",
        },
        {
            "label": "ربط الاستئذان بالزيارة",
            "value": _pct(link["rate"]),
            "sub": f"{link['linked']} من {link['permits']} استئذانًا صحيًا — الهدف 95% فأكثر",
        },
        {
            "label": "تغطية الترميز",
            "value": _pct(cov["rate"]),
            "sub": f"{cov['coded']} من {cov['visits']} زيارة",
        },
        {
            "label": "تدقيق الفتح",
            "value": _pct(aud["rate"]),
            "sub": f"{aud['audited']} من {aud['visits']} زيارة — الهدف 100%",
        },
        {
            "label": "التطابق الشهري",
            "value": _pct(rec["rate"]),
            "sub": f"{sum(rec['dimensions'].values())} من {len(rec['dimensions'])} أبعاد — الهدف 100%",
        },
    ]
