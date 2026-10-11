"""[SCHEDULE] سقفُ الأولى الشخصيّ قرارٌ إداريّ يُحرَّر من الأدمن (W-20261010-033).

كانت استثناءاتُ المالك (أربعٌ لاثني عشرَ معلّماً) في ملفٍّ خارج المستودع لا يراه الأدمن، فسأل المالك «لا يوجد
أقصى أولى؟». صار لها عمودٌ nullable (فارغ = العامّ) كتوأمه `max_last_periods`: يُحرَّر من الأدمن بتدقيقٍ قبل/بعد،
ولا يراه المعلّم، ويقرؤه المولّدُ والمُقيِّمُ من المصدر نفسه.
"""

import json
import re
from io import StringIO

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.urls import reverse

from core.models import AuditLog
from operations.models import TeacherPreference
from operations.schedule_evaluator import admin_first_caps, evaluate_slots
from operations.scheduler_v2 import runner
from tests.conftest import MembershipFactory, RoleFactory, UserFactory
from tests.test_schedule_evaluator import YEAR, run_scene  # noqa: F401  (fixture)

pytestmark = pytest.mark.django_db
EVENT = "teacher_first_period_cap_changed"


@pytest.fixture
def superuser(developer_user):
    developer_user.is_staff = developer_user.is_superuser = True
    developer_user.must_change_password = False
    developer_user.save()
    return developer_user


def _pref(school, teacher_id, cap=None):
    return TeacherPreference.objects.create(
        teacher_id=teacher_id, school=school, academic_year=YEAR, max_first_periods=cap
    )


# ── النموذج والمدى ────────────────────────────────────────────────


def test_the_default_is_the_general_cap_not_a_number(school):
    pref = _pref(school, UserFactory().pk)

    assert pref.max_first_periods is None


@pytest.mark.parametrize("value, ok", [(1, False), (2, True), (4, True), (5, True), (6, False)])
def test_the_range_is_the_general_cap_to_five(school, value, ok):
    pref = _pref(school, UserFactory().pk)
    pref.max_first_periods = value

    if ok:
        pref.full_clean(exclude=["teacher", "school"])
    else:
        with pytest.raises(ValidationError):
            pref.full_clean(exclude=["teacher", "school"])


def test_the_cap_is_not_a_teacher_editable_field():
    assert "max_first_periods" not in TeacherPreference.TEACHER_EDITABLE_FIELDS


def test_the_teacher_page_neither_shows_nor_accepts_it(client, school):
    teacher = UserFactory()
    MembershipFactory(user=teacher, school=school, role=RoleFactory(school=school, name="teacher"))
    pref = _pref(school, teacher.pk, cap=4)
    client.force_login(teacher)
    url = reverse("teacher_preferences") + f"?year={YEAR}"

    body = client.get(url).content.decode()
    client.post(
        url,
        {"max_daily_periods": "5", "max_consecutive": "", "max_gap": "", "max_first_periods": "2"},
    )

    pref.refresh_from_db()
    assert "max_first_periods" not in body and "أقصى حصص أولى" not in body
    assert pref.max_first_periods == 4


# ── الأدمن والتدقيق ───────────────────────────────────────────────


def _admin_post(client, pref, school, **extra):
    url = reverse("admin:operations_teacherpreference_change", args=[pref.pk])
    data = {
        "teacher": pref.teacher_id,
        "school": school.pk,
        "academic_year": YEAR,
        "max_daily_periods": 5,
        "max_first_periods": 2,
        "max_last_periods": 2,
        "notes": "",
    }
    data.update(extra)
    return client.post(url, data, follow=True)


def test_the_admin_edit_is_audited_without_the_teacher_name(client, superuser, school):
    teacher = UserFactory(full_name="معلّمٌ له استثناء")
    pref = _pref(school, teacher.pk)
    client.force_login(superuser)

    _admin_post(client, pref, school, max_first_periods=4)

    pref.refresh_from_db()
    assert pref.max_first_periods == 4
    entry = AuditLog.objects.get(changes__event=EVENT)
    assert (entry.changes["before"], entry.changes["after"]) == (None, 4)
    assert entry.object_id == str(pref.pk) and teacher.full_name not in entry.object_repr


def test_an_admin_save_that_leaves_the_cap_alone_writes_no_audit(client, superuser, school):
    pref = _pref(school, UserFactory().pk, cap=4)
    client.force_login(superuser)

    _admin_post(client, pref, school, max_first_periods=4)

    assert not AuditLog.objects.filter(changes__event=EVENT).exists()


def test_the_field_is_in_the_admin_list_and_form(client, superuser, school):
    pref = _pref(school, UserFactory().pk, cap=3)
    client.force_login(superuser)

    listing = client.get(reverse("admin:operations_teacherpreference_changelist")).content.decode()
    form = client.get(
        reverse("admin:operations_teacherpreference_change", args=[pref.pk])
    ).content.decode()

    assert "أقصى حصص أولى أسبوعيّاً" in listing and 'name="max_first_periods"' in form


# ── القراءة في المولّد والمُقيِّم ──────────────────────────────────


def test_only_in_range_values_above_the_general_cap_are_read(school):
    kept = UserFactory().pk
    _pref(school, kept, cap=4)
    _pref(school, UserFactory().pk, cap=None)
    _pref(school, UserFactory().pk, cap=2)  # يساوي العامّ فلا تخفيف
    _pref(school, UserFactory().pk, cap=1)  # خارج المدى (كتابةٌ مباشرة) = كغيابه
    _pref(school, UserFactory().pk, cap=9)

    assert admin_first_caps(school, YEAR) == {str(kept): 4}


def test_a_stored_cap_reaches_the_solver_options_and_wins_over_a_lower_file_value(school):
    teacher = str(UserFactory().pk)
    _pref(school, teacher, cap=4)
    file_config = runner.SolverConfig(
        relaxations=(("first_cap_override", {teacher: 3, "other": 4}),)
    )

    merged = runner.with_admin_first_caps(file_config, school, YEAR)

    assert dict(merged.relaxations)["first_cap_override"] == {teacher: 4, "other": 4}
    options = runner.options_from_relaxations(dict(merged.relaxations))
    assert dict(options["first_cap_override"])[teacher] == 4


def test_a_higher_file_value_still_wins_over_a_lower_stored_one(school):
    teacher = str(UserFactory().pk)
    _pref(school, teacher, cap=3)
    config = runner.SolverConfig(relaxations=(("first_cap_override", {teacher: 5}),))

    merged = runner.with_admin_first_caps(config, school, YEAR)

    assert dict(merged.relaxations)["first_cap_override"][teacher] == 5


def test_without_stored_caps_the_config_is_untouched(school):
    config = runner.SolverConfig(relaxations=(("run_cap", 2),))

    assert runner.with_admin_first_caps(config, school, YEAR) is config


def test_the_evaluator_judges_a_teacher_by_the_stored_cap(run_scene):  # noqa: F811
    slots = run_scene.slots((0, 0, 1), (1, 1, 1), (2, 2, 1))
    strict = evaluate_slots(run_scene.school, YEAR, slots)
    _pref(run_scene.school, run_scene.teacher, cap=3)

    stored = evaluate_slots(run_scene.school, YEAR, slots)

    assert strict.hard_breaches.get("HC22") == 1
    assert "HC22" not in stored.hard_breaches and stored.eased == {"HC22": 1}


def test_an_empty_field_gives_the_general_cap_exactly(run_scene):  # noqa: F811
    _pref(run_scene.school, run_scene.teacher, cap=None)

    result = evaluate_slots(
        run_scene.school, YEAR, run_scene.slots((0, 0, 1), (1, 1, 1), (2, 2, 1))
    )

    assert result.hard_breaches.get("HC22") == 1


def test_a_cap_stored_for_another_teacher_eases_nothing(run_scene):  # noqa: F811
    _pref(run_scene.school, run_scene.other, cap=4)

    result = evaluate_slots(
        run_scene.school, YEAR, run_scene.slots((0, 0, 1), (1, 1, 1), (2, 2, 1))
    )

    assert result.hard_breaches.get("HC22") == 1 and result.eased == {}


# ── أمر النقل ─────────────────────────────────────────────────────


def _transfer(path, *args):
    out = StringIO()
    call_command("transfer_first_caps", "--file", str(path), *args, stdout=out)
    return out.getvalue()


def _relax_file(tmp_path, overrides):
    path = tmp_path / "relax.json"
    path.write_text(json.dumps({"first_cap_override": overrides}), encoding="utf-8")
    return path


def test_the_transfer_writes_the_file_values_once_and_is_idempotent(school, tmp_path):
    a, b = UserFactory(full_name="الأوّل"), UserFactory(full_name="الثاني")
    pa, pb = _pref(school, a.pk), _pref(school, b.pk)
    path = _relax_file(tmp_path, {str(a.pk): 4, str(b.pk): 4, "ghost": 4, "far": 9})

    first = _transfer(path, "--year", YEAR, "--school", school.code)
    second = _transfer(path, "--year", YEAR, "--school", school.code)

    pa.refresh_from_db()
    pb.refresh_from_db()
    assert (pa.max_first_periods, pb.max_first_periods) == (4, 4)
    assert "محدَّث=2" in first and "بلا صفّ تفضيل=1" in first and "خارج المدى=1" in first
    assert "محدَّث=0" in second and "بلا تغيير=2" in second
    assert AuditLog.objects.filter(changes__event=EVENT).count() == 2


def test_the_transfer_prints_no_name_and_never_lowers_a_higher_admin_value(school, tmp_path):
    teacher = UserFactory(full_name="اسمٌ لا يُطبع")
    pref = _pref(school, teacher.pk, cap=5)
    path = _relax_file(tmp_path, {str(teacher.pk): 4})

    output = _transfer(path, "--year", YEAR, "--school", school.code)

    pref.refresh_from_db()
    assert pref.max_first_periods == 5 and "اسمٌ لا يُطبع" not in output
    assert str(teacher.pk) not in output


def test_the_dry_run_counts_and_writes_nothing(school, tmp_path):
    teacher = UserFactory()
    pref = _pref(school, teacher.pk)
    path = _relax_file(tmp_path, {str(teacher.pk): 4})

    output = _transfer(path, "--year", YEAR, "--school", school.code, "--dry-run")

    pref.refresh_from_db()
    assert pref.max_first_periods is None and "محدَّث=1" in output
    assert not AuditLog.objects.filter(changes__event=EVENT).exists()


def test_a_missing_teacher_row_is_counted_not_created(school, tmp_path):
    teacher = UserFactory()
    path = _relax_file(tmp_path, {str(teacher.pk): 4})

    output = _transfer(path, "--year", YEAR, "--school", school.code)

    assert "بلا صفّ تفضيل=1" in output
    assert not TeacherPreference.objects.filter(teacher=teacher).exists()


# ── سقف السابعة: المدى نفسه 2–5 إدخالاً لا قراءةً (قرارُ المالك 10-10) ─────


@pytest.mark.parametrize("value, ok", [(1, False), (2, True), (5, True), (6, False)])
def test_the_seventh_cap_range_is_the_same_two_to_five(school, value, ok):
    pref = _pref(school, UserFactory().pk)
    pref.max_last_periods = value

    if ok:
        pref.full_clean(exclude=["teacher", "school"])
    else:
        with pytest.raises(ValidationError):
            pref.full_clean(exclude=["teacher", "school"])


def test_the_help_text_names_the_meaning_without_an_empty_choice(school):
    for name in ("max_last_periods", "max_first_periods"):
        text = TeacherPreference._meta.get_field(name).help_text
        assert "2 هو السقفُ العامّ" in text and "فارغ" not in text


def test_a_value_stored_before_the_range_is_not_rewritten_and_is_read_as_before(school):
    """الحدُّ للإدخال وحده: ما خُزّن (1) لا يُعدَّل ولا يتغيّر أثرُه في المولّد."""
    from operations.last_period_cap import personal_last_cap

    pref = _pref(school, UserFactory().pk)
    TeacherPreference.objects.filter(pk=pref.pk).update(max_last_periods=1)

    pref.refresh_from_db()
    assert pref.max_last_periods == 1 and personal_last_cap(pref.max_last_periods) == 1


def _select(page, name):
    block = re.search(rf'<select[^>]*name="{name}"[^>]*>(.*?)</select>', page, re.S)
    assert block, f"{name} ليس قائمةً منسدلة"
    return block.group(0), re.findall(r'<option value="([^"]*)"', block.group(1))


def test_the_admin_caps_are_selects_of_two_to_five_only(client, superuser):
    """قرارُ المالك 10-10: قائمةٌ خياراتُها 2 و3 و4 و5 لا غير — بلا خيارٍ فارغ ولا min/max ولا إدخالٍ حرّ."""
    client.force_login(superuser)

    page = client.get(reverse("admin:operations_teacherpreference_add")).content.decode()

    for name in ("max_first_periods", "max_last_periods"):
        block, values = _select(page, name)
        assert values == ["2", "3", "4", "5"]
        assert "min=" not in block and "max=" not in block
        assert re.search(r'<option value="2"[^>]* selected', block)


def test_a_row_without_a_personal_cap_shows_the_general_two_preselected(client, superuser, school):
    pref = _pref(school, UserFactory().pk)
    client.force_login(superuser)

    page = client.get(
        reverse("admin:operations_teacherpreference_change", args=[pref.pk])
    ).content.decode()

    for name in ("max_first_periods", "max_last_periods"):
        block, _ = _select(page, name)
        assert re.search(r'<option value="2"[^>]* selected', block)


def test_saving_a_blank_row_as_two_changes_nothing_in_audit_or_judgement(client, superuser, school):
    """الفارغ والعامّ (2) حكمٌ واحد: حفظٌ عابرٌ لا يكتب سجلّاً ولا يغيّر ما يقرؤه المحرّك."""
    pref = _pref(school, UserFactory().pk)
    client.force_login(superuser)

    _admin_post(client, pref, school)

    pref.refresh_from_db()
    assert (pref.max_first_periods, pref.max_last_periods) == (2, 2)
    assert not AuditLog.objects.filter(
        changes__event__in=[EVENT, "teacher_last_period_cap_changed"]
    ).exists()
    assert admin_first_caps(school, YEAR) == {}


def test_a_chosen_cap_is_saved_and_audited_for_both_fields(client, superuser, school):
    pref = _pref(school, UserFactory().pk)
    client.force_login(superuser)

    _admin_post(client, pref, school, max_first_periods=4, max_last_periods=3)

    pref.refresh_from_db()
    assert (pref.max_first_periods, pref.max_last_periods) == (4, 3)
    assert AuditLog.objects.filter(changes__event=EVENT).count() == 1
    assert AuditLog.objects.filter(changes__event="teacher_last_period_cap_changed").count() == 1


def test_a_legacy_value_outside_the_range_stays_selected_for_its_owner_only(
    client, superuser, school
):
    """ما خُزّن قبل القرار (1) لا يُكتب فوقه بحفظٍ عابر: يظهر محدَّداً لصاحبه وحده."""
    legacy = _pref(school, UserFactory().pk)
    TeacherPreference.objects.filter(pk=legacy.pk).update(max_last_periods=1)
    other = _pref(school, UserFactory().pk)
    client.force_login(superuser)

    page = client.get(
        reverse("admin:operations_teacherpreference_change", args=[legacy.pk])
    ).content.decode()
    other_page = client.get(
        reverse("admin:operations_teacherpreference_change", args=[other.pk])
    ).content.decode()
    _admin_post(client, legacy, school, max_last_periods=1)

    legacy.refresh_from_db()
    assert _select(page, "max_last_periods")[1] == ["1", "2", "3", "4", "5"]
    assert _select(other_page, "max_last_periods")[1] == ["2", "3", "4", "5"]
    assert legacy.max_last_periods == 1


def test_the_admin_run_cap_is_a_select_like_the_other_two_with_general_first(client, superuser):
    """قرارُ المالك 10-10: «أقصى حصص متتالية» قائمةٌ مثلهما — «السقف العامّ» فارغاً أوّلاً ثم 1 إلى 7."""
    from operations.preference_capacity import effective_run_cap

    client.force_login(superuser)

    page = client.get(reverse("admin:operations_teacherpreference_add")).content.decode()

    block, values = _select(page, "max_consecutive")
    assert values == ["", "1", "2", "3", "4", "5", "6", "7"]
    assert f"السقف العامّ ({effective_run_cap(None)})" in block
    assert re.search(r'<option value=""[^>]* selected', block)
    assert "min=" not in block and "max=" not in block


def test_the_admin_run_cap_saves_blank_as_general_and_audits_only_above_it(
    client, superuser, school
):
    pref = _pref(school, UserFactory().pk)
    client.force_login(superuser)

    _admin_post(client, pref, school, max_consecutive="")
    pref.refresh_from_db()
    assert pref.max_consecutive is None

    _admin_post(client, pref, school, max_consecutive="4")
    pref.refresh_from_db()
    assert pref.max_consecutive == 4
    assert AuditLog.objects.filter(changes__event="teacher_run_cap_above_general").count() == 1


def test_a_legacy_run_cap_outside_one_to_seven_stays_selected_for_its_owner_only(
    client, superuser, school
):
    legacy = _pref(school, UserFactory().pk)
    TeacherPreference.objects.filter(pk=legacy.pk).update(max_consecutive=9)
    other = _pref(school, UserFactory().pk)
    client.force_login(superuser)

    page = client.get(
        reverse("admin:operations_teacherpreference_change", args=[legacy.pk])
    ).content.decode()
    other_page = client.get(
        reverse("admin:operations_teacherpreference_change", args=[other.pk])
    ).content.decode()

    assert _select(page, "max_consecutive")[1][:3] == ["", "9", "1"]
    assert "9" not in _select(other_page, "max_consecutive")[1]
    assert re.search(r'<option value="9"[^>]* selected', _select(page, "max_consecutive")[0])
