"""صلاحيّاتُ مدير المدرسة داخل `/admin/` — `is_staff` بصلاحياتٍ صريحةً لا `is_superuser`.

قرارُ المالك (2026-09-22): «ليس كلُّ شيءٍ متاحاً للمدير في صفحات الإدارة». كان
حسابُه `is_superuser` مباشرةً (`full_seed.py`)، وهو يتجاوز نظامَ الصلاحيّات
بالكامل بلا استثناء — كلَّ حارسٍ بُني في `services.py` والتحقّقِ والتدقيق، وحتى
حصرَ `roadmap/` بالمطوّر (`is_platform_developer` تُرجع True لأيّ superuser).

فالمديرُ الآن `is_staff` عضوٌ في مجموعة Django باسم `PRINCIPAL_GROUP_NAME`،
صلاحيّاتُها صريحةٌ لا تخمينيّة: `sync_principal_admin_group()` هي مصدرُ الحقيقة
الوحيد، تُنشئ المجموعةَ إن غابت وتُطابق صلاحيّاتِها مع القوائم أدناه بالضبط —
تُضيف الناقص وتحذف الزائد، فلا يبقى أثرٌ لصلاحيّةٍ سُحبت من القائمة.

## الفئات

- **`FULL_ACCESS_MODELS`**: تعديلٌ كامل (عرض/إضافة/تغيير/حذف) — إعدادٌ مدرسيٌّ
  لا شاشةَ مخصَّصةً له في المنصّة (المدرسة، السنة والفصل، التقويم، النطاقات
  الزمنيّة، الأجنحة، الأقسام، الشُّعب، والنقل).
- **`VIEW_ONLY_MODELS`**: قراءةٌ فقط — تدقيقٌ واطمئنانٌ لا تعديلٌ خام (سجلُّ
  التدقيق نفسُه محميٌّ من الحذف/التعديل حتى عن `superuser`، ومحاولاتُ الدخول،
  وسجلّاتُ الإشعارات الفاشلة، والرموزُ المُبطَلة، وسجلُّ الاستيراد).
- **الحسابات (`CustomUser`/`Membership`/`Role`)**: قراءةٌ فقط عمداً، لا تعديل
  ولا حذف — منحُ `change` على `CustomUser` يسمح نظريّاً بإعادة تعيين
  `is_superuser` يدويّاً فيُبطل هذا الحصرَ كلَّه؛ ولتغيير كلمة المرور مسارٌ
  مخصَّصٌ في المنصّة (`/auth/`) لا `/admin/`.
- **ما ليس في أيّ قائمة (الباقي، نحو 75 نموذجاً)**: بلا صلاحيّةٍ إطلاقاً — لها
  مسارٌ خدميٌّ في المنصّة بتحقّقٍ وتدقيقٍ خاصَّين (الدرجات والتقييمات والسلوك
  والعيادة وتقييم الأداء وكنترول الاختبارات والجدول والحضور والمكتبة وشؤون
  الموظّفين والطلاب)، أو مخصَّصةٌ للمطوّر وحده (`developer_feedback`،
  `roadmap` — تسقط تلقائيّاً حين يفقد المديرُ `is_superuser`).
"""

from __future__ import annotations

from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

PRINCIPAL_GROUP_NAME = "مدير المدرسة — لوحة الإدارة التقنية"

#: (app_label, model_name) — model_name بأحرفٍ صغيرة كما يسجّله Django.
FULL_ACCESS_MODELS: frozenset[tuple[str, str]] = frozenset(
    {
        ("core", "school"),
        ("core", "academicyear"),
        ("core", "semester"),
        ("core", "calendarevent"),
        ("core", "timeband"),
        ("core", "wing"),
        ("core", "wingcoverage"),
        ("core", "department"),
        ("core", "classgroup"),
        ("transport", "busroute"),
        ("transport", "schoolbus"),
    }
)

VIEW_ONLY_MODELS: frozenset[tuple[str, str]] = frozenset(
    {
        ("core", "auditlog"),
        ("core", "customuser"),
        ("core", "membership"),
        ("core", "role"),
        ("axes", "accessattempt"),
        ("axes", "accessfailurelog"),
        ("axes", "accesslog"),
        ("notifications", "deadlettermessage"),
        ("notifications", "notificationlog"),
        ("token_blacklist", "blacklistedtoken"),
        ("token_blacklist", "outstandingtoken"),
        ("staging", "importlog"),
    }
)

_ACTIONS_FULL = ("view", "add", "change", "delete")
_ACTIONS_VIEW = ("view",)


def _permissions_for(models: frozenset[tuple[str, str]], actions: tuple[str, ...]) -> set[int]:
    ids: set[int] = set()
    for app_label, model in models:
        try:
            ct = ContentType.objects.get(app_label=app_label, model=model)
        except ContentType.DoesNotExist:
            continue  # النموذجُ لم يُهاجَر بعدُ في هذه القاعدة — لا يُوقف المزامنة.
        for action in actions:
            perm = Permission.objects.filter(content_type=ct, codename=f"{action}_{model}").first()
            if perm:
                ids.add(perm.id)
    return ids


def sync_principal_admin_group() -> Group:
    """يُنشئ المجموعةَ إن غابت ويُطابق صلاحيّاتِها مع القوائم أعلاه بالضبط — مصدرُ
    الحقيقة الوحيد؛ استدعاؤها مرّةً أخرى بعد تعديل القوائم يُصلح الانجراف."""
    group, _ = Group.objects.get_or_create(name=PRINCIPAL_GROUP_NAME)
    wanted = _permissions_for(FULL_ACCESS_MODELS, _ACTIONS_FULL) | _permissions_for(
        VIEW_ONLY_MODELS, _ACTIONS_VIEW
    )
    current = set(group.permissions.values_list("id", flat=True))
    if wanted != current:
        group.permissions.set(wanted)
    return group
