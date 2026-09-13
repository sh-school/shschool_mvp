"""تصحيحُ الأرقام الشخصيّة من كشف الكادر — بالرقم الوظيفيّ، وبأثرٍ يُقرأ."""

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from core.auth_identity import resolve_user
from core.management.commands.correct_identity_from_register import _mask
from core.models import CustomUser
from core.models.audit import AuditLog
from tests.conftest import UserFactory

pytestmark = pytest.mark.django_db


def _register(tmp_path, rows):
    """كشفٌ وزاريٌّ مصغَّر: الرقم الشخصيّ، الاسم، الرقم الوظيفيّ، المسمّى، الجوّال."""
    import openpyxl

    book = openpyxl.Workbook()
    sheet = book.active
    sheet.title = "الوزارية"
    sheet.append(["م", "الرقم الشخصى", "الاسم", "رقم الموظف", "مسمى الوظيفة", "رقم الجوال"])
    for index, row in enumerate(rows, 1):
        sheet.append([index, *row])
    path = tmp_path / "كشف.xlsx"
    book.save(path)
    return str(path)


def _plan(tmp_path, rows, capsys):
    call_command("correct_identity_from_register", file=_register(tmp_path, rows))
    return capsys.readouterr().out


class TestMask:
    def test_the_mask_shows_enough_to_tell_apart_and_not_enough_to_identify(self):
        masked = _mask("28100000001")
        assert masked.startswith("281")
        assert masked.endswith("01")
        assert "28100000001" not in masked

    def test_a_short_value_is_hidden_entirely(self):
        assert _mask("123") == "***"


class TestPlanning:
    def test_the_employee_number_identifies_and_the_national_id_is_corrected(
        self, db, school, tmp_path, capsys
    ):
        user = UserFactory(full_name="سالم الأوّل", national_id="28100000001")
        user.employee_number = "111111"
        user.save(update_fields=["employee_number"])

        out = _plan(
            tmp_path, [["28100000002", "سالم الأوّل", "111111", "محاسب", "97455500001"]], capsys
        )

        assert "تصحيحاتٌ مقترحة: 1" in out
        assert "بالرقم الوظيفيّ" in out
        assert "281******01 ← 281******02" in out

    def test_nothing_is_proposed_when_the_database_already_agrees(
        self, db, school, tmp_path, capsys
    ):
        user = UserFactory(full_name="سالم الثاني", national_id="28100000003")
        user.employee_number = "222222"
        user.save(update_fields=["employee_number"])

        out = _plan(
            tmp_path, [["28100000003", "سالم الثاني", "222222", "محاسب", "97455500002"]], capsys
        )
        assert "لا رقمَ يحتاج تصحيحاً" in out

    def test_a_person_without_an_employee_number_is_matched_by_a_unique_name(
        self, db, school, tmp_path, capsys
    ):
        """الرقمُ الملفَّقُ لا يُطابَق به — ولا يبقى الشخصُ بلا علاج."""
        UserFactory(full_name="خالد الفريد", national_id="66666666666")

        out = _plan(
            tmp_path,
            [["30100000004", "خالد الفريد", "333333", "معلم رياضيات", "97455500003"]],
            capsys,
        )

        assert "بالاسم الفريد" in out
        assert "الرقم الوظيفيّ: (فارغ) ← 333333" in out

    def test_a_repeated_name_is_never_matched(self, db, school, tmp_path, capsys):
        """اسمان متطابقان في القاعدة — والتخمينُ هنا يُغيّر هويّةَ الشخص الخطأ."""
        UserFactory(full_name="محمد المكرّر", national_id="66666666661")
        UserFactory(full_name="محمد المكرّر", national_id="66666666662")

        out = _plan(
            tmp_path, [["30100000005", "محمد المكرّر", "444444", "محاسب", "97455500004"]], capsys
        )
        assert "لا رقمَ يحتاج تصحيحاً" in out


class TestApplying:
    def _staff(self, name, national_id, employee_number=""):
        user = UserFactory(full_name=name, national_id=national_id)
        if employee_number:
            user.employee_number = employee_number
            user.save(update_fields=["employee_number"])
        return user

    def test_the_correction_is_written_and_the_door_still_opens(self, db, school, tmp_path):
        """أخطرُ تفصيلةٍ في العمليّة: البصمةُ تُعاد مع الرقم.

        `update_fields` لا يحفظ إلّا ما سُمّي — ونسيانُ البصمة يترك بصمةً قديمةً
        على رقمٍ جديد، فيُغلق البابُ في وجه صاحبه بلا رسالةِ خطأ.
        """
        user = self._staff("سالم المصحَّح", "28100000010", "555555")
        path = _register(
            tmp_path, [["28100000011", "سالم المصحَّح", "555555", "محاسب", "97455500005"]]
        )

        call_command("correct_identity_from_register", file=path, apply=True)

        user.refresh_from_db()
        assert user.national_id == "28100000011"
        assert resolve_user("28100000011") == user
        assert resolve_user("28100000010") is None

    def test_every_write_leaves_an_audit_row_with_masked_numbers(self, db, school, tmp_path):
        user = self._staff("سالم المدقَّق", "28100000020", "666666")
        path = _register(
            tmp_path, [["28100000021", "سالم المدقَّق", "666666", "محاسب", "97455500006"]]
        )

        call_command("correct_identity_from_register", file=path, apply=True)

        entry = AuditLog.objects.filter(object_id=str(user.pk), action="update").latest("timestamp")
        assert entry.model_name == "CustomUser"
        assert entry.changes["national_id"] == ["281******20", "281******21"]
        assert "كشف الكادر" in entry.changes["reason"]
        # ولا رقمَ كاملاً في سجلٍّ يُصدَّر.
        assert "28100000021" not in str(entry.changes)

    def test_whoever_needs_a_freed_number_waits_for_it(self, db, school, tmp_path):
        """الترتيبُ يُحلّ ولا يُفترض: من يأخذ رقماً مشغولاً يأتي بعد من يُفرّغه."""
        holder = self._staff("حاملُ الرقم", "28100000030", "777777")
        waiting = self._staff("منتظرُ الرقم", "28100000031", "888888")
        path = _register(
            tmp_path,
            [
                # الحاملُ ينتقل إلى رقمٍ شاغر، فيُفرّغ رقمَه للمنتظر.
                ["28100000032", "حاملُ الرقم", "777777", "محاسب", "97455500007"],
                ["28100000030", "منتظرُ الرقم", "888888", "محاسب", "97455500008"],
            ],
        )

        call_command("correct_identity_from_register", file=path, apply=True)

        holder.refresh_from_db()
        waiting.refresh_from_db()
        assert holder.national_id == "28100000032"
        assert waiting.national_id == "28100000030"

    def test_a_closed_cycle_stops_the_command(self, db, school, tmp_path):
        """تبادُلُ رقمين لا يُحَلّ بترتيب — ويُقال ذلك بدل أن يُكسر القيد."""
        self._staff("الأوّل", "28100000040", "991111")
        self._staff("الثاني", "28100000041", "992222")
        path = _register(
            tmp_path,
            [
                ["28100000041", "الأوّل", "991111", "محاسب", "97455500009"],
                ["28100000040", "الثاني", "992222", "محاسب", "97455500010"],
            ],
        )

        with pytest.raises(CommandError, match="حلقةٌ مغلقة"):
            call_command("correct_identity_from_register", file=path, apply=True)

        assert CustomUser.objects.filter(national_id="28100000040").exists()
        assert CustomUser.objects.filter(national_id="28100000041").exists()

    def test_nothing_is_written_without_apply(self, db, school, tmp_path):
        user = self._staff("سالم الآمن", "28100000050", "993333")
        path = _register(
            tmp_path, [["28100000051", "سالم الآمن", "993333", "محاسب", "97455500011"]]
        )

        call_command("correct_identity_from_register", file=path)

        user.refresh_from_db()
        assert user.national_id == "28100000050"
        # إشارةُ التدقيق تكتب سطرَ «تعديل» عند كلّ حفظِ مستخدم، فالتأكيدُ على
        # سببِ الأمر لا على وجود سطرٍ ما — وإلّا أفشلَه سطرُ التجهيز نفسُه.
        reasons = [
            (entry.changes or {}).get("reason", "")
            for entry in AuditLog.objects.filter(object_id=str(user.pk))
        ]
        assert not any("كشف الكادر" in reason for reason in reasons)


class TestThePackedRegister:
    """قاعدةُ الإنتاج لا يصلها الملفّ — والتصحيحُ يسبق الكشفَ ضرورةً."""

    def test_the_packed_rows_correct_exactly_what_the_file_corrects(
        self, db, school, tmp_path, capsys
    ):
        """الحزمةُ حزمةُ `import_staff_register --emit-b64` نفسُها لا صيغةٌ ثانية."""
        from core.management.commands.import_staff_register import Command as StaffCommand
        from core.management.commands.import_staff_register import _pack

        UserFactory(full_name="سالمٌ الأوّل", national_id="28100000001", employee_number="7001")
        path = _register(tmp_path, [["28100000009", "سالمٌ الأوّل", "7001", "معلم", "55500001"]])
        packed = _pack(StaffCommand()._read(path, ""))

        call_command("correct_identity_from_register", rows_b64=packed, apply=True)

        assert CustomUser.objects.get(employee_number="7001").national_id == "28100000009"

    def test_neither_input_is_refused(self, db, school):
        """صمتُ الأمر عن مصدرِه أخطرُ من رفضه: يقرأ ملفّاً فارغاً ويقول لا تصحيح."""
        with pytest.raises(CommandError, match="واحداً منهما"):
            call_command("correct_identity_from_register")

    def test_both_inputs_at_once_are_refused(self, db, school, tmp_path):
        path = _register(tmp_path, [["28100000009", "سالم", "7001", "معلم", "55500001"]])
        with pytest.raises(CommandError, match="واحداً منهما"):
            call_command("correct_identity_from_register", file=path, rows_b64="x")

    def test_a_payload_that_is_not_a_packed_register_is_refused(self, db, school):
        with pytest.raises(CommandError):
            call_command("correct_identity_from_register", rows_b64="ليست حزمة")
