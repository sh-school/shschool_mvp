"""علامة «يحتاج مراعاةً» (W-20261010-045، D-336م وD-337م) — بياناتٌ مولَّدةٌ فقط.

بياناتٌ صحّيّةٌ لقُصّر: يثبّت هذا الملفّ ما لا يُتهاون فيه —
- المحدِّدُ يعيد المعرّفاتِ فقط ولا يفكّ حقلاً مشفَّراً؛
- العلامةُ صريحةٌ من الممرّض (لا تلقائيّة)؛
- الاستيرادُ: تساوٍ تامّ على 11 خانة، صفٌّ بلا مطابقةٍ أو مخالفٌ لا يُضبط، تقريرُ أعدادٍ فقط؛
- الرقمُ الوطنيّ لا يظهر في تدقيقٍ ولا logs ولا رسالة خطأ ولا ردّ الصفحة، والملفُّ لا يُحفظ.
"""

from __future__ import annotations

import csv
import io
import logging
import re
from unittest import mock

import openpyxl
import pytest
from django.contrib import admin
from django.db import connection
from django.test.utils import CaptureQueriesContext

from clinic.models import HealthRecord
from clinic.needs_care_services import (
    MAX_FILE_BYTES,
    NeedsCareFileError,
    import_needs_care,
    students_needing_care_ids,
)
from core.models import AuditLog, ClassGroup
from tests.conftest import (
    ClassGroupFactory,
    MembershipFactory,
    RoleFactory,
    SchoolFactory,
    StudentEnrollmentFactory,
    UserFactory,
)

pytestmark = pytest.mark.django_db

NID11 = re.compile(r"\d{11}")


def _student(school, *, grade="G10", section="2", active=True):
    """طالبٌ مولَّد في شعبةٍ من المدرسة."""
    role = RoleFactory(school=school, name="student")
    user = UserFactory(full_name="طالب مولّد")
    MembershipFactory(user=user, school=school, role=role)
    level = "sec" if grade != "G7" else "prep"
    group = ClassGroup.objects.filter(school=school, grade=grade, section=section).first()
    group = group or ClassGroupFactory(
        school=school, grade=grade, section=section, level_type=level
    )
    StudentEnrollmentFactory(student=user, class_group=group, is_active=active)
    return user


def _csv(rows) -> bytes:
    out = io.StringIO()
    csv.writer(out).writerows(rows)
    return out.getvalue().encode("utf-8-sig")


def _xlsx(rows) -> bytes:
    wb = openpyxl.Workbook()
    for r in rows:
        wb.active.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def _run(content, school, nurse):
    return import_needs_care(content, school=school, user=nurse)


# ── الحقل والمحدِّد ─────────────────────────────────────────────────────


def test_default_is_false_and_set_only_explicitly(school, student_user):
    rec = HealthRecord.objects.create(student=student_user)
    assert rec.needs_care is False


def test_selector_returns_only_marked_ids(school):
    a, b, c = (_student(school) for _ in range(3))
    HealthRecord.objects.create(student=a, needs_care=True)
    HealthRecord.objects.create(student=b, needs_care=False)  # بلا علامة
    # c بلا سجلٍّ أصلاً
    assert students_needing_care_ids([a.id, b.id, c.id]) == frozenset({a.id})


def test_selector_empty_input_runs_no_query(school):
    with CaptureQueriesContext(connection) as ctx:
        assert students_needing_care_ids([]) == frozenset()
    assert len(ctx) == 0


def test_selector_never_decrypts_a_medical_field(school):
    """المحدِّد يقرأ عمودين غيرَ مشفَّرين: لا `from_db_value` ولا فكّ ولا عمودٌ طبّيّ في SQL."""
    a = _student(school)
    HealthRecord.objects.create(
        student=a, needs_care=True, allergies="سرّ", chronic_diseases="سرّ", medications="سرّ"
    )
    with (
        mock.patch("core.models.decrypt_field", side_effect=AssertionError("فكُّ تشفير!")) as spy,
        CaptureQueriesContext(connection) as ctx,
    ):
        assert students_needing_care_ids([a.id]) == frozenset({a.id})
    spy.assert_not_called()
    sql = " ".join(q["sql"] for q in ctx.captured_queries).lower()
    for col in (
        "allergies",
        "chronic_diseases",
        "medications",
        "blood_type_encrypted",
        "emergency_contact",
        "health_card_number",
    ):
        assert col not in sql


def test_admin_exposes_the_field():
    model_admin = admin.site._registry[HealthRecord]
    fields = [f for _, opts in model_admin.fieldsets for f in opts["fields"]]
    assert "needs_care" in fields
    assert "needs_care" in model_admin.list_display


# ── الخانة الصريحة في شاشة السجلّ ───────────────────────────────────────


def test_nurse_checkbox_is_explicit_both_ways(client_as, nurse_user, school, student_user):
    client = client_as(nurse_user)
    url = f"/clinic/student/{student_user.id}/record/"
    client.post(url, {"needs_care": "1"})
    assert HealthRecord.objects.get(student=student_user).needs_care is True
    client.post(url, {})  # خانةٌ غيرُ مؤشَّرة = لا
    assert HealthRecord.objects.get(student=student_user).needs_care is False


def test_opening_the_record_does_not_mark_anyone(client_as, nurse_user, school, student_user):
    """لا علامةَ تلقائيّة: فتحُ الصفحة أو زيارةٌ أو تشخيصٌ لا يضعها."""
    HealthRecord.objects.create(student=student_user, chronic_diseases="مرض مولّد")
    client_as(nurse_user).get(f"/clinic/student/{student_user.id}/record/")
    assert HealthRecord.objects.get(student=student_user).needs_care is False


# ── الاستيراد ───────────────────────────────────────────────────────────


def test_matches_by_exact_id_and_grade_both_formats(school, nurse_user):
    a = _student(school, grade="G10", section="2")
    b = _student(school, grade="G7", section="1")
    for content in (
        _csv([(a.national_id, "10/2"), (b.national_id, "7")]),
        _xlsx([(a.national_id, "10"), (b.national_id, "G7")]),
    ):
        HealthRecord.objects.all().delete()
        report = _run(content, school, nurse_user)
        assert (report.matched, report.unmatched, report.violating) == (2, 0, 0)
        assert students_needing_care_ids([a.id, b.id]) == frozenset({a.id, b.id})


def test_creates_the_record_when_missing_and_keeps_existing_data(school, nurse_user):
    a = _student(school)
    b = _student(school)
    HealthRecord.objects.create(student=b, allergies="حساسية مولّدة")
    _run(_csv([(a.national_id, "10"), (b.national_id, "10")]), school, nurse_user)
    assert HealthRecord.objects.get(student=a).needs_care is True
    kept = HealthRecord.objects.get(student=b)
    assert kept.needs_care is True and kept.allergies == "حساسية مولّدة"


def test_never_clears_an_existing_mark(school, nurse_user):
    a = _student(school)
    b = _student(school)
    HealthRecord.objects.create(student=b, needs_care=True)
    _run(_csv([(a.national_id, "10")]), school, nurse_user)
    assert HealthRecord.objects.get(student=b).needs_care is True


def test_unmatched_is_counted_and_nothing_is_guessed(school, nurse_user):
    a = _student(school)
    near = str(int(a.national_id) + 5_000_000)  # مجاورٌ لا يطابق: لا تخمينَ بالتقارب
    other = SchoolFactory()
    stranger = _student(other)  # طالبٌ في مدرسةٍ أخرى
    report = _run(_csv([(near, "10"), (stranger.national_id, "10")]), school, nurse_user)
    assert (report.matched, report.unmatched, report.violating) == (0, 2, 0)
    assert not HealthRecord.objects.filter(needs_care=True).exists()


def test_partial_ids_never_match(school, nurse_user):
    """تساوٍ تامٌّ: ولو كان `partial` مسموحاً لغير الممرّض فاستيرادُه لا يحتوي."""
    a = _student(school)
    report = _run(_csv([(a.national_id[:8], "10")]), school, nurse_user)
    assert report.matched == 0 and report.violating == 1


@pytest.mark.parametrize("bad", ["123", "1234567890123", "abcdefghijk", "2876 000 1"])
def test_wrong_shape_is_a_violating_row(school, nurse_user, bad):
    report = _run(_csv([("x", "y"), (bad, "10")]), school, nurse_user)
    assert report.violating == 1 and report.matched == 0


def test_grade_mismatch_is_not_set(school, nurse_user):
    a = _student(school, grade="G10", section="2")
    b = _student(school, grade="G10", section="2")
    c = _student(school, grade="G10", section="2")
    report = _run(
        _csv([(a.national_id, "9"), (b.national_id, "10/3"), (c.national_id, "غير مفهوم")]),
        school,
        nurse_user,
    )
    assert (report.matched, report.violating) == (0, 3)
    assert not HealthRecord.objects.filter(needs_care=True).exists()


def test_student_without_active_enrollment_is_violating(school, nurse_user):
    a = _student(school, active=False)
    report = _run(_csv([(a.national_id, "10")]), school, nurse_user)
    assert (report.matched, report.violating) == (0, 1)


def test_tolerates_numbers_spaces_arabic_digits_header_and_trailing_junk(school, nurse_user):
    a = _student(school)
    b = _student(school)
    c = _student(school)
    arabic = a.national_id.translate(str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩"))
    content = _xlsx(
        [
            ("الرقم الوطني", "الصف"),  # رأس
            (int(b.national_id), 10.0),  # رقمٌ وعددٌ لا نصّ
            (f" {c.national_id[:4]} {c.national_id[4:]} ", " 10 "),  # فراغات داخلية وخارجية
            (arabic, "١٠"),
            (None, None),
            (".", None),  # أسطرٌ ختاميةٌ بحرفٍ واحد تُهمَل
            ("-", None),
        ]
    )
    report = _run(content, school, nurse_user)
    assert (report.matched, report.unmatched, report.violating) == (3, 0, 0)


def test_duplicate_numbers_count_once(school, nurse_user):
    a = _student(school)
    report = _run(
        _csv([(a.national_id, "10"), (a.national_id, "10")]),
        school,
        nurse_user,
    )
    assert report.matched == 1


def test_bad_files_raise_a_generic_error(school, nurse_user):
    for content in (b"", b"PK\x03\x04garbage" + b"x" * 50, b"x" * (MAX_FILE_BYTES + 1)):
        with pytest.raises(NeedsCareFileError) as exc:
            _run(content, school, nurse_user)
        assert not NID11.search(str(exc.value))


# ── الخصوصيّة: لا رقمَ في أيّ أثر ───────────────────────────────────────


def test_national_id_never_reaches_audit_or_logs(school, nurse_user, caplog):
    students = [_student(school) for _ in range(3)]
    ids = [s.national_id for s in students]
    rows = [(i, "10") for i in ids] + [("28769999999", "10"), ("12", "10")]
    with caplog.at_level(logging.DEBUG):
        _run(_csv(rows), school, nurse_user)
    haystack = caplog.text + "\n".join(
        " ".join(
            str(getattr(r, f) or "")
            for f in ("object_id", "object_repr", "changes", "user_agent", "model_name")
        )
        for r in AuditLog.objects.all()
    )
    for nid in [*ids, "28769999999"]:
        assert nid not in haystack
    # تدقيقٌ إجماليٌّ واحدٌ بأعدادٍ فقط، لا معرّفَ طالب
    entry = AuditLog.objects.filter(model_name="HealthRecord", user=nurse_user).latest("timestamp")
    assert entry.changes == {"matched": 3, "unmatched": 1, "violating": 1}
    assert entry.object_id == ""
    for s in students:
        assert str(s.id) not in f"{entry.object_repr} {entry.changes}"


def test_import_writes_no_per_student_audit_rows(school, nurse_user):
    students = [_student(school) for _ in range(4)]
    before = AuditLog.objects.count()
    _run(_csv([(s.national_id, "10") for s in students]), school, nurse_user)
    assert AuditLog.objects.count() == before + 1


# ── الشاشة ──────────────────────────────────────────────────────────────


def _upload(content: bytes, name="x.xlsx"):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(name, content)


def test_screen_is_nurse_only_and_shows_counts_not_numbers(
    client_as, nurse_user, teacher_user, school
):
    a = _student(school)
    assert client_as(teacher_user).get("/clinic/needs-care/import/").status_code in (302, 403)
    client = client_as(nurse_user)
    assert client.get("/clinic/needs-care/import/").status_code == 200
    resp = client.post(
        "/clinic/needs-care/import/",
        {"needs_care_file": _upload(_xlsx([(a.national_id, "10"), ("28769999999", "10")]))},
    )
    assert resp.status_code == 200
    report = resp.context["report"]
    assert (report.matched, report.unmatched, report.violating) == (1, 1, 0)
    body = resp.content.decode()
    assert a.national_id not in body and "28769999999" not in body
    assert HealthRecord.objects.get(student=a).needs_care is True


def test_screen_reports_a_bad_file_without_its_content(client_as, nurse_user, school):
    client = client_as(nurse_user)
    resp = client.post(
        "/clinic/needs-care/import/",
        {"needs_care_file": _upload(b"PK\x03\x04" + b"28769999999" * 5)},
    )
    assert resp.status_code == 200 and resp.context["error"]
    assert "28769999999" not in resp.content.decode()
    resp = client.post("/clinic/needs-care/import/", {})
    assert resp.context["error"]


def test_screen_stores_no_file(client_as, nurse_user, school, tmp_path, settings):
    settings.MEDIA_ROOT = str(tmp_path)
    a = _student(school)
    client_as(nurse_user).post(
        "/clinic/needs-care/import/",
        {"needs_care_file": _upload(_xlsx([(a.national_id, "10")]), name="students.xlsx")},
    )
    assert list(tmp_path.rglob("*")) == []


# ── الوصول من قائمة «الخدمات» ────────────────────────────────────────────


def _services_menu(html: str) -> str:
    """قائمةُ «الخدمات» المنسدلة من الصفحة."""
    m = re.search(r'id="m-services".*?\n</div>', html, re.S)
    assert m, "قائمةُ الخدمات غائبة"
    return m.group(0)


def test_principal_reaches_the_import_from_the_services_menu(client_as, principal_user):
    """المديرُ يجد «علامة المراعاة» تحت «العيادة المدرسية» في «الخدمات» كبقيّة القوائم بأقسامها."""
    menu = _services_menu(client_as(principal_user).get("/clinic/").content.decode())
    assert 'class="sd-label">العيادة المدرسية<' in menu
    assert 'href="/clinic/needs-care/import/"' in menu
    assert menu.index("العيادة المدرسية<") < menu.index("/clinic/needs-care/import/")


def test_services_menu_hides_the_import_from_who_cannot_open_it(client_as, teacher_user):
    # المعلّمُ لا يُرسم له قسمُ الخدمات أصلاً؛ فالرابطُ غائبٌ عن الصفحة كلّها.
    html = client_as(teacher_user).get("/dashboard/").content.decode()
    assert "/clinic/needs-care/import/" not in html
