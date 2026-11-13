"""ملفُّ التصدير بالرابط المرسوم يطابق صفوفَ الصفحة (W-20261113-003): سجلُّ الطلاب وزياراتُ العيادة ومتابعةُ الغياب.

الصفحةُ تُطلب مرشَّحةً، ثم يُتبع رابطُ Excel **المستخرج من HTML** (لا مسارٌ يكتبه الاختبار) فيُقارَن عددُ صفوف الملفّ وأوّلُ عمودٍ
بما في سياق الصفحة. ما ضاع من معاملات الرابط يظهر هنا فرقاً في العدد: الترشيحُ يُبقي صفّاً واحداً من اثنين، فإن فُقد خرج الاثنان.
"""

import datetime as dt

import pytest
from django.urls import reverse
from django.utils import timezone

from clinic.models import ClinicVisit
from tests.export_display_helpers import data_rows, download, first_column, link_of
from tests.operations.test_absence_followup import (  # noqa: F401
    DAY,
    _calendar_first,
    absent_both,
    second_wing,
    staff,
)
from tests.test_period_register import (  # noqa: F401
    kids,
    klass,
    other_teacher,
    subjects,
    supervisor,
    teacher,
    year,
)
from tests.test_student_list_export import eighth, pupils, seventh  # noqa: F401

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]


def test_student_list_file_from_the_page_link_matches_the_filtered_page(
    client_as, principal_user, pupils
):
    client = client_as(principal_user)
    resp = client.get(reverse("student_affairs:student_list"), {"grade": "G7"})
    assert resp.status_code == 200
    shown = sorted(row["full_name"] for row in resp.context["students"])
    assert shown == ["طالبُ السابع"], "الترشيحُ بالصفّ يُبقي طالباً واحداً من اثنين"

    content, _ = download(client, principal_user, link_of(resp.content.decode(), "xlsx"))

    rows = data_rows(content)
    assert len(rows) == len(shown)
    assert first_column(rows) == shown


def test_clinic_visits_file_from_the_page_link_matches_the_ranged_page(
    client_as, nurse_user, school, student_user
):
    stamps = {
        "old": timezone.make_aware(dt.datetime(2026, 11, 2, 9, 0)),
        "new": timezone.make_aware(dt.datetime(2026, 11, 10, 9, 30)),
    }
    for when in stamps.values():
        visit = ClinicVisit.objects.create(
            school=school, student=student_user, nurse=nurse_user, reason="x"
        )
        ClinicVisit.objects.filter(pk=visit.pk).update(visit_date=when)

    client = client_as(nurse_user)
    resp = client.get(
        reverse("clinic:visits_list"), {"date_from": "2026-11-08", "date_to": "2026-11-12"}
    )
    assert resp.status_code == 200
    shown = sorted(
        timezone.localtime(v.visit_date).strftime("%d/%m/%Y %H:%M") for v in resp.context["visits"]
    )
    assert shown == ["10/11/2026 09:30"], "المدى يُبقي زيارةً واحدةً من اثنتين"

    content, _ = download(client, nurse_user, link_of(resp.content.decode(), "xlsx"))

    rows = data_rows(content)
    assert len(rows) == len(shown)
    assert first_column(rows) == shown


def test_absence_followup_file_from_the_page_link_matches_the_filtered_page(
    client_as, staff, absent_both
):
    principal = staff["principal"]
    client = client_as(principal)
    resp = client.get(reverse("daily_report"), {"date": DAY, "grade": "G8"})
    assert resp.status_code == 200
    shown = sorted(row["student"].full_name for row in resp.context["rows"])
    assert shown == ["طالب الجناح الثاني"], "الترشيحُ بالصفّ يُبقي غائباً واحداً من اثنين"

    content, _ = download(client, principal, link_of(resp.content.decode(), "xlsx"))

    rows = data_rows(content)
    assert len(rows) == len(shown)
    assert first_column(rows) == shown
