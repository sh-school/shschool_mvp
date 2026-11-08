"""كلُّ PDF تصدّره صفحاتُ المخالفات يحمل عنوانًا صريحًا في الإطار المركزيّ — W-20261108-011.

قرارُ المالك: «اكتب على كل ملف بي دي تصدير ما هو هذا الملف؟». العنوانُ واسمُ المدرسة والتاريخُ
من `print_frame_header` لا من نمطٍ محلّيّ؛ ولا يخرج ملفٌّ بلا عنوان.
"""

from unittest.mock import patch

import pytest
from django.http import HttpResponse

pytestmark = pytest.mark.django_db

_FORMS = [
    ("warning", "نموذج إنذار سلوكي"),
    ("parent", "تعهّد خطّي لولي الأمر"),
    ("student", "تعهّد خطّي للطالب"),
]


def _captured_html(client, url: str) -> str:
    with patch("core.pdf_utils.render_pdf") as mock_render:
        mock_render.return_value = HttpResponse(b"%PDF-1.4", content_type="application/pdf")
        resp = client.get(url)
        assert resp.status_code == 200
        return mock_render.call_args.args[0]


@pytest.mark.parametrize(("suffix", "title"), _FORMS)
def test_form_pdf_header_names_the_file(
    suffix, title, client_as, principal_user, school, behavior_infraction
):
    """العنوانُ في `#print-header` مع اسم المدرسة والتاريخ."""
    client = client_as(principal_user)
    html = _captured_html(client, f"/behavior/infraction/{behavior_infraction.id}/pdf/{suffix}/")
    header = html.split('id="print-header"', 1)[1].split("</div>\n</div>", 1)[0]
    assert f'<div class="pf-title">{title}</div>' in header
    assert school.name in header
    assert f"التاريخ: {behavior_infraction.date:%Y/%m/%d}" in header


def test_pdf_without_title_is_refused(rf, principal_user):
    """لا يخرج ملفٌّ بلا عنوان."""
    from behavior.views import _render_behavior_pdf

    request = rf.get("/")
    request.user = principal_user
    with pytest.raises(ValueError):
        _render_behavior_pdf(request, "x.html", {}, "f.pdf", kind="k", title="  ")
