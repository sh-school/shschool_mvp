"""دليلُ الهويّة — مرجعُ المطوّرين: أمثلةٌ توضيحيّةٌ بلا بياناتِ أشخاص.

ثلاثُ صفحات: مكوّناتُ الواجهة ولوحةُ الرموز (`styleguide/components/`)، والأيقونات
(`styleguide/icons/`)، وأنماطُ تخطيط الصفحات (`styleguide/layouts/`، قرار D-16). و`styleguide/` القديم تحويلٌ دائمٌ إلى الأولى في `urls.py`.
"""

from django.shortcuts import render

from core.developer_access import developer_only
from core.icons import ICONS
from core.styleguide import colour_token_groups, icon_dictionary_groups


@developer_only
def ui_components(request):
    return render(
        request,
        "styleguide/components.html",
        {
            "swatch_groups": colour_token_groups(),
            "icon_count": len(ICONS),
            # خياراتُ أمثلة القسم 12 (field · filter_bar) — توضيحيّةٌ لا من قاعدة البيانات.
            "sg_grades": [("7", "السابع"), ("8", "الثامن"), ("9", "التاسع")],
            "sg_types": [("a", "نشاطٌ ثقافيّ"), ("b", "نشاطٌ رياضيّ"), ("c", "نشاطٌ علميّ")],
        },
    )


@developer_only
def icon_preview(request):
    return render(
        request,
        "styleguide/icon_preview.html",
        {"icon_groups": icon_dictionary_groups(), "icon_count": len(ICONS)},
    )


@developer_only
def ui_layouts(request):
    """أنماطُ التخطيط السبعة — المواصفاتُ في docs/design/page_layouts.md، والأصنافُ في LAY-03."""
    return render(request, "styleguide/layouts.html")
