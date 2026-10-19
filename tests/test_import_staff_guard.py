"""W-20261008-024: الاستيرادُ لا يمسّ حسابَ موظّف — في المسارين (القالب القديم والوزاريّ).

الرقمُ الشخصيّ في الملف يطابق حساباً قائماً ويكتب فوقه؛ فلو كان حسابَ معلّمٍ
أو مديرٍ لتبدّلت بياناتُه وأُضيفت له عضويّةُ طالب. يُتخطّى بسطرٍ مستور الرقم،
وحسابُ الطالب/الوليّ يُحدَّث كما كان، والجديدُ يُنشأ.
"""

import io

import openpyxl
import pytest
from django.core.files.uploadedfile import SimpleUploadedFile

from core.import_staff_guard import mask_nid
from core.models import CustomUser, Membership
from core.models.audit import AuditLog
from core.services import import_result_context, process_student_import
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

# أرقامٌ وهميّةٌ صريحة.
STAFF_NID = "39900000101"
OTHER_STAFF_NID = "39900000102"
STUDENT_NID = "39900000103"
NEW_NID = "39900000104"
PARENT_NID = "29900000105"


def _upload(rows, header) -> SimpleUploadedFile:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(header)
    for r in rows:
        ws.append(r)
    buf = io.BytesIO()
    wb.save(buf)
    return SimpleUploadedFile("f.xlsx", buf.getvalue())


LEGACY_HEADER = ["رأس"] * 11
MINISTRY_HEADER = ["الرقم", "الاسم", "رقم الهاتف", "رقم ولي الامر", "اسم ولي الامر"]


def _legacy_row(nid, name, parent_nid="", parent_name=""):
    return [nid, name, "", "", "", "", parent_nid, parent_name, "", "", "father"]


def _ministry_row(nid, name, parent_nid="", parent_name=""):
    return [nid, name, "55500000", parent_nid, parent_name]


def _snapshot(user):
    user.refresh_from_db()
    return (
        user.full_name,
        user.email,
        user.get_phone_decrypted(),
        sorted(
            Membership.objects.filter(user=user).values_list("role__name", "school_id", "is_active")
        ),
    )


@pytest.fixture
def roles(db, school):
    return RoleFactory(school=school, name="student"), RoleFactory(school=school, name="parent")


@pytest.fixture
def staff(db, school):
    user = UserFactory(national_id=STAFF_NID, full_name="معلم قائم", email="t@example.test")
    MembershipFactory(user=user, school=school, role=RoleFactory(school=school, name="teacher"))
    return user


@pytest.fixture(params=["legacy", "ministry"])
def path(request):
    header = LEGACY_HEADER if request.param == "legacy" else MINISTRY_HEADER
    row = _legacy_row if request.param == "legacy" else _ministry_row
    return lambda rows: _upload([row(*r) for r in rows], header)


def test_staff_student_row_is_skipped_untouched(school, roles, staff, path):
    before = _snapshot(staff)
    result = process_student_import(path([(STAFF_NID, "اسم من الملف")]), school, "2026-2027")
    assert _snapshot(staff) == before
    assert result["staff_skipped"] == 1
    assert any(mask_nid(STAFF_NID) in line for line in result["errors"])
    assert not any(STAFF_NID in line for line in result["errors"])  # الرقمُ كاملاً لا يظهر
    assert not Membership.objects.filter(user=staff, role__name="student").exists()


def test_staff_who_is_a_parent_is_skipped_for_manual_linking(school, roles, staff, path):
    before = _snapshot(staff)
    result = process_student_import(
        path([(NEW_NID, "طالب جديد", STAFF_NID, "اسم من الملف")]), school, "2026-2027"
    )
    assert _snapshot(staff) == before
    assert result["staff_skipped"] == 1
    assert result["links_created"] == 0
    assert any("يدويّاً" in line for line in result["errors"])
    # الطالبُ الجديد يُنشأ كما كان
    assert CustomUser.objects.filter(national_id=NEW_NID).exists()


def test_any_staff_role_blocks_even_with_student_membership(school, roles, staff, path):
    MembershipFactory(user=staff, school=school, role=roles[0])
    before = _snapshot(staff)
    result = process_student_import(path([(STAFF_NID, "x")]), school, "2026-2027")
    assert _snapshot(staff) == before
    assert result["staff_skipped"] == 1


def test_student_and_parent_accounts_update_as_before(school, roles, path):
    old = UserFactory(national_id=STUDENT_NID, full_name="")
    MembershipFactory(user=old, school=school, role=roles[0])
    result = process_student_import(
        path([(STUDENT_NID, "اسم الطالب", PARENT_NID, "اسم الوليّ"), (NEW_NID, "طالب جديد")]),
        school,
        "2026-2027",
    )
    assert result["staff_skipped"] == 0
    old.refresh_from_db()
    assert old.full_name == "اسم الطالب"
    assert CustomUser.objects.filter(national_id=NEW_NID).exists()
    assert Membership.objects.filter(user__national_id=PARENT_NID, role__name="parent").exists()


def test_other_rows_proceed_when_one_is_staff(school, roles, staff, path):
    result = process_student_import(
        path([(STAFF_NID, "x"), (NEW_NID, "طالب جديد")]), school, "2026-2027"
    )
    assert result["staff_skipped"] == 1
    assert CustomUser.objects.filter(national_id=NEW_NID).exists()


def test_audit_log_records_count_without_ids(school, roles, staff, principal_user, path):
    result = process_student_import(path([(STAFF_NID, "x")]), school, "2026-2027")
    import_result_context(principal_user, school, result)
    entry = AuditLog.objects.get(changes__event="import_staff_accounts_skipped")
    assert entry.changes == {"event": "import_staff_accounts_skipped", "count": 1}
    assert STAFF_NID not in entry.object_repr


def test_mask_nid_keeps_only_last_three():
    assert mask_nid("39900000101") == "********101"
