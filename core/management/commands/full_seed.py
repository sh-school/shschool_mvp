"""
core/management/commands/full_seed.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
حقن بيانات كاملة لمدرسة الشحانية — جميع وحدات النظام

يشمل:
  1. المدرسة + الأدوار
  2. الموظفون (من CSV)
  3. الفصول الدراسية (من CSV الطلاب)
  4. الطلاب + أولياء الأمور (من CSV)
  5. ربط أولياء الأمور بأبنائهم (ParentStudentLink)
  6. المواد الدراسية
  7. الجدول الأسبوعي (عينة)
  8. حضور تجريبي (آخر 14 يوم)
  9. المواد والإعدادات (SubjectClassSetup)
 10. درجات تجريبية (AssessmentPackage + Assessment + Grades)
 11. الخطة التشغيلية (من CSV كاملاً)
 12. لجنة الجودة (من CSV)
 13. ربط المنفذين تلقائياً
 14. إعدادات الإشعارات

تشغيل:
    python manage.py full_seed
    python manage.py full_seed --reset   (يحذف ويعيد)
    python manage.py full_seed --step=quality  (خطوة واحدة فقط)
"""

import csv
import random
import re
import secrets
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
DATA_DIR = BASE_DIR / "data"
YEAR = "2025-2026"
TODAY = timezone.now().date()


def clean(text):
    return re.sub(r"\s+", " ", text or "").strip()


def read_csv(filename):
    path = DATA_DIR / filename
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def map_role(job_title_norm: str) -> str:
    t = job_title_norm.strip().lower()
    if "مدير المدرسه" in t or "مدير المدرسة" in t:
        return "principal"
    if "النائب الاداري" in t:
        return "vice_admin"
    if "نائب المدير" in t or "الاكاديمي" in t:
        return "vice_academic"
    if t.startswith("منسق"):
        return "coordinator"
    if t.startswith("معلم"):
        return "teacher"
    if "اخصائي" in t or "مرشد" in t:
        return "specialist"
    return "admin"


class Command(BaseCommand):
    help = "حقن بيانات كاملة لاختبار النظام — مدرسة الشحانية"

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset", action="store_true", help="حذف البيانات السابقة وإعادة الحقن"
        )
        parser.add_argument(
            "--step",
            default="all",
            choices=[
                "all",
                "school",
                "staff",
                "students",
                "links",
                "subjects",
                "schedule",
                "attendance",
                "grades",
                "quality",
                "notifications",
            ],
            help="تشغيل خطوة واحدة فقط",
        )
        parser.add_argument(
            "--password",
            default="",
            help="كلمة المرور للحسابات المُنشأة (افتراضياً: توليد عشوائي آمن)",
        )

    def handle(self, *args, **options):
        step = options["step"]
        reset = options["reset"]
        self._seed_password = options["password"] or secrets.token_urlsafe(12)

        if reset:
            self._reset()

        with transaction.atomic():
            school, role_objs = self._step_school()

            if step in ("all", "staff"):
                self._step_staff(school, role_objs)

            if step in ("all", "students"):
                class_map, student_map, parent_map = self._step_students(school, role_objs)
            else:
                class_map, student_map, parent_map = self._load_maps(school)

            if step in ("all", "links"):
                self._step_parent_links(school, student_map, parent_map)

            if step in ("all", "subjects"):
                subject_map = self._step_subjects(school)
            else:
                subject_map = self._load_subjects(school)

            if step in ("all", "schedule"):
                self._step_schedule(school, subject_map, class_map, role_objs)

            if step in ("all", "attendance"):
                self._step_attendance(school, class_map)

            if step in ("all", "grades"):
                self._step_grades(school, subject_map, class_map, role_objs)

            if step in ("all", "quality"):
                self._step_quality(school, role_objs)

            if step in ("all", "notifications"):
                self._step_notifications(school)

        self._print_summary(school)

    # ─────────────────────────────────────────────────────────
    # 1. المدرسة والأدوار
    # ─────────────────────────────────────────────────────────
    def _step_school(self):
        from core.models import Role, School

        school, _ = School.objects.get_or_create(
            code="SHH",
            defaults={
                "name": "مدرسة الشحانية الإعدادية الثانوية للبنين",
                "city": "الشحانية",
            },
        )
        role_objs = {}
        for rname in [
            "principal",
            "vice_admin",
            "vice_academic",
            "coordinator",
            "teacher",
            "specialist",
            "admin",
            "student",
            "parent",
        ]:
            role, _ = Role.objects.get_or_create(school=school, name=rname)
            role_objs[rname] = role
        self.stdout.write(f"✅ المدرسة: {school.name}")
        return school, role_objs

    # ─────────────────────────────────────────────────────────
    # 2. الموظفون
    # ─────────────────────────────────────────────────────────
    def _step_staff(self, school, role_objs):
        from core.models import CustomUser, Membership, Profile

        staff_rows = read_csv("2_Normalized_Staff_List.csv")
        created = 0
        for row in staff_rows:
            nat_id = clean(row.get("national_no", ""))
            name = clean(row.get("stuff _name", ""))
            job_norm = clean(row.get("job_title_norm", ""))
            email = clean(row.get("email", ""))
            phone = clean(row.get("phone_no", ""))
            if not nat_id or not name:
                continue
            user, c = CustomUser.objects.get_or_create(
                national_id=nat_id,
                defaults={"full_name": name, "email": email, "phone": phone, "is_staff": True},
            )
            if c:
                user.set_password(self._seed_password)
                user.save()
                created += 1
            else:
                user.full_name = name
                user.email = email or user.email
                user.is_staff = True
                user.save(update_fields=["full_name", "email", "is_staff"])

            Profile.objects.get_or_create(user=user)
            if "مدير المدرسه" in job_norm or "مدير المدرسة" in job_norm:
                user.is_superuser = True
                user.save(update_fields=["is_superuser"])

            role_name = map_role(job_norm)
            Membership.objects.get_or_create(
                user=user, school=school, role=role_objs[role_name], defaults={"is_active": True}
            )

        self.stdout.write(f"✅ الموظفون: {len(staff_rows)} ({created} جديد)")

    # ─────────────────────────────────────────────────────────
    # 3. الطلاب + أولياء الأمور + الفصول
    # ─────────────────────────────────────────────────────────
    def _step_students(self, school, role_objs):
        from core.models import ClassGroup, CustomUser, Membership, Profile, StudentEnrollment

        GRADE_MAP = {"7": "G7", "8": "G8", "9": "G9", "10": "G10", "11": "G11", "12": "G12"}
        LEVEL_MAP = {"7": "prep", "8": "prep", "9": "prep", "10": "sec", "11": "sec", "12": "sec"}

        student_rows = read_csv("new_students_full.csv")

        # الفصول
        class_map = {}
        for row in student_rows:
            g = str(row.get("grade", "")).strip()
            s = str(row.get("section", "")).strip()
            if g and s and (g, s) not in class_map:
                gc = GRADE_MAP.get(g)
                if gc:
                    cg, _ = ClassGroup.objects.get_or_create(
                        school=school,
                        grade=gc,
                        section=s,
                        academic_year=YEAR,
                        defaults={"level_type": LEVEL_MAP.get(g, "prep"), "is_active": True},
                    )
                    class_map[(g, s)] = cg

        stu_map = {}
        par_map = {}
        stu_c = 0
        par_c = 0
        enr_c = 0

        for row in student_rows:
            nat_id = clean(row.get("national_no", ""))
            name_ar = clean(row.get("studant_name", ""))
            grade = str(row.get("grade", "")).strip()
            section = str(row.get("section", "")).strip()
            par_nat = clean(row.get("parent_national_no", ""))
            par_name = clean(row.get("name_parent", ""))
            par_rel = clean(row.get("relation_parent", "أب"))
            par_phone = clean(row.get("parent_phone_no", "")).split(",")[0].strip()
            par_email = clean(row.get("parent_email", ""))

            if not nat_id or not name_ar:
                continue

            stu, c = CustomUser.objects.get_or_create(
                national_id=nat_id, defaults={"full_name": name_ar, "is_staff": False}
            )
            if c:
                stu.set_password(self._seed_password)
                stu.save()
                stu_c += 1
            else:
                stu.full_name = name_ar
                stu.save(update_fields=["full_name"])

            Profile.objects.get_or_create(user=stu)
            Membership.objects.get_or_create(
                user=stu, school=school, role=role_objs["student"], defaults={"is_active": True}
            )

            cg = class_map.get((grade, section))
            if cg:
                _, ec = StudentEnrollment.objects.get_or_create(
                    student=stu, class_group=cg, defaults={"is_active": True}
                )
                if ec:
                    enr_c += 1

            stu_map[nat_id] = {"user": stu, "par_nat": par_nat, "par_rel": par_rel}

            if par_nat and par_name:
                par, pc = CustomUser.objects.get_or_create(
                    national_id=par_nat,
                    defaults={
                        "full_name": par_name,
                        "phone": par_phone,
                        "email": par_email if par_email not in ("-", "") else "",
                    },
                )
                if pc:
                    par.set_password(self._seed_password)
                    par.save()
                    par_c += 1
                else:
                    par.full_name = par_name
                    par.save(update_fields=["full_name"])

                Profile.objects.get_or_create(user=par)
                Membership.objects.get_or_create(
                    user=par, school=school, role=role_objs["parent"], defaults={"is_active": True}
                )
                par_map[par_nat] = par

        self.stdout.write(f"✅ الفصول: {len(class_map)}")
        self.stdout.write(f"✅ الطلاب: {len(stu_map)} ({stu_c} جديد) | تسجيلات: {enr_c}")
        self.stdout.write(f"✅ أولياء الأمور: {len(par_map)} ({par_c} جديد)")
        return class_map, stu_map, par_map

    def _load_maps(self, school):
        from core.models import ClassGroup, CustomUser

        class_map = {}
        GRADE_MAP = {"7": "G7", "8": "G8", "9": "G9", "10": "G10", "11": "G11", "12": "G12"}
        for row in read_csv("new_students_full.csv"):
            g = str(row.get("grade", "")).strip()
            s = str(row.get("section", "")).strip()
            gc = GRADE_MAP.get(g)
            if gc:
                cg = ClassGroup.objects.filter(
                    school=school, grade=gc, section=s, academic_year=YEAR
                ).first()
                if cg:
                    class_map[(g, s)] = cg
        student_map = {}
        for row in read_csv("new_students_full.csv"):
            nat_id = clean(row.get("national_no", ""))
            u = CustomUser.objects.filter(national_id=nat_id).first()
            if u:
                student_map[nat_id] = {
                    "user": u,
                    "par_nat": clean(row.get("parent_national_no", "")),
                    "par_rel": clean(row.get("relation_parent", "أب")),
                }
        parent_map = {}
        from core.models import Membership

        for m in Membership.objects.filter(school=school, role__name="parent", is_active=True):
            parent_map[m.user.national_id] = m.user
        return class_map, student_map, parent_map

    # ─────────────────────────────────────────────────────────
    # 4. ربط أولياء الأمور بأبنائهم
    # ─────────────────────────────────────────────────────────
    def _step_parent_links(self, school, student_map, parent_map):
        try:
            from core.models import ParentStudentLink
        except ImportError:
            self.stdout.write("⚠️  ParentStudentLink غير موجود — تخطي")
            return

        REL_MAP = {
            "أب": "father",
            "أم": "mother",
            "الأب": "father",
            "الأم": "mother",
            "وصي": "guardian",
            "ولي": "guardian",
        }

        created = 0
        for nat_id, data in student_map.items():
            par_nat = data.get("par_nat", "")
            par_rel = data.get("par_rel", "أب")
            parent = parent_map.get(par_nat)
            student = data["user"]
            if not parent:
                continue
            rel = REL_MAP.get(par_rel, "father")
            _, c = ParentStudentLink.objects.get_or_create(
                school=school,
                parent=parent,
                student=student,
                defaults={
                    "relationship": rel,
                    "can_view_grades": True,
                    "can_view_attendance": True,
                },
            )
            if c:
                created += 1

        self.stdout.write(f"✅ روابط أولياء الأمور: {created} رابط جديد")

    # ─────────────────────────────────────────────────────────
    # 5. المواد الدراسية
    # ─────────────────────────────────────────────────────────
    def _step_subjects(self, school):
        from operations.models import Subject

        SUBJECTS = [
            ("اللغة العربية", "Arabic Language"),
            ("اللغة الإنجليزية", "English Language"),
            ("الرياضيات", "Mathematics"),
            ("العلوم", "Sciences"),
            ("الكيمياء", "Chemistry"),
            ("الأحياء", "Biology"),
            ("الفيزياء", "Physics"),
            ("الدراسات الاجتماعية", "Social Studies"),
            ("التربية الإسلامية", "Islamic Education"),
            ("التربية البدنية", "Physical Education"),
            ("الفنون البصرية", "Visual Arts"),
            ("تكنولوجيا المعلومات", "Information Technology"),
        ]
        subject_map = {}
        for name_ar, name_en in SUBJECTS:
            subj, _ = Subject.objects.get_or_create(
                school=school, name_ar=name_ar, defaults={"name_en": name_en}
            )
            subject_map[name_ar] = subj
        self.stdout.write(f"✅ المواد: {len(subject_map)}")
        return subject_map

    def _load_subjects(self, school):
        from operations.models import Subject

        return {s.name_ar: s for s in Subject.objects.filter(school=school)}

    # ─────────────────────────────────────────────────────────
    # 6. الجدول الأسبوعي (عينة)
    # ─────────────────────────────────────────────────────────
    def _step_schedule(self, school, subject_map, class_map, role_objs):
        from datetime import time

        from core.models import CustomUser
        from operations.models import ScheduleSlot

        teachers = list(
            CustomUser.objects.filter(
                memberships__school=school,
                memberships__role__name__in=["teacher", "coordinator"],
                memberships__is_active=True,
            ).distinct()[:20]
        )

        if not teachers:
            self.stdout.write("⚠️  لا يوجد معلمون — تخطي الجدول")
            return

        PERIODS = [
            (1, time(7, 30), time(8, 15)),
            (2, time(8, 20), time(9, 5)),
            (3, time(9, 10), time(9, 55)),
            (4, time(10, 5), time(10, 50)),
            (5, time(11, 0), time(11, 45)),
        ]

        subj_list = list(subject_map.values())
        class_list = list(class_map.values())[:10]
        created = 0

        for day in range(5):
            for period, start, end in PERIODS:
                for i, cg in enumerate(class_list):
                    teacher = teachers[i % len(teachers)]
                    subj = subj_list[(i + day + period) % len(subj_list)]
                    _, c = ScheduleSlot.objects.get_or_create(
                        school=school,
                        class_group=cg,
                        day_of_week=day,
                        period_number=period,
                        academic_year=YEAR,
                        defaults={
                            "teacher": teacher,
                            "subject": subj,
                            "start_time": start,
                            "end_time": end,
                            "is_active": True,
                        },
                    )
                    if c:
                        created += 1

        self.stdout.write(f"✅ الجدول الأسبوعي: {created} حصة")

    # ─────────────────────────────────────────────────────────
    # 7. حضور تجريبي — آخر 14 يوم
    # ─────────────────────────────────────────────────────────
    def _step_attendance(self, school, class_map):
        from core.models import StudentEnrollment
        from operations.models import ScheduleSlot, Session, StudentAttendance

        sessions_created = 0
        att_created = 0

        for day_offset in range(14, 0, -1):
            d = TODAY - timedelta(days=day_offset)
            if d.weekday() >= 5:  # جمعة/سبت
                continue

            # توليد Sessions يتم أدناه مباشرة

            # توليد Sessions من الجدول
            day_py_to_our = {6: 0, 0: 1, 1: 2, 2: 3, 3: 4}
            our_day = day_py_to_our.get(d.weekday(), -1)
            if our_day == -1:
                continue

            slots = ScheduleSlot.objects.filter(
                school=school, day_of_week=our_day, academic_year=YEAR, is_active=True
            ).select_related("teacher", "class_group", "subject")

            for slot in slots:
                session, s_created = Session.objects.get_or_create(
                    school=school,
                    teacher=slot.teacher,
                    class_group=slot.class_group,
                    date=d,
                    start_time=slot.start_time,
                    defaults={
                        "subject": slot.subject,
                        "end_time": slot.end_time,
                        "status": "completed",
                    },
                )
                if s_created:
                    sessions_created += 1

                # حضور الطلاب
                students = StudentEnrollment.objects.filter(
                    class_group=slot.class_group, is_active=True
                ).select_related("student")

                for enr in students:
                    # 85% حاضر، 10% غائب، 5% متأخر
                    rnd = random.random()
                    status = "present" if rnd < 0.85 else ("absent" if rnd < 0.95 else "late")

                    _, ac = StudentAttendance.objects.get_or_create(
                        session=session,
                        student=enr.student,
                        defaults={"school": school, "status": status},
                    )
                    if ac:
                        att_created += 1

        self.stdout.write(f"✅ الحضور: {sessions_created} حصة | {att_created} سجل")

    # ─────────────────────────────────────────────────────────
    # 8. درجات تجريبية
    # ─────────────────────────────────────────────────────────
    def _step_grades(self, school, subject_map, class_map, role_objs):
        from assessments.models import (
            Assessment,
            AssessmentPackage,
            StudentAssessmentGrade,
            SubjectClassSetup,
        )
        from assessments.services import GradeService
        from core.models import CustomUser, StudentEnrollment

        teachers = list(
            CustomUser.objects.filter(
                memberships__school=school,
                memberships__role__name__in=["teacher", "coordinator"],
                memberships__is_active=True,
            ).distinct()[:12]
        )

        if not teachers or not subject_map or not class_map:
            self.stdout.write("⚠️  لا توجد بيانات كافية للدرجات")
            return

        subj_list = list(subject_map.values())
        class_list = list(class_map.values())[:8]
        setups_done = grades_done = 0

        for i, cg in enumerate(class_list):
            for j, subj in enumerate(subj_list[:6]):
                teacher = teachers[(i + j) % len(teachers)]

                setup, _ = SubjectClassSetup.objects.get_or_create(
                    school=school,
                    subject=subj,
                    class_group=cg,
                    academic_year=YEAR,
                    defaults={"teacher": teacher, "is_active": True},
                )
                setups_done += 1

                for semester, sem_max, weights in [
                    ("S1", Decimal("40"), {"P1": Decimal("50"), "P4": Decimal("50")}),
                    (
                        "S2",
                        Decimal("60"),
                        {"P1": Decimal("16.67"), "P3": Decimal("33.33"), "P4": Decimal("50")},
                    ),
                ]:
                    for ptype, weight in weights.items():
                        pkg, _ = AssessmentPackage.objects.get_or_create(
                            setup=setup,
                            package_type=ptype,
                            semester=semester,
                            defaults={
                                "school": school,
                                "weight": weight,
                                "semester_max_grade": sem_max,
                                "is_active": True,
                            },
                        )

                        if pkg.assessments.exists():
                            continue

                        type_map = {"P1": "classwork", "P3": "exam", "P4": "exam"}
                        title_map = {
                            "P1": "أعمال مستمرة",
                            "P3": "اختبار منتصف الفصل",
                            "P4": "اختبار نهاية الفصل"
                            if semester == "S1"
                            else "اختبار نهاية العام",
                        }
                        assessment = Assessment.objects.create(
                            package=pkg,
                            school=school,
                            title=title_map[ptype],
                            assessment_type=type_map.get(ptype, "exam"),
                            max_grade=Decimal("100"),
                            weight_in_package=Decimal("100"),
                            status="graded",
                            created_by=teacher,
                        )

                        # درجات الطلاب
                        students = StudentEnrollment.objects.filter(
                            class_group=cg, is_active=True
                        ).select_related("student")

                        for enr in students:
                            # توزيع واقعي: معظم الطلاب بين 55-95
                            grade_val = (
                                Decimal(str(round(random.gauss(72, 15), 1)))
                                .max(Decimal("0"))
                                .min(Decimal("100"))
                            )

                            # 8% راسبون (أقل من 50)
                            if random.random() < 0.08:
                                grade_val = Decimal(str(round(random.uniform(20, 49), 1)))

                            StudentAssessmentGrade.objects.get_or_create(
                                assessment=assessment,
                                student=enr.student,
                                defaults={
                                    "school": school,
                                    "grade": grade_val,
                                    "is_absent": False,
                                    "entered_by": teacher,
                                },
                            )
                            grades_done += 1

                        # حساب النتائج
                        # يتم حساب النتائج بعد حفظ كل الدرجات

                # حساب نتائج الفصلين والسنوي لكل طالب
                for enr in StudentEnrollment.objects.filter(class_group=cg, is_active=True):
                    for sem in ("S1", "S2"):
                        GradeService.recalculate_semester_result(enr.student, setup, sem)
                    GradeService.recalculate_annual_result(enr.student, setup)

        self.stdout.write(f"✅ الدرجات: {setups_done} إعداد | {grades_done} درجة")

    # ─────────────────────────────────────────────────────────
    # 9. الخطة التشغيلية كاملة
    # ─────────────────────────────────────────────────────────
    def _step_quality(self, school, role_objs):
        from core.models import CustomUser
        from quality.models import (
            ExecutorMapping,
            OperationalDomain,
            OperationalIndicator,
            OperationalProcedure,
            OperationalTarget,
            QualityCommitteeMember,
        )

        plan_rows = read_csv("1_Clean_Operational_Plan.csv")

        # ── المجالات والأهداف والمؤشرات والإجراءات ──
        domain_map = {}
        target_map = {}
        indicator_map = {}
        proc_count = 0

        DOMAIN_ORDER = {}
        for row in plan_rows:
            d_name = clean(row.get("rank_name", ""))
            if d_name and d_name not in DOMAIN_ORDER:
                DOMAIN_ORDER[d_name] = len(DOMAIN_ORDER) + 1

        for row in plan_rows:
            d_name = clean(row.get("rank_name", ""))
            t_no = clean(row.get("target_no", ""))
            t_text = clean(row.get("target", ""))
            i_no = clean(row.get("indicator_no", ""))
            i_text = clean(row.get("indicator", ""))
            p_no = clean(row.get("procedure_no", ""))
            p_text = clean(row.get("procedure", ""))
            executor = clean(row.get("executor_norm", "") or row.get("executor", ""))
            date_r = clean(row.get("date_range", ""))
            status = clean(row.get("status", "In Progress"))
            ev_type = clean(row.get("evidence_type", ""))
            ev_emp = clean(row.get("evidence_source_employee", ""))
            ev_file = clean(row.get("evidence_source_file", ""))
            evaluation = clean(row.get("evaluation", ""))
            eval_notes = clean(row.get("evaluation_notes", ""))
            follow_up = clean(row.get("follow_up", ""))
            comments = clean(row.get("comments", ""))

            if not d_name or not p_text:
                continue

            # المجال
            if d_name not in domain_map:
                domain, _ = OperationalDomain.objects.get_or_create(
                    school=school,
                    name=d_name,
                    academic_year=YEAR,
                    defaults={"order": DOMAIN_ORDER.get(d_name, 99)},
                )
                domain_map[d_name] = domain
            domain = domain_map[d_name]

            # الهدف
            t_key = (d_name, t_no)
            if t_key not in target_map:
                target, _ = OperationalTarget.objects.get_or_create(
                    domain=domain, number=t_no, defaults={"text": t_text}
                )
                target_map[t_key] = target
            target = target_map[t_key]

            # المؤشر
            i_key = (t_no, i_no)
            if i_key not in indicator_map:
                indicator, _ = OperationalIndicator.objects.get_or_create(
                    target=target, number=i_no, defaults={"text": i_text}
                )
                indicator_map[i_key] = indicator
            indicator = indicator_map[i_key]

            # الإجراء
            _, c = OperationalProcedure.objects.get_or_create(
                school=school,
                indicator=indicator,
                number=p_no,
                defaults={
                    "text": p_text,
                    "executor_norm": executor,
                    "date_range": date_r,
                    "status": status
                    if status in ("In Progress", "Completed", "Not Started", "Cancelled")
                    else "In Progress",
                    "evidence_type": ev_type,
                    "evidence_source_employee": ev_emp,
                    "evidence_source_file": ev_file,
                    "evaluation": evaluation,
                    "evaluation_notes": eval_notes,
                    "follow_up": follow_up,
                    "comments": comments,
                    "academic_year": YEAR,
                },
            )
            if c:
                proc_count += 1

        self.stdout.write(
            f"✅ الخطة التشغيلية: {len(domain_map)} مجال | "
            f"{len(target_map)} هدف | {len(indicator_map)} مؤشر | {proc_count} إجراء"
        )

        # ── لجنة الجودة ──
        quality_rows = read_csv("4_Quality_Structure_v2.csv")
        committee_created = 0
        for row in quality_rows:
            title = clean(row.get("المسمى الوظيفي", ""))
            resp = clean(row.get("المسؤولية", ""))
            field = clean(row.get("المجال المسؤول عنه", ""))
            if not title or not resp:
                continue
            domain_obj = domain_map.get(field)
            _, c = QualityCommitteeMember.objects.get_or_create(
                school=school,
                job_title=title,
                academic_year=YEAR,
                defaults={
                    "responsibility": resp
                    if resp in ["رئيس اللجنة", "نائب رئيس اللجنة", "مقرر", "عضو"]
                    else "عضو",
                    "domain": domain_obj,
                    "is_active": True,
                },
            )
            if c:
                committee_created += 1

        self.stdout.write(f"✅ لجنة الجودة: {committee_created} عضو")

        # ── ربط المنفذين بالموظفين ──
        try:
            exec_rows = read_csv("3_Unique_Executors_Inventory.csv")
            mapped = 0
            for row in exec_rows:
                exec_norm = clean(row.get("normalized_executor", "") or row.get("executor", ""))
                if not exec_norm:
                    continue

                # ابحث عن موظف يطابق المسمى (جزئياً)
                keyword = exec_norm.replace("منسق ", "").replace("منسقة ", "")
                user = (
                    CustomUser.objects.filter(
                        memberships__school=school, memberships__is_active=True
                    )
                    .filter(
                        memberships__role__name__in=[
                            "coordinator",
                            "teacher",
                            "specialist",
                            "admin",
                            "vice_admin",
                            "vice_academic",
                            "principal",
                        ]
                    )
                    .filter(memberships__user__full_name__icontains=keyword)
                    .first()
                )

                if not user:
                    # بحث بالمسمى الوظيفي من الـ staff CSV
                    for srow in read_csv("2_Normalized_Staff_List.csv"):
                        if exec_norm in clean(srow.get("job_title_norm", "")):
                            nat = clean(srow.get("national_no", ""))
                            user = CustomUser.objects.filter(national_id=nat).first()
                            if user:
                                break

                mapping, c = ExecutorMapping.objects.get_or_create(
                    school=school,
                    executor_norm=exec_norm,
                    academic_year=YEAR,
                    defaults={"user": user},
                )
                if not c and user and not mapping.user:
                    mapping.user = user
                    mapping.save(update_fields=["user"])

                if user:
                    mapping.apply_mapping()
                    mapped += 1

            self.stdout.write(f"✅ ربط المنفذين: {mapped} من {len(exec_rows)} مرتبط")
        except Exception as e:
            self.stdout.write(f"⚠️  ربط المنفذين: {e}")

    # ─────────────────────────────────────────────────────────
    # 10. إعدادات الإشعارات
    # ─────────────────────────────────────────────────────────
    def _step_notifications(self, school):
        try:
            from notifications.models import NotificationSettings

            cfg, c = NotificationSettings.objects.get_or_create(
                school=school,
                defaults={
                    "email_enabled": True,
                    "absence_email_enabled": True,
                    "fail_email_enabled": True,
                    "sms_enabled": False,
                    "absence_threshold": 3,
                    "from_name": school.name,
                },
            )
            self.stdout.write(f"✅ إعدادات الإشعارات: {'جديدة' if c else 'موجودة'}")
        except Exception as e:
            self.stdout.write(f"⚠️  إعدادات الإشعارات: {e}")

    # ─────────────────────────────────────────────────────────
    # Reset
    # ─────────────────────────────────────────────────────────
    def _reset(self):
        from core.models import School

        school = School.objects.filter(code="SHH").first()
        if school:
            school.delete()
            self.stdout.write(self.style.WARNING("🗑️  تم حذف بيانات المدرسة السابقة"))

    # ─────────────────────────────────────────────────────────
    # ملخص نهائي
    # ─────────────────────────────────────────────────────────
    def _print_summary(self, school):
        from core.models import ClassGroup, CustomUser, Membership, StudentEnrollment

        self.stdout.write("\n" + "═" * 58)
        self.stdout.write(self.style.SUCCESS("🎉 اكتملت عملية الحقن!"))
        self.stdout.write("═" * 58)

        total_users = CustomUser.objects.count()
        staff_count = Membership.objects.filter(
            school=school,
            is_active=True,
            role__name__in=[
                "principal",
                "vice_admin",
                "vice_academic",
                "coordinator",
                "teacher",
                "specialist",
                "admin",
            ],
        ).count()
        stu_count = Membership.objects.filter(school=school, role__name="student").count()
        par_count = Membership.objects.filter(school=school, role__name="parent").count()
        cls_count = ClassGroup.objects.filter(school=school, academic_year=YEAR).count()
        enr_count = StudentEnrollment.objects.filter(
            class_group__school=school, is_active=True
        ).count()

        self.stdout.write(f"  مجموع المستخدمين:    {total_users}")
        self.stdout.write(f"  موظفون:              {staff_count}")
        self.stdout.write(f"  طلاب:                {stu_count}")
        self.stdout.write(f"  أولياء أمور:         {par_count}")
        self.stdout.write(f"  فصول دراسية:         {cls_count}")
        self.stdout.write(f"  تسجيلات:             {enr_count}")

        principal = (
            Membership.objects.filter(school=school, role__name="principal", is_active=True)
            .select_related("user")
            .first()
        )

        self.stdout.write("\n── بيانات الدخول ─────────────────────────────────────")
        self.stdout.write(self.style.WARNING(f"  كلمة المرور الموحدة: {self._seed_password}"))
        if principal:
            self.stdout.write(
                self.style.SUCCESS(f"  المدير:    {principal.user.national_id}")
            )
        self.stdout.write("  المعلمون:  <الرقم الوطني>")
        self.stdout.write("  الطلاب:    <الرقم الوطني>")
        self.stdout.write("  الأولياء:  <الرقم الوطني>")
        self.stdout.write("═" * 58)
        self.stdout.write("\n── روابط مهمة ─────────────────────────────────────────")
        self.stdout.write("  http://localhost:8000/          ← الداشبورد")
        self.stdout.write("  http://localhost:8000/admin/    ← الإدارة")
        self.stdout.write("  http://localhost:8000/analytics/ ← الإحصاءات")
        self.stdout.write("  http://localhost:8000/quality/   ← الخطة التشغيلية")
        self.stdout.write("  http://localhost:8000/reports/   ← التقارير والشهادات")
        self.stdout.write("═" * 58)
