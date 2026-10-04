"""[W-20261004-015] كشفُ المشرف بعد استخراج الجزئيّة المشتركة **لا يتحرّك بصريّاً**: مخرجُه مطابقٌ لمخرج القالب الأصليّ حرفاً (بعد تسوية ما يتغيّر كلَّ لحظة).

`tests/fixtures/record_section_legacy.html` نسخةُ قالب `wings/record_section.html` قبل الاستخراج، تُرسم بالسياق نفسِه الذي رسم به الخادمُ الصفحةَ الجديدة.
فإن تغيّر حرفٌ في بنية كشف المشرف (لقطاتُ VI-13) سقط هذا الاختبار.
"""

import re
from pathlib import Path

import pytest
from django.template import engines
from django.urls import reverse
from django.utils import timezone

from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY, at

pytestmark = pytest.mark.django_db

LEGACY = Path(__file__).parent / "fixtures" / "record_section_legacy.html"


@pytest.fixture
def now_0730(monkeypatch):
    monkeypatch.setattr(timezone, "now", lambda: at(7, 30))


def _normal(html: str) -> str:
    html = re.sub(
        r'name="csrfmiddlewaretoken" value="[^"]+"', 'name="csrfmiddlewaretoken" value="T"', html
    )
    html = re.sub(r"\d{2}:\d{2}:\d{2}", "HH:MM:SS", html)
    html = re.sub(r'data-(now|offset)="[^"]*"', r'data-\1="X"', html)
    return re.sub(r"\s+", " ", html).strip()


def test_the_supervisor_sheet_is_byte_for_byte_the_legacy_markup(
    client_as, now_0730, klass, session, holder, kid
):
    response = client_as(holder).get(
        reverse("wings:record_section", args=[klass.id]), {"date": SUNDAY.isoformat()}
    )
    assert response.status_code == 200
    new = response.content.decode()
    context: dict = {}
    for ctx in reversed(list(response.context)):  # الأقدمُ أوّلاً فيغلب الأحدث
        context.update(ctx.flatten())
    legacy = (
        engines["django"]
        .from_string(LEGACY.read_text(encoding="utf-8"))
        .render(context, response.wsgi_request)
    )
    assert _normal(new) == _normal(legacy)
    assert 'class="per-head"' in new and 'data-bulk="absent"' in new  # الفحصُ ليس على صفحةٍ فارغة
