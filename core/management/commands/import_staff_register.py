"""استيرادُ كشف الكادر الرسميّ — كلُّ منتسبٍ بمسمّاه ورقمه.

    JobTitle → Role        بجدولٍ صريحٍ لا بتخمين

كان في المنصّة كادرٌ تدريسيٌّ وحدَه: تسعةٌ وسبعون معلّماً ومنسّقاً بُذروا من
كشفٍ لا يحمل غيرَهم. فلا مشرفَ إداريّاً ولا ملاحظَ طلبةٍ ولا محاسبَ ولا أمينَ
مخزن — سبعةٌ وأربعون موظّفاً خارج النظام، وهم في المدرسة كلَّ يوم.

وهذا الأمرُ يقرأ كشفَ الكادر الكامل (إكسل: الرقم الشخصيّ، الاسم، المسمّى
الوظيفيّ، الرقم الوظيفيّ، البريد، الجوّال) ويُدخل من ليس في القاعدة.

## ثلاثةُ مبادئ

    المسمّى يُحمل كما هو      ولا يُحشر في «إداريّ» ما لا يقابله دور
    الرقمُ الشخصيُّ هو الهويّة  فمن كان في القاعدة يُستكمل ولا يُكرَّر
    المرجعُ يُسجَّل            كشفُ الكادر هو مرجعُ الالتحاق

ولا يكتب شيئاً بلا `--apply`، وهو مُعاوِد: تشغيلُه مرّتين لا يُنشئ عضويّةً ثانية.

    python manage.py import_staff_register --file data/stuff_03.xlsx
    python manage.py import_staff_register --file data/stuff_03.xlsx --apply
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from core.models import CustomUser, Membership, Role, School

#: المسمّى الوظيفيُّ في الكشف ← دورُ المنصّة. وما لم يُذكر هنا يُوقف الاستيرادَ
#: ولا يُخمَّن: دورٌ خاطئٌ يفتح شاشاتٍ لا تخصّ صاحبَه.
TITLE_ROLES = {
    "مدير المدرسة": "principal",
    "نائب المدير للشؤون الاكاديمية": "vice_academic",
    "النائب الإداري": "vice_admin",
    "النائب الاداري": "vice_admin",
    "مشرف اداري": "admin_supervisor",
    "مشرف إداري": "admin_supervisor",
    "الاخصائي الاجتماعي": "social_worker",
    "الأخصائي الاجتماعي": "social_worker",
    "الاخصائي النفسي": "psychologist",
    "الأخصائي النفسي": "psychologist",
    "مرشد أكاديمي": "academic_advisor",
    "مرشد اكاديمي": "academic_advisor",
    "أخصائي الأنشطة المعلمية": "activities_coordinator",
    "أخصائي الأنشطة المدرسية": "activities_coordinator",
    "السكرتير": "secretary",
    "مساعد سكرتير معلمة": "secretary",
    "موظف استقبال": "receptionist",
    "فني تقنية معلومات": "it_technician",
    "مسؤول مصادر التعلم": "librarian",
    "ممرض المدرسة": "nurse",
    # ليس `ese_assistant`: التفريقُ منصوصٌ في سياسة الدعم التعليميّ الإضافيّ
    # (ص155 و161-163 مقابل ص129) — راجع التعليقَ عند تعريف الدور في `access.py`.
    "مرافق الدعم": "support_companion",
    "معلم تربية خاصة": "ese_teacher",
    "منسق المشاريع الالكترونية": "e_projects_coordinator",
    "ملاحظ طلبه": "student_observer",
    "ملاحظ طلبة": "student_observer",
    "محضر مختبر أحياء": "lab_technician",
    "محضر مختبر فيزياء": "lab_technician",
    "امين مخزن": "storekeeper",
    "أمين مخزن": "storekeeper",
    "محاسب": "accountant",
    "مشرف مقصف": "canteen_supervisor",
    "عامل خدمات": "services_worker",
    "مندوب": "messenger",
    # ── صيغُ الكشف الوزاريّ 2026-2027 ────────────────────────────────
    # قالبُ مدرسةِ البناتِ لم يُنظَّف في الورقة المدرسيّة، فبقي «مدير معلمة»
    # و«سكرتير معلمة» — والكشفُ الوزاريُّ يصحّحهما. وكلاهما يُحمل: الوزاريُّ
    # لأنّه المرجع، والمدرسيُّ لأنّ خمسةَ موظّفين لا يعرفهم الكشفُ الوزاريّ.
    "مدير مدرسة": "principal",
    "مدير معلمة": "principal",
    "نائب المدير للشؤون الادارية": "vice_admin",
    "نائب المدير للشؤون الإدارية وشؤون الطلاب": "vice_admin",
    "سكرتير مدرسة": "secretary",
    "سكرتير معلمة": "secretary",
    "مساعد سكرتير مدرسة": "secretary",
    "مسؤول مركز مصادر التعلم": "librarian",
}

#: ما بدأ بهذه يُقرأ من بادئته — «معلم رياضيات» و«منسق العلوم» عشراتُ صيغ،
#: و«محضر مختبر» يليه اسمُ المادّة أو لا يليه شيء.
PREFIX_ROLES = (
    ("منسق", "coordinator"),
    ("معلم", "teacher"),
    ("محضر مختبر", "lab_technician"),
)

#: من يذكرُه الكشفُ ولا يُستورَد — بقرارٍ بشريٍّ مكتوبٍ لا باجتهاد.
#:
#: الكشفُ الوزاريُّ يتأخّر عن الواقع: ذكر أيوب القرفان بمسمّى النيابة الأكاديميّة
#: وهو منقولٌ من المدرسة (تأكيدُ المستخدم 2026-09-10). ولولا هذه القائمةُ لأعاده
#: أوّلُ تشغيلٍ إلى الكادر صامتاً، ولصار للمدرسة نائبان أكاديميّان نشطان.
#:
#: **والمفتاحُ الرقمُ الوظيفيُّ لا الشخصيّ**: المستودعُ عامّ، والرقمُ الشخصيُّ
#: بياناتٌ شخصيّةٌ بنصّ PDPPL لا تُكتب في شيفرةٍ يقرؤها الناس. والرقمُ الوظيفيُّ
#: معرّفٌ إداريٌّ تُراسَل به الوزارةُ في شؤون الموظّف — وهو كافٍ للتمييز.
#:
#: والسببُ يُكتب مع الرقم: قائمةٌ بلا أسبابٍ تصير بعد سنةٍ لغزاً لا يجرؤ أحدٌ
#: على حذف سطرٍ منه.
EXCLUDED_EMPLOYEE_NUMBERS = {
    "65227": (
        "أيوب حسين القرفان — نُقل من المدرسة، وعضويّتُه انتهت 2026-09-06."
        " والكشفان يذكرانه بمسمّى النيابة الأكاديميّة. تأكيدُ المستخدم 2026-09-10."
    ),
}

#: الكادرُ التدريسيُّ — في القاعدة أصلاً، ولا يُستورَد (طلبُ المستخدم 2026-09-06).
TEACHING_ROLES = frozenset({"teacher", "coordinator", "ese_teacher", "e_projects_coordinator"})


#: حروفٌ يتبدّل رسمُها بين كشفٍ وكشفٍ ولا يتبدّل بها المعنى.
_LETTERS = str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ة": "ه"})


def normalize_title(title: str) -> str:
    """صورةٌ واحدةٌ للمسمّى مهما اختلف رسمُه.

    الكشفُ الوزاريُّ يكتب «أخصائي اجتماعي» والمدرسيُّ «الاخصائي الاجتماعي»،
    و«الأكاديمية» تُكتب «الاكاديمية». وهذه فروقُ رسمٍ لا فروقُ وظيفة — فلو
    حُملت في الجدول صيغةً صيغةً لصار الجدولُ سجلَّ أخطاءٍ إملائيّة، ولوقف
    الاستيرادُ عند الصيغة السابعة عشرة.

    والتعريفُ يُنزع من كلّ كلمة: «نائب المدير» و«نائب مدير» واحد.
    """
    words = (title or "").translate(_LETTERS).split()
    return " ".join(w[2:] if len(w) > 3 and w.startswith("ال") else w for w in words)


#: الجدولُ نفسُه بصورته المطبَّعة — يُبنى مرّةً عند التحميل.
_NORMALIZED = {normalize_title(k): v for k, v in TITLE_ROLES.items()}


def role_for(title: str) -> str | None:
    title = " ".join((title or "").split())
    if title in TITLE_ROLES:
        return TITLE_ROLES[title]

    normalized = normalize_title(title)
    if normalized in _NORMALIZED:
        return _NORMALIZED[normalized]

    for prefix, role in PREFIX_ROLES:
        if title.startswith(prefix) or normalized.startswith(normalize_title(prefix)):
            return role
    return None


class Command(BaseCommand):
    help = "يستورد كشفَ الكادر الكامل من إكسل — بلا كتابةٍ إلّا بـ--apply"

    def add_arguments(self, parser):
        parser.add_argument("--file", default="", help="مسارُ ملفّ الإكسل")
        parser.add_argument(
            "--rows-b64",
            default="",
            help=(
                "سطورُ الكشف محزومةً gzip+base64 بدل الملفّ — لقاعدةٍ لا يصلها الملفّ."
                " و«-» تقرأ الحزمةَ من المدخل القياسيّ، وهو الأسلم"
            ),
        )
        parser.add_argument(
            "--emit-b64",
            action="store_true",
            help="اطبع سطورَ الكشف محزومةً ولا تكتب شيئاً — لتُمرَّر إلى --rows-b64",
        )
        parser.add_argument(
            "--include-teaching",
            action="store_true",
            help="أدخِل المعلّمين والمنسّقين أيضاً — والافتراضُ الكادرُ الإداريُّ وحدَه",
        )
        parser.add_argument(
            "--complete-existing",
            action="store_true",
            help="أكمِل الفارغَ عند القائمين: الرقمُ الوظيفيّ والجوّالُ والبريدُ والمسمّى — ولا يُكتب فوق ممتلئ",
        )
        parser.add_argument(
            "--no-create",
            action="store_true",
            help="لا تُنشئ حساباً ولا عضويّةً جديدة — أكمِل القائمَ فقط",
        )
        parser.add_argument(
            "--reconcile-roles",
            default="",
            help=(
                "أدوارٌ عامّةٌ يجوز تبديلُها بدور الكشف الدقيق، مفصولةً بفاصلة"
                " (مثل admin,specialist) — ومن يحمل دوراً خارجها يبقى «يُراجَع»"
            ),
        )
        parser.add_argument("--sheet", default="", help="اسمُ الورقة — والافتراضُ الأولى")
        parser.add_argument("--school", default="", help="رمزُ المدرسة — والافتراضُ الأولى")
        parser.add_argument("--reference", default="", help="مرجعُ الالتحاق — والافتراضُ اسمُ الملفّ")
        parser.add_argument("--apply", action="store_true")

    def handle(self, *args, **options):
        school = self._school(options["school"])
        rows, source = self._rows(options)
        reference = options["reference"] or f"كشف الكادر: {source}"

        # الكادرُ التدريسيُّ في القاعدة أصلاً (طلبُ المستخدم 2026-09-06): يُقرأ
        # الكشفُ كلُّه ليُفحص، ولا يُدخل منه إلّا الإداريّون.
        if not options["include_teaching"]:
            rows = [r for r in rows if role_for(r["title"]) not in TEACHING_ROLES]

        # الاستثناءُ يُعلَن ولا يقع صامتاً: من حُذف من الاستيراد يُذكر بسببه،
        # وإلّا ظنّ قارئُ التقرير أنّ الكشفَ لم يذكره أصلاً.
        excluded = [r for r in rows if r["employee_number"] in EXCLUDED_EMPLOYEE_NUMBERS]
        if excluded:
            rows = [r for r in rows if r["employee_number"] not in EXCLUDED_EMPLOYEE_NUMBERS]
            for row in excluded:
                why = EXCLUDED_EMPLOYEE_NUMBERS[row["employee_number"]]
                self.stdout.write(self.style.WARNING(f"  ⊘ {row['name']} — {why}"))

        if options["emit_b64"]:
            self.stdout.write(_pack(rows))
            self.stderr.write(f"حُزم {len(rows)} سطراً — مرّرها إلى --rows-b64 على القاعدة الأخرى")
            return

        unknown = sorted({r["title"] for r in rows if role_for(r["title"]) is None})
        if unknown:
            raise CommandError(
                "مسمّياتٌ لا يقابلها دورٌ في المنصّة — أضِفها إلى الجدول أوّلاً:\n  "
                + "\n  ".join(unknown)
            )

        known = {
            u.national_id: u
            for u in CustomUser.objects.filter(national_id__in=[r["national_id"] for r in rows])
        }
        roles_held = {}
        for m in Membership.objects.filter(school=school, is_active=True).select_related(
            "user", "role"
        ):
            roles_held.setdefault(m.user.national_id, set()).add(m.role.name)

        new, existing, conflicts, skipped = [], [], [], []
        for row in rows:
            if not row["national_id"]:
                skipped.append((row["name"], "بلا رقمٍ شخصيّ في الكشف"))
                continue
            role = role_for(row["title"])
            mine = roles_held.get(row["national_id"], set())
            # عضويّةُ وليّ الأمر ليست تعارضاً: موظّفٌ ابنُه في المدرسة له صفتان،
            # وهي أشهرُ حالةٍ في كشف الكادر لا أندرُها.
            staff_roles = mine - {"student", "parent"}
            if role in mine:
                existing.append(row)
            elif staff_roles:
                # له عضويّةٌ نشطةٌ بدورٍ آخر من الكادر — قرارُ تصحيحٍ لا استيراد.
                conflicts.append((row, role, sorted(staff_roles)))
            else:
                new.append((row, role))

        # الدورُ العامّ («إداريّ»، «أخصائيّ») يُبدَّل بالدقيق من الكشف إن أذن
        # المستخدمُ بذلك صراحةً — ومن يحمل دوراً خارج المأذون يبقى قرارَ مراجعة.
        reconcilable = {r.strip() for r in options["reconcile_roles"].split(",") if r.strip()}
        retitle, kept = [], []
        for row, role, mine in conflicts:
            if reconcilable and set(mine) <= reconcilable and role not in reconcilable:
                retitle.append((row, role, mine))
            else:
                kept.append((row, role, mine))
        conflicts = kept

        self.stdout.write(f"المدرسة: {school.name} · الكشف: {len(rows)} سطراً")
        self.stdout.write(
            f"قائمٌ بالفعل: {len(existing)} · جديد: {len(new)} ·"
            f" يُصحَّح دورُه: {len(retitle)} ·"
            f" يُراجَع: {len(conflicts)} · متعذّر: {len(skipped)}"
        )

        gaps = []
        if options["complete_existing"]:
            gaps = self._gaps(school, existing, known, reference)
            # من يُصحَّح دورُه تُكمَل حقولُ حسابه هنا، أمّا عضويّتُه فيكتبها التصحيحُ نفسُه.
            gaps += self._gaps(
                school, [row for row, _r, _m in retitle], known, reference, with_membership=False
            )
        if options["complete_existing"]:
            by_field = {}
            for _obj, field, _value in gaps:
                by_field[field] = by_field.get(field, 0) + 1
            people = len({id(obj) for obj, _f, _v in gaps})
            self.stdout.write(
                f"يُكمَل عند القائمين: {len(gaps)} حقلاً فارغاً في {people} سجلّاً — "
                + ("، ".join(f"{k}: {v}" for k, v in sorted(by_field.items())) or "لا شيء")
            )

        new_mark = " — لن يُنشأ (--no-create)" if options["no_create"] else ""
        for row, role in sorted(new, key=lambda p: (p[1], p[0]["name"])):
            mark = "حسابٌ قائم" if row["national_id"] in known else "حسابٌ جديد"
            self.stdout.write(f"  + {row['title']:<26} {row['name']:<34} [{role}] {mark}{new_mark}")
        for row, role, mine in sorted(retitle, key=lambda p: p[0]["name"]):
            self.stdout.write(
                f"  ↻ {row['title']:<26} {row['name']:<34} [{'، '.join(mine)} → {role}]"
            )
        for row, role, mine in sorted(conflicts, key=lambda p: p[0]["name"]):
            self.stdout.write(
                self.style.WARNING(
                    f"  ? {row['title']:<26} {row['name']:<34} الكشفُ [{role}]"
                    f" والقاعدةُ [{'، '.join(mine)}] — يُراجَع يدويّاً"
                )
            )
        for name, why in skipped:
            self.stdout.write(self.style.WARNING(f"  ! {name} — {why}"))

        if not options["apply"]:
            self.stdout.write("\nتقريرٌ فقط — أضِف --apply للكتابة.")
            return

        if new and not options["no_create"]:
            created_users, created_memberships = self._write(school, new, reference)
            self.stdout.write(
                f"\nأُنشئ {created_users} حساباً و{created_memberships} عضويّة — "
                "والحساباتُ بلا كلمة مرورٍ حتّى تُصدَر لها."
            )
        if retitle:
            changed, refused = self._retitle(school, retitle, known, reference)
            self.stdout.write(f"\nصُحّح دورُ {changed} عضويّةً.")
            for name, why in refused:
                self.stdout.write(self.style.WARNING(f"  ✗ {name} — {why}"))
        if gaps:
            filled, rejected = self._complete(gaps)
            self.stdout.write(f"\nأُكمل {filled} حقلاً عند القائمين.")
            for name, why in rejected:
                self.stdout.write(self.style.WARNING(f"  ✗ {name} — {why}"))

    # ── القراءة ──────────────────────────────────────────────────────

    def _rows(self, options):
        """سطورُ الكشف من الملفّ أو من حزمةٍ — وواحدٌ منهما لا كلاهما."""
        if bool(options["file"]) == bool(options["rows_b64"]):
            raise CommandError("حدّد --file أو --rows-b64 — واحداً منهما.")
        if options["rows_b64"]:
            return _unpack(_payload(options["rows_b64"])), "حزمة"
        return self._read(options["file"], options["sheet"]), options["file"].split("/")[-1]

    def _school(self, code):
        school = (School.objects.filter(code=code) if code else School.objects.all()).first()
        if school is None:
            raise CommandError("لا مدرسةَ بهذا الرمز.")
        return school

    #: رؤوسُ الكشفين العربيّين — الوزاريُّ والمدرسيُّ يسمّيان الشيءَ باسمين.
    ARABIC_HEADERS = {
        "national_id": ("الرقم الشخصي", "الرقم الشخصى"),
        "name": ("الاسم",),
        "title": ("المسمى الوظيفي", "مسمى الوظيفة"),
        "employee_number": ("الرقم الوظيفي", "رقم الموظف"),
        "email": ("البريد الالكتروني", "البريد الإلكتروني"),
        "phone": ("رقم الهاتف", "رقم الجوال"),
        "residence_area": ("السكن",),
    }

    def _read_arabic(self, book):
        """كشفُ 2026-2027: ورقتان لا تكفي إحداهما — تُدمجان بالرقم الشخصيّ.

        الوزاريّةُ فيها 130 سطراً بالمسمّى الرسميّ والرقم الوظيفيّ والجوّال،
        والمدرسيّةُ 120 بالبريد والسكن. والاتّحادُ 135: مئةٌ وخمسةَ عشرَ في
        كلتيهما، وخمسةَ عشرَ في الوزاريّة وحدَها، وخمسةٌ في المدرسيّة وحدَها.

        **والوزاريّةُ تحكم** (قرارُ المستخدم 2026-09-10): الاسمُ والمسمّى والرقمُ
        الوظيفيُّ والجوّالُ منها، والمدرسيّةُ تُكمل البريدَ والسكنَ وحدَهما.
        وهذا يُصلح قالبَ مدرسةِ البناتِ الذي لم يُنظَّف في الورقة المدرسيّة —
        «مدير معلمة» تصير «مدير مدرسة»، وخمسةُ مسمّياتٍ منها المديرُ نفسُه.

        وتُعرَف الورقتان بمحتواهما لا باسمهما: التي فيها البريدُ هي المدرسيّة.
        فتسميةُ الأوراق تتغيّر بين تصديرٍ وتصدير، والأعمدةُ لا تتغيّر.

        يُرجع `None` إن لم تكن أيُّ ورقةٍ عربيّةَ الرؤوس — فيُقرأ الملفُّ بالشكل
        القديم.
        """
        sheets = [
            parsed
            for parsed in (self._parse_arabic_sheet(ws) for ws in book.worksheets)
            if parsed is not None
        ]
        if not sheets:
            return None

        school_sheet = next((s for s in sheets if any(r.get("email") for r in s)), None)
        ministry = [s for s in sheets if s is not school_sheet]

        authoritative = {}
        for rows in ministry:
            for row in rows:
                authoritative[row["national_id"]] = row
        supplemental = {r["national_id"]: r for r in (school_sheet or [])}

        merged = []
        for qid in list(authoritative) + [q for q in supplemental if q not in authoritative]:
            base = dict(authoritative.get(qid) or supplemental[qid])
            extra = supplemental.get(qid) or {}
            for field in ("email", "residence_area"):
                if not base.get(field) and extra.get(field):
                    base[field] = extra[field]
            merged.append(base)
        return merged

    def _parse_arabic_sheet(self, worksheet):
        """سطورُ ورقةٍ عربيّةِ الرؤوس، أو `None` إن لم تكن كذلك.

        والفرقُ بين `None` و`[]` ليس ذوقاً: ورقةٌ عربيّةُ الرؤوس خلت سطورُها من
        رقمٍ صالحٍ كانت تُقرأ «ليست عربيّة»، فيسقط الملفُّ في القارئ الإنجليزيّ
        ويشكو من أعمدةٍ لا وجودَ لها في ملفٍّ عربيّ — رسالةٌ تُضلّل قارئَها.

        وموضعُ الرؤوس يُبحث عنه ولا يُفترض: الوزاريّةُ تضعها في السطر الأوّل
        والمدرسيّةُ في الثاني (فوقهما عنوانٌ مدموج). واشتراطُ سطرٍ بعينه يجعل
        الأمرَ يفشل بـ«لم يُقرأ موظّفٌ واحد» كلَّما أضاف أحدٌ سطرَ عنوان.
        """
        rows = list(worksheet.iter_rows(max_row=6, values_only=True))
        columns, header_index = {}, None
        for index, row in enumerate(rows):
            found = self._match_headers(row)
            if len(found) >= 4 and "national_id" in found and "name" in found:
                columns, header_index = found, index
                break
        if header_index is None:
            return None

        out = []
        for row in worksheet.iter_rows(min_row=header_index + 2, values_only=True):
            if not any(row):
                continue
            record = {
                field: _text(row[position]) if position < len(row) else ""
                for field, position in columns.items()
            }
            qid = record.get("national_id", "")
            if not record.get("name") or not qid.isdigit():
                continue
            record.setdefault("email", "")
            record.setdefault("residence_area", "")
            record["phone"] = _local_phone(record.get("phone", ""))
            out.append(
                {
                    "national_id": qid,
                    "name": record["name"],
                    "title": record.get("title", ""),
                    "employee_number": record.get("employee_number", ""),
                    "email": record["email"],
                    "phone": record["phone"],
                    "residence_area": record["residence_area"],
                }
            )
        return out

    def _match_headers(self, row):
        wanted = {
            _header_key(alias): field
            for field, aliases in self.ARABIC_HEADERS.items()
            for alias in aliases
        }
        found = {}
        for position, value in enumerate(row):
            field = wanted.get(_header_key(_text(value)))
            if field and field not in found:
                found[field] = position
        return found

    def _read(self, path, sheet):
        try:
            import openpyxl
        except ImportError as exc:  # pragma: no cover - بيئةٌ بلا المكتبة
            raise CommandError("openpyxl غيرُ مثبّتة.") from exc

        try:
            book = openpyxl.load_workbook(path, read_only=True, data_only=True)
        except OSError as exc:
            raise CommandError(f"تعذّر فتحُ الملفّ: {path}") from exc

        # كشفُ 2026-2027 عربيُّ الرؤوس وورقتان، والكشفُ القديم إنجليزيٌّ وورقةٌ
        # واحدة. فيُقرأ الشكلان: الملفُّ القديم لا يُكسر، والجديدُ لا يُعاد تشكيله
        # بيد أحدٍ قبل الاستيراد — وكلُّ تشكيلٍ يدويٍّ خطوةٌ تُنسى أو تُخطئ.
        if not sheet:
            arabic = self._read_arabic(book)
            if arabic is not None:
                book.close()
                return arabic

        worksheet = book[sheet] if sheet else book[book.sheetnames[0]]
        raw = list(worksheet.iter_rows(values_only=True))
        book.close()
        if not raw:
            raise CommandError("الورقةُ فارغة.")

        header = [str(c).strip() if c is not None else "" for c in raw[0]]
        columns = {name: index for index, name in enumerate(header)}
        needed = ("national_no", "stuff _name", "job_title")
        missing = [c for c in needed if c not in columns]
        if missing:
            raise CommandError(f"أعمدةٌ ناقصةٌ في الكشف: {'، '.join(missing)}")

        def cell(row, name):
            index = columns.get(name)
            if index is None or index >= len(row) or row[index] is None:
                return ""
            return str(row[index]).strip()

        rows = []
        for row in raw[1:]:
            if not any(row):
                continue
            name = " ".join(cell(row, "stuff _name").split())
            if not name:
                continue
            rows.append(
                {
                    "national_id": cell(row, "national_no"),
                    "name": name,
                    "title": " ".join(cell(row, "job_title").split()),
                    "employee_number": cell(row, "job_no"),
                    "email": cell(row, "email"),
                    "phone": cell(row, "phone_no"),
                }
            )
        return rows

    # ── الكتابة ──────────────────────────────────────────────────────

    @transaction.atomic
    def _write(self, school, new, reference):
        today = timezone.localdate()
        users, memberships = 0, 0
        for row, role_name in new:
            user = CustomUser.objects.filter(national_id=row["national_id"]).first()
            if user is None:
                user = CustomUser(
                    national_id=row["national_id"],
                    full_name=row["name"],
                    email=row["email"],
                    phone=row["phone"],
                    employee_number=row["employee_number"],
                    residence_area=row.get("residence_area", ""),
                )
                user.set_unusable_password()
                user.full_clean(exclude=["password", "last_login"])
                user.save()
                users += 1
            else:
                changed = []
                for field, value in (
                    ("email", row["email"]),
                    ("phone", row["phone"]),
                    ("employee_number", row["employee_number"]),
                    ("residence_area", row.get("residence_area", "")),
                ):
                    if value and not getattr(user, field):
                        setattr(user, field, value)
                        changed.append(field)
                if changed:
                    user.save(update_fields=_with_derived(changed))

            role, _ = Role.objects.get_or_create(school=school, name=role_name)
            membership = Membership(
                user=user,
                school=school,
                role=role,
                joined_at=today,
                job_title=row["title"],
                appointment_reference=reference,
                is_active=True,
            )
            membership.full_clean(exclude=["user", "school", "role"])
            membership.save()
            memberships += 1
            user.invalidate_active_membership()
        return users, memberships

    # ── الإكمال ──────────────────────────────────────────────────────

    def _gaps(self, school, existing, known, reference, *, with_membership=True):
        """ما في الكشف وليس في القاعدة عند من هم فيها أصلاً — الفارغُ وحدَه.

        فالكشفُ مرجعٌ للرقم الوظيفيّ والجوّال والبريد والمسمّى، والقاعدةُ قد
        تحمل قيمةً أحدثَ أدخلها صاحبُها — فلا يُكتب فوق ممتلئ.
        """
        gaps = []
        for row in existing:
            user = known.get(row["national_id"])
            if user is None:
                continue
            for field, value in (
                ("email", row["email"]),
                ("phone", row["phone"]),
                ("employee_number", row["employee_number"]),
                ("residence_area", row.get("residence_area", "")),
            ):
                if value and not getattr(user, field):
                    gaps.append((user, field, value))
            if not with_membership:
                continue
            membership = (
                Membership.objects.filter(
                    user=user, school=school, role__name=role_for(row["title"]), is_active=True
                )
                .order_by("-joined_at")
                .first()
            )
            if membership is None:
                continue
            if row["title"] and not membership.job_title:
                gaps.append((membership, "job_title", row["title"]))
                if not membership.appointment_reference:
                    gaps.append((membership, "appointment_reference", reference))
        return gaps

    @transaction.atomic
    def _retitle(self, school, retitle, known, reference):
        """يبدّل الدورَ العامَّ بالدقيق على العضويّة نفسِها — بأثرٍ يُقرأ بعد سنة.

        لا تُنشأ عضويّةٌ ثانية: تاريخُ الالتحاق والقسمُ والمرجعُ تبقى، ويُكتب في
        ملاحظة التعيين أنّ الدورَ صُحّح ومن أيّ كشف — فلا فجوةَ بلا تفسير.
        """
        from django.core.exceptions import ValidationError

        changed, refused = 0, []
        for row, new_role, mine in retitle:
            user = known.get(row["national_id"])
            membership = (
                Membership.objects.filter(
                    user=user, school=school, role__name__in=mine, is_active=True
                )
                .select_related("role")
                .order_by("-joined_at")
                .first()
            )
            if membership is None:
                refused.append((row["name"], "لا عضويّةَ نشطةً بالدور العامّ"))
                continue
            old = membership.role.name
            role, _ = Role.objects.get_or_create(school=school, name=new_role)
            membership.role = role
            if not membership.job_title:
                membership.job_title = row["title"]
            if not membership.appointment_reference:
                membership.appointment_reference = reference
            trail = f"صُحّح الدورُ من {old} إلى {new_role} — {reference}"
            membership.appointment_note = " · ".join(
                filter(None, [membership.appointment_note, trail])
            )[:200]
            try:
                membership.full_clean(exclude=["user", "school", "role"])
            except ValidationError as exc:
                refused.append(
                    (
                        row["name"],
                        "؛ ".join(f"{k}: {', '.join(v)}" for k, v in exc.message_dict.items()),
                    )
                )
                continue
            membership.save(
                update_fields=["role", "job_title", "appointment_reference", "appointment_note"]
            )
            user.invalidate_active_membership()
            changed += 1
        return changed, refused

    @transaction.atomic
    def _complete(self, gaps):
        """يكتب الفراغاتِ سجلّاً سجلّاً — ورفضُ التحقّق لسجلٍّ لا يوقف البقيّة."""
        from django.core.exceptions import ValidationError

        grouped = {}
        for obj, field, value in gaps:
            grouped.setdefault(id(obj), (obj, []))[1].append((field, value))

        filled, rejected = 0, []
        for obj, changes in grouped.values():
            for field, value in changes:
                setattr(obj, field, value)
            fields = [f for f, _v in changes]
            try:
                if isinstance(obj, CustomUser):
                    obj.full_clean(exclude=["password", "last_login"])
                    obj.save(update_fields=_with_derived(fields))
                else:
                    obj.full_clean(exclude=["user", "school", "role"])
                    obj.save(update_fields=fields)
            except ValidationError as exc:
                who = obj.full_name if isinstance(obj, CustomUser) else obj.user.full_name
                rejected.append(
                    (who, "؛ ".join(f"{k}: {', '.join(v)}" for k, v in exc.message_dict.items()))
                )
                continue
            filled += len(changes)
        return filled, rejected


def _with_derived(fields):
    """الجوّالُ يحمل معه مشتقّاته: `save()` يحسب التشفيرَ والبصمةَ لكنّ
    `update_fields` لا يحفظ إلّا ما سُمّي — فكان الجوّالُ يُحفظ ورقماً بلا بصمةٍ."""
    fields = list(fields)
    if "phone" in fields:
        fields += ["phone_encrypted", "phone_hmac"]
    return fields


def _pack(rows):
    import base64
    import gzip
    import json

    raw = json.dumps(rows, ensure_ascii=False).encode("utf-8")
    return base64.b64encode(gzip.compress(raw, 9)).decode("ascii")


def _unpack(payload):
    import base64
    import gzip
    import json

    try:
        rows = json.loads(gzip.decompress(base64.b64decode(payload)).decode("utf-8"))
    except (ValueError, OSError) as exc:
        raise CommandError(f"حزمةُ --rows-b64 ليست gzip+base64 صالحة: {exc}") from exc
    if not isinstance(rows, list):
        raise CommandError("الحزمةُ ليست قائمةَ سطور.")
    return rows


def _text(value) -> str:
    """خليّةٌ نصّاً بلا فراغاتٍ زائدة — والأرقامُ تخرج من إكسل عائمةً أحياناً."""
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return " ".join(str(value).split())


def _header_key(value: str) -> str:
    """رأسُ العمود بصورةٍ واحدة — «الرقم الشخصى» و«الرقم الشخصي» رأسٌ واحد."""
    return normalize_title(value)


def _local_phone(value: str) -> str:
    """الجوّالُ ثمانيَ خاناتٍ كما تحفظه القاعدة — والكشفُ الوزاريُّ يسبقه بـ974.

    ولا يُقتطع ما ليس مفتاحَ دولةٍ: رقمٌ من ثمانٍ يبدأ بـ974 يبقى كما هو.
    """
    digits = "".join(ch for ch in value if ch.isdigit())
    if len(digits) == 11 and digits.startswith("974"):
        return digits[3:]
    return digits


def _payload(value: str) -> str:
    """الحزمةُ نفسُها، أو ما يقرؤه المدخلُ القياسيُّ إن كانت «-».

    و«-» هي الصيغةُ الموصى بها: الحزمةُ في سطر الأوامر تضع بياناتِ 135 موظّفاً
    في وسائط العمليّة — تُقرأ بـ`ps`، وتُسجَّل في سجلّات تشغيل الأوامر على
    الخادم، وتبقى في تاريخ الصدَفة. وbase64 ترميزٌ لا تشفير.
    """
    if value != "-":
        return value
    import sys

    data = sys.stdin.read().strip()
    if not data:
        raise CommandError("المدخلُ القياسيُّ فارغ — لم تصل حزمة.")
    return data
