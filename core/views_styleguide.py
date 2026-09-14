"""دليلُ الهويّة — مرجعُ المطوّرين: أمثلةٌ توضيحيّةٌ بلا بياناتِ أشخاص.

صفحتان: مكوّناتُ الواجهة ولوحةُ الرموز (`styleguide/components/`)، والأيقونات
(`styleguide/icons/`). و`styleguide/` القديم تحويلٌ دائمٌ إلى الأولى في `urls.py`.
"""

from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from core.styleguide import colour_token_groups, sprite_icons


@login_required
def ui_components(request):
    return render(
        request,
        "styleguide/components.html",
        {"swatch_groups": colour_token_groups(), "icon_count": len(sprite_icons())},
    )


@login_required
def icon_preview(request):
    return render(request, "styleguide/icon_preview.html", {"icons": sprite_icons()})
