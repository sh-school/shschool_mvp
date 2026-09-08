"""نقلُ سجلّ الأقسام بين قاعدتين — `core.management.commands.sync_departments`.

القسمُ قرارٌ إداريٌّ لا اشتقاقٌ من الجدول (قرار 2026-09-06)، فنقلُه إلى الإنتاج
يجب أن يحمل القرارَ كما هو. وهذه الاختبارات تحرس ثلاثةَ أشياء: أنّ الجولةَ
كاملةً لا تُغيّر شيئاً حين تكون القاعدتان متّفقتين، وأنّها تُعيد ما نقص، وأنّ
سطراً واحداً متعذّراً يوقف الكتابةَ كلَّها.
"""

import base64
import gzip
import json
from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from core.models import Department, Membership
from tests.conftest import MembershipFactory, RoleFactory, SchoolFactory, UserFactory


def _payload(school):
    """حمولةُ التصدير نصّاً مفكوكاً — كي تُقرأ وتُعدَّل في الاختبار."""
    out = StringIO()
    call_command("sync_departments", "export", school=school.code, stdout=out)
    return json.loads(out.getvalue())


def _b64(data):
    return base64.b64encode(gzip.compress(json.dumps(data).encode("utf-8"), 9)).decode("ascii")


def _run(school, data, **options):
    err = StringIO()
    call_command(
        "sync_departments", "import", school=school.code, b64=_b64(data), stderr=err, **options
    )
    return err.getvalue()


@pytest.fixture
def staffed_school(db):
    """مدرسةٌ بقسمين ومعلّمَين مربوطَين بهما."""
    school = SchoolFactory()
    role = RoleFactory(school=school, name="teacher")
    math = Department.objects.create(school=school, code="math", name="الرياضيات", sort_order=2)
    arts = Department.objects.create(
        school=school, code="arts", name="الفنون البصرية", sort_order=12
    )
    for name, department in (("معلّم الرياضيات", math), ("معلّم الفنون", arts)):
        user = UserFactory(full_name=name)
        MembershipFactory(user=user, school=school, role=role, department_obj=department)
    return school


@pytest.mark.django_db
def test_a_round_trip_onto_itself_changes_nothing(staffed_school):
    """تصديرٌ ثمّ استيرادٌ على القاعدة نفسها: لا إنشاءَ ولا تعديلَ ولا نقل."""
    report = _run(staffed_school, _payload(staffed_school), apply=True)

    assert "إنشاءُ قسم 0" in report
    assert "تعديلُ قسم 0" in report
    assert "نقلُ معلّم 0" in report


@pytest.mark.django_db
def test_a_missing_department_comes_back_with_its_members(staffed_school):
    """قسمٌ ذهب من الهدف يعود باسمه وترتيبه وأعضائه — وهذا هو حالُ الإنتاج."""
    data = _payload(staffed_school)
    gone = Department.objects.get(school=staffed_school, code="arts")
    Membership.objects.filter(school=staffed_school, department_obj=gone).update(
        department_obj=None
    )
    gone.delete()

    _run(staffed_school, data, apply=True)

    back = Department.objects.get(school=staffed_school, code="arts")
    assert back.name == "الفنون البصرية"
    assert back.sort_order == 12
    assert Membership.objects.filter(school=staffed_school, department_obj=back).count() == 1


@pytest.mark.django_db
def test_a_renamed_department_is_put_back_as_the_file_says(staffed_school):
    """الاسمُ والترتيبُ يتبعان الملفّ — فترتيبُ الورقة لا يتبدّل بين قاعدتين."""
    data = _payload(staffed_school)
    Department.objects.filter(school=staffed_school, code="arts").update(
        name="الفنون", sort_order=99
    )

    _run(staffed_school, data, apply=True)

    fixed = Department.objects.get(school=staffed_school, code="arts")
    assert (fixed.name, fixed.sort_order) == ("الفنون البصرية", 12)


@pytest.mark.django_db
def test_a_dry_run_writes_nothing(staffed_school):
    """بلا `--apply` يُعرض ما سيقع ولا يقع."""
    data = _payload(staffed_school)
    Department.objects.filter(school=staffed_school, code="arts").update(sort_order=99)

    report = _run(staffed_school, data)

    assert "عرضٌ فقط" in report
    assert Department.objects.get(school=staffed_school, code="arts").sort_order == 99


@pytest.mark.django_db
def test_one_unknown_name_stops_the_whole_write(staffed_school):
    """اسمٌ لا يُعرف في الهدف يوقف النقلَ كلَّه — لا نصفَه."""
    data = _payload(staffed_school)
    data["members"].append({"teacher": "معلّمٌ لا وجودَ له", "code": "math"})
    Department.objects.filter(school=staffed_school, code="arts").update(sort_order=99)

    with pytest.raises(CommandError):
        _run(staffed_school, data, apply=True)

    assert Department.objects.get(school=staffed_school, code="arts").sort_order == 99


@pytest.mark.django_db
def test_the_report_names_those_without_a_department(staffed_school):
    """التقريرُ يسمّي من لا قسمَ له — فهم من يقعون في الاشتقاق على الورقة."""
    role = RoleFactory(school=staffed_school, name="teacher")
    MembershipFactory(user=UserFactory(full_name="معلّمٌ بلا قسم"), school=staffed_school, role=role)

    out = StringIO()
    call_command("sync_departments", "report", school=staffed_school.code, stdout=out)

    assert "بلا قسمٍ مسجَّل: 1" in out.getvalue()
    assert "معلّمٌ بلا قسم" in out.getvalue()


@pytest.mark.django_db
def test_an_emptied_legacy_department_is_switched_off_not_deleted(staffed_school):
    """رمزٌ قديمٌ حلّ محلَّه رمزٌ جديد يُطفأ بعد أن يخلو — ولا يُحذف."""
    legacy = Department.objects.create(
        school=staffed_school, code="islamic", name="التربية الإسلامية", sort_order=5
    )
    data = _payload(staffed_school)
    data["departments"] = [d for d in data["departments"] if d["code"] != "islamic"]

    _run(staffed_school, data, apply=True, retire_extra=True)

    legacy.refresh_from_db()
    assert legacy.is_active is False


@pytest.mark.django_db
def test_a_legacy_department_with_members_stays_on(staffed_school):
    """ولا يُطفأ قسمٌ ما زال فيه أحد — الإطفاءُ لمن خلا لا لمن بقي."""
    role = RoleFactory(school=staffed_school, name="teacher")
    legacy = Department.objects.create(
        school=staffed_school, code="islamic", name="التربية الإسلامية", sort_order=5
    )
    MembershipFactory(
        user=UserFactory(full_name="معلّمُ الشريعة"),
        school=staffed_school,
        role=role,
        department_obj=legacy,
    )
    data = _payload(staffed_school)
    data["departments"] = [d for d in data["departments"] if d["code"] != "islamic"]
    data["members"] = [m for m in data["members"] if m["teacher"] != "معلّمُ الشريعة"]

    _run(staffed_school, data, apply=True, retire_extra=True)

    legacy.refresh_from_db()
    assert legacy.is_active is True
