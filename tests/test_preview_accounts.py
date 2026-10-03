"""حساباتُ المعاينة الدائمة على 8500: قائمةٌ مغلقة، بذرٌ يرفض غيرَ المعاينة، مصيدةُ الإنتاج، واستثناءُ الحقن (W-20261003-023، D-167م، حكمُ 0105).

«الحساباتُ كلُّها على المحلّيّ ولا تُحقن في الإنتاج» (المالك). فالمحروسُ هنا أربعةُ أشياء:

1. القائمةُ المغلقةُ في ملفٍّ واحد: تسعةُ أدوارٍ، لا platform_developer، أرقامُها `PV-…` فريدة، ويفشل الاختبارُ إن ظهر دورٌ خارجها.
2. الأمرُ `preview_accounts` لا يلمس القاعدةَ خارج `shschool.settings.preview` وقاعدةِ المعاينة والربط 127.0.0.1 وكلمةِ البيئة؛ ومعه idempotence.
3. المصيدةُ: حسابٌ موسومٌ (الوسمُ المركَّب) خارج إعداد المعاينة لا يدخل وتسقط جلستُه، بحدثٍ يحمل المعرّفَ لا الاسمَ ولا الرقم.
4. الحقنُ 8500→الإنتاج: الدمقُ يُسقط الموسومين، والتطبيقُ يرفض ملفّاً يحمل مفتاحاً خارج القائمة أو معلّماً موسوماً.

كلمةُ المرور هنا قيمةٌ مولَّدةٌ للاختبار وحدَه — لا كلمةَ في كودٍ ولا compose.
"""

import json
import logging
import re
import secrets
from pathlib import Path

import pytest
from django.contrib.auth import authenticate
from django.core.management import CommandError, call_command
from django.db import connection
from django.test import override_settings
from django.urls import reverse

from academic_management import preview_reconciliation as recon
from core import preview_accounts as pa
from core.management.commands import preview_accounts as pa_command
from core.models import CustomUser, Membership, Role
from tests.conftest import MembershipFactory, RoleFactory, UserFactory

pytestmark = pytest.mark.django_db

ROOT = Path(__file__).resolve().parent.parent
PREVIEW = override_settings(SETTINGS_MODULE=pa.PREVIEW_SETTINGS_MODULE)
EXPECTED_ROLES = {
    "principal",
    "vice_admin",
    "vice_academic",
    "admin_supervisor",
    "secretary",
    "teacher",
    "ese_teacher",
    "coordinator",
    "specialist",
}


@pytest.fixture
def password():
    return secrets.token_urlsafe(10)


@pytest.fixture
def preview_env(monkeypatch, password):
    """بيئةُ معاينةٍ سليمة: اسمُ القاعدة، والربطُ المحلّيّ، والكلمةُ من البيئة."""
    monkeypatch.setenv("PREVIEW_DB_NAME", connection.settings_dict["NAME"])
    monkeypatch.setenv("PREVIEW_BIND", "127.0.0.1")
    monkeypatch.setenv(pa_command.PASSWORD_ENV, password)
    return password


def _sync(**kwargs):
    call_command("preview_accounts", "--sync", **kwargs)


def _fakes():
    return CustomUser.objects.filter(pa.preview_accounts_q())


# ══════════════════════════════════════════════════════════════════
# ١) القائمةُ المغلقة
# ══════════════════════════════════════════════════════════════════


def test_the_closed_list_is_exactly_the_nine_roles():
    assert set(pa.ROLES) == EXPECTED_ROLES


def test_no_forbidden_role_is_in_the_list_and_every_role_is_a_platform_role():
    assert not set(pa.ROLES) & pa.FORBIDDEN_ROLES
    assert "platform_developer" in pa.FORBIDDEN_ROLES
    assert set(pa.ROLES) <= {name for name, _ in Role.ROLES}


def test_the_synthetic_ids_are_unique_and_carry_the_prefix():
    ids = list(pa.ROLES.values())
    assert len(set(ids)) == len(ids) == 9
    assert all(i.startswith(pa.ID_PREFIX) for i in ids)


def test_a_role_outside_the_list_never_gets_an_account(school, preview_env):
    with PREVIEW:
        _sync()
    roles = set(Membership.objects.filter(user__in=_fakes()).values_list("role__name", flat=True))
    assert roles == EXPECTED_ROLES


# ══════════════════════════════════════════════════════════════════
# ٢) الأمرُ: الرفضُ خارج المعاينة، والأثرُ المتساوي
# ══════════════════════════════════════════════════════════════════


def test_the_command_refuses_outside_the_preview_settings_and_touches_nothing(school, preview_env):
    with pytest.raises(CommandError, match="shschool.settings.preview"):
        _sync()  # إعدادُ الاختبار لا المعاينة
    assert not _fakes().exists()


def test_the_command_refuses_without_the_preview_db_name(school, monkeypatch, preview_env):
    monkeypatch.delenv("PREVIEW_DB_NAME")
    with PREVIEW, pytest.raises(CommandError, match="PREVIEW_DB_NAME"):
        _sync()
    assert not _fakes().exists()


def test_the_command_refuses_when_the_db_name_differs(school, monkeypatch, preview_env):
    monkeypatch.setenv("PREVIEW_DB_NAME", "some_other_db")
    with PREVIEW, pytest.raises(CommandError, match="لا يساوي"):
        _sync()
    assert not _fakes().exists()


def test_the_command_refuses_without_a_password(school, monkeypatch, preview_env):
    monkeypatch.delenv(pa_command.PASSWORD_ENV)
    with PREVIEW, pytest.raises(CommandError, match="لا كلمةَ مرور"):
        _sync()
    assert not _fakes().exists()


def test_a_non_loopback_bind_seeds_nothing_and_deactivates_what_was_seeded(
    school, monkeypatch, preview_env
):
    with PREVIEW:
        _sync()
        assert _fakes().filter(is_active=True).count() == 9
        monkeypatch.setenv("PREVIEW_BIND", "0.0.0.0")
        with pytest.raises(CommandError, match="PREVIEW_BIND"):
            _sync()
    assert _fakes().filter(is_active=True).count() == 0
    assert _fakes().count() == 9


def test_sync_creates_the_nine_accounts_with_safe_flags(school, preview_env):
    with PREVIEW:
        _sync()
    users = list(_fakes())
    assert len(users) == 9
    for user in users:
        assert user.full_name.startswith(pa.FULL_NAME_PREFIX)
        assert user.email.startswith(pa.EMAIL_PREFIX)
        assert not user.is_superuser and not user.is_staff and not user.must_change_password
        assert user.check_password(preview_env)
        assert Membership.objects.filter(user=user, is_active=True).count() == 1


def test_sync_is_idempotent(school, preview_env):
    with PREVIEW:
        _sync()
        _sync()
    assert _fakes().count() == 9
    assert Membership.objects.filter(user__in=_fakes()).count() == 9


def test_sync_corrects_a_drifted_role_membership_and_flags(school, preview_env):
    with PREVIEW:
        _sync()
        teacher = CustomUser.objects.get(national_id=pa.ROLES["teacher"])
        Membership.objects.filter(user=teacher).update(is_active=False)
        wrong = RoleFactory(school=school, name="principal")
        MembershipFactory(user=teacher, school=school, role=wrong)
        CustomUser.objects.filter(pk=teacher.pk).update(
            is_superuser=True, is_staff=True, is_active=False
        )

        _sync()

    teacher.refresh_from_db()
    assert not teacher.is_superuser and not teacher.is_staff and teacher.is_active
    active = set(
        Membership.objects.filter(user=teacher, is_active=True).values_list("role__name", flat=True)
    )
    assert active == {"teacher"}


def test_a_taken_id_belonging_to_a_real_user_aborts_without_changing_it(school, preview_env):
    UserFactory(full_name="موظّفٌ حقيقيّ", national_id=pa.ROLES["teacher"])
    with PREVIEW, pytest.raises(CommandError, match="غيرِ موسوم"):
        _sync()
    assert CustomUser.objects.get(national_id=pa.ROLES["teacher"]).full_name == "موظّفٌ حقيقيّ"


def test_the_check_mode_reports_a_missing_account(school, preview_env):
    with PREVIEW:
        _sync()
        CustomUser.objects.filter(national_id=pa.ROLES["secretary"]).delete()
        with pytest.raises(CommandError, match="secretary"):
            call_command("preview_accounts", "--check")


def test_the_seeded_accounts_can_log_in_under_the_preview_settings(client, school, preview_env):
    with PREVIEW:
        _sync()
        response = client.post(
            reverse("login"), {"identifier": pa.ROLES["teacher"], "password": preview_env}
        )
    assert response.status_code == 302 and response["Location"] == "/dashboard/"


# ══════════════════════════════════════════════════════════════════
# ٣) المصيدةُ في الإنتاج
# ══════════════════════════════════════════════════════════════════


def _fake_user(password, national_id="PV-teacher"):
    user = UserFactory(
        full_name=f"{pa.FULL_NAME_PREFIX}معلّم", national_id=national_id, password=password
    )
    return user


def test_a_tagged_account_cannot_authenticate_outside_the_preview_and_the_event_has_the_id_not_the_name(
    password, caplog, monkeypatch
):
    user = _fake_user(password)
    sent = []
    import sentry_sdk

    monkeypatch.setattr(sentry_sdk, "capture_message", lambda message, **kw: sent.append(message))
    with caplog.at_level(logging.ERROR, logger="core.preview_accounts"):
        assert authenticate(identifier=user.national_id, password=password) is None
    text = caplog.text
    assert str(user.pk) in text
    assert user.full_name not in text and user.national_id not in text
    assert sent and str(user.pk) in sent[0] and user.national_id not in sent[0]


def test_the_same_account_authenticates_inside_the_preview(password):
    user = _fake_user(password)
    with PREVIEW:
        assert authenticate(identifier=user.national_id, password=password) == user


def test_an_open_session_of_a_tagged_account_is_closed_outside_the_preview(client, password):
    user = _fake_user(password)
    with PREVIEW:
        client.force_login(user, backend="core.backends.HMACAuthBackend")
        inside = client.get("/dashboard/")
        assert "login" not in inside.get("Location", "")  # الجلسةُ قائمةٌ داخل المعاينة
    response = client.get("/dashboard/")
    assert response.status_code == 302 and "login" in response["Location"]


def test_a_name_prefix_alone_does_not_block_a_real_user(password):
    user = UserFactory(
        full_name=f"{pa.FULL_NAME_PREFIX}اسمٌ يشبه الوسم",
        national_id="29000001234",
        password=password,
    )
    assert not pa.is_preview_account(user)
    assert authenticate(identifier=user.national_id, password=password) == user


def test_an_id_prefix_alone_does_not_block_a_real_user(password):
    user = UserFactory(full_name="موظّفٌ حقيقيّ", national_id="PV-9999", password=password)
    assert not pa.is_preview_account(user)
    assert authenticate(identifier=user.national_id, password=password) == user


# ══════════════════════════════════════════════════════════════════
# ٤) استثناءُ الحقن 8500 → الإنتاج
# ══════════════════════════════════════════════════════════════════


def _assignment(school, klass, subject, teacher):
    from operations.models import SubjectClassAssignment

    return SubjectClassAssignment.objects.create(
        school=school,
        class_group=klass,
        subject=subject,
        teacher=teacher,
        weekly_periods=4,
        academic_year="2026-2027",
    )


@pytest.fixture
def injection_world(school):
    from core.models import ClassGroup
    from operations.models import Subject

    subject = Subject.objects.create(school=school, name_ar="الكيمياء", code="CHM")
    klass = ClassGroup.objects.create(
        school=school,
        grade="G12",
        section="1",
        level_type="sec",
        track="science",
        academic_year="2026-2027",
    )
    real = UserFactory(full_name="معلّمٌ حقيقيّ")
    fake = UserFactory(full_name=f"{pa.FULL_NAME_PREFIX}معلّم", national_id="PV-teacher")
    return school, klass, subject, real, fake


def test_the_dump_leaves_out_rows_of_a_tagged_teacher(tmp_path, injection_world):
    school, klass, subject, real, fake = injection_world
    real_row = _assignment(school, klass, subject, real)
    other_subject = type(subject).objects.create(school=school, name_ar="الفيزياء", code="PHY")
    _assignment(school, klass, other_subject, fake)
    out = tmp_path / "d.json"
    call_command(
        "dump_preview_workload_changes", "--since", "2000-01-01T00:00:00+00:00", "--out", str(out)
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert [r["teacher_hmac"] for r in payload["assignments"]] == [real.national_id_hmac]
    assert fake.national_id_hmac not in out.read_text(encoding="utf-8")
    assert real_row.pk is not None


def test_the_exclusion_filter_removes_exactly_the_tagged_teachers(injection_world):
    from operations.models import SubjectClassAssignment

    school, klass, subject, real, fake = injection_world
    _assignment(school, klass, subject, real)
    other_subject = type(subject).objects.create(school=school, name_ar="الفيزياء", code="PHY")
    _assignment(school, klass, other_subject, fake)
    kept = recon.exclude_preview_teachers(SubjectClassAssignment.objects.all())
    assert [row.teacher_id for row in kept] == [real.pk]


def test_apply_rejects_a_file_with_a_tagged_teacher_by_hmac_before_any_write(
    tmp_path, injection_world
):
    school, klass, subject, real, fake = injection_world
    from operations.models import SubjectClassAssignment

    path = tmp_path / "c.json"
    path.write_text(
        json.dumps(
            {
                "assignments": [
                    {
                        "school_code": school.code,
                        "academic_year": "2026-2027",
                        "grade": "G12",
                        "section": "1",
                        "subject_code": "CHM",
                        "teacher_hmac": fake.national_id_hmac,
                        "weekly_periods": 4,
                        "requires_lab": False,
                        "parallel_group": "",
                        "periods_override_reason": "",
                        "is_active": True,
                    }
                ],
                "workload_plans": [],
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(CommandError, match="حسابُ معاينةٍ وهميّ"):
        call_command("apply_preview_workload_changes", "--in", str(path))
    assert not SubjectClassAssignment.objects.exists()


def test_apply_rejects_a_tagged_employee_number(tmp_path, injection_world):
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps(
            {"assignments": [], "workload_plans": [{"teacher_employee_number": "PV-teacher"}]}
        ),
        encoding="utf-8",
    )
    with pytest.raises(CommandError, match="حسابُ معاينةٍ وهميّ"):
        call_command("apply_preview_workload_changes", "--in", str(path))


def test_apply_rejects_a_key_outside_the_allowlist(tmp_path, injection_world):
    path = tmp_path / "c.json"
    path.write_text(
        json.dumps({"assignments": [], "workload_plans": [], "users": [{"x": 1}]}), encoding="utf-8"
    )
    with pytest.raises(CommandError, match="users"):
        call_command("apply_preview_workload_changes", "--in", str(path))


def test_the_allowlist_is_exactly_what_the_dump_writes(tmp_path, injection_world):
    out = tmp_path / "d.json"
    call_command(
        "dump_preview_workload_changes", "--since", "2000-01-01T00:00:00+00:00", "--out", str(out)
    )
    assert set(json.loads(out.read_text(encoding="utf-8"))) == recon.INJECTABLE_KEYS


# ══════════════════════════════════════════════════════════════════
# ٥) الإقلاعُ في compose المعاينة وحدَه، والكلمةُ ليست فيه
# ══════════════════════════════════════════════════════════════════

OTHER_STARTUP_FILES = (
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.session.yml",
    "railway.toml",
    "railway.json",
    "scripts/railway-predeploy.sh",
    "scripts/railway-release.sh",
    "scripts/railway-worker.sh",
    "scripts/railway-beat.sh",
)


def test_the_seed_runs_after_migrate_in_the_preview_compose():
    text = (ROOT / "docker-compose.preview.yml").read_text(encoding="utf-8")
    assert "preview_accounts --sync" in text
    assert text.index("manage.py migrate") < text.index("preview_accounts --sync")
    assert (
        "PREVIEW_DB_NAME: ${PREVIEW_DB}" in text
        and "PREVIEW_BIND: ${PREVIEW_BIND:-127.0.0.1}" in text
    )


def test_no_other_startup_path_calls_the_seed():
    leaks = [
        rel
        for rel in OTHER_STARTUP_FILES
        if (ROOT / rel).exists() and "preview_accounts" in (ROOT / rel).read_text(encoding="utf-8")
    ]
    assert not leaks, leaks


def test_no_password_value_is_written_in_the_compose_or_the_code():
    compose = (ROOT / "docker-compose.preview.yml").read_text(encoding="utf-8")
    assert not re.search(r"PREVIEW_ACCOUNTS_PASSWORD\s*[:=]\s*\S", compose)
    for rel in ("core/preview_accounts.py", "core/management/commands/preview_accounts.py"):
        source = (ROOT / rel).read_text(encoding="utf-8")
        assert not re.search(r"""(?i)password\s*=\s*["'][^"']+["']""", source), rel
