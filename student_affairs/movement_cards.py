"""بطاقاتُ شاشة «تحركات الطلبة»: بطاقةٌ لكلّ وجهةٍ من الوجهات العشر (طلب المدير 2026-11-14).

دالّةٌ صرفةٌ بلا استعلام: تأخذ عدّاداتِ اليوم المجمَّعةَ من العرض وتبني بياناتِ البلاطات،
فلا يزيد العرضُ استدعاءً. والرمزان القديمان (`admin`, `other`) لا بطاقةَ لهما: تبقى صفوفُهما
في الجدول والمرشِّح فقط.
"""

from __future__ import annotations

from collections.abc import Mapping

from operations.models import ClassExit

#: أيقونةُ كلّ وجهة من سجلّ `core/icons.py`.
ICON_OF = {
    "clinic": "clinic",
    "restroom": "restroom",
    "sa_coord": "student_info",
    "wing_sup": "supervisors",
    "vice": "staff",
    "arts": "activities",
    "lab_cs": "elearning",
    "lab_sci": "departments",
    "pe": "attendance_register",
    "school": "sent_home",
}


def destination_cards(counts: Mapping[str, int], day_query: str) -> list[dict[str, str]]:
    """بطاقاتُ الوجهات العشر بعدّادِ اليوم لكلٍّ منها، والنقرُ يصفّي الجدولَ بوجهتها."""
    return [
        {
            "title": label,
            "desc": f"اليوم: {counts.get(code, 0)}",
            "icon": ICON_OF[code],
            "href": f"?{day_query}&destination={code}",
        }
        for code, label in ClassExit.CURRENT_DESTINATIONS
    ]
