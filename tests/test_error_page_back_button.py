"""زرّ «الرجوع للخلف» في صفحات الأخطاء يعمل تحت CSP (بلاغ المالك W-20261002-013).

كان `href="javascript:history.back()"` فتحجبه سياسةُ CSP (لا `unsafe-inline`)، فلا يفعل
شيئاً على 403 (شوهد على /analytics/ في الإنتاج). الآن رابطٌ حقيقيٌّ إلى الرئيسيّة يعمل بلا JS،
وسكربتٌ بنونس يرقّيه إلى الرجوع الفعليّ حين يوجد مرجعٌ من المنصّة نفسها.
"""

import re

import pytest
from django.contrib.auth.models import AnonymousUser
from django.template.loader import render_to_string
from django.test import RequestFactory

pytestmark = pytest.mark.django_db

PAGES = ["403.html", "404.html", "500.html", "errors/forbidden.html"]


def _render(template: str) -> str:
    request = RequestFactory().get("/analytics/")
    request.user = AnonymousUser()
    request.csp_nonce = "test-nonce"
    return render_to_string(template, {"message": "ممنوع"}, request=request)


def test_no_template_uses_a_javascript_url():
    """حارسٌ شاملٌ: رابطُ `href="javascript:` تحجبه CSP في الإنتاج في أيّ قالب، لا صفحاتِ الأخطاء وحدَها."""
    from pathlib import Path

    pattern = re.compile(r"""href\s*=\s*["']\s*javascript:""", re.I)
    offenders = [
        str(path)
        for path in Path("templates").rglob("*.html")
        if pattern.search(path.read_text(encoding="utf-8", errors="ignore"))
    ]
    assert not offenders, (
        "روابطُ javascript: تحجبها CSP — استعمل data-action أو سكربتاً بنونس:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("template", PAGES)
def test_the_back_button_is_not_a_javascript_url(template):
    html = _render(template)
    assert "javascript:" not in html, f"{template}: رابطُ javascript: تحجبه CSP"


@pytest.mark.parametrize("template", PAGES)
def test_the_back_button_falls_back_to_a_real_home_link(template):
    html = _render(template)
    match = re.search(r"<a [^>]*data-error-back[^>]*>", html)
    assert match, f"{template}: لا زرَّ رجوعٍ بسمة data-error-back"
    assert 'href="/dashboard/"' in match.group(0), f"{template}: لا احتياطَ إلى الرئيسيّة بلا JS"


@pytest.mark.parametrize("template", PAGES)
def test_the_upgrade_script_carries_the_csp_nonce(template):
    html = _render(template)
    assert re.search(
        r'<script nonce="test-nonce">[^<]*data-error-back[^<]*history\.back\(\)', html
    ), f"{template}: سكربتُ الرجوع بلا نونس أو بلا history.back()"
