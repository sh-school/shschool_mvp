"""طباعةُ «نموذج 19»: ترتيبُ الورقة، والصفحةُ العارضة، والصلاحيات، وسجلُّ التصدير (W-20261125-007)."""

import re
import uuid

import pytest
from django.urls import reverse

from core.exports.runner import run_job
from core.models import AuditLog, ExportJob
from core.pdf_utils import _inject_fonts
from quality import supervisor_followup_selectors as selectors
from quality.supervisor_followup_exports import render_sheet_html
from quality.supervisor_followup_indicators import INDICATORS
from tests.conftest import SchoolFactory
from tests.test_supervisor_followup import STRENGTH, _member, _post, supervisor, vice

__all__ = ["supervisor", "vice"]  # تركيباتٌ مشتركةٌ من ملفّ الإدخال

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

TICK = '<span class="tick">✓</span>'


def _html(school, pk):
    return render_sheet_html(school, selectors.get_follow_up(school, pk))


def _fake_pdf(monkeypatch):
    seen: dict[str, str] = {}

    def fake(html, *args, **kwargs):
        seen["html"] = html
        return b"%PDF-1.7"

    monkeypatch.setattr("core.pdf_utils._generate_pdf_bytes", fake)
    return seen


def test_the_sheet_follows_the_paper_order_and_titles(client_as, school, vice, supervisor):
    pk = uuid.uuid4()
    _post(client_as(vice), pk, supervisor, recs=[(str(uuid.uuid4()), "توصية للطباعة")])
    html = _html(school, pk)
    body = html[html.index('<div id="sheet19">') :]
    order = [
        "استمارة متابعة أداء مشرف إداري</h1>",
        "العام الأكاديمي",
        "متابعة التوصيات السابقة</th>",
        "متابعة الغياب والاستئذان والتأخير الصباحي</th>",
        "اسم المشرف الإداري</th>",
        "اليوم</th>",
        "التاريخ</th>",
        "مؤشرات المتابعة</th>",
        "متابعة تنفيذ المهام</th>",
        "جوانب القوة</th>",
        "جوانب تحتاج إلى تحسين</th>",
        ">التوصيات</th>",
        "توقيع الموظف</th>",
        "اعتماد المسؤول المباشر</th>",
    ]
    positions = [body.index(text) for text in order]
    assert positions == sorted(positions)
    assert "توصية للطباعة" in body and STRENGTH in body
    assert all(text in body for _n, text in INDICATORS)
    # التقديرُ نصٌّ لا علامة؛ والمسودةُ وحدَها تحمل كلمتَها
    assert re.search(r"<td data-mid>مستكمل</td>", body)
    assert "<p data-draft>" not in body
    assert not re.search(r"<th(?![^>]*scope=)[ >]", body)


def test_the_sheet_carries_the_paper_header_and_footer_outside_the_central_frame(
    client_as, school, vice, supervisor
):
    pk = uuid.uuid4()
    _post(client_as(vice), pk, supervisor)
    html = _html(school, pk)
    head = html[html.index('<div id="head19">') : html.index('<div id="foot19">')]
    foot = html[html.index('<div id="foot19">') : html.index('<div id="sheet19">')]
    assert "<body data-pdf-own-page>" in html
    assert 'class="ministry-logo"' in head and school.name in head
    assert "قسم دعم الإدارة المدرسية" in foot and "نموذج 19" in foot
    assert head.count("data-gem=") == foot.count("data-gem=") == 12
    # بلا توصياتٍ سابقة يبقى صفّا الورقة المرقّمان
    recs = html[html.index('<table id="recs">') : html.index('<table id="attendance">')]
    assert "<td>1.</td>" in recs and "<td>2.</td>" in recs


def test_previous_recommendation_status_is_ticked_in_its_column(
    client_as, school, vice, supervisor
):
    client = client_as(vice)
    first, second, done, untouched = (uuid.uuid4() for _ in range(4))
    _post(client, first, supervisor, recs=[(str(done), "أ"), (str(untouched), "ب")])
    _post(
        client,
        second,
        supervisor,
        review_id=str(done),
        **{f"review_status_{done}": "done", f"review_note_{done}": "تم"},
    )
    assert _html(school, second).count(TICK) == 1


def test_a_draft_is_printed_with_the_word_draft(client_as, school, vice, supervisor):
    pk = uuid.uuid4()
    _post(client_as(vice), pk, supervisor, action="draft")
    assert "<p data-draft>مسودة</p>" in _html(school, pk)


def test_signatures_appear_by_state_with_the_name_only(client_as, school, vice, supervisor):
    from weasyprint import HTML

    pk = uuid.uuid4()
    _post(client_as(vice), pk, supervisor)

    def cells():
        html = _html(school, pk)
        table = html[html.index('<table id="sign">') :]
        found = re.findall(r"<td>(.*?)</td>", table[: table.index("</table>")], re.S)
        return [cell.strip() for cell in found]

    def stamp(user):
        return f'<div class="e-sign"><div>{user.full_name}</div></div>'

    assert cells() == ["", ""]
    client_as(vice).post(reverse("supervisor_followup_send", args=[pk]))
    assert cells() == ["", stamp(vice)]
    assert "<p data-draft>" not in _html(school, pk)
    client_as(supervisor).post(reverse("supervisor_followup_acknowledge", args=[pk]))
    assert cells() == [stamp(supervisor), stamp(vice)]
    assert len(HTML(string=_inject_fonts(_html(school, pk))).render().pages) == 1


def test_pdf_is_inline_framable_and_logged_without_the_name(
    client_as, vice, supervisor, monkeypatch
):
    seen = _fake_pdf(monkeypatch)
    client = client_as(vice)
    pk = uuid.uuid4()
    _post(client, pk, supervisor)
    response = client.get(reverse("supervisor_followup_pdf", args=[pk]))
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    assert response["Content-Disposition"].startswith("inline")
    assert response["X-Frame-Options"] == "SAMEORIGIN"
    assert supervisor.full_name in seen["html"]
    row = AuditLog.objects.filter(object_id=str(pk), action="export").get()
    assert supervisor.full_name not in f"{row.object_repr} {row.changes}"


def test_download_goes_through_the_central_export_job(client_as, vice, supervisor, monkeypatch):
    queued: list = []
    monkeypatch.setattr(
        "core.tasks.run_export_job.apply_async", lambda *a, **k: queued.append(k["args"])
    )
    client = client_as(vice)
    pk = uuid.uuid4()
    _post(client, pk, supervisor)
    url = reverse("supervisor_followup_pdf", args=[pk])
    response = client.get(url, {"download": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    assert response.status_code == 202 and len(queued) == 1
    job = ExportJob.objects.get(pk=queued[0][0])
    assert job.kind == "quality.supervisor_followup_pdf" and str(pk) in job.query_string
    seen = _fake_pdf(monkeypatch)
    assert run_job(str(job.pk))["ok"]
    assert supervisor.full_name in seen["html"]
    job.refresh_from_db()
    assert job.status == "done" and supervisor.full_name not in job.filename


def test_the_detail_button_opens_the_viewer_with_its_toolbar(client_as, vice, supervisor):
    client = client_as(vice)
    pk = uuid.uuid4()
    _post(client, pk, supervisor)
    viewer = reverse("supervisor_followup_pdf_view", args=[pk])
    detail = client.get(reverse("supervisor_followup_detail", args=[pk])).content.decode()
    assert viewer in detail and "طباعة / PDF" in detail
    response = client.get(viewer)
    assert response.status_code == 200
    assert response["X-Frame-Options"] == "DENY"
    html = response.content.decode()
    assert reverse("supervisor_followup_detail", args=[pk]) in html
    assert f'<iframe src="{reverse("supervisor_followup_pdf", args=[pk])}"' in html
    assert "?download=1" in html and "أيقونة الطباعة" in html
    assert "style=" not in html[html.index('class="obs-pdf-page"') : html.index("</iframe>")]


@pytest.mark.parametrize("name", ["supervisor_followup_pdf", "supervisor_followup_pdf_view"])
def test_printing_follows_the_reading_rule(client_as, school, vice, supervisor, monkeypatch, name):
    _fake_pdf(monkeypatch)
    manager = client_as(vice)
    draft, saved = uuid.uuid4(), uuid.uuid4()
    _post(manager, saved, supervisor)
    _post(manager, draft, supervisor, action="draft")
    own = client_as(supervisor)
    assert own.get(reverse(name, args=[saved])).status_code == 200
    assert own.get(reverse(name, args=[draft])).status_code == 403
    teacher = _member(school, "teacher", "معلم اختباري")
    assert client_as(teacher).get(reverse(name, args=[saved])).status_code == 403
    elsewhere = SchoolFactory()
    outsider = _member(elsewhere, "principal", "مدير مدرسة أخرى")
    assert client_as(outsider).get(reverse(name, args=[saved])).status_code == 404


def test_form_19_renders_to_a_real_portrait_pdf(client_as, school, vice, supervisor):
    from weasyprint import HTML

    pk = uuid.uuid4()
    _post(client_as(vice), pk, supervisor)
    # بخطوط الوثيقة المحقونة كما في الإنتاج: صفحةُ A4 عموديّةٌ واحدة
    pages = HTML(string=_inject_fonts(_html(school, pk))).render().pages
    assert len(pages) == 1
    assert pages[0].height > pages[0].width
