"""
staff_affairs/probation.py — فترة الاختبار وأثرها على الإجازات (قانون الموارد البشرية 15/2016) — W-20261001-027

- م72: المرضُ تحت الاختبار يمدّد النهايةَ بقدره، بحدٍّ أقصى مدّةٌ مساويةٌ لفترة الاختبار؛
  والوضعُ والعدّةُ لا تُحسبان منها (فتمدّدانها كاملتين).
- م62: الدوريّةُ بعد انتهاء الاختبار بنجاح، وتُحسب بنسبة المدة المعمولة بعده في السنة.
- لائحة م85: لا إجازةَ مرافقة زوجٍ خلال الاختبار.

الموظّفُ بلا سجلّ عقدٍ لا قيدَ عليه (بياناتٌ قديمة).
"""

from __future__ import annotations

import datetime as dt

from dateutil.relativedelta import relativedelta
from django.db import transaction

from .models import EmploymentContract, LeaveRequest

#: يمدّدها المرضُ (م72 ف1) بسقفٍ؛ والوضعُ والعدّة (م72 ف2) بلا سقف.
SICK_TYPES = ("sick",)
EXCLUDED_TYPES = ("maternity", "iddah")
#: لا تُمنح تحت الاختبار: الدوريّة (م62) ومرافقة الزوج (لائحة م85).
BLOCKED_UNDER_PROBATION = {
    "annual": "الإجازة الدورية تُستحق بعد انتهاء فترة الاختبار بنجاح (م62).",
    "spouse_companion": "لا تُمنح إجازة مرافقة الزوج خلال فترة الاختبار (لائحة م85).",
}


def _overlap_days(leaves, start: dt.date, end: dt.date) -> int:
    """أيامُ التقويم المشتركة بين إجازاتٍ ونافذة [start, end] — لا يُعدّ يومٌ تداخلت فيه إجازتان مرّتين."""
    days: set[dt.date] = set()
    for leave in leaves:
        day = max(leave.start_date, start)
        last = min(leave.end_date, end)
        while day <= last:
            days.add(day)
            day += dt.timedelta(days=1)
    return len(days)


def compute_end(contract: EmploymentContract) -> tuple[dt.date, int]:
    """(النهاية الفعلية، أيام التمديد) من إجازات الموظف المعتمَدة — حسابٌ خالصٌ idempotent."""
    base_end = contract.base_end
    length = (base_end - contract.contract_start).days
    approved = LeaveRequest.objects.filter(
        school=contract.school, staff=contract.staff, status="approved"
    )
    sick = list(approved.filter(leave_type__in=SICK_TYPES))
    excluded = list(approved.filter(leave_type__in=EXCLUDED_TYPES))
    end = base_end
    for _ in range(20):  # التمديد قد يُدخل إجازةً لاحقةً في النافذة؛ يستقرّ سريعاً
        sick_days = min(_overlap_days(sick, contract.contract_start, end), length)
        other_days = _overlap_days(excluded, contract.contract_start, end)
        new_end = base_end + dt.timedelta(days=sick_days + other_days)
        if new_end == end:
            break
        end = new_end
    return end, (end - base_end).days


@transaction.atomic
def open_contract(
    school, staff, contract_start: dt.date, probation_months: int, actor, contract_ref: str = ""
) -> EmploymentContract:
    """تسجيلُ عقدٍ بفترة اختبار؛ التكرارُ للموظف نفسه يُحدّث ولا يُضاعف."""
    base_end = contract_start + relativedelta(months=probation_months)
    contract, created = EmploymentContract.objects.get_or_create(
        school=school,
        staff=staff,
        defaults={
            "contract_ref": contract_ref,
            "contract_start": contract_start,
            "probation_months": probation_months,
            "base_end": base_end,
            "probation_end": base_end,
            "created_by": actor,
            "updated_by": actor,
        },
    )
    if not created:
        contract.contract_ref = contract_ref
        contract.contract_start = contract_start
        contract.probation_months = probation_months
        contract.base_end = base_end
        contract.updated_by = actor
        contract.save()
    return refresh_end(contract)


def refresh_end(contract: EmploymentContract) -> EmploymentContract:
    """يعيد حسابَ النهاية الفعلية والتمديد ويحفظهما."""
    end, extension = compute_end(contract)
    if (contract.probation_end, contract.extension_days) != (end, extension):
        contract.probation_end = end
        contract.extension_days = extension
        contract.save(update_fields=["probation_end", "extension_days", "updated_at"])
    return contract


def refresh_for_leave(leave: LeaveRequest) -> None:
    """بعد اعتماد إجازةٍ تمدّد الاختبارَ (مرض/وضع/عدّة) أعِد حساب نهاية موظفها."""
    if leave.leave_type not in SICK_TYPES + EXCLUDED_TYPES:
        return
    contract = EmploymentContract.objects.filter(school=leave.school, staff=leave.staff).first()
    if contract:
        refresh_end(contract)


def record_result(
    contract: EmploymentContract, result: str, actor, on: dt.date
) -> EmploymentContract:
    """نتيجةُ الاختبار؛ لا تُسجَّل قبل انتهاء الفترة الفعلية ولا تُعدَّل بعد صدورها."""
    if result not in ("passed", "failed"):
        raise ValueError("نتيجةٌ غير صالحة.")
    if contract.result != "pending":
        raise ValueError("سُجّلت نتيجة الاختبار سابقاً.")
    if on <= contract.probation_end:
        raise ValueError("لا تُسجَّل النتيجة قبل انتهاء فترة الاختبار الفعلية.")
    contract.result = result
    contract.result_at = on
    contract.updated_by = actor
    contract.save(update_fields=["result", "result_at", "updated_by", "updated_at"])
    return contract


def probation_block_error(school, staff, leave_type: str) -> str | None:
    """رسالةُ الرفض إن كان النوعُ ممنوعاً على موظفٍ لم يجتز اختباره بنجاح، وإلا ``None``."""
    reason = BLOCKED_UNDER_PROBATION.get(leave_type)
    if not reason:
        return None
    contract = EmploymentContract.objects.filter(school=school, staff=staff).first()
    if contract is None or contract.result == "passed":
        return None
    return reason


def prorated_annual_days(
    contract: EmploymentContract, year_start: dt.date, year_end: dt.date, full_days: int
) -> int:
    """الدوريّة بعد النجاح نسبيّةٌ للمدة المعمولة بعد نهاية الاختبار داخل السنة (م62)."""
    first = max(year_start, contract.probation_end + dt.timedelta(days=1))
    worked = max(0, (year_end - first).days + 1)
    total = (year_end - year_start).days + 1
    return int(full_days * worked / total + 0.5)
