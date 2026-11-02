"""دليلُ الهويّة — مرجعُ المطوّرين: أمثلةٌ توضيحيّةٌ بلا بياناتِ أشخاص.

ثلاثُ صفحات: مكوّناتُ الواجهة ولوحةُ الرموز (`styleguide/components/`)، والأيقونات
(`styleguide/icons/`)، وأنماطُ تخطيط الصفحات (`styleguide/layouts/`، قرار D-16). و`styleguide/` القديم تحويلٌ دائمٌ إلى الأولى في `urls.py`.
"""

from django.shortcuts import render

from core.developer_access import developer_only
from core.icons import ICONS
from core.school_logo import SIZES_PX
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
            "grade_numbers": [row["grade"] for row in GRADE_EXAMPLE_ROWS],
            "grade_rows": GRADE_EXAMPLE_ROWS,
            # خياراتُ أمثلة القسم 12 (field · filter_bar) — توضيحيّةٌ لا من قاعدة البيانات.
            "sg_grades": [("7", "السابع"), ("8", "الثامن"), ("9", "التاسع")],
            "sg_types": [("a", "نشاطٌ ثقافيّ"), ("b", "نشاطٌ رياضيّ"), ("c", "نشاطٌ علميّ")],
        },
    )


#: صفوفٌ توضيحيّةٌ لمثال ألوان الصفوف (7/1 … 12/4) — أسماءٌ وهميّةٌ لا طلبةٌ حقيقيّون.
GRADE_EXAMPLE_ROWS = (
    {"grade": "7", "section": "1", "name": "طالبٌ نموذجيٌّ أوّل", "absent": 1},
    {"grade": "8", "section": "2", "name": "طالبٌ نموذجيٌّ ثانٍ", "absent": 0},
    {"grade": "9", "section": "3", "name": "طالبٌ نموذجيٌّ ثالث", "absent": 4},
    {"grade": "10", "section": "1", "name": "طالبٌ نموذجيٌّ رابع", "absent": 2},
    {"grade": "11", "section": "2", "name": "طالبٌ نموذجيٌّ خامس", "absent": 0},
    {"grade": "12", "section": "4", "name": "طالبٌ نموذجيٌّ سادس", "absent": 3},
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
        {
            "icon_groups": groups,
            "icon_count": len(ICONS),
            "icon_tones": ICON_TONES,
            "logo_sizes": tuple(SIZES_PX.items()),
        },
    )


@developer_only
def ui_layouts(request):
    """أنماطُ التخطيط السبعة — المواصفاتُ في docs/design/page_layouts.md، والأصنافُ في LAY-03."""
    return render(request, "styleguide/layouts.html", {"icon_count": len(ICONS)})
