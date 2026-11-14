"""صفحةُ رفع ملفَّي aSc (W-20261114-005): تقريرٌ بلا كتابة، ثمّ مسودّةٌ غيرُ مفعَّلة تطابق ناتجَ الأمر.

الصفحةُ والأمرُ يناديان خدمةً واحدة (`academic_management.asc_import`)، فالاختبارُ يقارن الكتابتين
على الملفّين نفسيهما. ولا PDF حقيقيّاً: الصفحاتُ كائناتٌ مصطنعة تُسلَّم بدل `open_pdf`، والبايتاتُ
تبدأ بتوقيع `%PDF` لتجتاز التحقّق. لا مهمّةَ Celery حقيقيّة: `delay` تُنفّذ جسمَ المهمّة في الحال.
"""

import json
from contextlib import contextmanager
from pathlib import Path
from typing import Any

import pytest
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.urls import reverse

from academic_management import asc_import_job as job
from academic_management import asc_pdf
from core.models import AuditLog
from operations import views_asc_import
from operations.models import ScheduleGeneration, ScheduleSlot
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_import_schedule_from_asc_pdf import (  # noqa: F401
    FakePdf,
    _no_private_rules,
    _simple,
    class_page,
    teacher_page,
    world,
    year,
)

pytestmark = pytest.mark.django_db

T_BYTES, C_BYTES = b"%PDF-teachers-page", b"%PDF-classes-page"


def _user(school, role):
    user = UserFactory(full_name="سرّي-الاسم")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name=role))
    return user


@pytest.fixture
def developer(school):
    return _user(school, "platform_developer")


@pytest.fixture
def books(monkeypatch):
    """يضع كتبَ الـPDF المصطنعة بمفتاح البايتات؛ ويُنفّذ المهمّةَ في الحال."""
    shelf: dict[bytes, FakePdf] = {}

    @contextmanager
    def opener(source: Any) -> Any:
        data = source.getvalue() if hasattr(source, "getvalue") else Path(source).read_bytes()
        yield shelf[data]

    monkeypatch.setattr(asc_pdf, "open_pdf", opener)

    class _Inline:
        @staticmethod
        def delay(*args: Any) -> None:
            job.run_job(*args)

    monkeypatch.setattr(views_asc_import, "asc_import_run_task", _Inline)
    cache.clear()

    def put(teachers: list, classes: list) -> None:
        shelf[T_BYTES], shelf[C_BYTES] = FakePdf(teachers), FakePdf(classes)

    return put


def _upload(name: str, data: bytes) -> SimpleUploadedFile:
    return SimpleUploadedFile(name, data)


def _submit(client, action: str, **overrides: Any):
    body = {
        "action": action,
        "teachers_pdf": _upload("t.pdf", T_BYTES),
        "classes_pdf": _upload("c.pdf", C_BYTES),
        **overrides,
    }
    return client.post(reverse("asc_import_submit"), body)


def _finish(client, response) -> Any:
    """يقرأ نتيجةَ التشغيل كما تفعل الصفحةُ بعد الاستطلاع."""
    return client.get(reverse("asc_import_status", args=[response.context["token"]]))


# ── الصلاحيّة ──────────────────────────────────────────────────────────


def test_user_without_capability_gets_403_on_every_route(client_as, school):
    client = client_as(_user(school, "teacher"))
    assert client.get(reverse("asc_import")).status_code == 403
    assert client.post(reverse("asc_import_submit")).status_code == 403
    assert client.get(reverse("asc_import_status", args=["x"])).status_code == 403


def test_developer_opens_the_page_and_smart_schedule_links_to_it(client_as, developer):
    client = client_as(developer)
    assert client.get(reverse("asc_import")).status_code == 200
    page = client.get(reverse("smart_schedule")).content.decode()
    assert reverse("asc_import") in page


# ── التحقّق من الملفّات ────────────────────────────────────────────────


def test_non_pdf_extension_is_rejected_with_message(client_as, developer, books):
    response = _submit(client_as(developer), "analyze", teachers_pdf=_upload("t.txt", T_BYTES))
    assert "الامتدادُ ليس pdf" in response.content.decode()
    assert "token" not in response.context


def test_pdf_extension_without_pdf_signature_is_rejected(client_as, developer, books):
    response = _submit(client_as(developer), "analyze", classes_pdf=_upload("c.pdf", b"MZ-exe"))
    assert "المحتوى ليس PDF" in response.content.decode()
    assert ScheduleGeneration.objects.count() == 0


def test_oversize_pdf_is_rejected_with_message(client_as, developer, books, monkeypatch):
    monkeypatch.setattr(job, "MAX_PDF_BYTES", 10)
    response = _submit(client_as(developer), "analyze")
    assert "أكبرُ من الحدّ" in response.content.decode()


@pytest.mark.parametrize(
    ("data", "message"),
    [
        (b"{not json", "ليس JSON صحيحاً"),
        (json.dumps(["قائمة"]).encode(), "يجب أن يكون كائناً"),
        (json.dumps({"asc_ignore": "نص"}).encode(), "يجب أن يكون قائمة"),
        (json.dumps({"teacher_aliases": []}).encode(), "يجب أن يكون قاموساً"),
        (b"{" + b" " * (job.MAX_RULES_BYTES + 1) + b"}", "أكبرُ من الحدّ"),
    ],
)
def test_bad_rules_json_is_rejected(client_as, developer, books, data, message):
    response = _submit(client_as(developer), "analyze", rules_json=_upload("r.json", data))
    assert message in response.content.decode()


def test_rules_file_must_be_json_by_extension(client_as, developer, books):
    response = _submit(client_as(developer), "analyze", rules_json=_upload("r.txt", b"{}"))
    assert "الامتدادُ ليس json" in response.content.decode()


# ── التحليل لا يكتب ─────────────────────────────────────────────────────


def test_analyze_reports_counts_and_writes_no_row(client_as, developer, books, world):
    teachers, classes = _simple(world)
    books(teachers, classes)
    client = client_as(developer)
    response = _finish(client, _submit(client, "analyze"))
    html = response.content.decode()
    assert "تقريرُ التحليل" in html and "بنودُ التقرير" in html
    assert ScheduleGeneration.objects.count() == 0
    assert ScheduleSlot.objects.count() == 0


def test_analyze_shows_conflict_items(client_as, developer, books, world):
    teachers, _ = _simple(world)
    books(teachers, [class_page("7.1", [(0, 1)])])
    client = client_as(developer)
    html = _finish(client, _submit(client, "analyze")).content.decode()
    assert "تعارض: في ملفّ المعلّمين ولا في ملفّ الشعب" in html


# ── إنشاء المسودّة ───────────────────────────────────────────────────────


def _slots() -> list[tuple]:
    return sorted(
        ScheduleSlot.objects.values_list(
            "teacher_id",
            "class_group_id",
            "subject_id",
            "day_of_week",
            "period_number",
            "elective_group",
            "is_active",
            "generation__status",
        ),
        key=str,
    )


def test_create_writes_the_same_draft_as_the_command(client_as, developer, books, world, tmp_path):
    teachers, classes = _simple(world)
    books(teachers, classes)
    client = client_as(developer)
    response = _finish(client, _submit(client, "create"))
    assert response.status_code == 204
    assert response["HX-Redirect"].startswith(reverse("smart_schedule"))
    from_page = _slots()
    generation = ScheduleGeneration.objects.get()
    assert generation.status == "draft" and not any(s[6] for s in from_page)
    page_snapshot = generation.config_snapshot

    ScheduleSlot.objects.all().delete()
    ScheduleGeneration.objects.all().delete()
    (tmp_path / "t.pdf").write_bytes(T_BYTES)
    (tmp_path / "c.pdf").write_bytes(C_BYTES)
    call_command(
        "import_schedule_from_asc_pdf",
        "--teachers",
        str(tmp_path / "t.pdf"),
        "--classes",
        str(tmp_path / "c.pdf"),
        "--apply",
    )
    assert _slots() == from_page
    assert ScheduleGeneration.objects.get().config_snapshot == page_snapshot


def test_create_refused_while_report_has_blocking_items(client_as, developer, books, world):
    world["assign"](world["people"]["معلم الف"], world["math"], 3)
    books([teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات")])], [class_page("7.1", [(0, 1)])])
    client = client_as(developer)
    html = _finish(client, _submit(client, "create")).content.decode()
    assert "مرفوض" in html
    assert ScheduleGeneration.objects.count() == 0


def test_uploaded_rules_ignore_list_unblocks_create(client_as, developer, books, world):
    world["assign"](world["people"]["معلم الف"], world["math"], 3)
    books([teacher_page("معلم الف", [(0, 1, "7.1", "رياضيات")])], [class_page("7.1", [(0, 1)])])
    rules = json.dumps({"asc_ignore": ["معلم الف|7.1"]}).encode()
    client = client_as(developer)
    response = _finish(client, _submit(client, "create", rules_json=_upload("r.json", rules)))
    assert response.status_code == 204
    assert ScheduleSlot.objects.count() == 1


def test_repeat_create_does_nothing_and_replace_swaps_the_draft(client_as, developer, books, world):
    teachers, classes = _simple(world)
    books(teachers, classes)
    client = client_as(developer)
    _finish(client, _submit(client, "create"))
    first = ScheduleGeneration.objects.get()
    html = _finish(client, _submit(client, "create")).content.decode()
    assert "موجودةٌ من قبل" in html
    assert ScheduleGeneration.objects.get().pk == first.pk
    _finish(client, _submit(client, "create", replace="1"))
    assert ScheduleGeneration.objects.get().pk != first.pk
    assert ScheduleSlot.objects.count() == 2


# ── الكاش والتدقيق ──────────────────────────────────────────────────────


def test_cache_keys_are_deleted_after_the_run_and_after_the_report_is_read(
    client_as, developer, books, world
):
    teachers, classes = _simple(world)
    books(teachers, classes)
    client = client_as(developer)
    submitted = _submit(client, "analyze", rules_json=_upload("r.json", b"{}"))
    token = submitted.context["token"]
    for part in ("teachers", "classes", "rules"):
        assert cache.get(f"asc_import:{token}:{part}") is None
    assert cache.get(f"asc_import:{token}:state")["state"] == "done"
    _finish(client, submitted)
    assert cache.get(f"asc_import:{token}:state") is None
    expired = _finish(client, submitted).content.decode()
    assert "انتهت صلاحيةُ هذا التشغيل" in expired


def test_state_of_another_school_is_not_readable(client_as, developer, books, world):
    from tests.conftest import SchoolFactory

    teachers, classes = _simple(world)
    books(teachers, classes)
    client = client_as(developer)
    token = _submit(client, "analyze").context["token"]
    assert job.poll(token, SchoolFactory().id) is None


def test_audit_log_has_user_sha256_and_counts_without_names(client_as, developer, books, world):
    teachers, classes = _simple(world)
    books(teachers, classes)
    client = client_as(developer)
    _finish(client, _submit(client, "create"))
    entry = AuditLog.objects.filter(action="create").latest("timestamp")
    assert entry.user_id == developer.pk
    assert len(entry.changes["sha256_teachers"]) == 64
    assert len(entry.changes["sha256_classes"]) == 64
    assert entry.changes["lessons"] == 2 and entry.changes["written"] == 2
    dumped = json.dumps(entry.changes, ensure_ascii=False) + entry.object_repr
    assert "معلم" not in dumped and "سرّي" not in dumped


def test_unreadable_pdf_gives_a_generic_error_and_no_names_in_logs(
    client_as, developer, books, world, caplog
):
    books([], [])
    client = client_as(developer)
    submitted = _submit(client, "analyze")
    html = _finish(client, submitted).content.decode()
    assert "لم تُقرأ منه أيُّ خانة" in html or "تعذّرت" in html
    assert "معلم" not in caplog.text
