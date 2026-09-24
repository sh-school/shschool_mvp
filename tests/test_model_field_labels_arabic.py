"""[UX] كلُّ حقلٍ في نماذج المنصّة يحمل اسماً عربيّاً (OWN-19).

الحقلُ بلا `verbose_name` يأخذ اسمَه البرمجيّ: `is_active` ← «is active»، فيظهر
في لوحة الإدارة عنوانَ عمودٍ «IS ACTIVE» ومرشِّحاً «حسب is active»، وفي النماذج
ورسائل التحقّق «date joined: هذا الحقل مطلوب». كانت 470 حقلاً على هذه الحال في
سبعة عشر تطبيقاً (2026-09-24) — وأغلبُ الحقول حولها عربيّةٌ، فهو سهوٌ لا اصطلاح.

والاسمُ في النموذج لا في لوحة الإدارة: منه تقرأ اللوحةُ والنماذجُ ورسائلُ الخطأ
معاً، فيُكتب مرّةً واحدة. ومعه الجمعُ: نموذجٌ بلا `verbose_name_plural` يُجمع
بإلصاق «s» اللاتينيّة — فكانت «ملف شخصيs» عنواناً في الفهرس.

`id` مستثنى: «ID» اسمُ Django للمفتاح، ولا يُعرض إلّا نادراً.
"""

import re

from django.apps import apps
from django.conf import settings
from django.utils.translation import override

_ARABIC = re.compile(r"[؀-ۿ]")
_LATIN_PLURAL = re.compile(r"[؀-ۿ]s$")


def _own_models():
    """نماذجُ تطبيقات المنصّة وحدَها — لا Django ولا الحزم الخارجيّة."""
    base = str(settings.BASE_DIR)
    own = {
        cfg.label
        for cfg in apps.get_app_configs()
        if str(cfg.path).startswith(base) and "site-packages" not in str(cfg.path)
    }
    return [m for m in apps.get_models() if m._meta.app_label in own]


def test_the_platform_apps_are_found():
    """حارسٌ لا يجد نموذجاً ينجح صامتاً — فليُثبت أنّه يرى المنصّة."""
    labels = {m._meta.label for m in _own_models()}

    assert {"core.CustomUser", "operations.StudentAttendance"} <= labels


def test_every_platform_field_has_an_arabic_label():
    missing = []
    with override("ar"):
        for model in _own_models():
            for field in model._meta.get_fields():
                if field.auto_created and not field.concrete:
                    continue  # العلاقاتُ العكسيّة لا تُعرض عموداً ولا حقلاً
                if field.name == "id":
                    continue
                if not _ARABIC.search(str(field.verbose_name)):
                    missing.append(f"{model._meta.label}.{field.name}")

    assert not missing, f"حقولٌ بلا اسمٍ عربيّ ({len(missing)}) — أضِف لها verbose_name: {missing}"


def test_no_model_is_pluralised_with_a_latin_s():
    broken = [
        f"{m._meta.label}: {m._meta.verbose_name_plural}"
        for m in _own_models()
        if _LATIN_PLURAL.search(str(m._meta.verbose_name_plural))
    ]

    assert not broken, f"أضِف verbose_name_plural عربيّاً: {broken}"
