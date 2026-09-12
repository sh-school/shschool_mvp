"""تكليفُ موظّفٍ بدورٍ في المنصّة غيرِ دور مسمّاه — بقرارٍ له مرجع.

    python manage.py reassign_staff_role --school SHH001 \\
        --employee-number 122606 --role bus_supervisor \\
        --reference "قرار مدير المدرسة رقم ... بتاريخ ..." --apply

**الفرقُ بين المسمّى والدور** مكتوبٌ في `Membership.job_title`: المسمّى وثيقةٌ
إداريّةٌ تُكتب في الكشوف كما وردت، والدورُ مفتاحُ صلاحيّاتٍ يفتح شاشاتٍ ويمنع أخرى.
والغالبُ أن يتطابقا، فيكفي `import_staff_register`. وهذا الأمرُ لما لا يتطابقان
بقرارٍ إداريّ: موظّفٌ مسمّاه «ملاحظ طلبة» في كشف الوزارة، وأسنده المديرُ مشرفَ نقل —
فدورُه في المنصّة `bus_supervisor`، ومسمّاه يبقى «ملاحظ طلبة» حيث يُقرأ.

**ولماذا لا يُترك للمستورد:** `TITLE_ROLES` يقرأ المسمّى فيعيده إلى
`student_observer`. والمستوردُ لا يُصحّح دوراً قائماً إلّا بـ`--reconcile-roles`
صريح، فالتكليفُ هنا يبقى — لكنّه يظهر في كلّ تشغيلٍ لاحقٍ سطرَ «تعارض» يُقرأ ولا
يُطبَّق، ومرجعُه في العضويّة يشرحه.

**وقيوده:**

- **المرجعُ لازمٌ ولا يُقبل مؤقّتاً.** تكليفُ موظّفٍ قرارٌ؛ ورقمٌ بلا مرجعٍ لا
  يُراجَع. والقيمةُ التي تحمل علامةَ نقصٍ (`...` أو `<` أو «المرجع») تُرفض: القيمُ
  المؤقّتةُ في أوامر المستخدم يجب أن تُفشل التنفيذَ إن نُسيت.
- **عضويّةُ كادرٍ نشطةٌ واحدةٌ فقط.** صفرٌ أو اثنتان ← يُرفض: تغييرُ دورٍ في
  عضويّةٍ لا يُعرف أيُّها يُصيب الشخصَ الخطأ. ووليُّ الأمر والطالب ليسا كادراً.
- **الدورُ الهدفُ دورُ كادر.** لا يُكلَّف موظّفٌ بـ`parent` أو `student`.
- **المفتاحُ الرقمُ الوظيفيّ** لا الشخصيّ: المستودعُ عامّ، والرقمُ الوظيفيُّ معرّفٌ
  إداريٌّ كافٍ للتمييز.
- **لا يكتب شيئاً بلا `--apply`**، وتشغيلُه مرّتين لا يُحدث تغييراً ثانياً.

ويُكتب في `PermissionAuditLog` — فالإشارةُ التي تسجّل تغييرَ الدور لا تعمل من سطر
الأوامر (لا مستخدمَ في السياق)، فيُسجَّل صراحةً هنا لا يُترك لها.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import CustomUser, Membership, PermissionAuditLog, Role, School
from core.models.access import ALL_STAFF_ROLES

#: ما يدلّ على أنّ القيمة لم تُستبدَل — مأخوذٌ من مثال التوثيق نفسِه.
_PLACEHOLDER_MARKS = ("...", "…", "<", ">", "المرجع", "XXX", "TODO")


def _reject_placeholder(reference: str) -> str:
    reference = (reference or "").strip()
    if len(reference) < 8:
        raise CommandError("مرجعُ القرار لازم — والتكليفُ بلا مرجعٍ لا يُراجَع.")
    for mark in _PLACEHOLDER_MARKS:
        if mark in reference:
            raise CommandError(
                f"المرجعُ يحمل علامةَ نقص «{mark}» — استبدل القيمةَ المؤقّتة بمرجع القرار الحقيقيّ."
            )
    return reference


class Command(BaseCommand):
    help = "يكلّف موظّفاً بدورٍ غيرِ دور مسمّاه، بمرجع قرار — ولا يكتب بلا --apply"

    def add_arguments(self, parser):
        parser.add_argument("--school", required=True, help="رمز المدرسة (SHH001 على الإنتاج)")
        parser.add_argument("--employee-number", required=True, help="الرقم الوظيفيّ")
        parser.add_argument("--role", required=True, help="الدورُ الهدف في المنصّة")
        parser.add_argument("--job-title", default="", help="المسمّى الوظيفيّ — يُترك إن كان مكتوباً")
        parser.add_argument("--reference", required=True, help="مرجعُ قرار التكليف — إلزاميّ")
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        reference = _reject_placeholder(options["reference"])
        school = School.objects.filter(code=options["school"]).first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالرمز {options['school']}")

        target_role = options["role"].strip()
        if target_role not in ALL_STAFF_ROLES:
            raise CommandError(f"«{target_role}» ليس دورَ كادر — لا يُكلَّف به موظّف.")

        user = CustomUser.objects.filter(employee_number=options["employee_number"].strip()).first()
        if user is None:
            raise CommandError(f"لا موظّفَ بالرقم الوظيفيّ {options['employee_number']}")

        staff = list(
            Membership.objects.filter(
                user=user, school=school, is_active=True, role__name__in=ALL_STAFF_ROLES
            ).select_related("role")
        )
        if not staff:
            raise CommandError(f"«{user.full_name}» بلا عضويّةِ كادرٍ نشطةٍ في {school.code}.")
        if len(staff) > 1:
            roles = "، ".join(m.role.name for m in staff)
            raise CommandError(
                f"«{user.full_name}» له {len(staff)} عضويّاتِ كادر ({roles}) — "
                "لا يُعرف أيُّها يُغيَّر، فلا يُغيَّر شيء."
            )

        membership = staff[0]
        old_role = membership.role.name
        job_title = options["job_title"].strip() or membership.job_title

        self.stdout.write(f"\n{user.full_name} — {user.employee_number}")
        self.stdout.write("═" * 56)
        self.stdout.write(f"  الدور           {old_role}  ←  {target_role}")
        self.stdout.write(f"  المسمّى الوظيفيّ {membership.job_title or '—'}  ←  {job_title or '—'}")
        self.stdout.write(f"  المرجع          {reference}")

        if old_role == target_role and membership.job_title == job_title:
            self.stdout.write(self.style.SUCCESS("\nمكلَّفٌ بهذا الدور أصلاً — لا تغيير."))
            return

        if not options["apply"]:
            self.stdout.write(self.style.WARNING("\nعرضٌ فقط — لم يُكتب شيء. أعِد التشغيلَ بـ--apply."))
            return

        with transaction.atomic():
            role, _ = Role.objects.get_or_create(school=school, name=target_role)
            membership.role = role
            membership.job_title = job_title
            membership.appointment_reference = reference[:200]
            membership.appointment_note = f"كُلِّف بدور {target_role} بدل {old_role}"[:200]
            membership.full_clean(exclude=["user", "school", "role"])
            membership.save(
                update_fields=["role", "job_title", "appointment_reference", "appointment_note"]
            )
            PermissionAuditLog.log(
                actor=None,
                target=user,
                action="role_assigned",
                school=school,
                details={
                    "via": "reassign_staff_role",
                    "from": old_role,
                    "to": target_role,
                    "job_title": job_title,
                    "reference": reference,
                },
            )
            user.invalidate_active_membership()

        self.stdout.write(self.style.SUCCESS(f"\nكُلِّف «{user.full_name}» بدور {target_role}."))
