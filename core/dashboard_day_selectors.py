"""اليومُ الذي تعرضه اللوحةُ لكلّ الأدوار — للقراءة فقط (W-20261010-056، قرارُ المالك 2026-10-11).

قرارُ المالك: «كلُّ الأدوار» تتنقّل بين الأيام (السابق · اليوم · التالي)، وهو **عرضٌ فقط** لا يقيّد شيئاً،
ومداه **العامُّ الدراسيُّ كلُّه بفصلَيه** من التقويم المدرسيّ في الباك اند (`academic_year_window`) لا من تاريخٍ مكتوبٍ هنا.
تاريخٌ خارج المدى (أو نصٌّ لا يُقرأ) يعود إلى اليوم الحقيقيّ بصمتٍ — لا خطأ ولا رفض.

وما كان «الآن» — الحصّةُ الجاريةُ والتاليةُ وطورُ اليوم الحيّ ورصدُ الجناح — لا معنى له في يومٍ غير اليوم؛
فيُقرأ `is_today` من هنا ويُطفئ كلُّ موضعٍ ما يخصّه، ولا يُنشئ يومٌ مضى جلساتٍ ولا يفتح رصداً.
"""

from __future__ import annotations

import datetime as dt
from typing import Any
from urllib.parse import urlencode

from core.academic_calendar import academic_year_window

PARAM = "date"


def day_window(school: Any, real_today: dt.date) -> tuple[dt.date, dt.date]:
    """مدى التنقّل: العامُّ الدراسيُّ الذي يقع فيه اليومُ الحقيقيّ؛ وإن لم يُعرَف فاليومُ وحدَه."""
    window = academic_year_window(school, real_today)
    if not window:
        return real_today, real_today
    start, end = window
    # اليومُ الحقيقيّ يقع داخل مداه دائماً (إجازةُ الصيف بعد نهاية العام لا تُخرجه منه).
    return min(start, real_today), max(end, real_today)


def chosen_day(school: Any, real_today: dt.date, raw: str | None) -> dt.date:
    """اليومُ المطلوب `?date=YYYY-MM-DD` إن كان في المدى، وإلّا اليومُ الحقيقيّ."""
    if not raw:
        return real_today
    try:
        day = dt.date.fromisoformat(raw.strip())
    except ValueError:
        return real_today
    start, end = day_window(school, real_today)
    return day if start <= day <= end else real_today


def _link(path: str, day: dt.date, real_today: dt.date) -> str:
    """رابطُ اليوم؛ واليومُ الحقيقيّ بلا وسيط فيبقى العنوانُ الأصليُّ هو عنوانَه."""
    return path if day == real_today else f"{path}?{urlencode({PARAM: day.isoformat()})}"


def day_nav(school: Any, real_today: dt.date, day: dt.date, path: str) -> dict[str, Any]:
    """ما يحتاجه المحدِّدُ لرسم نفسه: روابطُ السابق والتالي واليوم (`None` عند حدّ المدى)، وحدّا حقل التاريخ."""
    start, end = day_window(school, real_today)
    one = dt.timedelta(days=1)
    return {
        "day": day,
        "is_today": day == real_today,
        "min": start.isoformat(),
        "max": end.isoformat(),
        "prev_url": _link(path, day - one, real_today) if day > start else None,
        "next_url": _link(path, day + one, real_today) if day < end else None,
        "today_url": path,
        "form_action": path,
    }
