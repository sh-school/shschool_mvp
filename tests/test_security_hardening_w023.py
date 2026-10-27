"""[W-20261027-023] سواط 017 توصية 3: لا |safe داخل سكربت، وPermissions-Policy، وCSP بلا سماحاتٍ ميّتة."""

import pathlib
import re

import pytest
from django.conf import settings
from django.urls import reverse

TEMPLATES = pathlib.Path("templates")
_SCRIPT_BODY = re.compile(r"<script\b(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.S | re.I)


def test_no_safe_filter_inside_inline_scripts():
    """`|safe` داخل `<script>` يحقن بياناً غيرَ مُهرَّبٍ في شيفرةٍ تُنفَّذ؛ البديلُ `json_script`."""
    hits = [
        f.as_posix()
        for f in TEMPLATES.rglob("*.html")
        for m in _SCRIPT_BODY.finditer(f.read_text(encoding="utf-8", errors="ignore"))
        if "|safe" in m.group(1)
    ]

    assert not hits, f"|safe داخل سكربت (استعمل json_script): {sorted(set(hits))}"


def test_policy_names_no_external_cdn_or_font_hosts():
    """صفرُ مرجعٍ لشبكات التوصيل وخطوط Google في القوالب والثابت، فسماحاتُها سطحٌ بلا فائدة."""
    policy = (
        getattr(settings, "CONTENT_SECURITY_POLICY", None)
        or settings.CONTENT_SECURITY_POLICY_REPORT_ONLY
    )
    directives = policy["DIRECTIVES"]
    external = {
        value
        for name in ("script-src", "style-src", "font-src")
        for value in directives[name]
        if isinstance(value, str) and value.startswith("http")
    }

    assert not external, f"سماحاتٌ خارجيّة: {sorted(external)}"


def test_production_connect_src_is_not_open_to_any_websocket_host():
    """`wss:` المجرَّدة تسمح بمقبسٍ إلى أيّ مضيف؛ والإنتاجُ يشتقّ المضيفاتِ من ALLOWED_HOSTS."""
    source = pathlib.Path("shschool/settings/production.py").read_text(encoding="utf-8")

    assert '"connect-src": [SELF, *(f"wss://{h}"' in source
    assert not re.search(r'"connect-src":\s*\[[^\]]*"wss?:"', source)


@pytest.mark.django_db
def test_every_response_carries_permissions_policy(client):
    resp = client.get(reverse("login"))

    policy = resp.headers.get("Permissions-Policy", "")
    for feature in ("camera", "microphone", "geolocation", "payment", "usb"):
        assert f"{feature}=()" in policy, policy


@pytest.mark.django_db
def test_a_view_that_sets_its_own_permissions_policy_is_left_alone(rf):
    from django.http import HttpResponse

    from core.middleware import PermissionsPolicyMiddleware

    def view(request):
        response = HttpResponse("ok")
        response["Permissions-Policy"] = "camera=(self)"
        return response

    resp = PermissionsPolicyMiddleware(view)(rf.get("/"))

    assert resp["Permissions-Policy"] == "camera=(self)"
