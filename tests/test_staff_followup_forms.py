"""محرّكُ استمارات متابعة الأداء الإداريّ: نموذجا 10 و11 وبقاءُ 19 (W-20261128-007)."""

import uuid

import pytest
from django.urls import reverse
from django.utils import timezone
from django.utils.html import escape

from core.exports.runner import run_job
from core.models import AuditLog, ExportJob
from core.pdf_utils import _inject_fonts
from quality import supervisor_followup_selectors as selectors
from quality.models import SupervisorFollowUp, SupervisorFollowUpScore
from quality.supervisor_followup_exports import render_sheet_html
from quality.supervisor_followup_indicators import FOLLOWED_ROLES, FORMS
from tests.conftest import SchoolFactory
from tests.test_supervisor_followup import _member, supervisor, vice

__all__ = ["supervisor", "vice"]  # تركيباتٌ مشتركةٌ من ملفّ الإدخال

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

#: الدفعةُ الثانية: رمزُ الاستمارة ← (دورُها، أرقامُ مؤشراتها).
BATCH_TWO = {
    "7": ("storekeeper", list(range(1, 12))),
    "12": ("receptionist", list(range(1, 9))),
    "13": ("student_affairs_coordinator", list(range(1, 14))),
    "14": ("it_technician", list(range(1, 11))),
    "16": ("student_observer", [*range(1, 7), *range(8, 16)]),
}
NEW_CODES = ["10", "11", *BATCH_TWO]


@pytest.fixture
def staff(school):
    """موظّفٌ لكلّ استمارةٍ جديدة بدورها."""
    return {
        "10": _member(school, "social_worker", "اختصاصي اجتماعي اختباري"),
        "11": _member(school, "psychologist", "اختصاصي نفسي اختباري"),
        **{
            code: _member(school, role, f"موظف اختباري {code}")
            for code, (role, _numbers) in BATCH_TWO.items()
        },
    }


def test_the_second_batch_definitions_follow_their_papers():
    for code, (role, numbers) in BATCH_TWO.items():
        form = FORMS[code]
        assert (form.role, [n for n, _ in form.indicators]) == (role, numbers)
        assert not form.has_evidence and role in FOLLOWED_ROLES
    assert FORMS["7"].indicators[8][1] == (
        "المشاركة في مهام المناوبة بالمدرسة لحفظ أمن وسلامة الطلاب."
    )
    assert FORMS["13"].indicators[1][1].endswith("بوزارة التربية والتعليم العالي")
    assert FORMS["13"].indicators[10][1].endswith("للنائب الإداري .")
    assert len(FORMS["14"].indicators[3][1].splitlines()) == 6
    assert "عبر    Microsoft File & Print Server." in FORMS["14"].indicators[7][1]
    assert FORMS["16"].title == "استمارة متابعة أداء ملاحظ طلبه"


@pytest.mark.parametrize("code", list(BATCH_TWO))
def test_the_new_roles_read_only_and_cannot_manage(client_as, staff, code):
    own = client_as(staff[code])
    assert own.get(reverse("supervisor_followup_list")).status_code == 200
    url = reverse("supervisor_followup_new", args=[staff[code].pk])
    assert own.get(url, {"form": code}).status_code == 403


def _save(client, pk, person, code, *, action="save", recs=(), **extra):
    data = {
        "supervisor": str(person.pk),
        "form_code": code,
        "follow_date": timezone.localdate().isoformat(),
        "action": action,
        "rating_1": "complete",
        "rec_id": [r[0] for r in recs],
        "rec_text": [r[1] for r in recs],
        **extra,
    }
    return client.post(reverse("supervisor_followup_edit", args=[pk]), data)


def test_the_new_forms_carry_the_paper_indicators_literally():
    social, psych = FORMS["10"].indicators, FORMS["11"].indicators
    assert [n for n, _ in social] == list(range(1, 12))
    assert [n for n, _ in psych] == list(range(1, 8))
    assert social[3][1] == (
        "تنفيذ البرامج الخاصة بتوجيه وتطوير أداء الطلبة (الموهوبين / المتفوقين / الدعم التعليمي "
        "الإضافي / التأخر الدراسي /….. الخ)"
    )
    assert social[10][1] == "المواظبة والانضباط في العمل."
    # بلا تصحيح: «الي» وقوسُ المؤشر 5 غيرُ المُغلَق كما في الورقة
    assert "تحتاج الي دعم نفسي علاجي" in psych[2][1]
    assert psych[4][1].count("(") == 1 and ")" not in psych[4][1]
    assert (FORMS["10"].role, FORMS["11"].role) == ("social_worker", "psychologist")
    assert [FORMS[c].has_evidence for c in ("19", "10", "11")] == [True, False, False]


@pytest.mark.parametrize("code", NEW_CODES)
def test_each_form_lists_only_its_role_and_saves_its_indicators(
    client_as, school, vice, supervisor, staff, code
):
    client, form, person = client_as(vice), FORMS[code], staff[code]
    listing = client.get(reverse("supervisor_followup_list"), {"form": code}).content.decode()
    others = [supervisor, *(u for c, u in staff.items() if c != code)]
    assert person.full_name in listing
    assert not any(other.full_name in listing for other in others)

    url = reverse("supervisor_followup_new", args=[person.pk])
    html = client.get(url, {"form": code}).content.decode()
    assert form.title in html and f"اسم {form.staff_noun}" in html
    assert all(escape(line) in html for _n, t in form.indicators for line in t.splitlines())
    # موظّفُ دورٍ آخرَ لا تُفتح له الاستمارة
    wrong = reverse("supervisor_followup_new", args=[supervisor.pk])
    assert client.get(wrong, {"form": code}).status_code == 404

    pk = uuid.uuid4()
    assert _save(client, pk, person, code, rating_15="complete").status_code == 302
    row = SupervisorFollowUp.objects.get(pk=pk)
    assert row.form_code == code and row.status == "saved"
    assert SupervisorFollowUpScore.objects.filter(followup=row).count() == len(form.indicators)


def test_an_unknown_form_is_404_and_a_foreign_role_is_not_saved(client_as, vice, supervisor):
    client = client_as(vice)
    assert client.get(reverse("supervisor_followup_list"), {"form": "99"}).status_code == 404
    assert _save(client, uuid.uuid4(), supervisor, "10").status_code == 404
    assert not SupervisorFollowUp.objects.exists()


def test_drafts_and_previous_recommendations_stay_inside_their_form(client_as, school, vice):
    """مسودةُ استمارةٍ وسابقتُها لا تظهران لاستمارةٍ أخرى للشخص نفسِه."""
    both = _member(school, "social_worker", "موظف اختباري")
    client = client_as(vice)
    first = uuid.uuid4()
    _save(client, first, both, "10", recs=[(str(uuid.uuid4()), "توصية الاجتماعي")])
    row = SupervisorFollowUp.objects.get(pk=first)
    today = row.follow_date
    assert selectors.previous_saved(school, both, today, code="10") == row
    assert selectors.previous_saved(school, both, today, code="11") is None
    assert selectors.previous_saved(school, both, today) is None
    draft = uuid.uuid4()
    _save(client, draft, both, "10", action="draft")
    assert selectors.open_draft(school, both, "10").pk == draft
    assert selectors.open_draft(school, both, "11") is None
    assert selectors.open_draft(school, both) is None


@pytest.mark.parametrize("code", NEW_CODES)
def test_send_read_and_acknowledge_follow_the_19_permissions(
    client_as, school, vice, supervisor, staff, code
):
    person, manager = staff[code], client_as(vice)
    saved, draft = uuid.uuid4(), uuid.uuid4()
    _save(manager, saved, person, code)
    _save(manager, draft, person, code, action="draft")
    manager.post(reverse("supervisor_followup_send", args=[saved]))

    own = client_as(person)
    detail = reverse("supervisor_followup_detail", args=[saved])
    assert own.get(detail).status_code == 200
    assert own.get(reverse("supervisor_followup_detail", args=[draft])).status_code == 403
    listing = own.get(reverse("supervisor_followup_list")).content.decode()
    assert detail in listing and str(draft) not in listing
    assert own.get(reverse("supervisor_followup_new", args=[person.pk])).status_code == 403
    assert _save(own, uuid.uuid4(), person, code).status_code == 403

    # موظّفٌ مُتابَعٌ آخرُ ومعلمٌ: 403؛ ومدرسةٌ أخرى: 404
    other = staff["10" if code == "11" else "11"]
    teacher = _member(school, "teacher", "معلم اختباري")
    for stranger in (other, supervisor, teacher):
        assert client_as(stranger).get(detail).status_code == 403
    outsider = _member(SchoolFactory(), "principal", "مدير مدرسة أخرى")
    assert client_as(outsider).get(detail).status_code == 404

    own = client_as(person)
    own.post(reverse("supervisor_followup_acknowledge", args=[saved]))
    assert SupervisorFollowUp.objects.get(pk=saved).status == "acknowledged"


@pytest.mark.parametrize("code", NEW_CODES)
def test_the_sheet_matches_its_paper_on_one_a4_page(client_as, school, vice, staff, code):
    from weasyprint import HTML

    pk, form = uuid.uuid4(), FORMS[code]
    # أطولُ الحالات: كلُّ مؤشّرٍ مقدَّرٌ بأطول تقدير
    ratings = {f"rating_{n}": "not_measured" for n, _text in form.indicators}
    _save(client_as(vice), pk, staff[code], code, **ratings)
    html = render_sheet_html(school, selectors.get_follow_up(school, pk))
    body = html[html.index('<div id="head19">') :]
    sections = ["متابعة التوصيات السابقة</th>", "متابعة الغياب والاستئذان والتأخير الصباحي</th>"]
    sections.insert(0 if code in ("7", "12", "13") else 2, f"اسم {form.staff_noun}</th>")
    order = [
        school.name,
        f"نموذج {code}</div>",
        f"{form.title}</h1>",
        *sections,
        "متابعة تنفيذ المهام</th>",
        "جوانب القوة</th>",
        f"{form.improvements_title}</th>",
        ">التوصيات</th>",
        "توقيع الموظف</th>",
        "اعتماد المسؤول المباشر</th>",
    ]
    positions = [body.index(text, body.index(order[0])) for text in order]
    assert positions == sorted(positions)
    assert '<th scope="col">متابعة تنفيذ المهام</th><th scope="col">الملاحظات</th>' in body
    assert f'data-form="{code}"' in html and "Choose an item" not in html
    assert all(escape(line) in body for _n, t in form.indicators for line in t.splitlines())
    pages = HTML(string=_inject_fonts(html)).render().pages
    assert len(pages) == 1 and pages[0].height > pages[0].width


def test_form_19_keeps_its_default_code_and_sheet(client_as, school, vice, supervisor):
    """متابعةٌ بلا `form_code` (المحفوظةُ قبل المحرّك ورابطُها) نموذجُ 19 ومطبوعُها بنصّه."""
    today = timezone.localdate()
    old = SupervisorFollowUp.objects.create(
        school=school,
        supervisor=supervisor,
        follower=vice,
        status="saved",
        period_start=today,
        period_end=today,
    )
    old.refresh_from_db()
    assert old.form_code == "19"
    html = render_sheet_html(school, old)
    assert "<body data-pdf-own-page>" in html
    assert "<title>استمارة متابعة أداء مشرف إداري</title>" in html
    assert "<div data-number>نموذج 19</div>" in html and '<th scope="col">ملاحظات</th>' in html
    url = reverse("supervisor_followup_detail", args=[old.pk])
    assert client_as(vice).get(url).status_code == 200


@pytest.mark.parametrize("code", NEW_CODES)
def test_export_is_logged_and_named_without_the_person(client_as, vice, staff, monkeypatch, code):
    queued: list = []
    monkeypatch.setattr(
        "core.tasks.run_export_job.apply_async", lambda *a, **k: queued.append(k["args"])
    )
    monkeypatch.setattr("core.pdf_utils._generate_pdf_bytes", lambda *a, **k: b"%PDF-1.7")
    client, person, pk = client_as(vice), staff[code], uuid.uuid4()
    _save(client, pk, person, code)
    url = reverse("supervisor_followup_pdf", args=[pk])
    assert client.get(url).status_code == 200
    row = AuditLog.objects.filter(object_id=str(pk), action="export").get()
    assert person.full_name not in f"{row.object_repr} {row.changes}"
    client.get(url, {"download": "1"}, HTTP_X_REQUESTED_WITH="XMLHttpRequest")
    job = ExportJob.objects.get(pk=queued[0][0])
    assert run_job(str(job.pk))["ok"]
    job.refresh_from_db()
    assert f"نموذج_{code}_" in job.filename and person.full_name not in job.filename
