"""
reports/services.py
━━━━━━━━━━━━━━━━━━
Business logic لوحدة التقارير — بدون أي HTTP logic

يشمل:
  - ReportDataService  : تجميع بيانات التقارير
  - ExcelService       : إنشاء ملفات Excel باحترافية كاملة
"""

from __future__ import annotations

import logging
from io import BytesIO
from typing import TYPE_CHECKING

from django.conf import settings
from django.http import HttpResponse
from django.utils import timezone

from assessments.models import (
    AnnualSubjectResult,
    StudentSubjectResult,
    SubjectClassSetup,
)
from core.models import StudentEnrollment
from operations.models import StudentAttendance

if TYPE_CHECKING:
    from core.models import ClassGroup, CustomUser, School

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# ReportDataService — تجميع البيانات
# ══════════════════════════════════════════════════════════════════════


class ReportDataService:
    """تجميع بيانات التقارير — بدون أي HTTP logic"""

    @staticmethod
    def get_student_report(
        student: CustomUser,
        school: School,
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> dict:
        """بيانات تقرير الطالب السنوي الكاملة"""
        annual = (
            AnnualSubjectResult.objects.filter(student=student, school=school, academic_year=year)
            .select_related("setup__subject")
            .order_by("setup__subject__name_ar")
        )

        s1_map = {
            r.setup_id: r
            for r in StudentSubjectResult.objects.filter(
                student=student, school=school, semester="S1"
            )
        }
        s2_map = {
            r.setup_id: r
            for r in StudentSubjectResult.objects.filter(
                student=student, school=school, semester="S2"
            )
        }

        rows = [
            {
                "subject": ann.setup.subject.name_ar,
                "s1": s1_map.get(ann.setup_id),
                "s2": s2_map.get(ann.setup_id),
                "annual": ann,
            }
            for ann in annual
        ]

        total = annual.count()
        passed = annual.filter(status="pass").count()
        failed = annual.filter(status="fail").count()
        grades = [float(r.annual_total) for r in annual if r.annual_total]
        avg = round(sum(grades) / len(grades), 2) if grades else None

        enrollment = (
            StudentEnrollment.objects.filter(student=student, is_active=True)
            .select_related("class_group")
            .first()
        )

        att = StudentAttendance.objects.filter(student=student, session__school=school)
        absent_total = att.filter(status="absent").count()
        late_total = att.filter(status="late").count()

        return {
            "student": student,
            "school": school,
            "year": year,
            "enrollment": enrollment,
            "rows": rows,
            "total": total,
            "passed": passed,
            "failed": failed,
            "avg": avg,
            "absent_total": absent_total,
            "late_total": late_total,
            "print_date": timezone.now().date(),
        }

    @staticmethod
    def get_class_results(
        class_group: ClassGroup,
        school: School,
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> dict:
        """بيانات كشف نتائج الفصل الكامل مع ترتيب + ملخص"""
        enrollments = list(
            StudentEnrollment.objects.filter(class_group=class_group, is_active=True)
            .select_related("student")
            .order_by("student__full_name")
        )

        setups = list(
            SubjectClassSetup.objects.filter(
                class_group=class_group, school=school, academic_year=year
            )
            .select_related("subject")
            .order_by("subject__name_ar")
        )

        subjects = [s.subject for s in setups]

        # ── جلب كل النتائج السنوية دفعةً واحدة (يُلغي N×M queries) ──
        student_ids = [enr.student_id for enr in enrollments]
        all_annuals = AnnualSubjectResult.objects.filter(
            setup__in=setups,
            student_id__in=student_ids,
            academic_year=year,
        ).select_related("setup__subject")

        # lookup: (student_id, setup_id) → AnnualSubjectResult
        annual_map = {(a.student_id, a.setup_id): a for a in all_annuals}

        student_rows: list = []
        for enr in enrollments:
            row: dict = {"student": enr.student, "grades": {}}
            grades: list = []
            passed = failed = 0
            for setup in setups:
                annual = annual_map.get((enr.student_id, setup.id))
                row["grades"][setup.subject.name_ar] = annual
                if annual:
                    if annual.annual_total:
                        grades.append(float(annual.annual_total))
                    if annual.status == "pass":
                        passed += 1
                    elif annual.status == "fail":
                        failed += 1

            avg = round(sum(grades) / len(grades), 2) if grades else None
            row["avg"] = avg
            row["passed"] = passed
            row["failed"] = failed
            row["status"] = (
                "ناجح" if failed == 0 and passed > 0 else ("راسب" if failed > 0 else "—")
            )
            student_rows.append(row)

        # ترتيب حسب المتوسط
        student_rows.sort(key=lambda x: x["avg"] or 0, reverse=True)
        for i, row in enumerate(student_rows, start=1):
            row["rank"] = i
            row["grades_list"] = [row["grades"].get(s.name_ar) for s in subjects]

        total_passed = sum(1 for r in student_rows if r["failed"] == 0 and r["passed"] > 0)
        total_failed = sum(1 for r in student_rows if r["failed"] > 0)

        return {
            "class_group": class_group,
            "school": school,
            "year": year,
            "subjects": subjects,
            "student_rows": student_rows,
            "total_students": len(student_rows),
            "total_passed": total_passed,
            "total_failed": total_failed,
            "print_date": timezone.now().date(),
        }

    @staticmethod
    def get_attendance_report(
        class_group: ClassGroup,
        school: School,
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> dict:
        """بيانات تقرير الغياب لفصل"""
        enrollments = list(
            StudentEnrollment.objects.filter(class_group=class_group, is_active=True)
            .select_related("student")
            .order_by("student__full_name")
        )

        # ── جلب كل سجلات الحضور دفعةً واحدة (يُلغي N×4 queries) ──
        student_ids = [enr.student_id for enr in enrollments]
        all_att = StudentAttendance.objects.filter(
            student_id__in=student_ids,
            session__school=school,
        ).values("student_id", "status")

        # تجميع الإحصائيات لكل طالب في Python
        from collections import defaultdict

        att_counts = defaultdict(lambda: {"total": 0, "absent": 0, "late": 0, "excused": 0})
        for rec in all_att:
            sid = rec["student_id"]
            att_counts[sid]["total"] += 1
            if rec["status"] in ("absent", "late", "excused"):
                att_counts[sid][rec["status"]] += 1

        student_rows: list = []
        for enr in enrollments:
            counts = att_counts[enr.student_id]
            total = counts["total"]
            absent = counts["absent"]
            late = counts["late"]
            excused = counts["excused"]
            present = total - absent - late - excused
            pct = round(present / total * 100) if total else 0

            student_rows.append(
                {
                    "student": enr.student,
                    "total_sessions": total,
                    "present": present,
                    "absent": absent,
                    "late": late,
                    "excused": excused,
                    "attendance_pct": pct,
                }
            )

        return {
            "class_group": class_group,
            "school": school,
            "year": year,
            "student_rows": student_rows,
            "print_date": timezone.now().date(),
        }

    @staticmethod
    def get_behavior_report(school: School, year: str = settings.CURRENT_ACADEMIC_YEAR) -> dict:
        """بيانات تقرير السلوك العام"""
        from behavior.models import BehaviorInfraction

        infractions = (
            BehaviorInfraction.objects.filter(school=school)
            .select_related("student", "reported_by")
            .order_by("-date")
        )

        return {
            "school": school,
            "year": year,
            "infractions": infractions,
            "print_date": timezone.now().date(),
        }


# ══════════════════════════════════════════════════════════════════════
# ExcelService — إنشاء Excel باحترافية كاملة
# ══════════════════════════════════════════════════════════════════════


class ExcelService:
    """
    إنشاء ملفات Excel بهوية قطرية كاملة:
      - رأس 4 صفوف: وزارة + مدرسة + عنوان + أعمدة
      - شعار المدرسة في الرأس
      - حماية الورقة (قراءة فقط — كلمة السر من EXCEL_PROTECTION_PASSWORD)
      - فلاتر تلقائية + تجميد الرأس
      - RTL عربي + صفوف متبادلة + تلوين شرطي
    """

    MAROON = "8A1538"
    WHITE = "FFFFFF"
    ALT_BG = "FDF2F5"
    HEADER1 = "F5EEF1"  # وزارة
    HEADER2 = "FAFAFA"  # مدرسة
    HEADER3 = "FDF2F5"  # عنوان

    # ── بنية تحتية ────────────────────────────────────────────────────

    @classmethod
    def _make_workbook(cls, sheet_title: str) -> tuple:
        """Workbook جديد مع ستايل الهوية القطرية"""
        import openpyxl
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_title
        ws.sheet_view.rightToLeft = True

        styles = {
            "header_font": Font(name="Arial", bold=True, color=cls.WHITE, size=11),
            "header_fill": PatternFill("solid", fgColor=cls.MAROON),
            "header_align": Alignment(horizontal="center", vertical="center", wrap_text=True),
            "data_align": Alignment(horizontal="center", vertical="center", wrap_text=True),
            "thin_border": Border(
                left=Side(style="thin", color="DDDDDD"),
                right=Side(style="thin", color="DDDDDD"),
                top=Side(style="thin", color="DDDDDD"),
                bottom=Side(style="thin", color="DDDDDD"),
            ),
            "alt_fill": PatternFill("solid", fgColor=cls.ALT_BG),
        }
        return wb, ws, styles

    @classmethod
    def _add_professional_header(
        cls, ws: object, school_name: str, report_title: str, year: str, num_cols: int
    ) -> None:
        """
        4 صفوف رأس احترافية:
          الصف 1 — وزارة التربية والتعليم العالي — دولة قطر  + تاريخ الطباعة
          الصف 2 — اسم المدرسة (كبير، كستنائي)
          الصف 3 — عنوان التقرير | السنة الدراسية
          الصف 4 — رأس الأعمدة (يملأه المستدعي عبر _add_header_row)
        """
        from pathlib import Path

        from django.conf import settings
        from openpyxl.styles import Alignment, Border, Font, PatternFill, Side

        col_letter = ws.cell(row=1, column=num_cols).column_letter
        today_str = timezone.now().strftime("%Y/%m/%d")

        bottom_border = Border(bottom=Side(style="medium", color=cls.MAROON))

        # ── صف 1: وزارة التربية + تاريخ الطباعة ─────────────────────
        ws.merge_cells(f"A1:{col_letter}1")
        c = ws["A1"]
        c.value = f"وزارة التربية والتعليم والتعليم العالي — دولة قطر          {today_str}"
        c.font = Font(name="Arial", size=9, color="555555")
        c.fill = PatternFill("solid", fgColor=cls.HEADER1)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = bottom_border
        ws.row_dimensions[1].height = 22

        # ── صف 2: اسم المدرسة ────────────────────────────────────────
        ws.merge_cells(f"A2:{col_letter}2")
        c = ws["A2"]
        c.value = school_name
        c.font = Font(name="Arial", bold=True, size=16, color=cls.MAROON)
        c.fill = PatternFill("solid", fgColor=cls.HEADER2)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = bottom_border
        ws.row_dimensions[2].height = 38

        # ── صف 3: عنوان التقرير + السنة الدراسية ─────────────────────
        ws.merge_cells(f"A3:{col_letter}3")
        c = ws["A3"]
        c.value = f"{report_title}   |   السنة الدراسية: {year}"
        c.font = Font(name="Arial", bold=True, size=12, color=cls.MAROON)
        c.fill = PatternFill("solid", fgColor=cls.HEADER3)
        c.alignment = Alignment(horizontal="center", vertical="center")
        c.border = bottom_border
        ws.row_dimensions[3].height = 26

        # ── شعار المدرسة ──────────────────────────────────────────────
        try:
            from openpyxl.drawing.image import Image as XLImage

            logo_path = Path(settings.BASE_DIR) / "static" / "icons" / "badge-72.png"
            if not logo_path.exists():
                logo_path = Path(settings.BASE_DIR) / "static" / "icons" / "icon-192.png"
            if logo_path.exists():
                img = XLImage(str(logo_path))
                img.width = 54
                img.height = 54
                ws.add_image(img, "A1")
        except (ImportError, OSError, ValueError) as exc:
            logger.debug("Excel logo: %s", exc)

    @classmethod
    def _add_header_row(cls, ws: object, styles: dict, row_num: int, columns: list) -> None:
        """رأس الجدول: قائمة من (عنوان، عرض)"""
        for col_idx, (header, width) in enumerate(columns, start=1):
            cell = ws.cell(row=row_num, column=col_idx, value=header)
            cell.font = styles["header_font"]
            cell.fill = styles["header_fill"]
            cell.alignment = styles["header_align"]
            cell.border = styles["thin_border"]
            ws.column_dimensions[cell.column_letter].width = width
        ws.row_dimensions[row_num].height = 26

    @classmethod
    def _style_data_row(
        cls, ws: object, styles: dict, row_num: int, num_cols: int, is_alt: bool = False
    ) -> None:
        """تطبيق ستايل على صف بيانات"""
        for col_idx in range(1, num_cols + 1):
            cell = ws.cell(row=row_num, column=col_idx)
            cell.border = styles["thin_border"]
            cell.alignment = styles["data_align"]
            if is_alt:
                cell.fill = styles["alt_fill"]
        ws.row_dimensions[row_num].height = 20

    @classmethod
    def _apply_protection(cls, ws: object, num_cols: int) -> None:
        """
        حماية الورقة (قراءة فقط) مع السماح بالتصفية والفرز.
        كلمة السر تُقرأ من متغير البيئة EXCEL_PROTECTION_PASSWORD.
        """
        from django.conf import settings

        ws.protection.sheet = True
        ws.protection.password = getattr(settings, "EXCEL_PROTECTION_PASSWORD", "") or "protected"
        ws.protection.autoFilter = False  # يسمح باستخدام الفلاتر
        ws.protection.sort = False  # يسمح بالفرز

    @classmethod
    def _setup_print_a4_portrait(cls, ws: object, num_cols: int, num_data_rows: int) -> None:
        """
        إعداد الطباعة على ورق A4 عمودي (Portrait):
        - هوامش ضيقة مناسبة
        - تكرار صفوف الرأس في كل صفحة
        - ملاءمة العرض في صفحة واحدة
        """
        from openpyxl.worksheet.properties import PageSetupProperties

        # A4 = 9, portrait
        ws.page_setup.paperSize = 9
        ws.page_setup.orientation = "portrait"
        ws.page_setup.fitToWidth = 1
        ws.page_setup.fitToHeight = 0
        ws.sheet_properties.pageSetUpPr = PageSetupProperties(fitToPage=True)

        # هوامش ضيقة (بالبوصة)
        ws.page_margins.left = 0.4
        ws.page_margins.right = 0.4
        ws.page_margins.top = 0.5
        ws.page_margins.bottom = 0.5
        ws.page_margins.header = 0.2
        ws.page_margins.footer = 0.2

        # تكرار أول 4 صفوف (الرأس) في كل صفحة مطبوعة
        ws.print_title_rows = "1:4"

        # منطقة الطباعة
        from openpyxl.utils import get_column_letter

        col_letter = get_column_letter(num_cols)
        last_row = num_data_rows + 4
        ws.print_area = f"A1:{col_letter}{last_row}"

        # هيدر وفوتر الطباعة (Excel format codes)
        ws.oddHeader.center.text = (
            '&"Arial,Bold"&9'
            "\u0645\u062f\u0631\u0633\u0629 \u0627\u0644\u0634\u062d\u0627\u0646\u064a\u0629"
        )
        ws.oddFooter.center.text = "&P / &N"
        ws.oddFooter.right.text = "&D"

    @classmethod
    def to_response(cls, wb: object, filename: str) -> HttpResponse:
        """تحويل Workbook إلى HttpResponse جاهز للتنزيل"""
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(
            buf.read(),
            content_type=("application/vnd.openxmlformats-officedocument" ".spreadsheetml.sheet"),
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    # ── التقارير ──────────────────────────────────────────────────────

    @classmethod
    def class_results_excel(
        cls,
        class_group: ClassGroup,
        school: School,
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> HttpResponse:
        """
        Excel كشف نتائج الفصل:
        - رأس 4 صفوف احترافي + شعار
        - ترتيب حسب المتوسط
        - تلوين أحمر للدرجات < 50
        - تلوين الحالة (ناجح/راسب)
        - فلاتر تلقائية + تجميد الرأس + حماية الورقة
        """
        from openpyxl.styles import Font

        data = ReportDataService.get_class_results(class_group, school, year)
        subjects = data["subjects"]
        num_cols = 3 + len(subjects) + 3  # م + اسم + وطني + مواد + متوسط + حالة + ترتيب

        wb, ws, styles = cls._make_workbook("كشف النتائج")

        cls._add_professional_header(
            ws,
            school.name,
            f"كشف نتائج الفصل — {class_group}",
            year,
            num_cols,
        )

        columns = (
            [("م", 5), ("اسم الطالب", 28), ("الرقم الوطني", 16)]
            + [(s.name_ar[:18], 11) for s in subjects]
            + [("المتوسط", 10), ("الحالة", 10), ("الترتيب", 8)]
        )
        cls._add_header_row(ws, styles, 4, columns)

        # تجميد بعد صفوف الرأس الأربعة + فلاتر تلقائية
        ws.freeze_panes = "A5"
        col_letter = ws.cell(row=4, column=num_cols).column_letter
        ws.auto_filter.ref = f"A4:{col_letter}4"

        for row in data["student_rows"]:
            rank = row["rank"]
            row_num = rank + 4  # البيانات تبدأ من الصف 5
            is_alt = rank % 2 == 0
            st = row["student"]

            ws.cell(row=row_num, column=1, value=rank)
            ws.cell(row=row_num, column=2, value=st.full_name)
            ws.cell(row=row_num, column=3, value=st.national_id or "")

            for col_off, subj in enumerate(subjects, start=4):
                ann = row["grades"].get(subj.name_ar)
                grade = float(ann.annual_total) if ann and ann.annual_total else None
                cell = ws.cell(
                    row=row_num, column=col_off, value=grade if grade is not None else "—"
                )
                if grade is not None and grade < 50:
                    cell.font = Font(name="Arial", color="DC2626", bold=True)

            ws.cell(
                row=row_num,
                column=4 + len(subjects),
                value=row["avg"] if row["avg"] is not None else "—",
            )

            status_cell = ws.cell(row=row_num, column=5 + len(subjects), value=row["status"])
            if row["status"] == "ناجح":
                status_cell.font = Font(name="Arial", color="15803D", bold=True)
            elif row["status"] == "راسب":
                status_cell.font = Font(name="Arial", color="DC2626", bold=True)

            ws.cell(row=row_num, column=6 + len(subjects), value=rank)
            cls._style_data_row(ws, styles, row_num, num_cols, is_alt)

        cls._apply_protection(ws, num_cols)
        cls._setup_print_a4_portrait(ws, num_cols, len(data["student_rows"]))

        filename = f"نتائج_{class_group.get_grade_display()}" f"_{class_group.section}_{year}.xlsx"
        return cls.to_response(wb, filename)

    @classmethod
    def attendance_excel(
        cls,
        class_group: ClassGroup,
        school: School,
        year: str = settings.CURRENT_ACADEMIC_YEAR,
    ) -> HttpResponse:
        """
        Excel تقرير الغياب:
        - رأس 4 صفوف احترافي + شعار
        - أحمر للغياب > 10 حصة
        - أحمر/أخضر لنسبة الحضور
        - فلاتر تلقائية + تجميد الرأس + حماية الورقة
        """
        from openpyxl.styles import Font

        data = ReportDataService.get_attendance_report(class_group, school, year)
        num_cols = 8

        wb, ws, styles = cls._make_workbook("الحضور والغياب")

        cls._add_professional_header(
            ws,
            school.name,
            f"تقرير الحضور والغياب — {class_group}",
            year,
            num_cols,
        )

        columns = [
            ("م", 5),
            ("اسم الطالب", 28),
            ("الرقم الوطني", 16),
            ("إجمالي الحصص", 13),
            ("حاضر", 10),
            ("غائب", 10),
            ("متأخر", 10),
            ("نسبة الحضور %", 14),
        ]
        cls._add_header_row(ws, styles, 4, columns)

        ws.freeze_panes = "A5"
        ws.auto_filter.ref = "A4:H4"

        for idx, row in enumerate(data["student_rows"], start=1):
            row_num = idx + 4  # البيانات تبدأ من الصف 5
            st = row["student"]
            pct = row["attendance_pct"]

            ws.cell(row=row_num, column=1, value=idx)
            ws.cell(row=row_num, column=2, value=st.full_name)
            ws.cell(row=row_num, column=3, value=st.national_id or "")
            ws.cell(row=row_num, column=4, value=row["total_sessions"])
            ws.cell(row=row_num, column=5, value=row["present"])

            absent_cell = ws.cell(row=row_num, column=6, value=row["absent"])
            if row["absent"] > 10:
                absent_cell.font = Font(name="Arial", color="DC2626", bold=True)

            ws.cell(row=row_num, column=7, value=row["late"])

            pct_cell = ws.cell(row=row_num, column=8, value=pct)
            if pct < 80:
                pct_cell.font = Font(name="Arial", color="DC2626", bold=True)
            elif pct >= 95:
                pct_cell.font = Font(name="Arial", color="15803D", bold=True)

            cls._style_data_row(ws, styles, row_num, num_cols, idx % 2 == 0)

        cls._apply_protection(ws, num_cols)
        cls._setup_print_a4_portrait(ws, num_cols, len(data["student_rows"]))

        filename = f"غياب_{class_group.get_grade_display()}" f"_{class_group.section}_{year}.xlsx"
        return cls.to_response(wb, filename)

    @classmethod
    def behavior_excel(
        cls, school: School, year: str = settings.CURRENT_ACADEMIC_YEAR
    ) -> HttpResponse:
        """
        Excel تقرير السلوك:
        - رأس 4 صفوف احترافي + شعار
        - تلوين درجة المخالفة (1→4 ألوان متصاعدة)
        - فلاتر تلقائية + تجميد الرأس + حماية الورقة
        """
        from openpyxl.styles import Font

        data = ReportDataService.get_behavior_report(school, year)

        LEVEL_LABELS = {
            1: "درجة 1 — بسيطة",
            2: "درجة 2 — متوسطة",
            3: "درجة 3 — جسيمة",
            4: "درجة 4 — شديدة",
        }
        LEVEL_COLORS = {1: "854D0E", 2: "C2410C", 3: "B91C1C", 4: "BE123C"}
        num_cols = 8

        wb, ws, styles = cls._make_workbook("مخالفات السلوك")

        cls._add_professional_header(
            ws,
            school.name,
            "تقرير المخالفات السلوكية",
            year,
            num_cols,
        )

        columns = [
            ("م", 5),
            ("اسم الطالب", 28),
            ("الرقم الوطني", 16),
            ("التاريخ", 13),
            ("الدرجة", 18),
            ("النقاط المخصومة", 15),
            ("المُبلِّغ", 20),
            ("الوصف", 40),
        ]
        cls._add_header_row(ws, styles, 4, columns)

        ws.freeze_panes = "A5"
        ws.auto_filter.ref = "A4:H4"

        for idx, inf in enumerate(data["infractions"], start=1):
            row_num = idx + 4  # البيانات تبدأ من الصف 5

            ws.cell(row=row_num, column=1, value=idx)
            ws.cell(row=row_num, column=2, value=inf.student.full_name)
            ws.cell(row=row_num, column=3, value=inf.student.national_id or "")
            ws.cell(row=row_num, column=4, value=inf.date.strftime("%Y/%m/%d") if inf.date else "")

            level_cell = ws.cell(
                row=row_num,
                column=5,
                value=LEVEL_LABELS.get(inf.level, str(inf.level)),
            )
            level_cell.font = Font(
                name="Arial",
                color=LEVEL_COLORS.get(inf.level, "000000"),
                bold=True,
            )

            ws.cell(row=row_num, column=6, value=inf.points_deducted)
            ws.cell(
                row=row_num, column=7, value=inf.reported_by.full_name if inf.reported_by else "—"
            )
            ws.cell(row=row_num, column=8, value=inf.description or "")

            cls._style_data_row(ws, styles, row_num, num_cols, idx % 2 == 0)

        cls._apply_protection(ws, num_cols)
        cls._setup_print_a4_portrait(ws, num_cols, len(data["infractions"]))

        return cls.to_response(wb, f"سلوك_{school.name}_{year}.xlsx")
