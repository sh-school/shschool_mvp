"""[SECURITY] لا صفحةَ بلا وسائط تردّ مطوّرَ المنصّة بـ403 (قرار المالك D-118م).

ملاحظةُ المالك بعد معاينة 8500: «ما زالت صفحةٌ غيرُ مفتوحةٍ للمطوّر». فالمسحُ يمرّ بحسابٍ بدور
platform_developer وحدَه (لا superuser) على كلّ مسارٍ لا يحمل وسيطاً ويجمع ما يردّه 403؛ وما يبقى
قائمةٌ صريحةٌ معلَّلة، فصفحةٌ جديدةٌ تحجبه تُسقط الاختبارَ بدل أن تمرّ صامتة.
"""

import re

import pytest
from django.urls import URLPattern, URLResolver, get_resolver

from core.models import CustomUser
from core.models.access import Membership, Role

pytestmark = pytest.mark.django_db

#: مسارات تردّ GET بـ403 لا بدورٍ بل بحارس طريقةٍ أو هويّة، ومعها علّتُها.
EXPECTED_403 = {
    "/notifications/settings/": "POST فقط؛ GET يُردّ بـ403 لأيّ دور (حارسُ طريقة)",
    "/parents/admin/links/add/": "POST فقط؛ GET يُردّ بـ403 لأيّ دور (حارسُ طريقة)",
    "/parents/consent/": "موافقةُ وليّ الأمر الشخصيّة على بيانات أبنائه — هويّةٌ لا دور (PDPPL)",
    "/teacher/director-live/": "استطلاعُ لوحة المدير الحيّ (W-20261008-004، D-249م 9.3) — للمدير ونائبيه وحدَهم: المطوّر لا يدير يومَ المدرسة ولا يرصد",
    "/wings/live/": "استطلاعُ لوحة مشرف الجناح وبديله الحيّ (W-20261008-007، D-249م 9.3) — لمن يحمل جناحاً أو بديلِه المكلَّف: المطوّر لا يرصد ولا يحمل جناحاً (D-128م)",
    "/wings/record/": "رصدُ يوم الجناح — D-128م: المطوّر لا يُدخل ولا يعتمد رصدَ غياب الطلبة",
    "/wings/excuses/requests/": "طلباتُ أعذار الغياب واعتمادُها — D-128م (قدرة رصد الغياب)",
    "/student-affairs/tardiness/record/": "تسجيلُ التأخّر الصباحيّ — D-128م يشمله (قرارُ المالك)",
    "/student-affairs/tardiness/search/": "بحثُ الطلبة لرصد التأخّر الصباحيّ — D-128م يشمله (قرارُ المالك)",
    "/wings/absence-notices/": "إصدارُ إخطار وليّ الأمر بالغياب لحاصر الغياب العامّ وحدَه (D-246م) — D-128م: المطوّر لا يُدخل ولا يعتمد رصدَ الغياب ولا يُخطر أولياء الأمور",
    "/wings/ministry/": "ملخّصُ غياب الحصّتين للرفع — بقدرة رصد اليوم نفسِها (D-128م: المطوّر لا يُدخل ولا يعتمد رصدَ الغياب)",
    "/wings/students/find/": "بحثُ الطلبة لرصد الغياب — D-128م (قدرة رصد الغياب)",
    "/api/v1/erasure/request/": "طلبُ محو بيانات الطالب ممنوعٌ على المطوّر — قرارُ المالك على #781",
}

#: مساراتٌ لا تُمسح: الأدمن (حاجزُه is_staff)، والخروج (يُنهي الجلسة)، والثابت.
SKIPPED_PREFIXES = ("admin/", "auth/logout", "static")


def _routes(patterns, prefix=""):
    for pattern in patterns:
        route = prefix + str(pattern.pattern)
        if isinstance(pattern, URLResolver):
            yield from _routes(pattern.url_patterns, route)
        elif isinstance(pattern, URLPattern):
            yield route


def test_no_parameterless_page_refuses_the_developer(client, school):
    user = CustomUser.objects.create(
        must_change_password=False, national_id="28700000777", full_name="مطوّر المنصّة"
    )
    user.set_password("Aa!23456789")
    user.save()
    role, _ = Role.objects.get_or_create(school=school, name="platform_developer")
    Membership.objects.create(user=user, school=school, role=role)
    client.force_login(user)

    refused = set()
    for route in _routes(get_resolver().url_patterns):
        if re.search(r"[<(\[]", route) or route.startswith(SKIPPED_PREFIXES):
            continue
        path = "/" + route.lstrip("^").rstrip("$")
        try:
            status = client.get(path).status_code
        except Exception:  # noqa: BLE001 — مساراتُ API التي لا تُعرض بلا وسائط لا شأنَ لها بالصلاحيّة
            continue
        if status == 403:
            refused.add(path)

    assert refused == set(EXPECTED_403), (
        f"صفحاتٌ جديدةٌ تردّ المطوّرَ: {sorted(refused - set(EXPECTED_403))}؛ "
        f"وصفحاتٌ كانت مستثناةً فُتحت: {sorted(set(EXPECTED_403) - refused)}"
    )
