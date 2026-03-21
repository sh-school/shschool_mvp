"""
reports/services.py
━━━━━━━━━━━━━━━━━━
Business logic لوحدة التقارير — بدون أي HTTP logic

يشمل:
  - ReportDataService  : تجميع بيانات التقارير
  - ExcelService       : إنشاء ملفات Excel باحترافية كاملة
"""
import logging
from io import BytesIO

from django.http import HttpResponse
from django.utils import timezone

from assessments.models import (
    AnnualSubjectResult, StudentSubjectResult,
    SubjectClassSetup,
)
from core.models import CustomUser, StudentEnrollment, ClassGroup, School
from operations.models import StudentAttendance

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# ReportDataService — تجميع البيانات
# ══════════════════════════════════════════════════════════════════════

class ReportDataService:
    """تجميع بيانات التقارير — بدون أي HTTP logic"""

    @staticmethod
    def get_student_report(student, school, year="2025-2026"):
        """بيانات تقرير الطالب السنوي الكاملة"""
        annual = (
            AnnualSubjectResult.objects.filter(
                student=student, school=school, academic_year=year
            )
            .select_related("setup__subject")
            .order_by("setup__subject__name_ar")
        )

        s1_map = {
            r.setup_id: r for r in StudentSubjectResult.objects.filter(
                student=student, school=school, semester="S1"
            )
        }
        s2_map = {
            r.setup_id: r for r in StudentSubjectResult.objects.filter(
                student=student, school=school, semester="S2"
            )
        }

        rows = [
            {
                "subject": ann.setup.subject.name_ar,
                "s1":      s1_map.get(ann.setup_id),
                "s2":      s2_map.get(ann.setup_id),
                "annual":  ann,
            }
            for ann in annual
        ]

        total  = annual.count()
        passed = annual.filter(status="pass").count()
        failed = annual.filter(status="fail").count()
        grades = [float(r.annual_total) for r in annual if r.annual_total]
        avg    = round(sum(grades) / len(grades), 2) if grades else None

        enrollment = StudentEnrollment.objects.filter(
            student=student, is_active=True
        ).select_related("class_group").first()

        att = StudentAttendance.objects.filter(
            student=student, session__school=school
        )
        absent_total = att.filter(status="absent").count()
        late_total   = att.filter(status="late").count()

        return {
            "student":      student,
            "school":       school,
            "year":         year,
            "enrollment":   enrollment,
            "rows":         rows,
            "total":        total,
            "passed":       passed,
            "failed":       failed,
            "avg":          avg,
            "absent_total": absent_total,
            "late_total":   late_total,
            "print_date":   timezone.now().date(),
        }

    @staticmethod
    def get_class_results(class_group, school, year="2025-2026"):
        """بيانات كشف نتائج الفصل الكامل مع ترتيب + ملخص"""
        enrollments = (
            StudentEnrollment.objects.filter(
                class_group=class_group, is_active=True
            )
            .select_related("student")
            .order_by("student__full_name")
        )

        setups = SubjectClassSetup.objects.filter(
            class_group=class_group, school=school, academic_year=year
        ).select_related("subject").order_by("subject__name_ar")

        subjects = [s.subject for s in setups]

        student_rows = []
        for enr in enrollments:
            row = {"student": enr.student, "grades": {}}
            grades = []
            passed = failed = 0
            for setup in setups:
                annual = AnnualSubjectResult.objects.filter(
                    student=enr.student, setup=setup, academic_year=year
                ).first()
                row["grades"][setup.subject.name_ar] = annual
                if annual:
                    if annual.annual_total:
                        grades.append(float(annual.annual_total))
                    if annual.status == "pass":
                        passed += 1
                    elif annual.status == "fail":
                        failed += 1

            avg = round(sum(grades) / len(grades), 2) if grades else None
            row["avg"]    = avg
            row["passed"] = passed
            row["failed"] = failed
            row["status"] = "ناجح" if failed == 0 and passed > 0 else ("راسب" if failed > 0 else "—")
            student_rows.append(row)

        # ترتيب حسب المتوسط
        student_rows.sort(key=lambda x: x["avg"] or 0, reverse=True)
        for i, row in enumerate(student_rows, start=1):
            row["rank"] = i
            # grades_list: قائمة مرتبة بنفس ترتيب subjects للاستخدام في القوالب
            row["grades_list"] = [row["grades"].get(s.name_ar) for s in subjects]

        total_passed = sum(1 for r in student_rows if r["failed"] == 0 and r["passed"] > 0)
        total_failed = sum(1 for r in student_rows if r["failed"] > 0)

        return {
            "class_group":    class_group,
            "school":         school,
            "year":           year,
            "subjects":       subjects,
            "student_rows":   student_rows,
            "total_students": len(student_rows),
            "total_passed":   total_passed,
            "total_failed":   total_failed,
            "print_date":     timezone.now().date(),
        }

    @staticmethod
    def get_attendance_report(class_group, school, year="2025-2026"):
        """بيانات تقرير الغياب لفصل"""
        enrollments = (
            StudentEnrollment.objects.filter(
                class_group=class_group, is_active=True
            )
            .select_related("student")
            .order_by("student__full_name")
        )

        student_rows = []
        for enr in enrollments:
            att = StudentAttendance.objects.filter(
                student=enr.student, session__school=school,
            )
            total_sessions = att.count()
            absent  = att.filter(status="absent").count()
            late    = att.filter(status="late").count()
            excused = att.filter(status="excused").count()
            present = total_sessions - absent - late - excused
            pct = round(present / total_sessions * 100) if total_sessions else 0

            student_rows.append({
                "student":        enr.student,
                "total_sessions": total_sessions,
                "present":        present,
                "absent":         absent,
                "late":           late,
                "excused":        excused,
                "attendance_pct": pct,
            })

        return {
            "class_group":  class_group,
            "school":       school,
            "year":         year,
            "student_rows": student_rows,
            "print_date":   timezone.now().date(),
        }

    @staticmethod
    def get_behavior_report(school, year="2025-2026"):
        """بيانات تقرير السلوك العام"""
        from behavior.models import BehaviorInfraction

        infractions = (
            BehaviorInfraction.objects.filter(school=school)
            .select_related("student", "reported_by")
            .order_by("-date")
        )

        return {
            "school":      school,
            "year":        year,
            "infractions": infractions,
            "print_date":  timezone.now().date(),
        }


# ══════════════════════════════════════════════════════════════════════
# ExcelService — إنشاء Excel باحترافية كاملة
# ══════════════════════════════════════════════════════════════════════

class ExcelService:
    """
    إنشاء ملفات Excel بهوية قطرية كاملة:
      - RTL عربي
      - صف عنوان مدموج (كستنائي)
      - رأس جدول (كستنائي + أبيض)
      - صفوف متبادلة اللون
      - تلوين شرطي (راسب / غياب / درجات)
      - freeze panes
    """

    MAROON = "8A1538"
    WHITE  = "FFFFFF"
    ALT_BG = "FDF2F5"

    # ── بنية تحتية ────────────────────────────────────────────────────

    @classmethod
    def _make_workbook(cls, sheet_title: str):
        """Workbook جديد مع ستايل الهوية القطرية"""
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = sheet_title
        ws.sheet_view.rightToLeft = True

        styles = {
            "header_font":  Font(name="Arial", bold=True, color=cls.WHITE, size=11),
            "header_fill":  PatternFill("solid", fgColor=cls.MAROON),
            "header_align": Alignment(horizontal="center", vertical="center",
                                      wrap_text=True),
            "data_align":   Alignment(horizontal="center", vertical="center",
                                      wrap_text=True),
            "thin_border":  Border(
                left=Side(style="thin",  color="DDDDDD"),
                right=Side(style="thin", color="DDDDDD"),
                top=Side(style="thin",   color="DDDDDD"),
                bottom=Side(style="thin",color="DDDDDD"),
            ),
            "alt_fill": PatternFill("solid", fgColor=cls.ALT_BG),
        }
        return wb, ws, styles

    @classmethod
    def _add_title_row(cls, ws, title: str, num_cols: int):
        """صف عنوان مدموج — خلفية كستنائية، خط أبيض 13"""
        from openpyxl.styles import Font, PatternFill, Alignment
        col_letter = ws.cell(row=1, column=num_cols).column_letter
        ws.merge_cells(f"A1:{col_letter}1")
        cell            = ws["A1"]
        cell.value      = title
        cell.font       = Font(name="Arial", bold=True, color=cls.WHITE, size=13)
        cell.fill       = PatternFill("solid", fgColor=cls.MAROON)
        cell.alignment  = Alignment(horizontal="center", vertical="center")
        ws.row_dimensions[1].height = 32

    @classmethod
    def _add_header_row(cls, ws, styles, row_num: int, columns: list):
        """رأس الجدول: قائمة من (عنوان، عرض)"""
        for col_idx, (header, width) in enumerate(columns, start=1):
            cell            = ws.cell(row=row_num, column=col_idx, value=header)
            cell.font       = styles["header_font"]
            cell.fill       = styles["header_fill"]
            cell.alignment  = styles["header_align"]
            cell.border     = styles["thin_border"]
            ws.column_dimensions[cell.column_letter].width = width
        ws.row_dimensions[row_num].height = 24

    @classmethod
    def _style_data_row(cls, ws, styles, row_num: int, num_cols: int,
                        is_alt: bool = False):
        """تطبيق ستايل على صف بيانات"""
        for col_idx in range(1, num_cols + 1):
            cell           = ws.cell(row=row_num, column=col_idx)
            cell.border    = styles["thin_border"]
            cell.alignment = styles["data_align"]
            if is_alt:
                cell.fill = styles["alt_fill"]
        ws.row_dimensions[row_num].height = 20

    @classmethod
    def to_response(cls, wb, filename: str) -> HttpResponse:
        """تحويل Workbook إلى HttpResponse جاهز للتنزيل"""
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(
            buf.read(),
            content_type=(
                "application/vnd.openxmlformats-officedocument"
                ".spreadsheetml.sheet"
            ),
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    # ── التقارير ──────────────────────────────────────────────────────

    @classmethod
    def class_results_excel(cls, class_group, school,
                            year: str = "2025-2026") -> HttpResponse:
        """
        Excel كشف نتائج الفصل:
        - ترتيب حسب المتوسط
        - تلوين أحمر للدرجات < 50
        - تلوين الحالة (ناجح/راسب)
        - freeze panes بعد الرأس
        """
        from openpyxl.styles import Font

        data     = ReportDataService.get_class_results(class_group, school, year)
        subjects = data["subjects"]
        num_cols = 3 + len(subjects) + 3          # م + اسم + وطني + مواد + متوسط + حالة + ترتيب

        wb, ws, styles = cls._make_workbook("كشف النتائج")
        cls._add_title_row(
            ws,
            f"كشف نتائج — {class_group} — {year} — {school.name}",
            num_cols,
        )

        columns = (
            [("م", 5), ("اسم الطالب", 28), ("الرقم الوطني", 16)]
            + [(s.name_ar[:18], 11) for s in subjects]
            + [("المتوسط", 10), ("الحالة", 10), ("الترتيب", 8)]
        )
        cls._add_header_row(ws, styles, 2, columns)
        ws.freeze_panes = "A3"

        for row in data["student_rows"]:
            rank    = row["rank"]
            row_num = rank + 2
            is_alt  = rank % 2 == 0
            st      = row["student"]

            ws.cell(row=row_num, column=1, value=rank)
            ws.cell(row=row_num, column=2, value=st.full_name)
            ws.cell(row=row_num, column=3, value=st.national_id or "")

            for col_off, subj in enumerate(subjects, start=4):
                ann  = row["grades"].get(subj.name_ar)
                grade = float(ann.annual_total) if ann and ann.annual_total else None
                cell = ws.cell(row=row_num, column=col_off,
                               value=grade if grade is not None else "—")
                if grade is not None and grade < 50:
                    cell.font = Font(name="Arial", color="DC2626", bold=True)

            ws.cell(row=row_num, column=4 + len(subjects),
                    value=row["avg"] if row["avg"] is not None else "—")

            status_cell = ws.cell(row=row_num, column=5 + len(subjects),
                                  value=row["status"])
            if row["status"] == "ناجح":
                status_cell.font = Font(name="Arial", color="15803D", bold=True)
            elif row["status"] == "راسب":
                status_cell.font = Font(name="Arial", color="DC2626", bold=True)

            ws.cell(row=row_num, column=6 + len(subjects), value=rank)
            cls._style_data_row(ws, styles, row_num, num_cols, is_alt)

        filename = (
            f"نتائج_{class_group.get_grade_display()}"
            f"_{class_group.section}_{year}.xlsx"
        )
        return cls.to_response(wb, filename)

    @classmethod
    def attendance_excel(cls, class_group, school,
                         year: str = "2025-2026") -> HttpResponse:
        """
        Excel تقرير الغياب:
        - أحمر للغياب > 10 حصة
        - أحمر/أخضر لنسبة الحضور
        """
        from openpyxl.styles import Font

        data     = ReportDataService.get_attendance_report(class_group, school, year)
        num_cols = 8

        wb, ws, styles = cls._make_workbook("الحضور والغياب")
        cls._add_title_row(
            ws,
            f"تقرير الحضور والغياب — {class_group} — {year} — {school.name}",
            num_cols,
        )

        columns = [
            ("م", 5), ("اسم الطالب", 28), ("الرقم الوطني", 16),
            ("إجمالي الحصص", 13), ("حاضر", 10), ("غائب", 10),
            ("متأخر", 10), ("نسبة الحضور %", 14),
        ]
        cls._add_header_row(ws, styles, 2, columns)
        ws.freeze_panes = "A3"

        for idx, row in enumerate(data["student_rows"], start=1):
            row_num = idx + 2
            st      = row["student"]
            pct     = row["attendance_pct"]

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

        filename = (
            f"غياب_{class_group.get_grade_display()}"
            f"_{class_group.section}_{year}.xlsx"
        )
        return cls.to_response(wb, filename)

    @classmethod
    def behavior_excel(cls, school, year: str = "2025-2026") -> HttpResponse:
        """
        Excel تقرير السلوك:
        - تلوين درجة المخالفة (1→4 ألوان متصاعدة)
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
        cls._add_title_row(
            ws,
            f"تقرير المخالفات السلوكية — {school.name} — {year}",
            num_cols,
        )

        columns = [
            ("م", 5), ("اسم الطالب", 28), ("الرقم الوطني", 16),
            ("التاريخ", 13), ("الدرجة", 18), ("النقاط المخصومة", 15),
            ("المُبلِّغ", 20), ("الوصف", 40),
        ]
        cls._add_header_row(ws, styles, 2, columns)
        ws.freeze_panes = "A3"

        for idx, inf in enumerate(data["infractions"], start=1):
            row_num = idx + 2

            ws.cell(row=row_num, column=1, value=idx)
            ws.cell(row=row_num, column=2, value=inf.student.full_name)
            ws.cell(row=row_num, column=3, value=inf.student.national_id or "")
            ws.cell(row=row_num, column=4,
                    value=inf.date.strftime("%Y/%m/%d") if inf.date else "")

            level_cell = ws.cell(
                row=row_num, column=5,
                value=LEVEL_LABELS.get(inf.level, str(inf.level)),
            )
            level_cell.font = Font(
                name="Arial",
                color=LEVEL_COLORS.get(inf.level, "000000"),
                bold=True,
            )

            ws.cell(row=row_num, column=6, value=inf.points_deducted)
            ws.cell(row=row_num, column=7,
                    value=inf.reported_by.full_name if inf.reported_by else "—")
            ws.cell(row=row_num, column=8, value=inf.description or "")

            cls._style_data_row(ws, styles, row_num, num_cols, idx % 2 == 0)

        return cls.to_response(wb, f"سلوك_{school.name}_{year}.xlsx")
