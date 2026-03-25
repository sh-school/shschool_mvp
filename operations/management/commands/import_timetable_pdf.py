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
import uuid
from collections import defaultdict
from datetime import time

import fitz  # PyMuPDF

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

import unicodedata

from core.models import ClassGroup, CustomUser, School


def normalize_arabic(text):
    """تنظيف النص العربي: توحيد الأشكال المختلفة للحروف"""
    if not text:
        return ""
    # NFKC normalization - يحوّل الأشكال الخاصة للحروف
    text = unicodedata.normalize("NFKC", text)
    # استبدالات إضافية للحروف العربية الخاصة
    replacements = {
        "\ufefb": "لا", "\ufefc": "لا",  # لام ألف
        "\ufef7": "لأ", "\ufef8": "لأ",  # لام ألف همزة
        "\ufef9": "لإ", "\ufefa": "لإ",  # لام ألف همزة تحت
        "\ufef5": "لآ", "\ufef6": "لآ",  # لام ألف مد
        "\ufdf2": "الله",                 # لفظ الجلالة
        "ﷲ": "الله",
        "ﻻ": "لا", "ﻼ": "لا",
        "ﺷ": "ش", "ﺵ": "ش", "ﺶ": "ش",
        "ﺸ": "ش",
        "ﺣ": "ح", "ﺤ": "ح", "ﺡ": "ح", "ﺢ": "ح",
        "ﺠ": "ج", "ﺟ": "ج", "ﺝ": "ج", "ﺞ": "ج",
        "ﺸ": "ش",
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
    TimeSlotConfig,
)

try:
    from assessments.models import SubjectClassSetup
except ImportError:
    SubjectClassSetup = None


# ──────────────────────────────────────────────────
# مطابقة أسماء المواد: PDF (عربي معكوس) -> اسم نظيف
# ──────────────────────────────────────────────────
SUBJECT_MAP = {
    "ةيمﻼسا ةيبرت": "التربية الإسلامية",
    "ةيبرعلا ةغللا": "اللغة العربية",
    "ةيزيلجنإ ةغل": "اللغة الإنجليزية",
    "تايــــضاير": "الرياضيات",
    "موـــــــــلع": "العلوم",
    "ةـماع مولع": "العلوم العامة",
    "ةيندب ةيبرت": "التربية البدنية",
    "ةيرصب نونف": "الفنون البصرية",
    "ةيتايحلا تاراهملا": "المهارات الحياتية والمهنية",
    "ةيعامتجا مولع": "الدراسات الاجتماعية",
    "اــــيجولونكت": "التكنولوجيا",
    "تامولعملا ايجولونكت": "تكنولوجيا المعلومات",
    "بساحلا مولع": "علوم الحاسب",
    "ءاـــــــــــيميك": "الكيمياء",
    "ءاـــــــــيزيف": "الفيزياء",
    "ءاــــــــــــيحأ": "الأحياء",
    "خــــــــيرات": "التاريخ",
    "اــــيفارغج": "الجغرافيا",
    "ايفارغج": "الجغرافيا",
    "اــــــيفارغج": "الجغرافيا",
    "لامعا ةرادا": "إدارة الأعمال",
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
COL_TO_PERIOD = {8: 1, 6: 2, 5: 3, 4: 4, 2: 5, 1: 6, 0: 7}

# أيام الأسبوع
DAY_NAMES = ["الأحد", "الإثنين", "الثلاثاء", "الأربعاء", "الخميس"]


class Command(BaseCommand):
    help = "تنظيف + إعادة حقن الجدول الدراسي من PDF المعلمين"

    def add_arguments(self, parser):
        parser.add_argument(
            "--pdf",
            required=True,
            help="مسار ملف PDF المعلمين (75 صفحة)",
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

        mode_label = (
            "وضع التحقق فقط" if validate_only
            else "وضع المعاينة" if dry_run
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
        for cg in ClassGroup.objects.filter(is_active=True):
            grade_num = str(cg.grade).replace("G", "").replace("g", "")
            try:
                cg_grade_map[str(cg.id)] = int(grade_num)
            except (ValueError, TypeError):
                pass

        # ─── 4. تجهيز البيانات ───
        self.stdout.write("\nتجهيز البيانات...")
        schedule_rows, assignment_map, errors = self._prepare_data(
            teachers_data, teacher_id_map, classgroup_map
        )
        self.stdout.write(f"   {len(schedule_rows)} حصة جاهزة للحقن")
        self.stdout.write(
            f"   {len(assignment_map)} توزيع (معلم+مادة+شعبة)"
        )
        if errors:
            for e in errors:
                self.stdout.write(self.style.ERROR(f"   {e}"))

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
            self.stdout.write(self.style.WARNING(
                f"\n[تحذير] {len(thursday_warnings)} حصة خميس ح7 لشعب إعدادية (الحد 6 حصص):"
            ))
            for w in thursday_warnings:
                self.stdout.write(self.style.WARNING(w))

        # ─── 4c. ملخص التحقق ───
        total_errors = len(errors)
        total_warnings = len(thursday_warnings)
        if validate_only:
            self.stdout.write("\n" + "=" * 60)
            if total_errors == 0 and total_warnings == 0:
                self.stdout.write(self.style.SUCCESS(
                    "  [OK] التحقق ناجح — صفر اخطاء، صفر تحذيرات"
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f"  نتيجة التحقق: {total_errors} خطأ، {total_warnings} تحذير"
                ))
            self.stdout.write(f"  الحصص: {len(schedule_rows)}")
            self.stdout.write(f"  التوزيعات: {len(assignment_map)}")
            self.stdout.write("=" * 60)
            return

        if dry_run:
            self.stdout.write(self.style.WARNING("\nوضع المعاينة — لم يتم تنفيذ أي تغيير"))
            return

        # ─── 5. تنفيذ التنظيف + الحقن في transaction ───
        school = School.objects.first()
        academic_year = settings.CURRENT_ACADEMIC_YEAR

        with transaction.atomic():
            # حذف
            self.stdout.write("\nتنظيف الجداول...")
            n1 = ScheduleSlot.objects.filter(school=school).delete()[0]
            self.stdout.write(f"   ScheduleSlot: {n1} سجل محذوف")

            n2 = SubjectClassAssignment.objects.filter(school=school).delete()[0]
            self.stdout.write(f"   SubjectClassAssignment: {n2} سجل محذوف")

            if SubjectClassSetup:
                n3 = SubjectClassSetup.objects.filter(school=school).delete()[0]
                self.stdout.write(f"   SubjectClassSetup: {n3} سجل محذوف")

            n4 = Subject.objects.filter(school=school).delete()[0]
            self.stdout.write(f"   Subject: {n4} سجل محذوف")

            # إنشاء المواد
            self.stdout.write("\nإنشاء المواد...")
            subject_objs = {}
            for name, code in SUBJECT_CODES.items():
                s = Subject.objects.create(
                    school=school,
                    name_ar=name,
                    code=code,
                )
                subject_objs[name] = s
                self.stdout.write(f"   {name} ({code})")

            # إنشاء SubjectClassAssignment
            self.stdout.write("\nإنشاء SubjectClassAssignment...")
            sca_count = 0
            sca_objs = {}
            for key, info in assignment_map.items():
                subj_name, cg_id, teacher_uid = key
                subject = subject_objs.get(subj_name)
                if not subject:
                    self.stdout.write(
                        self.style.ERROR(f"   مادة غير موجودة: {subj_name}")
                    )
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
            seen_class = set()    # (class, day, period)
            skipped = 0
            skipped_details = []   # تفاصيل الحصص المتخطاة (تقسيم شعبة)
            thursday_prep_skipped = 0  # حصص خميس ح7 إعدادي محذوفة
            for row in schedule_rows:
                t_key = (row["teacher_id"], row["day_idx"], row["period"])
                c_key = (row["classgroup_id"], row["day_idx"], row["period"])

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
                        is_active=True,
                    )
                )
            ScheduleSlot.objects.bulk_create(slots, batch_size=200)
            self.stdout.write(f"   {len(slots)} حصة تم إنشاؤها")
            if skipped:
                self.stdout.write(f"   تخطي {skipped} تكرار (تقسيم شعبة)")
            if thursday_prep_skipped:
                self.stdout.write(self.style.WARNING(
                    f"   تخطي {thursday_prep_skipped} حصة خميس ح7 إعدادي"
                ))
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
        """استخراج بيانات جميع المعلمين من PDF (75 صفحة)"""
        doc = fitz.open(pdf_path)
        teachers = []

        for page_num in range(len(doc)):
            page = doc[page_num]

            # اسم المعلم (خط كبير حجم ~29.9 في y<60)
            teacher_name = ""
            blocks = page.get_text("dict")["blocks"]
            for b in blocks:
                if "lines" in b:
                    for line in b["lines"]:
                        for span in line["spans"]:
                            if 28 < span["size"] < 32 and span["origin"][1] < 60:
                                teacher_name = span["text"].strip()

            # جدول الحصص
            tables = page.find_tables()
            if not tables.tables:
                continue

            table = tables.tables[0]
            data = table.extract()

            schedule = []
            for row_idx in range(2, min(7, len(data))):
                day_idx = row_idx - 2
                row = data[row_idx]
                for col_idx in range(len(row)):
                    if col_idx in COL_TO_PERIOD and row[col_idx] and row[col_idx].strip():
                        cell = row[col_idx].strip()
                        parts = cell.split("\n")
                        if len(parts) >= 2:
                            section = parts[-1].strip()
                            info = parts[0].strip()
                            room = ""
                            subject_raw = info
                            match = re.match(r"^([A-Za-z0-9.]+)\s+(.*)", info)
                            if match:
                                room = match.group(1)
                                subject_raw = match.group(2)

                            # تنظيف اسم المادة من المسافات الزائدة
                            subject_raw = re.sub(r"\s+", " ", subject_raw).strip()

                            schedule.append(
                                {
                                    "day_idx": day_idx,
                                    "period": COL_TO_PERIOD[col_idx],
                                    "section": section,
                                    "subject_raw": subject_raw,
                                    "room": room,
                                }
                            )

            teachers.append(
                {
                    "pdf_name": teacher_name,
                    "page": page_num + 1,
                    "schedule": schedule,
                }
            )

        doc.close()
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

    def _build_classgroup_map(self):
        """بناء خريطة: section (e.g. '11.4') -> ClassGroup ID"""
        cg_map = {}
        for cg in ClassGroup.objects.filter(is_active=True):
            # section format: "7.1" -> grade=G7, section=1
            key = f"{cg.grade}.{cg.section}"
            # grade might have 'G' prefix or just number
            grade_num = cg.grade.replace("G", "").replace("g", "")
            key = f"{grade_num}.{cg.section}"
            cg_map[key] = str(cg.id)
            self.stdout.write(f"   {key} -> {cg}")
        return cg_map

    def _prepare_data(self, teachers_data, teacher_id_map, classgroup_map):
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

            if not platform_name:
                errors.append(f"معلم بدون مطابقة: '{pdf_name}' (ص{t['page']})")
                continue

            teacher_uid = teacher_id_map.get(platform_name)
            if not teacher_uid:
                norm_platform = normalize_arabic(platform_name)
                teacher_uid = teacher_id_map.get(norm_platform)

            if not teacher_uid:
                errors.append(
                    f"معلم غير موجود في DB: '{platform_name}' (PDF: '{pdf_name}')"
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
                    errors.append(
                        f"مادة غير معروفة: '{subject_raw}' ({pdf_name}, ص{t['page']})"
                    )
                    continue

                # حل الشعبة
                section = slot["section"]
                cg_id = classgroup_map.get(section)
                if not cg_id:
                    errors.append(
                        f"شعبة غير موجودة: '{section}' ({pdf_name})"
                    )
                    continue

                schedule_rows.append(
                    {
                        "teacher_id": teacher_uid,
                        "classgroup_id": cg_id,
                        "subject_name": subject_name,
                        "day_idx": slot["day_idx"],
                        "period": slot["period"],
                    }
                )

                # عداد الحصص الأسبوعية لكل (مادة، شعبة، معلم)
                akey = (subject_name, cg_id, teacher_uid)
                assignment_counter[akey] += 1

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

        return schedule_rows, assignment_map, errors
