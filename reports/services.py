"""
reports/services.py
━━━━━━━━━━━━━━━━━━
Business logic لوحدة التقارير

يشمل:
  - تجميع بيانات تقرير الطالب
  - تجميع بيانات كشف الفصل
  - بيانات تقرير الغياب
  - بيانات تقرير السلوك
  - إنشاء ملفات Excel
"""
from io import BytesIO
from django.utils import timezone
from django.db.models import Count, Q

from assessments.models import (
    AnnualSubjectResult, StudentSubjectResult,
    SubjectClassSetup, AssessmentPackage,
)
from core.models import CustomUser, StudentEnrollment, ClassGroup, School
from operations.models import StudentAttendance


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
        """بيانات كشف نتائج الفصل الكامل"""
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
            for setup in setups:
                annual = AnnualSubjectResult.objects.filter(
                    student=enr.student, setup=setup, academic_year=year
                ).first()
                row["grades"][setup.subject.name_ar] = annual
            student_rows.append(row)

        return {
            "class_group":   class_group,
            "school":        school,
            "year":          year,
            "subjects":      subjects,
            "student_rows":  student_rows,
            "print_date":    timezone.now().date(),
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
            "school":       school,
            "year":         year,
            "infractions":  infractions,
            "print_date":   timezone.now().date(),
        }


class ExcelService:
    """إنشاء ملفات Excel"""

    MAROON = "8A1538"

    @staticmethod
    def _make_workbook(title):
        """ينشئ Workbook مع ستايل الهوية القطرية"""
        import openpyxl
        from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = title
        ws.sheet_view.rightToLeft = True

        styles = {
            "header_font":  Font(name="Arial", bold=True, color="FFFFFF", size=11),
            "header_fill":  PatternFill("solid", fgColor=ExcelService.MAROON),
            "header_align": Alignment(horizontal="center", vertical="center", wrap_text=True),
            "thin_border":  Border(
                left=Side(style="thin", color="DDDDDD"),
                right=Side(style="thin", color="DDDDDD"),
                top=Side(style="thin", color="DDDDDD"),
                bottom=Side(style="thin", color="DDDDDD"),
            ),
            "alt_fill":     PatternFill("solid", fgColor="FDF2F5"),
        }
        return wb, ws, styles

    @staticmethod
    def apply_header(ws, styles, row_num, columns):
        """يطبّق ستايل رأس الجدول"""
        for col_idx, (header, width) in enumerate(columns, start=1):
            cell = ws.cell(row=row_num, column=col_idx, value=header)
            cell.font      = styles["header_font"]
            cell.fill      = styles["header_fill"]
            cell.alignment = styles["header_align"]
            cell.border    = styles["thin_border"]
            ws.column_dimensions[cell.column_letter].width = width

    @staticmethod
    def style_row(ws, styles, row_num, num_cols, is_alt=False):
        """يطبّق ستايل صف بيانات"""
        from openpyxl.styles import Alignment
        for col_idx in range(1, num_cols + 1):
            cell = ws.cell(row=row_num, column=col_idx)
            cell.border    = styles["thin_border"]
            cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            if is_alt:
                cell.fill = styles["alt_fill"]

    @staticmethod
    def to_response(wb, filename):
        """يحول Workbook إلى HttpResponse"""
        from django.http import HttpResponse
        buf = BytesIO()
        wb.save(buf)
        buf.seek(0)
        resp = HttpResponse(
            buf.read(),
            content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        resp["Content-Disposition"] = f'attachment; filename="{filename}"'
        return resp

    @staticmethod
    def class_results_excel(class_group, school, year="2025-2026"):
        """إنشاء Excel كشف نتائج الفصل"""
        data = ReportDataService.get_class_results(class_group, school, year)
        wb, ws, styles = ExcelService._make_workbook("كشف النتائج")

        # رأس الجدول
        columns = [
            ("الطالب", 25),
            *[(s.name_ar, 12) for s in data["subjects"]],
            ("المجموع", 10),
            ("الحالة", 10),
        ]
        ExcelService.apply_header(ws, styles, 1, columns)

        # البيانات
        for row_idx, row in enumerate(data["student_rows"], start=2):
            ws.cell(row=row_idx, column=1, value=row["student"].full_name)
            for col_idx, subj in enumerate(data["subjects"], start=2):
                ann = row["grades"].get(subj.name_ar)
                ws.cell(row=row_idx, column=col_idx,
                        value=float(ann.annual_total) if ann and ann.annual_total else "")
            # المجموع والحالة
            ann_vals = [row["grades"].get(s.name_ar) for s in data["subjects"]]
            totals = [float(a.annual_total) for a in ann_vals if a and a.annual_total]
            avg = round(sum(totals) / len(totals), 2) if totals else ""
            ws.cell(row=row_idx, column=len(data["subjects"]) + 2, value=avg)

            ExcelService.style_row(ws, styles, row_idx, len(columns), row_idx % 2 == 0)

        return ExcelService.to_response(wb, f"results_{class_group.grade}_{class_group.section}.xlsx")

    @staticmethod
    def attendance_excel(class_group, school, year="2025-2026"):
        """إنشاء Excel تقرير الغياب"""
        data = ReportDataService.get_attendance_report(class_group, school, year)
        wb, ws, styles = ExcelService._make_workbook("تقرير الغياب")

        columns = [
            ("الطالب", 25), ("الحصص", 10), ("حاضر", 10),
            ("غائب", 10), ("متأخر", 10), ("مستأذن", 10), ("النسبة %", 10),
        ]
        ExcelService.apply_header(ws, styles, 1, columns)

        for row_idx, row in enumerate(data["student_rows"], start=2):
            ws.cell(row=row_idx, column=1, value=row["student"].full_name)
            ws.cell(row=row_idx, column=2, value=row["total_sessions"])
            ws.cell(row=row_idx, column=3, value=row["present"])
            ws.cell(row=row_idx, column=4, value=row["absent"])
            ws.cell(row=row_idx, column=5, value=row["late"])
            ws.cell(row=row_idx, column=6, value=row["excused"])
            ws.cell(row=row_idx, column=7, value=row["attendance_pct"])
            ExcelService.style_row(ws, styles, row_idx, 7, row_idx % 2 == 0)

        return ExcelService.to_response(wb, f"attendance_{class_group.grade}_{class_group.section}.xlsx")

    @staticmethod
    def behavior_excel(school, year="2025-2026"):
        """إنشاء Excel تقرير السلوك"""
        data = ReportDataService.get_behavior_report(school, year)
        wb, ws, styles = ExcelService._make_workbook("مخالفات السلوك")

        columns = [
            ("الطالب", 25), ("الدرجة", 10), ("الوصف", 35),
            ("النقاط", 10), ("التاريخ", 15), ("المُبلِّغ", 20), ("الحالة", 10),
        ]
        ExcelService.apply_header(ws, styles, 1, columns)

        for row_idx, inf in enumerate(data["infractions"], start=2):
            ws.cell(row=row_idx, column=1, value=inf.student.full_name)
            ws.cell(row=row_idx, column=2, value=inf.level)
            ws.cell(row=row_idx, column=3, value=inf.description[:50])
            ws.cell(row=row_idx, column=4, value=inf.points_deducted)
            ws.cell(row=row_idx, column=5, value=inf.date.strftime("%Y-%m-%d") if inf.date else "")
            ws.cell(row=row_idx, column=6, value=inf.reported_by.full_name if inf.reported_by else "")
            ws.cell(row=row_idx, column=7, value="محلول" if inf.is_resolved else "مفتوح")
            ExcelService.style_row(ws, styles, row_idx, 7, row_idx % 2 == 0)

        return ExcelService.to_response(wb, f"behavior_{school.code}.xlsx")
