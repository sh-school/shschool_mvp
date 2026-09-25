"""قائمةُ الإدارة الأفقيّة تغطّي كلَّ نموذجٍ مسجَّلٍ مرّةً واحدة ولا تذكر ما لا وجودَ له."""

import collections
import warnings

from django.contrib import admin

from core.admin_menu import GROUPS, LABELS, build_menu, mapped_keys


def _registered() -> set[str]:
    return {f"{m._meta.app_label}.{m.__name__}" for m in admin.site._registry}


def test_no_model_is_in_two_groups():
    keys = mapped_keys()
    duplicates = [k for k, n in collections.Counter(keys).items() if n > 1]

    assert not duplicates, f"نموذجٌ في أكثر من قسم: {duplicates}"


def test_an_unmapped_model_is_a_warning_not_a_failure():
    """نموذجٌ مسجَّلٌ بلا قسمٍ يظهر تحت «أخرى» فلا يسقط شيء — فهو تنبيهٌ لا عطل (OWN-24).

    كان يُسقط البناءَ فيُسقط طلبَ كلِّ جلسةٍ تسجّل نموذجاً جديداً في الإدارة وهي لا تمسّ القائمة.
    يُكتب التنبيهُ ليُرى في مخرجات الاختبار، ويُصنَّف النموذجُ في `core/admin_menu.py:GROUPS`.
    """
    missing = sorted(_registered() - set(mapped_keys()))
    if missing:
        warnings.warn(
            f"نماذجُ مسجَّلةٌ بلا قسمٍ في core/admin_menu.py (تظهر تحت «أخرى»): {missing}",
            stacklevel=1,
        )


def test_no_group_names_a_model_that_does_not_exist():
    assert not sorted(set(mapped_keys()) - _registered())


def test_labels_only_rename_mapped_models():
    assert set(LABELS) <= set(mapped_keys())


def test_the_menu_keeps_the_platform_section_order_and_hides_nothing():
    apps = [
        {
            "app_label": "clinic",
            "models": [
                {
                    "object_name": "ClinicVisit",
                    "name": "زيارات العيادة",
                    "admin_url": "/admin/clinic/clinicvisit/",
                }
            ],
        },
        {
            "app_label": "core",
            "models": [
                {
                    "object_name": "StudentEnrollment",
                    "name": "تسجيل طالبs",
                    "admin_url": "/admin/core/studentenrollment/",
                }
            ],
        },
        {
            "app_label": "zzz",
            "models": [
                {"object_name": "Unknown", "name": "مجهول", "admin_url": "/admin/zzz/unknown/"}
            ],
        },
    ]

    menu = build_menu(apps, "/admin/clinic/clinicvisit/")

    assert [g["label"] for g in menu] == ["شؤون الطلاب", "الخدمات", "أخرى"]
    assert menu[0]["sections"][0]["items"][0]["name"] == "تسجيلات الطلاب"
    assert menu[1]["current"] is True and menu[0]["current"] is False
    assert menu[2]["sections"][0]["items"][0]["name"] == "مجهول"
    assert [g[0] for g in GROUPS][:3] == ["الشؤون الأكاديمية", "شؤون الموظفين", "شؤون الطلاب"]


def test_every_admin_list_shows_25_rows():
    """جانغو يعرض 100 صفٍّ؛ الإدارةُ لا تُمرَّر فيها الصفحةُ فكلُّ قائمةٍ 25 — ولا نموذجَ يشذّ."""
    off = {
        f"{m._meta.label}: {a.list_per_page}"
        for m, a in admin.site._registry.items()
        if a.list_per_page != 25
    }
    assert not off, f"قوائمُ بغير 25 صفّاً: {sorted(off)}"


def test_third_party_app_names_are_arabic_in_the_admin_template():
    """AXES وToken Blacklist عربيّةٌ في app_list.html وحدَه — الحزمتان نفسُهما لم تُعدَّلا."""
    from core.admin_menu import APP_LABELS
    from core.templatetags.admin_menu import app_label

    assert app_label("axes", "AXES") == APP_LABELS["axes"]
    assert app_label("token_blacklist", "Token Blacklist") == APP_LABELS["token_blacklist"]
    assert app_label("unknown_app", "Unknown") == "Unknown"


def test_search_index_covers_every_link_the_menu_shows():
    """فهرسُ البحث يطابق عدد الروابط في القائمة نفسِها — لا نقصان ولا تكرار."""
    from django.contrib import admin

    from core.admin_menu import build_menu, search_index

    apps = [
        {
            "app_label": m._meta.app_label,
            "models": [
                {"object_name": m.__name__, "name": m._meta.verbose_name, "admin_url": "/x/"}
            ],
        }
        for m in admin.site._registry
    ]
    menu = build_menu(apps, "/admin/")
    idx = search_index(menu)
    assert len(idx) == sum(len(s["items"]) for g in menu for s in g["sections"])
    assert all(isinstance(row["name"], str) and isinstance(row["group"], str) for row in idx)
