"""بذرُ حسابات المعاينة الدائمة على 8500 — يعمل في إقلاع حاوية المعاينة بعد migrate (W-20261003-023، D-167م، حكمُ 0105 أ وأ-٢).

    python manage.py preview_accounts --sync     # يبذر/يصحّح العشرةَ (متساوي الأثر)
    python manage.py preview_accounts --check    # يعطّل الحساباتِ إن لم يكن الربطُ على 127.0.0.1، ويُبلغ بالخلل

**لا يعمل إلّا في المعاينة** — وإلّا رفض بـ`CommandError` ولم يمسّ القاعدةَ أصلاً (قد تكون الإنتاج):
- بيئةُ معاينة (`core.preview_accounts.in_preview_environment`): الإعدادُ `shschool.settings.preview`، أو `shschool.settings.development` —
  المعاينةُ المثبَّتةُ على شجرة جلسةٍ، وهي استعمالُ المالك الرئيسيّ (تخفيفٌ مسبَّبٌ لحارس بحكم 0105) — **بشرط** `PREVIEW_MODE ∈ {prod, dev}` ولا غيرُ
  ذلك، وقاعدةٍ مطابقةٍ؛ وإعداداتُ الإنتاج/staging مرفوضةٌ دائماً مهما ضُبطت المتغيّراتُ؛
- قاعدةٌ اسمُها قاعدةُ المعاينة بفحصٍ **إيجابيّ**: `PREVIEW_DB_NAME` (يضبطها `docker-compose.preview.yml` وحدَه) تساوي اسمَ القاعدة الفعليّ **وهو يحوي
  «preview»** (قاعدةُ Railway الافتراضيّةُ «railway» تمرّ من فحصٍ سلبيٍّ)، وليست `shschool_db` ولا فيها prod؛
- كلمةٌ من `PREVIEW_ACCOUNTS_PASSWORD` في `.env` غير المتتبَّع (لا في compose ولا كودٍ ولا اختبار)، ولا كلمةَ افتراضيّة؛
- `PREVIEW_BIND = 127.0.0.1`: غيرُه (مثلاً `--lan`) **لا يبذر، ويُعطَّل ما بُذر** (`is_active=False`)، ويُرفع خطأٌ.

الإنشاءُ بالـORM بلا تعطيل مدقّقات، والدورُ نفسُه بعضويّةٍ واحدةٍ نشطةٍ في مدرسة المعاينة بلا superuser ولا is_staff، و`must_change_password=False`،
وسطرُ AuditLog لكلّ إنشاءٍ وتصحيحٍ بلا كلمة. الأدوارُ العشرةُ في `core/preview_accounts.py` وحدَه.
وحسابُ المشرف الإداريّ يُغطّي جناحاً بتغطيةٍ (`WingCoverage`) لا باستبدال حاملٍ (قرارُ المالك 2026-10-04) — ليراه ويرصد فيه بعد كلّ إعادة بناءٍ للقاعدة؛ متساوي الأثر.
بذراتُ البيانات الخاصّةُ بكلّ بطاقة (حصصُ اليوم…) ليست هنا.
"""

from __future__ import annotations

import os
from typing import Any

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction
from django.db.models import Q
from django.utils import timezone

from core import preview_accounts as preview_module
from core.academic_calendar import academic_year_for_school
from core.models import AuditLog, CustomUser, Membership, Role, School, Wing, WingCoverage
from core.preview_accounts import (
    EMAIL_PREFIX,
    EMPLOYEE_NUMBERS,
    FORBIDDEN_ROLES,
    FULL_NAME_PREFIX,
    ID_PREFIX,
    NAME_PREFIX,
    PREVIEW_DB_MARKER,
    PREVIEW_MODES,
    ROLES,
    in_preview_environment,
    legacy_accounts_q,
    preview_accounts_q,
)

#: وسمُ ملاحظة تغطيةِ هذا الحساب الدائمة — به يُعرف ما يجوز نقلُه (ولا تُنقل تغطيةٌ كتبها غيرُه).
OWN_COVERAGE_NOTE = "تغطيةُ حساب معاينةٍ دائم"
PASSWORD_ENV = "PREVIEW_ACCOUNTS_PASSWORD"  # pragma: allowlist secret — اسمُ متغيّر البيئة لا قيمتُه
LOOPBACK = "127.0.0.1"
PRODUCTION_DB = "shschool_db"


def environment_problems() -> list[str]:
    """أسبابُ رفض البذر قبل لمس القاعدة (الإعدادُ والقاعدةُ والوضع). فارغةٌ = مأذون."""
    problems = []
    if not in_preview_environment():
        problems.append(
            "ليست بيئةَ معاينة (الإعدادُ preview، أو development بـPREVIEW_MODE ∈ {prod, dev} وقاعدةِ معاينةٍ مطابقة؛ والإنتاجُ مرفوضٌ دائماً)"
        )
    if os.environ.get("PREVIEW_MODE", "") not in PREVIEW_MODES:
        problems.append("PREVIEW_MODE ليس prod ولا dev")
    name = preview_module.current_db_name()
    expected = os.environ.get("PREVIEW_DB_NAME", "")
    if not expected:
        problems.append("PREVIEW_DB_NAME غيرُ مضبوطٍ (يضبطه docker-compose.preview.yml وحدَه)")
    elif name != expected:
        problems.append("اسمُ القاعدة لا يساوي PREVIEW_DB_NAME")
    if PREVIEW_DB_MARKER not in name.lower():
        problems.append("اسمُ القاعدة لا يحوي «preview»")
    if name == PRODUCTION_DB or "prod" in name.lower():
        problems.append("القاعدةُ تبدو قاعدةَ إنتاج")
    return problems


def bind_is_loopback() -> bool:
    return os.environ.get("PREVIEW_BIND", "") == LOOPBACK


class Command(BaseCommand):
    help = "يبذر حساباتِ المعاينة الدائمة (عشرةُ أدوار) في قاعدة المعاينة وحدَها — يرفض أيَّ بيئةٍ أخرى."

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

        # حكمُ 0105 (٣ و٦): رقمٌ وظيفيٌّ من النطاق المحجوز لحسابٍ غيرِ حسابات المعاينة (حقيقيٌّ أو غيرُ موسوم) ⇒ توقّفٌ بلا تغيير.
        for role_name, nid in ROLES.items():
            holder = (
                CustomUser.objects.filter(employee_number=EMPLOYEE_NUMBERS[role_name])
                .exclude(national_id=nid)
                .first()
            )
            if holder is not None:
                raise CommandError(
                    "رقمٌ وظيفيٌّ من النطاق المحجوز لحساباتِ المعاينة ممسوكٌ لحسابٍ آخر — توقّف بلا تغيير"
                )
        created = fixed = 0
        wing_note = ""
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
                    # الرقمُ الوظيفيُّ الثماني من النطاق المحجوز: ما يكتبه المالكُ في الدخول، وبه يرفض `apply` الصفَّ (البصمةُ تختلف بمفتاح كلّ بيئة).
                    "employee_number": EMPLOYEE_NUMBERS[role_name],
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
                if role_name == "admin_supervisor":
                    wing_note = self._assign_wing(school, user)
            teacher_note = self._seed_teacher_classes(school)
            wing_note = "؛ ".join(note for note in (wing_note, teacher_note) if note)
        self.stdout.write(
            f"حساباتُ المعاينة: أُنشئ {created}، وصُحّح {fixed}، من {len(ROLES)}"
            + (f"؛ وأُزيل {removed} حساباً من الأداة السابقة" if removed else "")
            + (f"؛ {wing_note}" if wing_note else "")
            + "."
        )

    def _seed_teacher_classes(self, school: School) -> str:
        """يُسند المعلّمَ الوهميّ إلى شُعبٍ من جناحٍ واحدٍ يغطّيه المشرفُ الوهميّ (W-20261005-005).

        المنطقُ في أمر `seed_preview_teacher_classes` في operations (نماذجُ الإسناد ملكُها) — يُستدعى باسمه فلا تستورد النواةُ من operations (سقّاطةُ الطبقات).
        """
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        call_command("seed_preview_teacher_classes", school=school.code, stdout=out)
        return out.getvalue().strip()

    def _assign_wing(self, school: School, user: CustomUser) -> str:
        """يغطّي جناحاً بحساب المشرف الإداريّ الوهميّ **بتغطيةٍ (`WingCoverage`) لا باستبدال حاملٍ** — متساوي الأثر.

        بلا جناحٍ يرى «لا جناحَ مُسنَدٌ إليك» والفهرسُ فارغٌ وطلبُ شعبةٍ 404 (`wings_of` لغير القيادة)، فيبدو الرصدُ مختفياً. وقرارُ المالك
        (2026-10-04) تغطيةٌ دون المساس بأصيل أيّ جناحٍ ولا بأيّ حساب: التغطيةُ مفتوحةٌ من اليوم (`covers`)، وتُنهى بالطريق المعتاد.

        **الجناحُ هو جناحُ حصص المعلّم الوهميّ اليوم** (W-20261005-001): كان المنتقى «أوّلَ جناحٍ بلا تغطيةٍ» فيقع غالباً على جناحٍ غيرِ جناح حصصه
        فلا يصل رصدُه المشرفَ (واقعةُ w1/w3 2026-10-05). فتُضاف تغطيةٌ لكلّ جناحٍ فيه حصّةٌ للمعلّم الوهميّ اليومَ وهو بلا تغطيةٍ سارية — **إضافةً لا حذفاً**
        فلا تضيع تغطيةٌ قائمة، ويلتقطها إعادةُ `--sync` بعد بذر الحصص؛ وإن لم تكن له حصصٌ ولا تغطيةٌ فأوّلُ جناحٍ بلا تغطيةٍ سارية كما كان.
        """
        today = timezone.localdate()
        wings = list(
            Wing.objects.filter(
                school=school, academic_year=academic_year_for_school(school), is_active=True
            ).order_by("order", "code")
        )
        live = WingCoverage.objects.filter(wing__in=wings, start_date__lte=today).filter(
            Q(end_date__isnull=True) | Q(end_date__gte=today)
        )
        mine = {w.pk for w in wings if w.supervisor_id == user.pk} | set(
            live.filter(substitute=user).values_list("wing_id", flat=True)
        )
        busy = set(live.values_list("wing_id", flat=True))
        # جناحُ أبكر حصّةٍ للمعلّم الوهميّ اليومَ أوّلاً (حصّةُ رصد الجناح تُبذر أولاً) ثمّ بقيّةُ أجنحة حصصه
        rows = (
            school.sessions.filter(
                date=today,
                teacher__employee_number=EMPLOYEE_NUMBERS["teacher"],
                class_group__wing__in=wings,
            )
            .order_by("start_time")
            .values_list("class_group__wing_id", flat=True)
        )
        order: list = []
        for wing_id in rows:
            if wing_id not in order:
                order.append(wing_id)
        by_id = {w.pk: w for w in wings}
        free_teacher_wings = [by_id[i] for i in order if i not in busy and i not in mine]
        own = live.filter(substitute=user, note__startswith=OWN_COVERAGE_NOTE).first()
        if order and not (mine & set(order)) and free_teacher_wings:
            target = free_teacher_wings[0]
            if own is not None:
                # تغطيةُ هذا الحساب نفسِه على جناحٍ ليس فيه حصصُ المعلّم: تُنقل إلى جناح حصصه (تعديلٌ لا حذف؛ لا يحمل أحدٌ تغطيتين)
                old = own.wing.code
                own.wing = target
                try:
                    own.clean()
                    with transaction.atomic():
                        own.save(update_fields=["wing"])
                except (ValidationError, IntegrityError):
                    return f"تعذّر نقلُ التغطية إلى {target.code}"
                self._audit(
                    user.pk,
                    school,
                    "update",
                    "حسابُ معاينةٍ دائم — نقلُ تغطيةِ جناح",
                    {"from": old, "to": target.code},
                )
                return f"نُقلت تغطيةُ المشرف الوهميّ من {old} إلى {target.code} (جناحُ حصص المعلّم)"
            wanted = [target]
        elif mine:
            return ""
        else:
            first = next((w for w in wings if w.pk not in busy), None)
            if first is None:
                return "لا جناحَ بلا تغطيةٍ سارية لإسناده"
            wanted = [first]
        notes = []
        for wing in wanted:
            cover = WingCoverage(
                wing=wing,
                substitute=user,
                reason="other",
                start_date=today,
                note=OWN_COVERAGE_NOTE + " — بقرار المالك 2026-10-04",
            )
            try:
                cover.clean()
                with transaction.atomic():
                    cover.save()
            except (ValidationError, IntegrityError):
                notes.append(f"تعذّر إسنادُ تغطية {wing.code}")
                continue
            self._audit(
                user.pk, school, "create", "حسابُ معاينةٍ دائم — تغطيةُ جناح", {"wing": wing.code}
            )
            notes.append(f"غُطّي الجناح {wing.code} بالمشرف الوهميّ")
        return "؛ ".join(notes)

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
