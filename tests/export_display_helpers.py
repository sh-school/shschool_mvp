"""أدواتُ حارس «ما يُعرض هو ما يُصدَّر» (W-20261113-003): استخراجُ روابط التصدير من HTML وتنزيلُ الملفّ بالرابط المرسوم نفسِه.

مشتركةٌ بين `test_export_matches_display*.py`: الاختبارُ لا يستدعي مسارَ التصدير بمعاملاتٍ يكتبها بل يتبع **الرابطَ الذي ترسمه الصفحة**.
"""

from __future__ import annotations

import html
import re
from io import BytesIO
from typing import Any
from urllib.parse import parse_qs, unquote, urlsplit

from django.http import QueryDict
from openpyxl import load_workbook

from core.exports import registry
from core.models import ExportJob

#: رابطُ التصدير يبدأ بنوعه في `data-export-kind` ثم `href` (ترتيبُ وسم export_button).
EXPORT_LINK = re.compile(r'data-export-kind="(pdf|xlsx)"[^>]*?\bhref="([^"]*)"')


def export_links(page_html: str) -> list[tuple[str, str]]:
    """روابطُ التصدير في الصفحة (النوعُ، الرابطُ) بعد فكّ كيان HTML **مرّةً واحدة** كما يفعل المتصفّحُ بالسمة."""
    return [(kind, html.unescape(href)) for kind, href in EXPORT_LINK.findall(page_html)]


def link_of(page_html: str, kind: str) -> str:
    """رابطُ التصدير الوحيد من النوع المطلوب — وإلّا فالصفحةُ رسمت غيرَ ما يُظنّ."""
    found = [href for k, href in export_links(page_html) if k == kind]
    assert len(found) == 1, f"رابطُ {kind} المنتظَر واحدٌ في الصفحة: {found}"
    return found[0]


def query_of(href: str) -> dict[str, list[str]]:
    return parse_qs(urlsplit(href).query, keep_blank_values=True)


def _filename(response: Any) -> str:
    """اسمُ الملفّ من ترويسة التنزيل (RFC 5987) بعد فكّ ترميزه."""
    disposition = response.get("Content-Disposition", "")
    if "filename*=UTF-8''" in disposition:
        return unquote(disposition.split("filename*=UTF-8''", 1)[1])
    return unquote(disposition)


def download(client: Any, user: Any, href: str) -> tuple[bytes, str]:
    """يطلب الرابطَ المستخرجَ نفسَه ويعيد (محتوى الملفّ، اسمَه).

    التصديرُ المتزامنُ يردّ الملفَّ في الطلب؛ والخلفيُّ ينشئ صفَّ `ExportJob` بسلسلة استعلام الرابط ذاتِها، فيبني العاملُ
    الملفَّ منها — نبنيه هنا كما يبنيه العاملُ، فما فُقد من الرابط يُفقَد من الملفّ.
    """
    response = client.get(href)
    if "spreadsheetml" in response.get("Content-Type", ""):
        return response.content, _filename(response)
    job = ExportJob.objects.filter(requested_by=user).order_by("-created_at").first()
    assert (
        job is not None
    ), f"الرابطُ لم يردّ ملفّاً ولا أنشأ مهمّةَ تصدير: {href} ({response.status_code})"
    spec = registry.get(job.kind)
    assert spec is not None, job.kind
    result = spec.build(job.school, user, QueryDict(job.query_string))
    return result.content, result.filename


def data_rows(content: bytes) -> list[list[Any]]:
    """صفوفُ البيانات في الملفّ بلا الترويسة والتذييل: كلُّ صفٍّ رقمُه في عموده الأوّل (عمودُ «م»)."""
    sheet = load_workbook(BytesIO(content)).active
    return [
        [cell.value for cell in row]
        for row in sheet.iter_rows()
        if isinstance(row[0].value, int) and row[0].value >= 1
    ]


def first_column(rows: list[list[Any]]) -> list[str]:
    """أوّلُ عمود بياناتٍ (بعد «م») مرتَّباً — فالمقارنةُ بالمحتوى لا بالترتيب (الملفُّ يفرز بالجناح)."""
    return sorted(str(row[1]) for row in rows)
