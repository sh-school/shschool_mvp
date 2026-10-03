"""بذرُ حسابات المعاينة الدائمة على 8500 — يعمل في إقلاع حاوية المعاينة بعد migrate (W-20261003-023، D-167م، حكمُ 0105 أ وأ-٢).

    python manage.py preview_accounts --sync     # يبذر/يصحّح التسعةَ (متساوي الأثر)
    python manage.py preview_accounts --check    # يعطّل الحساباتِ إن لم يكن الربطُ على 127.0.0.1، ويُبلغ بالخلل

**لا يعمل إلّا في المعاينة** — وإلّا رفض بـ`CommandError` ولم يمسّ القاعدةَ أصلاً (قد تكون الإنتاج):
- الإعدادُ `shschool.settings.preview` (لا production ولا development ولا testing)؛
- قاعدةٌ اسمُها قاعدةُ المعاينة: `PREVIEW_DB_NAME` (يضبطها `docker-compose.preview.yml` وحدَه) تساوي اسمَ القاعدة الفعليّ، وليست `shschool_db`
  ولا فيها prod؛
- كلمةٌ من `PREVIEW_ACCOUNTS_PASSWORD` في `.env` غير المتتبَّع (لا في compose ولا كودٍ ولا اختبار)، ولا كلمةَ افتراضيّة؛
- `PREVIEW_BIND = 127.0.0.1`: غيرُه (مثلاً `--lan`) **لا يبذر، ويُعطَّل ما بُذر** (`is_active=False`)، ويُرفع خطأٌ.

الإنشاءُ بالـORM بلا تعطيل مدقّقات، والدورُ نفسُه بعضويّةٍ واحدةٍ نشطةٍ في مدرسة المعاينة بلا superuser ولا is_staff، و`must_change_password=False`،
وسطرُ AuditLog لكلّ إنشاءٍ وتصحيحٍ بلا كلمة. الأدوارُ التسعةُ في `core/preview_accounts.py` وحدَه.
بذراتُ البيانات الخاصّةُ بكلّ بطاقة (حصصُ اليوم، مشرفُ الجناح…) ليست هنا.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction

from core.models import AuditLog, CustomUser, Membership, Role, School
from core.preview_accounts import (
    EMAIL_PREFIX,
    FORBIDDEN_ROLES,
    FULL_NAME_PREFIX,
    ID_PREFIX,
    NAME_PREFIX,
    ROLES,
    in_preview_environment,
    legacy_accounts_q,
    preview_accounts_q,
)

PASSWORD_ENV = "PREVIEW_ACCOUNTS_PASSWORD"  # pragma: allowlist secret — اسمُ متغيّر البيئة لا قيمتُه
LOOPBACK = "127.0.0.1"
PRODUCTION_DB = "shschool_db"


def environment_problems() -> list[str]:
    """أسبابُ رفض البذر قبل لمس القاعدة (الإعدادُ والقاعدةُ). فارغةٌ = مأذون."""
    problems = []
    if not in_preview_environment():
        problems.append("الإعدادُ ليس shschool.settings.preview")
    name = connection.settings_dict.get("NAME") or ""
    expected = os.environ.get("PREVIEW_DB_NAME", "")
    if not expected:
        problems.append("PREVIEW_DB_NAME غيرُ مضبوطٍ (يضبطه docker-compose.preview.yml وحدَه)")
    elif name != expected:
        problems.append("اسمُ القاعدة لا يساوي PREVIEW_DB_NAME")
    if name == PRODUCTION_DB or "prod" in name.lower():
        problems.append("القاعدةُ تبدو قاعدةَ إنتاج")
    return problems


def bind_is_loopback() -> bool:
    return os.environ.get("PREVIEW_BIND", "") == LOOPBACK


class Command(BaseCommand):
    help = "يبذر حساباتِ المعاينة الدائمة (تسعةُ أدوار) في قاعدة المعاينة وحدَها — يرفض أيَّ بيئةٍ أخرى."

    def add_arguments(self, parser):
        mode = parser.add_mutually_exclusive_group(required=True)
        mode.add_argument("--sync", action="store_true", help="يبذر ويصحّح (متساوي الأثر)")
        mode.add_argument(
            "--check", action="store_true", help="يعطّل الحساباتِ إن لم يكن الربطُ محلّيّاً"
        )
        parser.add_argument(
            "--school",
            default=os.environ.get("PREVIEW_SCHOOL_CODE", ""),
            help="رمزُ المدرسة (افتراضاً أولُ نشطة)",
        )

    def handle(self, *args, **options):
        problems = environment_problems()
        if problems:
            # لا نلمس القاعدةَ: قد لا تكون قاعدةَ معاينة.
            raise CommandError("رُفض بذرُ حسابات المعاينة — " + "؛ ".join(problems))

        if not bind_is_loopback():
            off = CustomUser.objects.filter(
                preview_accounts_q(), national_id__in=list(ROLES.values())
            ).update(is_active=False)
            raise CommandError(
                f"رُفض: PREVIEW_BIND ليس {LOOPBACK} — لا بذرَ، وعُطّل {off} حساباً من حسابات المعاينة"
            )

        if options["check"]:
            self._check()
            return
        self._sync(options["school"])

    # ── --check ────────────────────────────────────────────────────
    def _check(self) -> None:
        issues = []
        present = {u.national_id: u for u in CustomUser.objects.filter(preview_accounts_q())}
        for role_name, nid in ROLES.items():
            user = present.get(nid)
            if user is None:
                issues.append(f"{role_name}: غائب")
                continue
            if not user.is_active:
                issues.append(f"{role_name}: معطَّل")
            if user.is_superuser or user.is_staff:
                issues.append(f"{role_name}: superuser/is_staff")
            roles = set(
                Membership.objects.filter(user=user, is_active=True).values_list(
                    "role__name", flat=True
                )
            )
            if roles != {role_name}:
                issues.append(f"{role_name}: عضويّاتٌ نشطةٌ {sorted(roles)}")
        extra = [n for n in present if n not in ROLES.values()]
        if extra:
            issues.append(f"حساباتٌ موسومةٌ خارج القائمة المغلقة: {len(extra)}")
        if issues:
            raise CommandError("خللٌ في حسابات المعاينة: " + "؛ ".join(issues))
        self.stdout.write("حساباتُ المعاينة سليمةٌ.")

    # ── --sync ─────────────────────────────────────────────────────
    def _sync(self, school_code: str) -> None:
        password = os.environ.get(PASSWORD_ENV, "")
        if not password:
            raise CommandError(f"رُفض: لا كلمةَ مرور — عيّن {PASSWORD_ENV} في .env غير المتتبَّع")
        schools = School.objects.filter(is_active=True)
        school = (
            schools.filter(code=school_code).first()
            if school_code
            else schools.order_by("code").first()
        )
        if school is None:
            raise CommandError("لا مدرسةَ نشطةٌ لتُبذر فيها الحسابات")
        known = {name for name, _ in Role.ROLES}
        for role_name in ROLES:
            if role_name in FORBIDDEN_ROLES or role_name not in known:
                raise CommandError(f"دورٌ غيرُ مسموحٍ في القائمة المغلقة: {role_name}")

        created = fixed = 0
        with transaction.atomic():
            removed = self._remove_legacy()
            for role_name, nid in ROLES.items():
                user = CustomUser.objects.filter(national_id=nid).first()
                if user is None:
                    user, is_new = CustomUser(national_id=nid), True
                elif not (
                    user.full_name.startswith(NAME_PREFIX)
                    and user.national_id.startswith(ID_PREFIX)
                ):
                    raise CommandError("رقمُ دخولٍ محجوزٌ لحسابٍ غيرِ موسوم — توقّف بلا تغيير")
                else:
                    is_new = False
                wanted = {
                    "full_name": f"{FULL_NAME_PREFIX}{role_name}",
                    # الرقمُ الوظيفيُّ `PV-<الدور>` يحمل الوسمَ في ملفّ الدمق (البصمةُ تختلف بمفتاح كلّ بيئة فلا تُطابَق) — حكمُ 0105 (P2).
                    "employee_number": nid,
                    "email": f"{EMAIL_PREFIX}{role_name}@preview.invalid",
                    "is_active": True,
                    "is_staff": False,
                    "is_superuser": False,
                    "must_change_password": False,
                }
                drift = [k for k, v in wanted.items() if getattr(user, k) != v]
                for key, value in wanted.items():
                    setattr(user, key, value)
                user.set_password(password)
                user.save()
                role, _ = Role.objects.get_or_create(school=school, name=role_name)
                Membership.objects.get_or_create(
                    user=user, school=school, role=role, defaults={"is_active": True}
                )
                Membership.objects.filter(user=user, school=school, role=role).update(
                    is_active=True
                )
                stray = (
                    Membership.objects.filter(user=user)
                    .exclude(school=school, role=role)
                    .update(is_active=False)
                )
                if is_new:
                    created += 1
                    self._audit(
                        user.pk, school, "create", "حسابُ معاينةٍ دائم — إنشاء", {"role": role_name}
                    )
                elif drift or stray:
                    fixed += 1
                    self._audit(
                        user.pk,
                        school,
                        "update",
                        "حسابُ معاينةٍ دائم — تصحيح",
                        {"role": role_name, "drift": drift, "stray_memberships": stray},
                    )
        self.stdout.write(
            f"حساباتُ المعاينة: أُنشئ {created}، وصُحّح {fixed}، من {len(ROLES)}"
            + (f"؛ وأُزيل {removed} حساباً من الأداة السابقة" if removed else "")
            + "."
        )

    def _remove_legacy(self) -> int:
        """يزيل حساباتِ الأداة الخارجيّة السابقة (29000009NNN) قبل بذر `PV-…` فلا يتكرّر دورٌ — حذفٌ وإلا تعطيل."""
        removed = 0
        for user in list(CustomUser.objects.filter(legacy_accounts_q())):
            school_id = (
                Membership.objects.filter(user=user).values_list("school", flat=True).first()
            )
            school = School.objects.filter(pk=school_id).first() if school_id else None
            account_id = (
                user.pk
            )  # يُفرَّغ pk الكائن بعد delete() فيُحفظ هنا ليبقى أثرُ الإزالة بمعرّفها (حكمُ 0105 P3)
            Membership.objects.filter(user=user).delete()
            try:
                with transaction.atomic():
                    user.delete()
            except Exception:
                user.is_active = False
                user.set_unusable_password()
                user.save(update_fields=["is_active", "password"])
            removed += 1
            self._audit(account_id, school, "delete", "حسابُ معاينةٍ من الأداة السابقة — إزالة", {})
        return removed

    @staticmethod
    def _audit(
        account_id: Any, school: School | None, action: str, text: str, changes: dict
    ) -> None:
        AuditLog.log(
            user=None,
            action=action,
            model_name="other",
            object_id=account_id,
            object_repr=text,
            changes=changes,
            school=school,
        )
