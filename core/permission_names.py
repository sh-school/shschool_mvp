"""أسماءُ الصلاحيات عربيّةٌ في الإدارة — «إضافة مستخدم» لا «Can add مستخدم».

جانغو ينشئ صلاحيّاتِ كلِّ نموذجٍ الأربعَ (إضافة، تعديل، حذف، عرض) باسمٍ إنجليزيٍّ ثابت — `"Can %s %s"` —
وبالاسم الخام للنموذج `verbose_name_raw` بلا ترجمة، فكانت صفحةُ المجموعة والمستخدم تعرض 560 صلاحيّةً
كلُّها نصفُها إنجليزيّ («Can add إسناد تحضير مقرّر»)، وأسماءُ نماذج جانغو نفسِه («Can add group») إنجليزيّةٌ كلُّها.

والاسمُ عرضٌ لا مفتاح: كلُّ بحثٍ في الشيفرة بـ`codename` (`core/admin_access.py`)، فإعادةُ التسمية آمنةٌ.

يجري ذلك في `post_migrate` لأنّ جانغو ينشئ الصلاحيّاتِ هناك (`create_permissions`) وهو مسجَّلٌ قبلنا في
`INSTALLED_APPS`، فيصل استقبالُنا لكلّ تطبيقٍ بعد إنشاء صلاحيّاته. ولا هجرةَ بياناتٍ: كلُّ `migrate` (ولو بلا هجرةٍ
جديدة، كما في preDeploy) يُطبّقه، فتُعرَّب الصلاحيّاتُ القائمةُ والجديدةُ معاً، والتطبيقُ مرّةً ثانيةً لا يغيّر شيئاً.
"""

from __future__ import annotations

import re
from typing import Any

from django.apps import apps as global_apps
from django.contrib.auth import get_permission_codename
from django.contrib.auth.models import Permission
from django.db import DEFAULT_DB_ALIAS
from django.utils.translation import override

#: أفعالُ الصلاحيّات الأربعة التي ينشئها جانغو لكلّ نموذج (`Meta.default_permissions`).
ACTIONS = {"add": "إضافة", "change": "تعديل", "delete": "حذف", "view": "عرض"}


def permission_name(action: str, verbose_name: object) -> str:
    """«إضافة مستخدم» — الفعلُ عربيّ والنموذجُ باسمه المترجَم حيث لجانغو ترجمةٌ عربيّة."""
    return f"{ACTIONS[action]} {verbose_name}"


def arabize_permission_names(
    sender: Any = None,
    using: str = DEFAULT_DB_ALIAS,
    **kwargs: Any,
) -> None:
    """يُعيد تسميةَ صلاحيّات نماذج التطبيق المُرسِل (`sender`) — بـ`post_migrate`."""
    label = getattr(sender, "label", None)
    if label is None:
        return
    try:
        models = global_apps.get_app_config(label).get_models()
    except LookupError:
        return

    from django.contrib.contenttypes.models import ContentType

    wanted: dict[tuple[int, str], str] = {}
    with override("ar"):
        for model in models:
            opts = model._meta
            content_type = ContentType.objects.db_manager(using).get_for_model(
                model, for_concrete_model=False
            )
            for action in opts.default_permissions:
                if action in ACTIONS:
                    codename = get_permission_codename(action, opts)
                    wanted[(content_type.pk, codename)] = permission_name(action, opts.verbose_name)
    changed = []
    for permission in (
        Permission.objects.using(using)
        .filter(content_type__app_label=label)
        .select_related("content_type")
    ):
        name = wanted.get((permission.content_type_id, permission.codename))
        if name is None and permission.content_type.model_class() is None:
            name = _rename_orphan(permission.name)
        if name is not None and permission.name != name:
            permission.name = name
            changed.append(permission)
    if changed:
        Permission.objects.using(using).bulk_update(changed, ["name"])


_ENGLISH = re.compile(r"^Can (add|change|delete|view) (.+)$")


def _rename_orphan(current: str) -> str | None:
    """صلاحيّةُ نموذجٍ حُذف (نوعُ محتواها باقٍ) لا يُعرف نموذجُها: يُعرَّب الفعلُ وحدَه ويبقى ما بعده.

    وحدَها: صلاحيّةٌ مخصَّصةٌ (`Meta.permissions`) لنموذجٍ قائمٍ يُبقى اسمُها كما كتبه صاحبُها.

    تبقى في جدول الصلاحيّات بعد حذف النموذج وتظهر في صفحة المجموعة كسائر الصلاحيّات. وحذفُها تنظيفُ بياناتٍ مستقلٌّ
    لا يخصّ التعريب: حُذفت اليتيماتُ المعروفةُ (`StaffEvaluation`، `TeacherSubjectQualification`) بهجرة
    `core/0072`، ويبقى هذا احتياطاً لما سيُحذف من النماذج قبل أن يُنظَّف.
    """
    match = _ENGLISH.match(current)
    return permission_name(match.group(1), match.group(2)) if match else None
