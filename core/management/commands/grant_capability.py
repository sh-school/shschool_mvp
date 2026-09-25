"""منحُ قدرةٍ مفوَّضةٍ لموظّفٍ بعينه وسحبُها — «مُشغِّل الجدول» أوّلَها (التذكرة SOS-20260924-1CFE، الجزء أ).

    python manage.py grant_capability --school SHH001 --capability schedule.operator \\
        --employee-number <رقمُ من تُمنح له> --by-employee-number <رقمُ من يمنح> \\
        --reason "<سببُ المنح كما يُقرأ في التدقيق>" --apply

    python manage.py grant_capability ... --revoke --reason "<سببُ السحب>" --apply
    python manage.py grant_capability --school SHH001 --list

المانحُ والساحبُ: المديرُ أو النائبُ الأكاديميّ أو مطوّرُ المنصّة وحدَهم (`core.capability_grants.can_manage`) — والأمرُ
يشترط رقمَه الوظيفيّ (`--by-employee-number`) فيُدقَّق باسمه لا بلا فاعل. والسببُ إلزاميٌّ في المنح والسحب، وكلٌّ منهما
في `PermissionAuditLog` و`AuditLog`.

**قيوده:** المفتاحُ الرقمُ الوظيفيّ لا الشخصيّ (المستودعُ عامّ)؛ ولا رقمَ ولا اسمَ يُكتب في مستودعٍ أو وثيقة — الأشخاصُ يُعيَّنون
هنا وقتَ التشغيل؛ والقيمةُ التي تحمل علامةَ نقصٍ (`...` أو `<` أو `>`) تُرفض كي لا يمرّ قالبٌ منسيّ؛ **ولا يكتب شيئاً بلا `--apply`**،
وتشغيلُه مرّتين لا يُحدث تغييراً ثانياً (منحٌ فعّالٌ قائمٌ يُبقى، وسحبٌ لمنحٍ غيرِ قائمٍ لا شيءَ فيه).
"""

from argparse import ArgumentParser
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from core import capability_grants as service
from core.models import CapabilityGrant, CustomUser, School
from core.models.capability_grant import DELEGABLE_CAPABILITIES

_PLACEHOLDER_MARKS = ("...", "…", "<", ">", "XXX", "TODO")


def _reject_placeholder(text: str, what: str) -> str:
    text = (text or "").strip()
    for mark in _PLACEHOLDER_MARKS:
        if mark in text:
            raise CommandError(f"{what} يحمل علامةَ نقص «{mark}» — استبدل القيمةَ المؤقّتةَ بالحقيقيّة.")
    return text


def _user_by_employee_number(number: str, what: str) -> CustomUser:
    user = CustomUser.objects.filter(employee_number=(number or "").strip()).first()
    if user is None:
        raise CommandError(f"لا موظّفَ بالرقم الوظيفيّ المعطى ({what}).")
    return user


class Command(BaseCommand):
    help = "يمنح قدرةً مفوَّضةً لموظّف أو يسحبها أو يعرض الفعّالَ منها — ولا يكتب بلا --apply"

    def add_arguments(self, parser: ArgumentParser) -> None:
        parser.add_argument("--school", required=True, help="رمز المدرسة (SHH001 على الإنتاج)")
        parser.add_argument(
            "--capability",
            default="schedule.operator",
            choices=sorted(DELEGABLE_CAPABILITIES),
            help="القدرة المفوَّضة",
        )
        parser.add_argument(
            "--employee-number", help="الرقمُ الوظيفيّ لمن تُمنح له القدرةُ أو تُسحب منه"
        )
        parser.add_argument(
            "--by-employee-number", help="الرقمُ الوظيفيّ لمن يمنح أو يسحب (مدير/نائب أكاديميّ/مطوّر)"
        )
        parser.add_argument("--reason", help="سببُ المنح أو السحب — إلزاميّ")
        parser.add_argument("--revoke", action="store_true", help="يسحب المنحَ الفعّالَ بدل أن يمنح")
        parser.add_argument(
            "--list", action="store_true", help="يعرض المنحَ الفعّالةَ لهذه القدرة في المدرسة"
        )
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args: Any, **options: Any) -> None:
        school = School.objects.filter(code=options["school"]).first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالرمز {options['school']}")
        capability = options["capability"]
        label = DELEGABLE_CAPABILITIES[capability]

        if options["list"]:
            return self._list(school, capability, label)

        for required in ("employee_number", "by_employee_number", "reason"):
            if not options.get(required):
                raise CommandError(f"--{required.replace('_', '-')} لازم.")
        reason = _reject_placeholder(options["reason"], "السبب")
        user = _user_by_employee_number(options["employee_number"], "من تُمنح له")
        by = _user_by_employee_number(options["by_employee_number"], "من يمنح")
        revoking = options["revoke"]
        verb = "سحب" if revoking else "منح"

        self.stdout.write(f"\n{verb} قدرة «{label}» ({capability}) — {school.code}")
        self.stdout.write("═" * 56)
        self.stdout.write(f"  الحامل   {user.full_name}")
        self.stdout.write(f"  المنفِّذ  {by.full_name}")
        self.stdout.write(f"  السبب    {reason}")

        active = CapabilityGrant.objects.filter(
            school=school, user=user, capability=capability, revoked_at__isnull=True
        ).exists()
        if revoking and not active:
            self.stdout.write(self.style.WARNING("\nلا منحَ فعّالاً لهذا الموظّف — لا شيءَ يُسحب."))
            return
        if not revoking and active:
            self.stdout.write(self.style.WARNING("\nمنحٌ فعّالٌ قائمٌ — لا تغيير."))
            return

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nعرضٌ فقط — لم يُكتب شيء. أعِد التشغيلَ بـ--apply."))
            return

        try:
            if revoking:
                service.revoke(user=user, capability=capability, by=by, reason=reason)
            else:
                service.grant(user=user, capability=capability, by=by, reason=reason)
        except service.GrantError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"\nتمّ {verb} القدرة."))

    def _list(self, school: School, capability: str, label: str) -> None:
        grants = (
            CapabilityGrant.objects.filter(
                school=school, capability=capability, revoked_at__isnull=True
            )
            .select_related("user", "granted_by")
            .order_by("created_at")
        )
        self.stdout.write(f"\nالمنحُ الفعّالة لقدرة «{label}» في {school.code}: {grants.count()}")
        for grant in grants:
            by = grant.granted_by.full_name if grant.granted_by else "—"
            self.stdout.write(
                f"  {grant.user.full_name} — منحه {by} في {grant.created_at:%Y-%m-%d} — {grant.reason}"
            )
