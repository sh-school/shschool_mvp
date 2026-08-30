"""
أمر تنظيف + إعادة حقن الجدول الدراسي من PDF (aSc Timetables)

الجداول المستهدفة بالتنظيف:
  1. Subject — حذف + إعادة إنشاء 19 مادة
  2. ScheduleSlot — حذف + إعادة حقن
  3. SubjectClassAssignment — حذف + إعادة حقن
  4. SubjectClassSetup — حذف + إعادة حقن

الجداول التي لن تُمس:
  - CustomUser, Membership, ClassGroup, TimeSlotConfig, StudentEnrollment
"""

import re
import unicodedata
from collections import defaultdict
from datetime import time

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from pypdf import PdfReader

from core.academic_calendar import academic_year_for_school
from core.models import ClassGroup, CustomUser, School


def normalize_arabic(text):
    """تنظيف النص العربي: توحيد الأشكال المختلفة للحروف"""
    if not text:
        return ""
    # NFKC normalization - يحوّل الأشكال الخاصة للحروف
    text = unicodedata.normalize("NFKC", text)
    # استبدالات إضافية للحروف العربية الخاصة
    replacements = {
        "\ufefb": "لا",
        "\ufefc": "لا",  # لام ألف
        "\ufef7": "لأ",
        "\ufef8": "لأ",  # لام ألف همزة
        "\ufef9": "لإ",
        "\ufefa": "لإ",  # لام ألف همزة تحت
        "\ufef5": "لآ",
        "\ufef6": "لآ",  # لام ألف مد
        "\ufdf2": "الله",
        "ﺷ": "ش",
        "ﺵ": "ش",
        "ﺶ": "ش",
        "ﺸ": "ش",
        "ﺣ": "ح",
        "ﺤ": "ح",
        "ﺡ": "ح",
        "ﺢ": "ح",
        "ﺠ": "ج",
        "ﺟ": "ج",
        "ﺝ": "ج",
        "ﺞ": "ج",
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    # إزالة التطويل (kashida/tatweel)
    text = text.replace("\u0640", "")
    # تنظيف المسافات
    text = re.sub(r"\s+", " ", text).strip()
    return text


from operations.models import (
    ScheduleSlot,
    Subject,
    SubjectClassAssignment,
)

try:
    from assessments.models import SubjectClassSetup
except ImportError:
    SubjectClassSetup = None


# ──────────────────────────────────────────────────
# مطابقة أسماء المواد: PDF (عربي معكوس) -> اسم نظيف
# ──────────────────────────────────────────────────
#: اسم المادة كما يكتبه الجدول -> اسمها في المنصّة.
#: كان هذا الجدول مكتوباً بحروفٍ معكوسة («ةيمﻼسا ةيبرت») لأنّ المستخرج القديم
#: كان يقرأ الحروف بترتيب الرسم لا بترتيب اللغة. و`pypdf` يقرأها كما تُقرأ،
#: فصار المفتاح نصّاً يفهمه من يصونه.
SUBJECT_MAP = {
    "تربية اسلامية": "التربية الإسلامية",
    "اللغة العربية": "اللغة العربية",
    "لغة إنجليزية": "اللغة الإنجليزية",
    "رياضيات": "الرياضيات",
    "علوم": "العلوم",
    "علوم عامة": "العلوم العامة",
    "تربية بدنية": "التربية البدنية",
    "فنون بصرية": "الفنون البصرية",
    "المهارات الحياتية": "المهارات الحياتية والمهنية",
    "علوم اجتماعية": "الدراسات الاجتماعية",
    "تكنولوجيا": "التكنولوجيا",
    "تكنولوجيا المعلومات": "تكنولوجيا المعلومات",
    "علوم الحاسب": "علوم الحاسب",
    "كيمياء": "الكيمياء",
    "فيزياء": "الفيزياء",
    "أحياء": "الأحياء",
    "احياء": "الأحياء",
    "تاريخ": "التاريخ",
    "جغرافيا": "الجغرافيا",
    "ادارة اعمال": "إدارة الأعمال",
}

# أكواد المواد
SUBJECT_CODES = {
    "التربية الإسلامية": "ISL",
    "اللغة العربية": "ARA",
    "اللغة الإنجليزية": "ENG",
    "الرياضيات": "MAT",
    "العلوم": "SCI",
    "العلوم العامة": "GSC",
    "التربية البدنية": "PE",
    "الفنون البصرية": "ART",
    "المهارات الحياتية والمهنية": "LFS",
    "الدراسات الاجتماعية": "SOC",
    "التكنولوجيا": "TECH",
    "تكنولوجيا المعلومات": "IT",
    "علوم الحاسب": "CS",
    "الكيمياء": "CHM",
    "الفيزياء": "PHY",
    "الأحياء": "BIO",
    "التاريخ": "HIS",
    "الجغرافيا": "GEO",
    "إدارة الأعمال": "BUS",
}

# ──────────────────────────────────────────────────
# مطابقة أسماء المعلمين: اسم PDF -> اسم المنصة
# ──────────────────────────────────────────────────
TEACHER_MAP = {
    "فيصل جليل الرويلي": "فيصل جليل محيميد القعيقعى الرويلى",
    "يوسف عثامنه": "يوسف جميل سليمان العبدالله",
    "ياسر حجي شلبي": "ياسر حجى شلبى احمد",
    "عماد العبسي": "عماد يحيى محمد العبسي نوح",
    "محمود الأسطة": "محمود عبد المهدى عبد القادر الاسطه",
    "محمد العرامين": "محمد نادي محمد العرامين",
    "علي ضيف": "على ضيف الله حمد على",
    "محمود سعد": "محمود ابرهيم ابراهيم سعد",
    "محمد درادكة": "محمد فلاح صالح درادكه",
    "محمد فرحان النوايسة": "محمد فرحان سالم النوايسه",
    "عمر العباس": "عمر مصطفى محمد العباس",
    "علاء القضاه": "علاء محمد عبد الهادي القضاه",
    "أحمد الحاج": "احمد المنصف الحاج قاسم",
    "عمر بني عطا": "عمر حسن عقله بني عطا",
    "محمد صبرى درويش": "محمد صبرى محمود درويش",
    "عبد الله الرمضان": "عبدالله الرمضان",
    "عدنان المصطفى": "عدنان بركات عدنان المصطفى",
    "عبدالباسط عبدالسلام الجاسم": "عبدالباسط عبدالسلام الجاسم",
    "عبد الله خالد": "عبدالله خالد كامل محمود عبدربه",
    "احمد رمضان حامد": "احمد رمضان خطاب ابراهيم حامد",
    "ليث السعودي": "ليث حامد محمد السعودي",
    "نادر على لطفى": "نادر على لطفى محمد لطفى",
    "محمد احمد عنانبه": "محمد احمد حسن عنانبه",
    "ناصر الهاجري": "ناصر فايز مناحى سعد الهاجرى",
    "البشير بو حلاب": "البشير بوحلاب سودان",
    "وجدي يوسفي": "وجدي بن محمد بن عمارة يوسفي",
    "عبد الله نوفل": "عبدالله حسين مفلح نوفل",
    "محمود ماجد الجرادات": "محمود ماجد يوسف الجرادات",
    "علي خريسات": "علي ضيف الله خليل خريسات",
    "عبدالرحمن الأحزم": "عبدالرحمن محمد عبدالله لطف الله الاحزم",
    "ابراهيم محمد زريقات": "ابراهيم محمد محمود الزريقات",
    "ابراهيم  محمد زريقات": "ابراهيم محمد محمود الزريقات",
    "ابراهيم سليمان حمد": "ابراهيم سليمان طه حمد",
    "ابراهيم  سليمان حمد": "ابراهيم سليمان طه حمد",
    "عزام احمد الزعبي": "عزام احمد يوسف الزعبى",
    "عماد محمد قاسم": "عمادالدين محمد الحبشى قاسم",
    "عماد الدين قاسم": "عمادالدين محمد الحبشى قاسم",
    "محمد عبدالوهاب عويس": "محمد عبدالوهاب عبدالبديع عويس",
    "عثمان الفاروسي": "عثمان عبدالرحمن فاروسي",
    "محمد اسماعيل السيد": "محمد اسماعيل عبدالحميد السيد",
    "مصطفى عمر النزهاوى": "مصطفى عمر حسين النزهاوى",
    "مجدى محمد قنديل": "مجدى محمد على احمد قنديل",
    "إمام رشدي": "امام محمد رشدى امام محمد",
    "أكرم القمودي": "أكرم رابح قمودي",
    "احمد عبدالعزيز جامع": "احمد عبدالعزيز جامع مرسى",
    "خليفة صالح عودات": "خليفه صالح ظاهر عودات",
    "علي مصطفى الدروبى": "علي مصطفى الدروبى",
    "سفيان أحمد مسيف": "سفيان احمد محمد مسيف",
    "سفيان احمد مسيف": "سفيان احمد محمد مسيف",
    "حسن الصافي": "حسن ابرهيم العربى الصافى",
    "سلطان عواد": "سلطان سعيد عبدالله عواد",
    "يوسف يعقوب عوض": "يوسف يعقوب يونس عوض",
    "السيد محمدي رفاعي": "السيد محمدي رفاعي عبدالوهاب الرفاعي",
    "وليد جمعه عبد اللطيف": "وليد عبد اللطيف",
    "محمد سلام سليمان": "محمد سلام سليمان حسين",
    "محمد عبدالعزيز عدوان": "محمد عبدالعزيز يونس عدوان",
    "عطية محمود": "عطيه محمود عطيه محمود",
    "عطية محمود عطية محمود": "عطيه محمود عطيه محمود",
    "أحمد الحاج قاسم": "احمد المنصف الحاج قاسم",
    "وجدي يوسف": "وجدي بن محمد بن عمارة يوسفي",
    "مرتضى أمين": "مرتضي امين ابوالبشر عبدالله",
    "عبدالرحمن رجب": "عبدالرحمن فيصل اسماعيل راجه",
    "عبدالرحمن رجا": "عبدالرحمن فيصل اسماعيل راجه",
    "مؤيد احمد المومني": "مؤيد احمد محمد المومني",
    "عربي السيد رجب": "عربى السيد يوسف السيد رجب",
    "محمد عبدالله العجلوني": "محمد عبدالله عارف العجلوني",
    "محمد عبدﷲ العجلوني": "محمد عبدالله عارف العجلوني",
    "بنجر الدوسري": "بنجر محمد بنجر جاسر الدوسرى",
    "أحمد أغلو": "احمد محمد أوغلو",
    "سامر غازي": "سامر غازي مصطفى محمد",
    "أحمد شاهين": "احمد جعفر عبد الفتاح شاهين",
    "أحمد بكر": "احمد بكر محمد الزبط",
    "عادل محمد نصر": "عادل محمد نصر احمد",
    "نادر جمعة حنفية": "نادر جمعه عثمان حنفيه",
    "عمرو حمايدة": "عمرو محمد حمدان حمايده",
    "احمد محمد إبراهيم": "احمد محمد حسن إبراهيم",
    "احمد محمد ابراهيم": "احمد محمد حسن إبراهيم",
    "سامر نصر جديع": "سامر نصر سليمان جديع",
    "حسام محمود غانم": "حسام محمود مبروك غانم",
    "عامر النجار": "عامر محمد نجار",
    "طارق باسم شملاوي": "طارق باسم مصطفى شملاوي",
    "علي محمد دار ناصر": "علي محمد محمد دار ناصر",
    "منير شتيات": "منير رافع شتيوي شتيات",
    "أحمد جبر خلف": "احمد جبر جبر خلف",
    "معز السعداوي": "معز بن احمد السعداوي",
}

# أوقات الحصص (regular days)
PERIOD_TIMES = {
    1: (time(7, 10), time(7, 55)),
    2: (time(8, 0), time(8, 45)),
    3: (time(8, 50), time(9, 35)),
    4: (time(9, 55), time(10, 40)),
    5: (time(10, 45), time(11, 30)),
    6: (time(11, 45), time(12, 30)),
    7: (time(12, 35), time(13, 20)),
}

# خريطة أعمدة الجدول إلى أرقام الحصص (RTL)
#: «11.4» أو «11/4» — الشعبة كما يكتبها الجدول في وسط الخلية.
SECTION_LABEL = re.compile(r"^\d{1,2}[./]\w+$")

#: أكواد القاعات: HC.11.2 قاعةُ صفٍّ، وLAB1 وART2 وSPORT1 قاعاتٌ متخصّصة.
ROOM_CODE = re.compile(r"^(HC\.[\d.]+|LAB\d*|ART\d*|SPORT\d*)$", re.IGNORECASE)

COL_TO_PERIOD = {8: 1, 6: 2, 5: 3, 4: 4, 2: 5, 1: 6, 0: 7}

# أيام الأسبوع
DAY_NAMES = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس"]

# المواد ذات الحصتين المتتاليتين (حصة مزدوجة) — تُستخرج كخلية مدمجة من PDF
# ملاحظة: التكنولوجيا (TECH) ليست مزدوجة — حصتان في أيام مختلفة
DOUBLE_PERIOD_SUBJECTS = {"الفنون البصرية", "تكنولوجيا المعلومات", "علوم الحاسب"}


def _merge_runs(items, gap=60.0):
    """يضمّ كلمتين متجاورتين حين تُكوّنان معاً اسم مادّةٍ معروفة.

    «علوم عامة» و«علوم الحاسب» و«تكنولوجيا المعلومات» تُرسم كلماتٍ منفصلة،
    وإسنادُ كلٍّ منها وحدها يُسقط الثانية خارج نافذة خليّتها فتصير المادّة
    «علوم» — وهي مادّةٌ أخرى تماماً.

    والحكمُ للمفردات لا للمسافة: جُرّب الضمُّ بالتجاور وحده فضمّ خليّتين
    متجاورتين تحملان المادّة نفسها («رياضيات رياضيات»)، وضمّ تاريخَ إنشاء
    الجدول إلى مادّة. فلا يُضمّ إلّا ما كان المضمومُ منه اسمَ مادّةٍ يعرفها
    `SUBJECT_MAP` — والمسافة سياجٌ احتياطيّ لا أكثر.
    """
    runs = []
    for i in sorted(items, key=lambda i: (round(i["y"], 1), -i["x"])):
        if runs:
            last = runs[-1]
            joined = f"{last['t']} {i['t']}"
            if (
                abs(last["y"] - i["y"]) < 2
                and 0 < last["x"] - i["x"] < gap
                and joined in SUBJECT_MAP
            ):
                last["t"] = joined
                last["x"] = i["x"]
                continue
        runs.append(dict(i))
    return runs


class Command(BaseCommand):
    help = "تنظيف + إعادة حقن الجدول الدراسي من PDF المعلمين"

    def add_arguments(self, parser):
        parser.add_argument(
            "--pdf",
            required=True,
            help="مسار ملف PDF المعلمين (75 صفحة)",
        )
        parser.add_argument(
            "--elective",
            action="append",
            default=[],
            metavar="اسم المعلّم=المادة",
            help=(
                "مادّة المعلّم في الحصص المنقسمة — تُكرَّر لكل معلّم. "
                'مثال: --elective "أحمد شاهين=الكيمياء"'
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="عرض التغييرات فقط بدون تنفيذ",
        )
        parser.add_argument(
            "--validate-only",
            action="store_true",
            help="التحقق من البيانات فقط (مطابقة المعلمين والمواد والشعب) بدون أي كتابة في قاعدة البيانات",
        )

    def handle(self, *args, **options):
        import io
        import sys

        self.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", line_buffering=True)

        pdf_path = options["pdf"]
        dry_run = options["dry_run"]
        validate_only = options["validate_only"]
        electives = {}
        for item in options["elective"]:
            if "=" not in item:
                raise CommandError(f"صيغة غير مفهومة: {item} — المتوقَّع «معلّم=مادة»")
            name, _, subject = item.partition("=")
            electives[name.strip()] = subject.strip()

        mode_label = (
            "وضع التحقق فقط"
            if validate_only
            else "وضع المعاينة"
            if dry_run
            else "تنظيف + إعادة حقن"
        )

        self.stdout.write(self.style.WARNING("=" * 60))
        self.stdout.write(self.style.WARNING(f"  {mode_label} — الجدول الدراسي"))
        self.stdout.write(self.style.WARNING("=" * 60))

        # ─── 1. استخراج بيانات PDF ───
        self.stdout.write("\nاستخراج بيانات PDF...")
        teachers_data = self._extract_pdf(pdf_path)
        self.stdout.write(f"   {len(teachers_data)} معلم مستخرج")

        # ─── 2. بناء خريطة المعلمين ───
        self.stdout.write("\nمطابقة المعلمين...")
        teacher_id_map = self._build_teacher_map()

        # ─── 3. بناء خريطة الشعب ───
        self.stdout.write("\nمطابقة الشعب...")
        classgroup_map = self._build_classgroup_map()

        # بناء خريطة عكسية: classgroup_id -> grade number
        cg_grade_map = {}
        cg_label = {}
        for cg in ClassGroup.objects.filter(academic_year=self._year(), is_active=True):
            grade_num = str(cg.grade).replace("G", "").replace("g", "")
            cg_label[str(cg.id)] = f"{grade_num}/{cg.section}"
            try:
                cg_grade_map[str(cg.id)] = int(grade_num)
            except (ValueError, TypeError):
                pass

        # ─── 4. تجهيز البيانات ───
        self.stdout.write("\nتجهيز البيانات...")
        schedule_rows, assignment_map, errors, parallel = self._prepare_data(
            teachers_data, teacher_id_map, classgroup_map, electives
        )
        self.stdout.write(f"   {len(schedule_rows)} حصة جاهزة للحقن")
        self.stdout.write(f"   {len(assignment_map)} توزيع (معلم+مادة+شعبة)")
        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f"   {e}"))

        if parallel:
            self.stdout.write(
                f"\n[i] {len(parallel)} حصة منقسمة — الشعبة تتفرّق بين مادّتين "
                "في التوقيت نفسه، وكلا النصفين يُحقن:"
            )
            for rows in parallel:
                first = rows[0]
                day = DAY_NAMES[first["day_idx"]]
                halves = " ‖ ".join(f"{r['subject_name']} ({r['pdf_name']})" for r in rows)
                label = cg_label.get(first["classgroup_id"], first["classgroup_id"][:8])
                self.stdout.write(f"   {label} {day} ح{first['period']}: {halves}")

        # ─── 4a+. ملء الحصص المزدوجة المفقودة (merged cells) ───
        schedule_rows, filled_count = self._fill_double_periods(schedule_rows, cg_grade_map)
        if filled_count:
            self.stdout.write(
                self.style.SUCCESS(
                    f"   [+] {filled_count} حصة مزدوجة مُكتملة (كانت مفقودة بسبب merged cells)"
                )
            )

        # ─── 4b. التحقق من قيد الخميس (إعدادي=6، ثانوي=7) ───
        thursday_warnings = []
        for row in schedule_rows:
            if row["day_idx"] == 4 and row["period"] == 7:
                grade = cg_grade_map.get(row["classgroup_id"])
                if grade and grade in (7, 8, 9):
                    thursday_warnings.append(
                        f"   [!] خميس ح7 لشعبة إعدادية (صف {grade}): "
                        f"معلم={row['teacher_id'][:8]}.. مادة={row['subject_name']}"
                    )
        if thursday_warnings:
            self.stdout.write(
                self.style.WARNING(
                    f"\n[تحذير] {len(thursday_warnings)} حصة خميس ح7 لشعب إعدادية (الحد 6 حصص):"
                )
            )
            for w in thursday_warnings:
                self.stdout.write(self.style.WARNING(w))

        # ─── 4c. ملخص التحقق ───
        total_errors = len(errors)
        total_warnings = len(thursday_warnings) + len(parallel)
        if validate_only:
            self.stdout.write("\n" + "=" * 60)
            if total_errors == 0 and total_warnings == 0:
                self.stdout.write(self.style.SUCCESS("  [OK] التحقق ناجح — صفر اخطاء، صفر تحذيرات"))
            else:
                self.stdout.write(
                    self.style.WARNING(
                        f"  نتيجة التحقق: {total_errors} خطأ، {total_warnings} تحذير"
                    )
                )
            self.stdout.write(f"  الحصص: {len(schedule_rows)}")
            self.stdout.write(f"  التوزيعات: {len(assignment_map)}")
            self.stdout.write("=" * 60)
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("\nوضع المعاينة — لم يتم تنفيذ أي تغيير"))
            return

        # ─── 5. تنفيذ التنظيف + الحقن في transaction ───
        school = School.objects.first()
        academic_year = academic_year_for_school(school)

        with transaction.atomic():
            # حذف — عامَ الاستيراد وحده. الحذف بلا عامٍ يمحو جدول العام
            # المنقضي وتوزيعاته معه، وهو أرشيفٌ لا مسوّدة.
            self.stdout.write(f"\nتنظيف جداول {academic_year}...")
            n1 = ScheduleSlot.objects.filter(school=school, academic_year=academic_year).delete()[0]
            self.stdout.write(f"   ScheduleSlot: {n1} سجل محذوف")

            n2 = SubjectClassAssignment.objects.filter(
                school=school, academic_year=academic_year
            ).delete()[0]
            self.stdout.write(f"   SubjectClassAssignment: {n2} سجل محذوف")

            if SubjectClassSetup:
                n3 = SubjectClassSetup.objects.filter(
                    school=school, academic_year=academic_year
                ).delete()[0]
                self.stdout.write(f"   SubjectClassSetup: {n3} سجل محذوف")

            # المواد لا تُحذف: مفرداتٌ مشتركةٌ بين الأعوام، وحذفُها يجرف معه
            # إعدادات التقييم (`SubjectClassSetup` بالتتالي) ويفكّ الزيارات
            # الصفّية عن مادّتها. فتُستحدث الناقصةُ وحدها.
            self.stdout.write("\nالمواد...")
            subject_objs = {}
            created_subjects = 0
            for name, code in SUBJECT_CODES.items():
                subject, made = Subject.objects.get_or_create(
                    school=school, name_ar=name, defaults={"code": code}
                )
                subject_objs[name] = subject
                created_subjects += made
            self.stdout.write(
                f"   {len(subject_objs)} مادة — {created_subjects} مستحدثة، "
                f"{len(subject_objs) - created_subjects} قائمة"
            )

            # إنشاء SubjectClassAssignment
            self.stdout.write("\nإنشاء SubjectClassAssignment...")
            sca_count = 0
            sca_objs = {}
            for key, info in assignment_map.items():
                subj_name, cg_id, teacher_uid = key
                subject = subject_objs.get(subj_name)
                if not subject:
                    self.stdout.write(self.style.ERROR(f"   مادة غير موجودة: {subj_name}"))
                    continue
                sca = SubjectClassAssignment.objects.create(
                    school=school,
                    class_group_id=cg_id,
                    subject=subject,
                    teacher_id=teacher_uid,
                    weekly_periods=info["weekly_periods"],
                    academic_year=academic_year,
                    is_active=True,
                )
                sca_objs[(subj_name, cg_id)] = sca
                sca_count += 1
            self.stdout.write(f"   {sca_count} توزيع تم إنشاؤه")

            # إنشاء SubjectClassSetup
            if SubjectClassSetup:
                self.stdout.write("\nإنشاء SubjectClassSetup...")
                scs_count = 0
                for key, info in assignment_map.items():
                    subj_name, cg_id, teacher_uid = key
                    subject = subject_objs.get(subj_name)
                    if not subject:
                        continue
                    SubjectClassSetup.objects.create(
                        school=school,
                        subject=subject,
                        class_group_id=cg_id,
                        teacher_id=teacher_uid,
                        academic_year=academic_year,
                        is_active=True,
                    )
                    scs_count += 1
                self.stdout.write(f"   {scs_count} إعداد مادة تم إنشاؤه")

            # إنشاء ScheduleSlot (مع إزالة التكرارات + تفريق الخميس)
            self.stdout.write("\nإنشاء ScheduleSlot...")
            slots = []
            seen_teacher = set()  # (teacher, day, period)
            seen_class = set()  # (class, day, period)
            skipped = 0
            skipped_details = []  # تفاصيل الحصص المتخطاة (تقسيم شعبة)
            thursday_prep_skipped = 0  # حصص خميس ح7 إعدادي محذوفة
            for row in schedule_rows:
                t_key = (row["teacher_id"], row["day_idx"], row["period"])
                c_key = (
                    row["classgroup_id"],
                    row["day_idx"],
                    row["period"],
                    row.get("elective_group", ""),
                )

                # تخطي الحصة السابعة يوم الخميس للشعب الإعدادية
                if row["day_idx"] == 4 and row["period"] == 7:
                    grade = cg_grade_map.get(row["classgroup_id"])
                    if grade and grade in (7, 8, 9):
                        thursday_prep_skipped += 1
                        skipped_details.append(
                            f"   خميس ح7 إعدادي (صف {grade}): "
                            f"{row['subject_name']} — تم التخطي (الحد 6 حصص)"
                        )
                        continue

                if t_key in seen_teacher or c_key in seen_class:
                    skipped += 1
                    skipped_details.append(
                        f"   تكرار (تقسيم شعبة): يوم={DAY_NAMES[row['day_idx']]} "
                        f"ح{row['period']} — {row['subject_name']}"
                    )
                    continue
                seen_teacher.add(t_key)
                seen_class.add(c_key)
                subject = subject_objs.get(row["subject_name"])
                start_t, end_t = PERIOD_TIMES[row["period"]]
                slots.append(
                    ScheduleSlot(
                        school=school,
                        teacher_id=row["teacher_id"],
                        class_group_id=row["classgroup_id"],
                        subject=subject,
                        day_of_week=row["day_idx"],
                        period_number=row["period"],
                        start_time=start_t,
                        end_time=end_t,
                        academic_year=academic_year,
                        elective_group=row.get("elective_group", ""),
                        is_active=True,
                    )
                )
            ScheduleSlot.objects.bulk_create(slots, batch_size=200)
            self.stdout.write(f"   {len(slots)} حصة تم إنشاؤها")
            if skipped:
                self.stdout.write(f"   تخطي {skipped} تكرار (تقسيم شعبة)")
            if thursday_prep_skipped:
                self.stdout.write(
                    self.style.WARNING(f"   تخطي {thursday_prep_skipped} حصة خميس ح7 إعدادي")
                )
            if skipped_details:
                self.stdout.write("\n   تفاصيل الحصص المتخطاة:")
                for detail in skipped_details:
                    self.stdout.write(detail)

        # ─── 6. ملخص نهائي ───
        self.stdout.write(self.style.SUCCESS("\n" + "=" * 60))
        self.stdout.write(self.style.SUCCESS("  تم الحقن بنجاح!"))
        self.stdout.write(self.style.SUCCESS("=" * 60))
        self.stdout.write(f"  المواد: {len(subject_objs)}")
        self.stdout.write(f"  SubjectClassAssignment: {sca_count}")
        self.stdout.write(f"  SubjectClassSetup: {scs_count if SubjectClassSetup else 'N/A'}")
        self.stdout.write(f"  ScheduleSlot: {len(slots)}")

    def _extract_pdf(self, pdf_path):
        """استخراج جدول كل معلّم من صفحته.

        القراءة بالإحداثيات لا بكشف الجداول: `aSc` يرسم الشبكة خطوطاً لا
        خلايا، فالموضع أصدق من البنية. وأحجام الخطّ تفصل المعاني:

            ٩٫٩    اسم المادة وكود القاعة
            ٢٦     اسم الشعبة (11.4)
            ١٨٫٤   أرقام الحصص في الترويسة — ومنها تُؤخذ مراكز الأعمدة
            ٣٦–٤٠  أسماء الأيام، وأكبرها في الترويسة اسم المعلّم

        ومراكز الأعمدة تُقرأ من الترويسة ولا تُخمَّن: صفحةٌ بعرضٍ مختلف
        تُزيح كل عمود، وجدولُ رقمٍ ثابتٍ يصمت عن ذلك ويُسند الحصة إلى جارتها.
        """
        reader = PdfReader(pdf_path)
        teachers = []

        for page_num, page in enumerate(reader.pages):
            items = []

            def visit(text, cm, tm, font, size, items=items):
                cleaned = normalize_arabic(text)
                if cleaned:
                    items.append({"t": cleaned, "x": tm[4], "y": tm[5], "s": size})

            page.extract_text(visitor_text=visit)

            periods = sorted(
                (
                    (i["x"], int(i["t"]))
                    for i in items
                    if 17 < i["s"] < 20 and i["t"].isascii() and i["t"].isdigit()
                ),
                key=lambda p: -p[0],
            )
            days = sorted(
                (i for i in items if i["t"] in DAY_NAMES and i["x"] > 990),
                key=lambda i: i["y"],
            )
            header = [i for i in items if i["s"] > 30 and i["x"] < 990]
            teacher_name = max(header, key=lambda i: i["s"])["t"] if header else ""

            if len(periods) != 7 or len(days) != len(DAY_NAMES):
                self.stdout.write(f"  ⚠ صفحة {page_num + 1}: ترويسةٌ غير مفهومة — تُخطّى")
                continue

            #: الخلية = اسم شعبةٍ كبير، وحوله مادّتُه وقاعتُه فوقه.
            cells = []
            for i in items:
                if 24 < i["s"] < 28 and SECTION_LABEL.match(i["t"]):
                    cells.append(
                        {
                            "day_idx": min(
                                range(len(days)), key=lambda d: abs(i["y"] - days[d]["y"])
                            ),
                            "period": min(periods, key=lambda p: abs(i["x"] - p[0]))[1],
                            "section": i["t"].replace("/", "."),
                            "y": i["y"],
                            "x": i["x"],
                            "subject_raw": "",
                            "reach": float("inf"),
                            "room": "",
                        }
                    )

            #: «علوم عامة» و«علوم الحاسب» تُرسمان كلمتين منفصلتين على السطر
            #: نفسه. وإسنادُ كلٍّ منهما وحدها يُسقط الثانية خارج نافذة خليّتها،
            #: فتصير المادّة «علوم» — وهي مادّةٌ أخرى تماماً. فتُضمّ الكلمات
            #: المتجاورة أوّلاً، ثمّ يُسنَد السطر كلُّه.
            #: حدود الشبكة: فوقها ترويسةٌ وأوقاتُ حصص، وتحتها تذييلٌ فيه
            #: تاريخُ إنشاء الجدول — وقد ضُمّ إلى مادّةٍ حين غابت هذه الحدود.
            inside = [i for i in items if 8 < i["s"] < 12 and i["x"] < 990 and 150 < i["y"] < 760]
            for i in _merge_runs(inside):
                #: الخلية المدمجة (حصّتان متتاليتان) ضعفُ عرض العمود، واسمُ
                #: مادّتها عند حافّتها لا وسطها — فنافذةٌ بعرض عمودٍ واحد
                #: تُسقطها. وهكذا ضاعت حصص الفنون البصرية في ثلاث عشرة شعبة.
                #: المادّة والقاعة على السطر الذي فوق اسم الشعبة دائماً، فلا
                #: يُنظر إلّا إلى ما تحتها. والنظر في الجهتين يجعل خليّةً
                #: تسرق مادّة جارتها: مادّةُ 8/2 كانت أقربَ إلى الشعبة التي
                #: فوقها منها إلى شعبتها، فسقطت 8/2 بلا مادّة.
                near = [c for c in cells if 0 < c["y"] - i["y"] < 70 and abs(c["x"] - i["x"]) < 120]
                if not near:
                    continue
                distance = min(abs(c["y"] - i["y"]) + abs(c["x"] - i["x"]) for c in near)
                cell = min(near, key=lambda c: abs(c["y"] - i["y"]) + abs(c["x"] - i["x"]))
                if ROOM_CODE.match(i["t"]):
                    cell["room"] = i["t"]
                elif distance < cell["reach"]:
                    #: تُؤخذ أقربُ مادّةٍ لا تُجمع المواد: خليّةٌ مدمجة تجاور
                    #: خليّةً تحمل المادّة نفسها كانت تُنتج «رياضيات رياضيات».
                    cell["subject_raw"] = i["t"]
                    cell["reach"] = distance

            schedule = [
                {k: c[k] for k in ("day_idx", "period", "section", "subject_raw", "room")}
                for c in cells
                if c["subject_raw"]
            ]
            teachers.append({"pdf_name": teacher_name, "page": page_num + 1, "schedule": schedule})

        return teachers

    def _build_teacher_map(self):
        """بناء خريطة: اسم المنصة -> user_id"""
        users = CustomUser.objects.all()
        name_to_id = {}
        for u in users:
            name_to_id[u.full_name] = str(u.id)
            clean = normalize_arabic(u.full_name)
            name_to_id[clean] = str(u.id)
        return name_to_id

    def _year(self):
        """عام الاستيراد — الشُّعب مرتبطةٌ بعامها، ولولاه لاختلط جدولا عامين."""
        from core.models import School

        return academic_year_for_school(School.objects.first())

    def _build_classgroup_map(self):
        """بناء خريطة: section (e.g. '11.4') -> ClassGroup ID"""
        cg_map = {}
        for cg in ClassGroup.objects.filter(academic_year=self._year(), is_active=True):
            # section format: "7.1" -> grade=G7, section=1
            key = f"{cg.grade}.{cg.section}"
            # grade might have 'G' prefix or just number
            grade_num = cg.grade.replace("G", "").replace("g", "")
            key = f"{grade_num}.{cg.section}"
            cg_map[key] = str(cg.id)
            self.stdout.write(f"   {key} -> {cg}")
        return cg_map

    def _prepare_data(self, teachers_data, teacher_id_map, classgroup_map, electives):
        """تجهيز بيانات الحقن"""
        schedule_rows = []
        # key = (subject_name, classgroup_id, teacher_id)
        assignment_counter = defaultdict(int)
        errors = []

        for t in teachers_data:
            pdf_name = t["pdf_name"]

            # حل اسم المعلم
            norm_pdf = normalize_arabic(pdf_name)
            platform_name = TEACHER_MAP.get(pdf_name)
            if not platform_name:
                platform_name = TEACHER_MAP.get(norm_pdf)
            if not platform_name:
                # جرب مطابقة بعد تنظيف كل المفاتيح
                for k, v in TEACHER_MAP.items():
                    if normalize_arabic(k) == norm_pdf:
                        platform_name = v
                        break

            if not platform_name and (pdf_name in teacher_id_map or norm_pdf in teacher_id_map):
                # `TEACHER_MAP` جدولُ الأسماء المختلفة وحدها. ومعلّمٌ اسمُه في
                # الجدول كاسمه في المنصّة لا موضع له فيه — فكان يسقط لأنّه
                # ليس مذكوراً، لا لأنّه غير موجود. ومنه سقط معلّمان جديدان
                # أُدخلا باسميهما كما في الجدول.
                platform_name = pdf_name

            if not platform_name:
                # يُقال عددُ حصصه: معلّمٌ جديدٌ لم يُدخل بعد يعني شعباً
                # كاملةً بلا مادّة، والاسم وحده لا يُنبئ عن حجم الفقد.
                errors.append(
                    f"معلم بدون مطابقة: '{pdf_name}' (ص{t['page']}) — "
                    f"{len(t['schedule'])} حصة لن تُحقن"
                )
                continue

            teacher_uid = teacher_id_map.get(platform_name)
            if not teacher_uid:
                norm_platform = normalize_arabic(platform_name)
                teacher_uid = teacher_id_map.get(norm_platform)

            if not teacher_uid:
                errors.append(
                    f"معلم غير موجود في DB: '{platform_name}' (PDF: '{pdf_name}') — "
                    f"{len(t['schedule'])} حصة لن تُحقن"
                )
                continue

            for slot in t["schedule"]:
                # حل اسم المادة
                subject_raw = slot["subject_raw"]
                subject_name = SUBJECT_MAP.get(subject_raw)
                if not subject_name:
                    norm_raw = normalize_arabic(subject_raw)
                    subject_name = SUBJECT_MAP.get(norm_raw)
                if not subject_name:
                    # جرب مطابقة بعد تنظيف كل المفاتيح
                    norm_raw = normalize_arabic(subject_raw)
                    for k, v in SUBJECT_MAP.items():
                        if normalize_arabic(k) == norm_raw:
                            subject_name = v
                            break
                if not subject_name:
                    # مطابقة جزئية
                    for k, v in SUBJECT_MAP.items():
                        if k in subject_raw or subject_raw in k:
                            subject_name = v
                            break
                if not subject_name:
                    errors.append(f"مادة غير معروفة: '{subject_raw}' ({pdf_name}, ص{t['page']})")
                    continue

                # حل الشعبة
                section = slot["section"]
                cg_id = classgroup_map.get(section)
                if not cg_id:
                    errors.append(f"شعبة غير موجودة: '{section}' ({pdf_name})")
                    continue

                schedule_rows.append(
                    {
                        "teacher_id": teacher_uid,
                        "classgroup_id": cg_id,
                        "subject_name": subject_name,
                        "day_idx": slot["day_idx"],
                        "period": slot["period"],
                        "pdf_name": pdf_name,
                    }
                )

        self._relabel_parallel_by_teacher(schedule_rows, electives)

        # النصاب الأسبوعي يُحسب بعد إعادة تسمية المنقسمة وقبل إسقاط نصفها:
        # المادّتان كلتاهما تستحقّان نصابهما في التوزيع، وإن لم يسع الجدولَ
        # إلّا إحداهما.
        for row in schedule_rows:
            assignment_counter[(row["subject_name"], row["classgroup_id"], row["teacher_id"])] += 1

        parallel = self._label_parallel_periods(schedule_rows)

        # تحويل العداد: نجمع حسب (مادة، شعبة) ونختار المعلم ذو الحصص الأكثر
        # key = (subject_name, cg_id) -> {teacher_id: count}
        grouped = defaultdict(lambda: defaultdict(int))
        for (subj, cg, teacher), count in assignment_counter.items():
            grouped[(subj, cg)][teacher] += count

        assignment_map = {}
        for (subj, cg), teachers in grouped.items():
            # المعلم صاحب أكثر حصص يكون المسؤول
            main_teacher = max(teachers, key=teachers.get)
            total = sum(teachers.values())
            assignment_map[(subj, cg, main_teacher)] = {"weekly_periods": total}

        return schedule_rows, assignment_map, errors, parallel

    def _relabel_parallel_by_teacher(self, schedule_rows, electives):
        """في الحصّة المنقسمة يُعيد لكلّ معلّمٍ مادّته التي أعلنتها المدرسة.

        الجدول يكتب في الخلية المنقسمة اسم مادّةٍ واحدة ومعلّمَين، فتظهر
        المادّة نفسها مرّتين وتختفي الأخرى: «الكيمياء ‖ الكيمياء» وقد كانت
        كيمياءً وفنوناً بصرية. ولو تُركت لتضاعف نصابُ الأولى وسقطت الثانية من
        توزيع المواد كلّه.

        ولا يُستدلّ عليها من الجدول: جُرّب أن تُؤخذ مادّةُ المعلّم الغالبة في
        بقيّة صفحاته فأخطأت — معلّم الكيمياء في الحادي عشر يدرّس العلوم في
        العاشر، فغلبت العلومُ عليه. ومن يدرّس مادّتين لا تُخمَّن مادّتُه.

        فتُعلَن في السطر: `--elective "أحمد شاهين=الكيمياء"`. والإعلان أصدق من
        الاستدلال، ويتبدّل مع اختيارات الطلاب في كل عام.
        """
        if not electives:
            return
        from collections import defaultdict

        collisions = defaultdict(list)
        for row in schedule_rows:
            collisions[(row["classgroup_id"], row["day_idx"], row["period"])].append(row)

        for rows in collisions.values():
            if len(rows) < 2:
                continue
            for row in rows:
                declared = electives.get(row.get("pdf_name", ""))
                if declared:
                    row["subject_name"] = declared

    def _label_parallel_periods(self, schedule_rows):
        """يُسمّي مجموعةَ كلّ نصفٍ من الحصّة المنقسمة، ويُبقي النصفين.

        شُعبٌ أربع تنقسم في حصّةٍ واحدة: 11/1 و12/1 بين التكنولوجيا والفنون
        البصرية، و11/4 و12/4 بين الكيمياء والفنون. القسمان في التوقيت نفسه،
        ويذهب أحدهما إلى معمل الحاسب أو غرفة الفنون ويبقى الآخر.

        وكان `no_class_period_overlap` يمنع النصف الثاني — حصّةٌ واحدة لشعبةٍ
        في التوقيت الواحد — فكان يُفصل ويُقال ولا يُحقن، فيرى المعلّم والطالب
        خليّةً ناقصة. فدخلت `elective_group` في القيد: فارغةٌ في حصص الشعبة
        كاملةً فيبقى المنع كما كان، ومُسمّاةٌ باسم المادّة في المنقسمة فيسع
        القيدُ نصفيها.

        والمعلّمان لا يتعارضان: قيدُهما على المعلّم لا على الشعبة، وكلٌّ منهما
        في حصّةٍ واحدة.
        """
        seen, groups, parallel = {}, {}, []
        for row in schedule_rows:
            key = (row["classgroup_id"], row["day_idx"], row["period"])
            if key in seen:
                first = seen[key]
                first["elective_group"] = first["subject_name"]
                row["elective_group"] = row["subject_name"]
                groups.setdefault(key, [first]).append(row)
            else:
                seen[key] = row
                row.setdefault("elective_group", "")
        for key, rows in groups.items():
            parallel.append(tuple(rows))
        return parallel

    def _fill_double_periods(self, schedule_rows, cg_grade_map):
        """
        ملء الحصص المزدوجة المفقودة.
        في PDF aSc Timetables، الحصة المزدوجة (مثل ART/IT/CS) تظهر كخلية مدمجة
        فيُستخرج منها حصة واحدة فقط. هذه الدالة تكتشف الحصة المفقودة وتضيفها.
        """
        from collections import defaultdict

        # فهرس الحصص الموجودة: (classgroup, day) -> set of periods
        class_day_periods = defaultdict(set)
        # فهرس المعلم: (teacher, day) -> set of periods
        teacher_day_periods = defaultdict(set)
        # فهرس الحصص حسب (teacher, classgroup, subject, day) -> [periods]
        teacher_subject_day = defaultdict(list)

        for row in schedule_rows:
            key_cd = (row["classgroup_id"], row["day_idx"])
            class_day_periods[key_cd].add(row["period"])

            key_td = (row["teacher_id"], row["day_idx"])
            teacher_day_periods[key_td].add(row["period"])

            if row["subject_name"] in DOUBLE_PERIOD_SUBJECTS:
                key_tsd = (
                    row["teacher_id"],
                    row["classgroup_id"],
                    row["subject_name"],
                    row["day_idx"],
                )
                teacher_subject_day[key_tsd].append(row["period"])

        # ترتيب: المواد الأقل حصصاً أولاً (IT/CS قبل ART)
        subject_total = defaultdict(int)
        for key, plist in teacher_subject_day.items():
            subject_total[key[2]] += len(plist)
        sorted_items = sorted(teacher_subject_day.items(), key=lambda x: subject_total[x[0][2]])

        filled = []
        for key, periods in sorted_items:
            if len(periods) >= 2:
                continue

            teacher_id, cg_id, subject_name, day_idx = key
            existing_period = periods[0]

            grade = cg_grade_map.get(cg_id)
            if day_idx == 4:
                max_period = 6 if grade and grade in (7, 8, 9) else 7
            else:
                max_period = 7

            class_occupied = class_day_periods[(cg_id, day_idx)]
            teacher_busy = teacher_day_periods[(teacher_id, day_idx)]

            candidate = None
            # أولاً: الحصة السابقة
            if (
                existing_period - 1 >= 1
                and (existing_period - 1) not in class_occupied
                and (existing_period - 1) not in teacher_busy
            ):
                candidate = existing_period - 1
            # ثانياً: الحصة التالية
            elif (
                existing_period + 1 <= max_period
                and (existing_period + 1) not in class_occupied
                and (existing_period + 1) not in teacher_busy
            ):
                candidate = existing_period + 1

            if candidate:
                new_row = {
                    "teacher_id": teacher_id,
                    "classgroup_id": cg_id,
                    "subject_name": subject_name,
                    "day_idx": day_idx,
                    "period": candidate,
                }
                filled.append(new_row)
                # تحديث الفهارس لمنع التصادم
                class_day_periods[(cg_id, day_idx)].add(candidate)
                teacher_day_periods[(teacher_id, day_idx)].add(candidate)

        schedule_rows.extend(filled)
        return schedule_rows, len(filled)
