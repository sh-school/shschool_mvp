"""حقنُ الصيغ في Excel (CWE-1236) — اسمٌ يبدأ بـ``=`` لا يُصدَّر صيغةً قابلةً للتنفيذ.

`neutralize_formula_value` تُسبق القيمةَ بـ``'`` قبل كتابتها في الخليّة، فيقرؤها
Excel نصّاً حرفيّاً. الاختبار الوحدويّ يغطّي الدالّة نفسَها، والتكامليّ يثبت أنّ
تصدير قائمة الطلاب فعلاً لا يترك اسماً خبيثاً صالحاً للتنفيذ في الملفّ الناتج.
"""

import io

import openpyxl
import pytest
from django.urls import reverse

from core.excel_safety import neutralize_formula_value
from tests.conftest import ClassGroupFactory, MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db


class TestNeutralizeFormulaValue:
    @pytest.mark.parametrize("prefix", ["=", "+", "-", "@"])
    def test_a_leading_formula_prefix_is_neutralized(self, prefix):
        malicious = f"{prefix}cmd|'/c calc'!A1"
        assert neutralize_formula_value(malicious) == "'" + malicious

    def test_leading_whitespace_before_the_prefix_is_still_caught(self):
        assert neutralize_formula_value("  =SUM(A1:A9)") == "'  =SUM(A1:A9)"

    def test_an_ordinary_name_passes_through_unchanged(self):
        assert neutralize_formula_value("سفيان مسيف") == "سفيان مسيف"

    @pytest.mark.parametrize("value", [None, 7, 3.5])
    def test_non_string_values_pass_through_unchanged(self, value):
        assert neutralize_formula_value(value) == value


class TestStudentExportNeutralizesRealFiles:
    def test_a_malicious_full_name_is_not_a_live_formula_in_the_exported_file(
        self, client_as, principal_user, school, seeded_calendar
    ):
        klass = ClassGroupFactory(school=school, academic_year=seeded_calendar)
        student = UserFactory(full_name="=cmd|'/c calc'!A1", national_id="99900000777")
        MembershipFactory(
            user=student, school=school, role=RoleFactory(school=school, name="student")
        )
        from tests.conftest import StudentEnrollmentFactory

        StudentEnrollmentFactory(student=student, class_group=klass)

        resp = client_as(principal_user).get(reverse("student_affairs:student_export"))
        assert resp.status_code == 200

        wb = openpyxl.load_workbook(io.BytesIO(resp.content))
        ws = wb.active
        # العمود الثاني هو «الاسم الكامل» (row_data[1] في العرض) — الأوّل رقمُ التسلسل
        names = [row[1].value for row in ws.iter_rows() if len(row) > 1]
        matches = [v for v in names if isinstance(v, str) and "cmd|" in v]
        assert matches, "الاسم الخبيث يجب أن يظهر في الملفّ — مُحيَّداً لا محذوفاً"
        assert all(v.startswith("'") for v in matches), (
            "خليّةٌ تبدأ بـ= بلا اقتباسٍ سابق تُنفَّذ صيغةً عند فتح الملفّ في Excel"
        )
