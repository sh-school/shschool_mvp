"""دليلُ الهويّة — مرجعُ المطوّرين: أمثلةٌ توضيحيّةٌ بلا بياناتِ أشخاص.

ثلاثُ صفحات: مكوّناتُ الواجهة ولوحةُ الرموز (`styleguide/components/`)، والأيقونات
(`styleguide/icons/`)، وأنماطُ تخطيط الصفحات (`styleguide/layouts/`، قرار D-16). و`styleguide/` القديم تحويلٌ دائمٌ إلى الأولى في `urls.py`.
"""

from django.shortcuts import render

from core.developer_access import developer_only
from core.icons import ICONS
from core.styleguide import (
    breakpoints,
    colour_token_groups,
    icon_dictionary_groups,
    scale_tokens,
)


@developer_only
def ui_components(request):
    return render(
        request,
        "styleguide/components.html",
        {
            "swatch_groups": colour_token_groups(),
            "scales": scale_tokens(),
            "breakpoints": breakpoints(),
            "icon_count": len(ICONS),
            # خياراتُ أمثلة القسم 12 (field · filter_bar) — توضيحيّةٌ لا من قاعدة البيانات.
            "sg_grades": [("7", "السابع"), ("8", "الثامن"), ("9", "التاسع")],
            "sg_types": [("a", "نشاطٌ ثقافيّ"), ("b", "نشاطٌ رياضيّ"), ("c", "نشاطٌ علميّ")],
        },
    )


#: مجموعةٌ أيقوناتُها أكثرُ من هذا تأخذ سطرَ `card-flow` كلَّه، وما دونها عمودين —
#: فتتجاور المجموعتان الصغيرتان بصفوفٍ متقاربة ولا تُترك إحداهما بسطرٍ فارغٍ نصفُه.
ICON_GROUP_WIDE_MAX = 12

#: ألوانُ الأيقونة الدلاليّة (10-foundation.css) — كلٌّ بمعنًى من القاموس يناسبه.
ICON_TONES = (
    ("maroon", "school_building"),
    ("success", "status_success"),
    ("danger", "delete"),
    ("warning", "status_warning"),
    ("info", "status_info"),
    ("muted", "time"),
)


@developer_only
def icon_preview(request):
    groups = icon_dictionary_groups()
    for group in groups:
        group["span"] = "wide" if len(group["icons"]) <= ICON_GROUP_WIDE_MAX else "full"
    return render(
        request,
        "styleguide/icon_preview.html",
        {"icon_groups": groups, "icon_count": len(ICONS), "icon_tones": ICON_TONES},
    )


@developer_only
def ui_layouts(request):
    """أنماطُ التخطيط السبعة — المواصفاتُ في docs/design/page_layouts.md، والأصنافُ في LAY-03."""
    return render(request, "styleguide/layouts.html", {"icon_count": len(ICONS)})
