"""قائمةُ الإدارة الأفقيّة تغطّي كلَّ نموذجٍ مسجَّلٍ مرّةً واحدة ولا تذكر ما لا وجودَ له."""

import collections

from django.contrib import admin

from roadmap.admin_menu import GROUPS, LABELS, build_menu, mapped_keys


def _registered() -> set[str]:
    return {f"{m._meta.app_label}.{m.__name__}" for m in admin.site._registry}


def test_every_registered_model_is_in_exactly_one_group():
    keys = mapped_keys()
    duplicates = [k for k, n in collections.Counter(keys).items() if n > 1]
    missing = sorted(_registered() - set(keys))

    assert not duplicates, f"نموذجٌ في أكثر من قسم: {duplicates}"
    assert not missing, f"نماذجُ مسجَّلةٌ بلا قسم (تظهر تحت «أخرى»): {missing}"


def test_no_group_names_a_model_that_does_not_exist():
    assert not sorted(set(mapped_keys()) - _registered())


def test_labels_only_rename_mapped_models():
    assert set(LABELS) <= set(mapped_keys())


def test_the_menu_keeps_the_platform_section_order_and_hides_nothing():
    apps = [
        {"app_label": "clinic", "models": [{"object_name": "ClinicVisit", "name": "زيارات العيادة", "admin_url": "/admin/clinic/clinicvisit/"}]},
        {"app_label": "core", "models": [{"object_name": "StudentEnrollment", "name": "تسجيل طالبs", "admin_url": "/admin/core/studentenrollment/"}]},
        {"app_label": "zzz", "models": [{"object_name": "Unknown", "name": "مجهول", "admin_url": "/admin/zzz/unknown/"}]},
    ]

    menu = build_menu(apps, "/admin/clinic/clinicvisit/")

    assert [g["label"] for g in menu] == ["شؤون الطلاب", "الخدمات", "أخرى"]
    assert menu[0]["sections"][0]["items"][0]["name"] == "تسجيلات الطلاب"
    assert menu[1]["current"] is True and menu[0]["current"] is False
    assert menu[2]["sections"][0]["items"][0]["name"] == "مجهول"
    assert [g[0] for g in GROUPS][:3] == ["الشؤون الأكاديمية", "شؤون الموظفين", "شؤون الطلاب"]
