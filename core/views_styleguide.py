"""دليلُ الهويّة — مرجعُ المطوّرين: أمثلةٌ توضيحيّةٌ بلا بياناتِ أشخاص.

صفحتان: مكوّناتُ الواجهة ولوحةُ الرموز (`styleguide/components/`)، والأيقونات
(`styleguide/icons/`). و`styleguide/` القديم تحويلٌ دائمٌ إلى الأولى في `urls.py`.
"""

from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.shortcuts import render

from core.icons import ICONS
from core.styleguide import colour_token_groups, icon_dictionary_groups


def developer_only(view):
    """دليلُ الهويّة لمطوّر المنصّة وحدَه (قرارُ المالك 2026-09-20): superuser أو مجموعة developers — كقائمة «أدوات المطوّر»."""

    @wraps(view)
    @login_required
    def wrapped(request, *args, **kwargs):
        user = request.user
        if not (user.is_superuser or user.groups.filter(name__iexact="developers").exists()):
            raise PermissionDenied
        return view(request, *args, **kwargs)

    return wrapped


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
