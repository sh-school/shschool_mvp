"""حدودُ «العرض بصفة دور» — الأدوارُ المعروضة، والمدد، وحدُّ التبديل، وما يُحجب أثناءه.

الأرقامُ من المواصفة: معاينةُ الدور افتراضُ 0301 (30 دقيقةً خاملةً وسقفُ ساعتين و30 تبديلاً في الساعة)، والحسابُ
المرتبطُ شروطُ 0104 (15 دقيقةً خاملةً وسقفُ ساعةٍ و10 تبديلاتٍ في الساعة). وتغييرُها قرارٌ يُراجَع لا ضبطٌ.
"""

from __future__ import annotations

from core.models.access import (
    TIER_1_LEADERSHIP,
    TIER_2_DEPUTIES,
    TIER_3_SUPERVISORS,
    TIER_4_STAFF,
    Role,
)

ROLE_IDLE_SECONDS = 30 * 60
ROLE_CAP_SECONDS = 2 * 60 * 60
ROLE_SWITCHES_PER_HOUR = 30

LINKED_IDLE_SECONDS = 15 * 60
LINKED_CAP_SECONDS = 60 * 60
LINKED_SWITCHES_PER_HOUR = 10

#: محاولاتُ إعادة التأكيد الخاطئة قبل إيقافها ربعَ ساعة.
REAUTH_FAILURES = 5
REAUTH_LOCK_SECONDS = 15 * 60

#: رمزُ العامل الثاني يصحّ ثلاثَ نوافذَ (`valid_window=1`، 90 ثانية)، فيُحجز طوالَها كي لا يُعاد — كالدخول تماماً.
TOTP_REPLAY_SECONDS = 90

#: أدوارُ الكادر المعروضة: مستوياتُ المدرسة الأربعة وحدَها. فلا مطوّرُ المنصّة (هو صاحبُ الميزة)، ولا الطالبُ ووليُّ
#: الأمر (قرارٌ أمنيٌّ من 0102 يعدّله المالك)، ولا «أخصائيّ (قديم)» (مسمًّى للتوافق الخلفيّ لا وظيفةٌ قائمة).
_STAFF = TIER_1_LEADERSHIP | TIER_2_DEPUTIES | TIER_3_SUPERVISORS | TIER_4_STAFF

#: بترتيب `Role.ROLES` (ترتيبُ الهيكل التنظيميّ) لا ترتيبَ مجموعةٍ لا يثبت.
VIEWABLE_ROLES: tuple[str, ...] = tuple(name for name, _ in Role.ROLES if name in _STAFF)
ROLE_LABELS: dict[str, str] = {name: str(label) for name, label in Role.ROLES}

#: أعمدةُ القائمة الأربعة. والمجموعتان الأخيرتان صريحتان، وما بقي من المستوى الرابع «الدعمُ والخدمات» —
#: فدورٌ يُضاف إلى المستويات يظهر في القائمة بلا تعديلٍ هنا.
CLASSROOM_ROLES = frozenset({"teacher", "ese_teacher", "teacher_assistant", "ese_assistant"})
ADMINISTRATIVE_ROLES = frozenset(
    {
        "admin",
        "secretary",
        "receptionist",
        "student_observer",
        "lab_technician",
        "storekeeper",
        "accountant",
        "canteen_supervisor",
        "services_worker",
        "messenger",
    }
)
_GROUP_TITLES = (
    ("leadership", "القيادةُ والإشراف"),
    ("classroom", "الكادرُ التدريسيّ"),
    ("support", "الدعمُ والخدمات"),
    ("administrative", "الإداريّون"),
)


def _group_of(role: str) -> str:
    if role in TIER_1_LEADERSHIP | TIER_2_DEPUTIES | TIER_3_SUPERVISORS:
        return "leadership"
    if role in CLASSROOM_ROLES:
        return "classroom"
    if role in ADMINISTRATIVE_ROLES:
        return "administrative"
    return "support"


def role_groups() -> list[dict[str, object]]:
    """الأدوارُ المعروضة في أعمدتها: `[{key, title, roles: [(name, label), …]}, …]`."""
    groups: list[dict[str, object]] = []
    for key, title in _GROUP_TITLES:
        roles = [(name, ROLE_LABELS[name]) for name in VIEWABLE_ROLES if _group_of(name) == key]
        groups.append({"key": key, "title": title, "roles": roles})
    return groups


def role_label(role: str) -> str:
    return ROLE_LABELS.get(role, role)


#: صفحاتُ الحساب نفسِه لا تُفتح أثناء العرض بصفة: كلمةُ المرور والثنائيّةُ وإعداداتُ الإشعارات ولوحةُ الإدارة.
#: وفي الحساب المرتبط هي شرطُ 0104 («يُحظر تغيير كلمة مرور المعلّم وبريده وهاتفه وعوامله وإعدادات الحساب
#: وفتح /admin/ بهويّته»)؛ وفي معاينة الدور حسابُ المطوّر يُدار بعد العودة إليه لا وهو مقنَّع.
#: ومعها شرطا 0104 قبل النشر: توكنُ API لا يُصدَر ولا يُجدَّد بهويّةٍ منتحَلة (فيعيش بعد العودة)، وإعادةُ كلمات
#: مرور الآخرين من الدعم التقنيّ لا تجري بصفةٍ معروضةٍ ولا بحسابٍ مرتبط.
ACCOUNT_PREFIXES = (
    "/admin/",
    "/auth/change-password/",
    "/auth/force_change_password/",
    "/auth/2fa/",
    "/notifications/settings/",
    "/api/v1/auth/token/",
    "/core/it-admin/password-reset/",
)

#: ما لا يُسجَّل صفحةً: ملفّاتٌ ثابتةٌ وفحوصُ صحّةٍ وعاملُ الخدمة.
UNLOGGED_PREFIXES = (
    "/static/",
    "/media/",
    "/health/",
    "/ready/",
    "/status/",
    "/sw.js",
    "/manifest.json",
    "/offline/",
    "/metrics",
)

PATH_LIMIT = 200


def clean_path(path: str) -> str:
    """المسارُ بلا استعلامٍ ولا محتوى (`request.path` لا `get_full_path`)، مقصوصاً — «بلا محتواها»."""
    return path[:PATH_LIMIT]
