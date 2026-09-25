"""[PDPPL] ملفُّ دليلِ الإجراء (الجودة) يُفحص ويُنظَّف قبل حفظه — DBT-43.

للدليل بابان: نافذةُ تحديث الإجراء (`task_update_modal`) وصفحتُه (`upload_evidence`). كان الأوّلُ يقبل أيَّ ملفٍّ
بلا فحصِ نوعٍ أو حجم (`.html` و`.svg` تُحفظ وتُقدَّم من نطاق المنصّة، وصورةُ جوّالٍ بإحداثيّاتها)، والثاني يفحص
الامتدادَ وحدَه. صار البابان يمرّان بـ`quality.evidence_files.screen_evidence` عبر `QualityService`.
"""

import ast
import io
from pathlib import Path

import pytest
from django.contrib.messages import get_messages
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse
from PIL import Image

from core.photo_privacy import MAX_PIXELS, MAX_SIDE
from quality.evidence_files import EVIDENCE_MAX_MB, screen_evidence
from quality.models import ProcedureEvidence, ProcedureStatusLog
from tests.test_quality_new_views import make_admin, make_domain, make_procedure

ROOT = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.django_db


def _gps_photo(size=(4000, 3000)):
    image = Image.new("RGB", size, "white")
    exif = Image.Exif()
    exif[0x010F] = "Apple"
    exif[0x0132] = "2026:09:14 07:30:00"
    gps = exif.get_ifd(0x8825)
    gps[2] = (25.0, 17.0, 10.0)
    gps[4] = (51.0, 32.0, 0.0)
    out = io.BytesIO()
    image.save(out, format="JPEG", exif=exif)
    return out.getvalue()


def _stored(evidence):
    with evidence.file.open("rb") as handle:
        return handle.read()


def _assert_clean_shrunk_jpeg(data):
    with Image.open(io.BytesIO(data)) as result:
        assert result.format == "JPEG"
        assert max(result.size) <= MAX_SIDE, "لم تُصغَّر"
        assert not result.getexif(), "إحداثيّاتٌ أو تاريخٌ أو جهازٌ بقي في الصورة"
        assert "exif" not in result.info and "xmp" not in result.info
    assert len(data) < len(_gps_photo())


@pytest.fixture
def setup(client, school):
    admin = make_admin(school)
    proc = make_procedure(school, make_domain(school))
    client.force_login(admin)
    return client, admin, proc


def _modal(client, proc, upload, **extra):
    return client.post(
        reverse("task_update_modal", kwargs={"proc_id": proc.pk}),
        {"status": "Completed", "evidence_file": upload, "evidence_title": "دليل", **extra},
    )


def _page(client, proc, upload):
    return client.post(
        reverse("upload_evidence", kwargs={"proc_id": proc.pk}),
        {"title": "دليل", "file": upload},
    )


# ── الصورةُ تُحفظ نظيفةً من البابين ─────────────────────────────


def test_the_modal_stores_a_phone_photo_shrunk_and_without_hidden_data(setup):
    client, _admin, proc = setup

    _modal(client, proc, SimpleUploadedFile("event.jpg", _gps_photo(), content_type="image/jpeg"))

    evidence = ProcedureEvidence.objects.get(procedure=proc)
    assert evidence.file.name.endswith(".jpg")
    _assert_clean_shrunk_jpeg(_stored(evidence))


def test_the_detail_page_stores_a_phone_photo_shrunk_and_without_hidden_data(setup):
    client, _admin, proc = setup

    _page(client, proc, SimpleUploadedFile("event.jpg", _gps_photo(), content_type="image/jpeg"))

    evidence = ProcedureEvidence.objects.get(procedure=proc)
    _assert_clean_shrunk_jpeg(_stored(evidence))


@pytest.mark.parametrize("name", ["report.docx", "notes.txt", "scan.xls"])
def test_a_photo_named_as_a_document_is_still_cleaned(setup, name):
    """الحكمُ بالمحتوى لا بالاسم: مستندٌ وبايتاتُه JPEG لا يُحفظ بإحداثيّاته."""
    client, _admin, proc = setup

    _page(client, proc, SimpleUploadedFile(name, _gps_photo()))

    evidence = ProcedureEvidence.objects.get(procedure=proc)
    assert evidence.file.name.endswith(".jpg")
    _assert_clean_shrunk_jpeg(_stored(evidence))


# ── المستنداتُ كما هي ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("name", "content"),
    [
        ("report.pdf", b"%PDF-1.4 dalil"),
        ("report.docx", b"PK\x03\x04 word"),
        ("sheet.xlsx", b"PK\x03\x04 excel"),
        ("old.doc", b"\xd0\xcf\x11\xe0 legacy"),
        ("notes.txt", "ملاحظات الدليل".encode()),
    ],
)
def test_documents_are_kept_as_they_are(setup, name, content):
    client, _admin, proc = setup

    _modal(client, proc, SimpleUploadedFile(name, content))

    evidence = ProcedureEvidence.objects.get(procedure=proc)
    assert _stored(evidence) == content


# ── ما يُرفض: لا شيء يُكتب، والإجراءُ لا يتغيّر ───────────────


REFUSED = [
    ("page.html", b"<html><script>alert(1)</script></html>"),
    ("art.svg", b"<svg xmlns='http://www.w3.org/2000/svg'><script>alert(1)</script></svg>"),
    ("run.exe", b"MZ\x90\x00 program"),
    ("fake.pdf", b"<html>not a pdf</html>"),
    ("fake.jpg", b"<html>not a jpeg</html>"),
    ("report.docx", b"<html>not word</html>"),
    ("notes.txt", b"\x89PNG\r\n\x1a\n\x00\x00 a truncated image in a txt"),
]


@pytest.mark.parametrize(("name", "content"), REFUSED)
def test_the_modal_refuses_and_leaves_the_procedure_untouched(setup, name, content):
    client, _admin, proc = setup
    before = proc.status

    resp = _modal(client, proc, SimpleUploadedFile(name, content))

    assert resp.status_code == 302
    proc.refresh_from_db()
    assert proc.status == before, "الحالةُ تغيّرت مع أنّ الملفَّ مرفوض"
    assert not ProcedureEvidence.objects.exists()
    assert not ProcedureStatusLog.objects.exists()


@pytest.mark.parametrize(("name", "content"), REFUSED)
def test_the_detail_page_refuses_the_same_files(setup, name, content):
    client, _admin, proc = setup

    resp = _page(client, proc, SimpleUploadedFile(name, content))

    assert resp.status_code == 302
    assert not ProcedureEvidence.objects.exists()


def test_a_refusal_shows_its_reason_to_the_user(setup):
    client, _admin, proc = setup

    resp = _modal(client, proc, SimpleUploadedFile("page.html", b"<html></html>"))

    texts = [str(m) for m in get_messages(resp.wsgi_request)]
    assert texts, "رُفض الملفُّ صامتاً — لا تُعرض علّتُه"
    assert not any("تم تحديث الإجراء بنجاح" in t for t in texts)


def test_an_oversized_file_is_refused_with_the_stated_limit(setup):
    client, _admin, proc = setup
    big = SimpleUploadedFile("big.pdf", b"%PDF-1.4" + b"0" * ((EVIDENCE_MAX_MB + 1) * 1024 * 1024))

    _modal(client, proc, big)

    assert not ProcedureEvidence.objects.exists()


def test_an_oversized_image_is_refused_before_anything_is_written(setup):
    client, _admin, proc = setup
    side = int(MAX_PIXELS**0.5) + 100
    out = io.BytesIO()
    Image.new("1", (side, side), 1).save(out, format="PNG", optimize=True)

    _modal(client, proc, SimpleUploadedFile("huge.png", out.getvalue()))

    assert not ProcedureEvidence.objects.exists()


def test_no_file_still_updates_the_procedure(setup):
    """التحديثُ بلا ملفٍّ يبقى كما كان — الفحصُ للملفّ وحدَه."""
    client, _admin, proc = setup

    client.post(
        reverse("task_update_modal", kwargs={"proc_id": proc.pk}), {"status": "Pending Review"}
    )

    proc.refresh_from_db()
    assert proc.status == "Pending Review"
    assert not ProcedureEvidence.objects.exists()


# ── الحارسُ: الفحصُ في الخدمة لا في كلّ view ───────────────────


def _calls(function_name):
    tree = ast.parse((ROOT / "quality/services.py").read_text(encoding="utf-8"))
    fn = next(
        n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == function_name
    )
    return {
        getattr(n.func, "id", getattr(n.func, "attr", ""))
        for n in ast.walk(fn)
        if isinstance(n, ast.Call)
    }


@pytest.mark.parametrize("function_name", ["upload_evidence", "update_procedure_status"])
def test_every_service_that_stores_an_evidence_file_screens_it(function_name):
    assert "screen_evidence" in _calls(function_name), (
        f"QualityService.{function_name} يكتب ملفَّ دليلٍ بلا screen_evidence — "
        "فأيُّ view جديدةٍ تمرّره تتجاوز الفحص"
    )


def test_the_screen_returns_documents_untouched_and_photos_cleaned():
    pdf = SimpleUploadedFile("a.pdf", b"%PDF-1.4 x")
    assert screen_evidence(pdf) is pdf
    cleaned = screen_evidence(SimpleUploadedFile("a.jpg", _gps_photo()))
    _assert_clean_shrunk_jpeg(cleaned.read())
