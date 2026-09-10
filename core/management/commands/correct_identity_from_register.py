"""تصحيحُ الأرقام الشخصيّة من كشف الكادر — والهويّةُ الثابتةُ الرقمُ الوظيفيّ.

    python manage.py correct_identity_from_register --file كشف.xlsx
    python manage.py correct_identity_from_register --file كشف.xlsx --apply

في القاعدة أرقامٌ شخصيّةٌ خاطئة: رقمٌ أُدخل لموظّفٍ وهو رقمُ زميله، ورقمٌ ملفَّق
كُتب ليُسدّ فراغُ حقلٍ إلزاميّ. وكلاهما يمرّ صامتاً حتّى يأتي كشفُ الوزارة
بالرقم الصحيح، فينكسر القيدُ الفريد — أو الأسوأ: يُحمَّل موظّفٌ بياناتِ آخر.

## المبدأ: الرقمُ الوظيفيُّ يعرّف، والشخصيُّ يُصحَّح

الرقمُ الوظيفيُّ معرّفٌ إداريٌّ لا يتبدّل ولا يُخطئ فيه أحد؛ والرقمُ الشخصيُّ
هو ما وقع فيه الخطأ. فالمطابقةُ به، **ولا يُكتب في هذا الملفّ رقمٌ شخصيٌّ
واحد** — المستودعُ عامّ، والتصحيحاتُ تُقرأ من الكشف لا من الشيفرة.

ومن لا رقمَ وظيفيَّ له في القاعدة يُطابَق **باسمه الكامل** بشرطين: أن يكون
فريداً في القاعدة وفي الكشف معاً. وبلا الشرطين لا يُقترح شيء.

## الترتيب يُحلّ ولا يُفترض

صحّةُ التصحيح قد تتوقّف على غيره: من يأخذ رقماً يحمله زميلُه اليومَ ينتظر أن
يُفرَّغ. فتُطبَّق التصحيحاتُ التي هدفُها شاغرٌ أوّلاً، ثمّ يُعاد النظرُ فيما
بقي — وإن دارت الحلقةُ على نفسها (تبادُلُ رقمين) وقف الأمرُ وقال ذلك.

ولا يكتب شيئاً بلا `--apply`، وكلُّ كتابةٍ لها سطرٌ في سجلّ التدقيق: هذا
تغييرُ هويّةٍ لا تصحيحُ إملاء.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import CustomUser, School
from core.models.audit import AuditLog

#: الحقولُ المشتقّةُ من الرقم الشخصيّ — `save()` يحسبها، و`update_fields` لا
#: يحفظ إلّا ما سُمّي. ونسيانُها يترك بصمةً قديمةً على رقمٍ جديد، فيُغلق البابُ
#: في وجه صاحبه بلا رسالةِ خطأ.
DERIVED = ["national_id_hmac", "national_id_encrypted"]


class Command(BaseCommand):
    help = "يصحّح الأرقامَ الشخصيّة الخاطئة من كشف الكادر — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser):
        parser.add_argument("--file", required=True, help="مسارُ كشف الكادر (xlsx)")
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument("--apply", action="store_true", help="بدونه يعرض ولا يكتب")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        rows = self._read(options["file"])
        corrections = self._plan(rows)

        self.stdout.write(f"المدرسة: {school.name} · الكشف: {len(rows)} سطراً")
        if not corrections:
            self.stdout.write(self.style.SUCCESS("لا رقمَ يحتاج تصحيحاً — القاعدةُ تطابق الكشف."))
            return

        self.stdout.write(f"\nتصحيحاتٌ مقترحة: {len(corrections)}")
        for c in corrections:
            held = f" — يحمله اليومَ {c['blocked_by']}" if c["blocked_by"] else ""
            self.stdout.write(
                f"  • {c['user'].full_name}  [{c['matched_by']}]\n"
                f"      الرقم الشخصيّ: {_mask(c['old'])} ← {_mask(c['new'])}{held}"
            )
            if c["employee_number"]:
                self.stdout.write(f"      الرقم الوظيفيّ: (فارغ) ← {c['employee_number']}")

        if not options["apply"]:
            self.stdout.write("\nعرضٌ فقط — أضِف --apply للكتابة.")
            return

        written = self._write(school, corrections)
        self.stdout.write(self.style.SUCCESS(f"\nصُحّح {written} سجلّاً، ولكلٍّ سطرٌ في سجلّ التدقيق."))

    # ── القراءة والتخطيط ─────────────────────────────────────────────

    def _read(self, path):
        from core.management.commands.import_staff_register import Command as StaffCommand

        rows = StaffCommand()._read(path, "")
        if not rows:
            raise CommandError("لم يُقرأ سطرٌ واحد — تأكّد أنّه كشفُ الكادر.")
        return rows

    def _plan(self, rows):
        """التصحيحاتُ المقترحة — بالرقم الوظيفيّ أوّلاً، ثمّ بالاسم الفريد."""
        by_employee = {r["employee_number"]: r for r in rows if r["employee_number"]}
        name_counts: dict[str, int] = {}
        for row in rows:
            key = _key(row["name"])
            name_counts[key] = name_counts.get(key, 0) + 1

        seen, corrections = set(), []
        for user in CustomUser.objects.exclude(employee_number="").order_by("full_name"):
            row = by_employee.get(user.employee_number)
            if row and row["national_id"] and row["national_id"] != user.national_id:
                corrections.append(self._one(user, row, "بالرقم الوظيفيّ"))
                seen.add(user.pk)

        # من لا رقمَ وظيفيَّ له في القاعدة: الاسمُ الفريدُ على الطرفين وحدَه.
        for user in CustomUser.objects.filter(employee_number="").order_by("full_name"):
            if user.pk in seen:
                continue
            key = _key(user.full_name)
            if name_counts.get(key) != 1:
                continue
            if CustomUser.objects.filter(full_name=user.full_name).count() != 1:
                continue
            row = next((r for r in rows if _key(r["name"]) == key), None)
            if row and row["national_id"] and row["national_id"] != user.national_id:
                corrections.append(self._one(user, row, "بالاسم الفريد"))
        return corrections

    def _one(self, user, row, matched_by):
        blocker = CustomUser.objects.filter(national_id=row["national_id"]).first()
        return {
            "user": user,
            "old": user.national_id,
            "new": row["national_id"],
            "employee_number": "" if user.employee_number else row["employee_number"],
            "matched_by": matched_by,
            "blocked_by": blocker.full_name if blocker else "",
        }

    # ── الكتابة ──────────────────────────────────────────────────────

    @transaction.atomic
    def _write(self, school, corrections):
        pending, written = list(corrections), 0
        while pending:
            free = [c for c in pending if not _taken(c["new"])]
            if not free:
                names = "، ".join(c["user"].full_name for c in pending)
                raise CommandError("حلقةٌ مغلقةٌ — كلُّ تصحيحٍ ينتظر غيرَه: " + names)
            for correction in free:
                self._one_write(school, correction)
                written += 1
            pending = [c for c in pending if c not in free]
        return written

    def _one_write(self, school, correction):
        user = correction["user"]
        changes = {"national_id": [_mask(correction["old"]), _mask(correction["new"])]}
        fields = ["national_id", *DERIVED]

        user.national_id = correction["new"]
        if correction["employee_number"]:
            user.employee_number = correction["employee_number"]
            fields.append("employee_number")
            changes["employee_number"] = ["", correction["employee_number"]]

        user.full_clean(exclude=["password", "last_login"])
        user.save(update_fields=fields)

        AuditLog.objects.create(
            school=school,
            user=None,
            action="update",
            model_name="CustomUser",
            object_id=str(user.pk),
            object_repr=user.full_name[:300],
            # الرقمُ مقنَّعٌ في السجلّ: التدقيقُ يحتاج أن يعرف **أنّ** الهويّة
            # تغيّرت ومَن صاحبُها، لا أن يحفظ رقمين شخصيّين كاملين في جدولٍ يُصدَّر.
            changes={**changes, "reason": f"تصحيحٌ من كشف الكادر ({correction['matched_by']})"},
        )

    def _school(self, code):
        school = School.objects.filter(code=code).first() if code else School.objects.first()
        if school is None:
            raise CommandError("لا مدرسةَ بهذا الرمز.")
        return school


def _key(name: str) -> str:
    return " ".join((name or "").split())


def _taken(national_id: str) -> bool:
    return CustomUser.objects.filter(national_id=national_id).exists()


def _mask(national_id: str) -> str:
    """أوّلُ ثلاثٍ وآخرُ اثنتين — يكفي للتمييز ولا يكفي للتعريف."""
    if len(national_id) < 6:
        return "*" * len(national_id)
    return f"{national_id[:3]}{'*' * (len(national_id) - 5)}{national_id[-2:]}"
