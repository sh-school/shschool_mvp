"""نقلُ سجلّ الأقسام بين قاعدتين — بالأسماء لا بالمعرّفات.

    report → حالُ القاعدة الحاضرة: أقسامُها وترتيبُها وأعضاؤها ومن لا قسمَ له
    export → ملفٌّ بأسماء الأقسام والمعلّمين
    import → مطابقةٌ بالأسماء على القاعدة الهدف، ثمّ كتابةٌ بـ`--apply`

## لمَ أمرٌ ثانٍ بجانب `seed_departments`؟

`seed_departments` **يشتقّ** القسمَ من إسنادات القاعدة التي يعمل عليها. فتشغيلُه
على الإنتاج يُنتج توزيعاً من إسنادات الإنتاج — وهي على بنية شُعبٍ تخالف
المحلّيّ — لا التوزيعَ الذي أقرّته الإدارة ورأته على الورق. وهذا الأمرُ **ينقل**
القرارَ كما هو: القسمُ ما قالته الإدارةُ، لا ما يقوله جدولُ القاعدة الهدف.

## ولمَ بالأسماء؟

`UUID` المستخدمِ والقسمِ يختلف بين قاعدةٍ وأخرى — بُذرتا على حدة. والنقلُ
بالمعرّف إمّا يسقط بخطأِ مفتاحٍ أجنبيّ، وإمّا ينجح خطأً فيُلحق معلّماً بقسمٍ
ليس قسمَه بلا صوت.

## لا يكتب سطراً بلا `--apply`

يُعرض أوّلاً ما سيقع: كم قسماً يُنشأ، وكم يُعدَّل، وكم معلّماً يُنقل، ومن تعذّر
اسمُه. ومن ينقل ثلاثةً وسبعين معلّماً إلى الإنتاج يستحقّ أن يرى الخطّةَ قبل
وقوعها. وسطرٌ واحدٌ متعذّرٌ يوقف الكتابةَ كلَّها — نقلٌ يقف ويسمّي خيرٌ من نقلٍ
يُصيب نصفَ الوقت.

    python manage.py sync_departments export --b64 > payload.txt
    railway run python manage.py sync_departments report
    railway run python manage.py sync_departments import --b64 "<الحمولة>"
    railway run python manage.py sync_departments import --b64 "<الحمولة>" --apply
"""

import base64
import gzip
import json
import sys
from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.models import CustomUser, Department, Membership, School
from operations.departments import TEACHING_ROLES


class Command(BaseCommand):
    help = "نقلُ سجلّ الأقسام وعضويّاته بين قاعدتين — بالمطابقة بالأسماء"

    def add_arguments(self, parser):
        parser.add_argument("mode", choices=["report", "export", "import"])
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument(
            "--file",
            default="-",
            help="مسارُ الملفّ، و«-» للمُدخَل/المُخرَج القياسيّ (الافتراض)",
        )
        # الحمولةُ سطراً واحداً: gzip ثمّ base64 — تعبر `railway ssh` وصدَفةَ
        # ويندوز معاً، حيث يبتلع المُفسِّرُ الاقتباساتِ ولا يُضمَن المُدخَلُ القياسيّ.
        # وقيمتُها اختياريّة: `--b64` وحدَها تعني «أخرِجها بهذه الصيغة» عند
        # التصدير، و`--b64 <حمولة>` تعني «اقرأها منها» عند الاستيراد.
        parser.add_argument(
            "--b64",
            nargs="?",
            const="1",
            default="",
            help="استيرادٌ: الحمولةُ gzip+base64 بدل الملفّ. تصديرٌ: `--b64` وحدَها",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="نفِّذ فعلاً — وبدونه يُعرض ما سيقع ولا يقع",
        )
        parser.add_argument(
            "--clear-missing",
            action="store_true",
            help="انزع القسمَ عمّن له قسمٌ في الهدف وليس في الملفّ",
        )
        parser.add_argument(
            "--retire-extra",
            action="store_true",
            help="أطفِئ أقسامَ الهدف التي ليست في الملفّ وقد خلت من أعضائها",
        )

    def handle(self, *args, **options):
        school = self._school(options["school"])
        if options["mode"] == "report":
            return self._report(school)
        if options["mode"] == "export":
            return self._export(school, options)
        return self._import(school, options)

    def _school(self, code):
        qs = School.objects.filter(code=code) if code else School.objects.all()
        school = qs.first()
        if school is None:
            raise CommandError(f"لا مدرسةَ بالرمز «{code}»." if code else "لا مدارسَ في القاعدة.")
        return school

    # ── قراءةُ القاعدة الحاضرة ───────────────────────────────────

    def _teaching_memberships(self, school):
        return (
            Membership.objects.filter(school=school, is_active=True, role__name__in=TEACHING_ROLES)
            .select_related("user", "department_obj")
            .order_by("user__full_name")
        )

    def _current(self, school):
        """{اسمُ المعلّم: رمزُ قسمه أو ''} — عضويّةُ التدريس وحدَها."""
        rows = {}
        for membership in self._teaching_memberships(school):
            name = (membership.user.full_name or "").strip()
            if name in rows:
                continue
            department = membership.department_obj
            rows[name] = department.code if department else ""
        return rows

    # ── تقرير ────────────────────────────────────────────────────

    def _report(self, school):
        """حالُ السجلّ هنا — قراءةٌ محضةٌ تُشغَّل على الإنتاج بلا خوف."""
        departments = Department.objects.filter(school=school).order_by("sort_order", "name")
        current = self._current(school)
        per_code = defaultdict(list)
        for name, code in current.items():
            per_code[code].append(name)

        self.stdout.write(f"المدرسة: {school.name} ({school.code})")
        self.stdout.write(f"الأقسامُ المسجَّلة: {departments.count()} · المعلّمون: {len(current)}")
        self.stdout.write("")
        for department in departments:
            head = department.head.full_name if department.head_id else "—"
            members = per_code.get(department.code, [])
            flag = "" if department.is_active else "  [غيرُ نشط]"
            self.stdout.write(
                f"  {department.sort_order:>3} | {department.code:<14} | {department.name:<28}"
                f" | أعضاء {len(members):<3} | رئيس: {head}{flag}"
            )
        orphans = per_code.get("", [])
        if orphans:
            self.stdout.write(f"\n  بلا قسمٍ مسجَّل: {len(orphans)} — يقعون في الاشتقاق:")
            for name in sorted(orphans):
                self.stdout.write(f"      {name}")

    # ── تصدير ────────────────────────────────────────────────────

    def _export(self, school, options):
        departments = [
            {
                "code": d.code,
                "name": d.name,
                "sort_order": d.sort_order,
                "is_active": d.is_active,
                "head": d.head.full_name.strip() if d.head_id else "",
            }
            for d in Department.objects.filter(school=school)
            .select_related("head")
            .order_by("sort_order", "name")
        ]
        members = [
            {"teacher": name, "code": code}
            for name, code in sorted(self._current(school).items())
            if code
        ]
        text = json.dumps(
            {"school": school.code, "departments": departments, "members": members},
            ensure_ascii=False,
            indent=1,
        )
        if options["b64"]:
            text = base64.b64encode(gzip.compress(text.encode("utf-8"), 9)).decode("ascii")
        path = options["file"]
        if path == "-":
            self.stdout.write(text)
        else:
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(text)
        self.stderr.write(f"صُدِّر {len(departments)} قسماً و{len(members)} معلّماً.")

    # ── استيراد ──────────────────────────────────────────────────

    def _read(self, options):
        if options["b64"]:
            try:
                raw = gzip.decompress(base64.b64decode(options["b64"])).decode("utf-8")
            except (ValueError, OSError) as exc:
                raise CommandError(f"حمولةُ --b64 ليست gzip+base64 صالحة: {exc}") from exc
        else:
            path = options["file"]
            raw = sys.stdin.read() if path == "-" else open(path, encoding="utf-8").read()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise CommandError(f"الملفُّ ليس JSON صالحاً: {exc}") from exc
        if not isinstance(data.get("departments"), list) or not isinstance(
            data.get("members"), list
        ):
            raise CommandError("الملفُّ بلا حقلَي `departments` و`members`.")
        return data

    def _resolver(self, school):
        """اسمٌ كاملٌ → مستخدم، بين أهل التدريس وحدهم.

        والاسمُ الواحد قد يكون لمعلّمٍ ولمطوّرِ المنصّة وهما شخصٌ بحسابين. فما
        بقي مكرَّراً يُسقَط كي لا يُختار أحدُهما بالقرعة.
        """
        names = {}
        for membership in self._teaching_memberships(school):
            key = (membership.user.full_name or "").strip()
            if not key:
                continue
            names[key] = None if key in names and names[key] != membership.user else membership.user
        return (
            {k: v for k, v in names.items() if v is not None},
            {k for k, v in names.items() if v is None},
        )

    def _import(self, school, options):
        data = self._read(options)
        known, ambiguous = self._resolver(school)
        current = self._current(school)
        existing = {d.code: d for d in Department.objects.filter(school=school)}

        wanted = {row["code"]: row for row in data["departments"]}
        made = [code for code in wanted if code not in existing]
        changed = [
            code
            for code, row in wanted.items()
            if code in existing
            and (
                existing[code].name != row["name"]
                or existing[code].sort_order != row["sort_order"]
                or existing[code].is_active != row.get("is_active", True)
            )
        ]

        moves, failed = [], []
        for row in data["members"]:
            name, code = row["teacher"].strip(), row["code"]
            if code not in wanted:
                failed.append((name, f"قسمٌ غيرُ معرَّفٍ في الملفّ: «{code}»"))
                continue
            if name in ambiguous:
                failed.append((name, "اسمٌ مكرَّر — لأكثرَ من مستخدم"))
                continue
            if name not in known:
                failed.append((name, "لا معلّمَ بهذا الاسم في القاعدة الهدف"))
                continue
            if current.get(name) != code:
                moves.append((name, current.get(name) or "—", code))

        in_file = {row["teacher"].strip() for row in data["members"]}
        stray = sorted(n for n, code in current.items() if code and n not in in_file)
        extra = sorted(code for code in existing if code not in wanted)

        self.stderr.write(
            f"الملفّ {len(wanted)} قسماً و{len(data['members'])} معلّماً"
            f" | إنشاءُ قسم {len(made)} | تعديلُ قسم {len(changed)}"
            f" | نقلُ معلّم {len(moves)} | تعذّر {len(failed)}"
            f" | في الهدف وليس في الملفّ: {len(stray)} معلّماً و{len(extra)} قسماً"
        )
        for name, was, now in moves:
            self.stderr.write(f"  → {name}: {was} ← {now}")
        for name, why in failed:
            self.stderr.write(f"  ✗ {name}: {why}")
        for name in stray:
            self.stderr.write(f"  ⌫ زائدٌ في الهدف: {name} ({current[name]})")
        for code in extra:
            fate = "يُطفأ إن خلا" if options["retire_extra"] else "لا يُحذف ولا يُطفأ"
            self.stderr.write(f"  ⌫ قسمٌ زائدٌ في الهدف: {code} — {fate}")

        if not options["apply"]:
            self.stderr.write("عرضٌ فقط — أضِف --apply للتنفيذ.")
            return
        if failed:
            raise CommandError("لن يُنفَّذ شيءٌ ما دام سطرٌ واحدٌ متعذّراً — صحّح الأسماءَ أوّلاً.")

        written = self._write(school, wanted, data["members"], known, stray, extra, options)
        self.stderr.write(
            f"أُنشئ {written['created']} قسماً، وعُدِّل {written['updated']}،"
            f" ورُبط {written['linked']} معلّماً، وأُزيل القسمُ من"
            f" {written['cleared']} عضويّةٍ غيرِ تدريسيّة."
        )
        if written["retired"]:
            self.stderr.write(
                "  وأُطفئ من الأقسام الزائدة الخاوية: " + "، ".join(written["retired"])
            )
        if written["headless"]:
            self.stderr.write(
                "  ولم يُوجد رئيسٌ باسمه لهذه الأقسام: " + "، ".join(written["headless"])
            )

    @transaction.atomic
    def _write(self, school, wanted, members, known, stray, extra, options):
        registry, created, updated = {}, 0, 0
        for code, row in wanted.items():
            department, made = Department.objects.get_or_create(
                school=school,
                code=code,
                defaults={
                    "name": row["name"],
                    "sort_order": row["sort_order"],
                    "is_active": row.get("is_active", True),
                },
            )
            registry[code] = department
            if made:
                created += 1
                continue
            fields = []
            for field, value in (
                ("name", row["name"]),
                ("sort_order", row["sort_order"]),
                ("is_active", row.get("is_active", True)),
            ):
                if getattr(department, field) != value:
                    setattr(department, field, value)
                    fields.append(field)
            if fields:
                department.save(update_fields=fields)
                updated += 1

        # القسمُ يخصّ عضويّةَ التدريس وحدَها — ومن له عضويّةٌ إداريّةٌ ثانيةٌ
        # كان يُنسب مرّتين، فيصير عددُ القسم أكبرَ من عدد معلّميه.
        linked, cleared = 0, 0
        for row in members:
            user = known[row["teacher"].strip()]
            mine = Membership.objects.filter(user=user, school=school, is_active=True)
            linked += int(
                bool(
                    mine.filter(role__name__in=TEACHING_ROLES)
                    .exclude(department_obj=registry[row["code"]])
                    .update(department_obj=registry[row["code"]])
                )
            )
            cleared += (
                mine.exclude(role__name__in=TEACHING_ROLES)
                .exclude(department_obj__isnull=True)
                .update(department_obj=None)
            )

        if options["clear_missing"] and stray:
            cleared += Membership.objects.filter(
                school=school, is_active=True, user__full_name__in=stray
            ).update(department_obj=None)

        # القسمُ القديمُ الذي حلّ محلَّه قسمٌ برمزٍ جديد («islamic» ← «sharia»)
        # يبقى في الهدف خاوياً: لا يظهر على الورقة إذ لا عضوَ له، لكنّه يظهر في
        # قوائم الإدارة فيُختار خطأً. فيُطفأ ولا يُحذف — والحذفُ يقطع ما قد
        # يشير إليه من سجلّاتٍ أخرى. ولا يُطفأ إلّا ما خلا فعلاً بعد النقل.
        retired = []
        if options["retire_extra"] and extra:
            for department in Department.objects.filter(
                school=school, code__in=extra, is_active=True
            ):
                if Membership.objects.filter(
                    school=school, is_active=True, department_obj=department
                ).exists():
                    continue
                department.is_active = False
                department.save(update_fields=["is_active"])
                retired.append(department.code)

        # الرئيسُ يُنقل بالاسم — ومن لا يُوجد اسمُه في الهدف يُترك القسمُ بلا
        # رئيسٍ ويُسمّى في التقرير، فلا يُربط القسمُ برجلٍ ليس فيه.
        headless = []
        for code, row in wanted.items():
            name = (row.get("head") or "").strip()
            if not name:
                continue
            head = known.get(name) or CustomUser.objects.filter(full_name=name).first()
            if head is None:
                headless.append(registry[code].name)
                continue
            if registry[code].head_id != head.id:
                registry[code].head = head
                registry[code].save(update_fields=["head"])
        return {
            "created": created,
            "updated": updated,
            "linked": linked,
            "cleared": cleared,
            "retired": retired,
            "headless": headless,
        }
