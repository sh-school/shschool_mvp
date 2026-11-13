"""ملفُّ تقرير الجناح (الحصّتان الأولى والثانية) بالرابط المرسوم يطابق الصفحةَ (W-20261113-003).

في ملفٍّ وحده: أجهزةُ `test_ministry_summary` (ومنها تثبيتُ الساعة على الأحد 09:00 تلقائيّاً) لا يجوز أن تسري على غيره.
"""

import pytest
from django.urls import reverse

from tests.attendance_fixtures import *  # noqa: F401,F403
from tests.attendance_fixtures import SUNDAY
from tests.export_display_helpers import data_rows, download, link_of
from tests.test_ministry_summary import _day, class_day, periods  # noqa: F401

pytestmark = pytest.mark.django_db


def test_ministry_file_from_the_page_link_matches_the_searched_page(
    school, klass, class_day, holder, client_as
):
    client = client_as(holder)
    resp = client.get(reverse("wings:ministry_report"), {"date": SUNDAY.isoformat(), "q": "بعذر"})
    assert resp.status_code == 200
    shown = sorted(m.name for m in resp.context["summary"].ministered)
    assert shown == ["غائبٌ بعذر"], "البحثُ بالاسم يُبقي مرفوعاً واحداً من اثنين"

    content, _ = download(client, holder, link_of(resp.content.decode(), "xlsx"))

    rows = data_rows(content)
    # أعمدةُ الجدول: م، الصفّ، الشعبة، الطالب، العذر، قيد الطالب — فالاسمُ في الرابع.
    assert len(rows) == len(shown)
    assert sorted(str(row[3]) for row in rows) == shown
