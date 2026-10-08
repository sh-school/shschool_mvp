"""staff_affairs/leave_rules.py — جدولُ قواعد الإجازات المركزيّ من قانون الموارد البشرية 15/2016.

مصدرٌ واحدٌ لكلّ ما تعرفه المنصّةُ عن نوع الإجازة: سقفُها، وهل تُعدّ بأيّام العمل،
وهل هي لمرّة واحدة في الخدمة، والمستندُ اللازم لها. والنصوصُ الحرفيّة في
``AAdocs/ministry_data/2026_2027/02d_hr_law_leaves_verbatim.md`` (المصدر هو الـPDF الحَكَم)،
وفي كلّ قاعدةٍ المادّةُ التي تسندها.

لا يعرف هذا الملفُّ نماذجَ التطبيق إلّا في قراءة تقويم المدرسة لعطلاته.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass

#: الجمعةُ والسبتُ عطلةُ نهاية الأسبوع (weekday بايثون: الاثنين 0 … الأحد 6).
WEEKEND_WEEKDAYS = frozenset({4, 5})


@dataclass(frozen=True)
class LeaveRule:
    """قاعدةُ نوعٍ واحد. الحقولُ الفارغة تعني «لا قيدَ منصوصاً عليه»."""

    article: str
    #: السقفُ بالأيّام لطلبٍ واحد أو للسنة بحسب المادّة؛ ``None`` بلا سقفٍ ثابت.
    cap_days: int | None = None
    #: ``True`` حيث تنصّ المادّةُ على «أيّام عمل» فتُستبعد العطلاتُ من العدّ.
    working_days: bool = False
    #: ``True`` للإجازة «لمرّة واحدة طوال مدة الخدمة».
    once_in_service: bool = False
    #: المستندُ اللازم لقبول الطلب؛ فارغٌ إن لم تشترط المادّةُ مستنداً.
    required_document: str = ""


#: م65: 10 أيام عمل/سنة · م75: 21 يوماً مرّةً واحدة · م76: 15 يوماً بصورة عقد الزواج ·
#: م73: وضعٌ بتقرير طبيّ أو شهادة ميلاد · م77: عدّةٌ بما يثبت الوفاة · لائحة م91: امتحاناتٌ بجدولها.
#: والمرضيّةُ (م66): ترخيصُ الجهة الطبّيّة ≤3 متّصلة و15/سنة وما زاد باعتماد الجهة المختصّة، فلا سقفَ
#: تفرضه المنصّةُ عليها — الاعتمادُ الطبّيّ خارجها — لكنّها بأيّام عمل.
LEAVE_RULES: dict[str, LeaveRule] = {
    "annual": LeaveRule(article="م62", working_days=True),
    "emergency": LeaveRule(article="م65", cap_days=10, working_days=True),
    "sick": LeaveRule(article="م66", working_days=True),
    "maternity": LeaveRule(
        article="م73", required_document="تقرير طبي أو صورة طبق الأصل من شهادة ميلاد الطفل"
    ),
    "hajj": LeaveRule(article="م75", cap_days=21, once_in_service=True),
    "marriage": LeaveRule(
        article="م76", cap_days=15, required_document="صورة طبق الأصل من عقد الزواج"
    ),
    "iddah": LeaveRule(article="م77", required_document="ما يثبت وفاة الزوج"),
    "exams": LeaveRule(
        article="لائحة م91", required_document="صورة طبق الأصل من جدول الامتحانات أو ما يفيد ذلك"
    ),
}

#: ترتيبُ م61 (1–17) → رمزُ النوع في ``LEAVE_TYPES``. يقارنه حارسٌ بنصّ المادّة الحرفيّ فلا يُنقص نوعٌ.
M61_TYPES: dict[int, str] = {
    1: "annual",
    2: "emergency",
    3: "sick",
    4: "maternity",
    5: "child_care",
    6: "hajj",
    7: "marriage",
    8: "iddah",
    9: "bereavement",
    10: "spouse_companion",
    11: "mahram",
    12: "patient_companion",
    13: "exceptional",
    14: "training",
    15: "study",
    16: "exams",
    17: "unpaid",
}


def leave_rule(leave_type: str) -> LeaveRule | None:
    return LEAVE_RULES.get(leave_type)


def default_total_days(leave_type: str, annual_days: int) -> int:
    """الرصيدُ الافتراضيّ لنوعٍ: سقفُه إن كان له سقف، ورصيدُ السنويّة للسنويّة، وصفرٌ لما عداهما."""
    if leave_type == "annual":
        return annual_days
    rule = LEAVE_RULES.get(leave_type)
    return rule.cap_days if rule and rule.cap_days is not None else 0


def staff_holidays(school, start: dt.date, end: dt.date) -> set[dt.date]:
    """أيّامُ العطل الرسميّة في [start, end] من تقويم المدرسة — ما كان جمهورُه الجميعَ أو الموظّفين.

    إجازةُ الطلبة وحدَهم ليست عطلةً للموظّف، فلا تُستبعد (م60 وم62).
    """
    from core.models import CalendarEvent

    days: set[dt.date] = set()
    events = CalendarEvent.objects.filter(
        academic_year__school=school,
        event_type="break",
        audience__in=("both", "staff"),
        start_date__lte=end,
        end_date__gte=start,
    ).values_list("start_date", "end_date")
    for ev_start, ev_end in events:
        day = max(ev_start, start)
        while day <= min(ev_end, end):
            days.add(day)
            day += dt.timedelta(days=1)
    return days


def count_leave_days(leave_type: str, start: dt.date, end: dt.date, school=None) -> int:
    """عددُ أيّام الطلب: أيّامُ عملٍ حيث نصّت المادّة، وتقويميّةٌ فيما عداه.

    بلا ``school`` لا يُعرف تقويمُه فتُستبعد عطلةُ نهاية الأسبوع وحدَها.
    """
    total = (end - start).days + 1
    rule = LEAVE_RULES.get(leave_type)
    if not rule or not rule.working_days:
        return total
    holidays = staff_holidays(school, start, end) if school is not None else set()
    return sum(
        1
        for offset in range(total)
        if (day := start + dt.timedelta(days=offset)).weekday() not in WEEKEND_WEEKDAYS
        and day not in holidays
    )


def per_request_cap_error(leave_type: str, days: int) -> str:
    """رسالةُ خطأٍ إن جاوز الطلبُ الواحدُ سقفَ نوعه، وإلّا فارغ."""
    rule = LEAVE_RULES.get(leave_type)
    if rule and rule.cap_days is not None and days > rule.cap_days:
        return f"الحدّ الأقصى لهذه الإجازة {rule.cap_days} يوماً ({rule.article})."
    return ""


def missing_document_error(leave_type: str, has_attachment: bool) -> str:
    """رسالةُ خطأٍ إن اشترط النوعُ مستنداً ولم يُرفق، وإلّا فارغ."""
    rule = LEAVE_RULES.get(leave_type)
    if rule and rule.required_document and not has_attachment:
        return f"يلزم إرفاق: {rule.required_document} ({rule.article})."
    return ""
