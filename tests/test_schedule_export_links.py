"""
tests/test_schedule_export_links.py
روابط تصدير الجدول الأسبوعي لمعلّمٍ بعينه — W-20261113-001

الخللُ المثبَت على الإنتاج: الرابطان يخرجان `?view=teacher&amp;amp;paper=a4…` فيقرأ المتصفّحُ
المعاملاتِ «amp;teacher» و«amp;year»…، ولا يصل الخادمَ إلا `view`، فيُصدَّر جدولٌ غيرُ المعروض.

يغطّي: الصفحةُ تُعرض، وكلُّ رابطِ تصديرٍ فيها يُحلَّل بعد فكّ الكيان مرّةً إلى معاملاتها بأسمائها.
"""

import html
import re
from urllib.parse import parse_qs, urlsplit

import pytest

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

#: الرابطُ يبدأ بنوع التصدير في السمة `data-export-kind` ثم `href` (ترتيبُ وسم export_button).
_EXPORT_LINK = re.compile(r'data-export-kind="(pdf|xlsx)"[^>]*?\bhref="([^"]*)"')

#: المعاملاتُ التي يحملها كلُّ رابطِ تصديرٍ لجدولِ معلّمٍ بعينه، بأسمائها.
_EXPECTED_PARAMS = {"view", "teacher", "year", "source", "week", "paper"}


def test_teacher_schedule_export_links_carry_named_params(client_as, principal_user, teacher_user):
    c = client_as(principal_user)
    resp = c.get(
        f"/teacher/weekly-schedule/?view=teacher&teacher={teacher_user.id}"
        "&source=actual&week=2026-11-08&paper=a4"
    )
    assert resp.status_code == 200

    # المتصفّحُ يفكّ الكيانَ مرّةً في السمة قبل أن يقرأ الاستعلام.
    links = {
        kind: html.unescape(href) for kind, href in _EXPORT_LINK.findall(resp.content.decode())
    }
    assert set(links) == {"pdf", "xlsx"}, links

    for kind, href in links.items():
        query = parse_qs(urlsplit(href).query)
        assert _EXPECTED_PARAMS <= set(query), (kind, href)
        assert query["view"] == ["teacher"], (kind, href)
        assert query["teacher"] == [str(teacher_user.id)], (kind, href)
        assert query["source"] == ["actual"], (kind, href)
        assert query["week"] == ["2026-11-08"], (kind, href)
        assert query["paper"] == ["a4"], (kind, href)
        assert query["year"][0], (kind, href)
        # لا معاملَ يحمل «amp;» في اسمه: ذلك التهريبُ المزدوجُ بعينه.
        assert not [k for k in query if "amp;" in k], (kind, href)
