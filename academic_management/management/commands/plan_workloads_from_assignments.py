"""دورةُ خطط الأنصبة كاملةً من واقع الإسناد: إدخالٌ ثمّ مراجعةٌ ثمّ اعتماد.

    الإسنادُ حقيقةٌ في القاعدة، والخطّةُ إقرارٌ بها — وبينهما توقيعات.

فالنصابُ لا يصير معتمَداً بأن يُكتب رقمُه، بل بأن يمرّ في يد ثلاثة: منسّقُ
القسم يُدخل ما أسنده لمعلّميه، والنائبُ الأكاديميّ يراجع، والمديرُ يعتمد. وهذا
الأمرُ يُجري الدورةَ نفسَها التي تُجريها الشاشة، بالخدمة نفسِها والبوّابة
نفسِها — لا بكتابةِ حالةٍ في حقل.

ومن أدخل ليس اختياراً: منسّقُ قسم المعلّم هو المُدخِل، فإن كان القسمُ بلا
منسّقٍ مسجَّل فالنائبُ الأكاديميّ ينوب عنه — قرارُ المستخدم 2026-09-07.

    python manage.py plan_workloads_from_assignments --year 2026-2027
    python manage.py plan_workloads_from_assignments --year 2026-2027 --apply
"""

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from academic_management import workload_workflow as wf
from academic_management.models import APPROVED, FROM_MANUAL, LOCKED, TeacherWorkloadPlan
from core.models import Department, School
from core.models.access import Membership
from operations.models import SubjectClassAssignment

#: منبعُ الرقم — واقعُ الإسناد المعتمَد، لا اجتهادَ أحد.
REFERENCE = "جدول الإسناد المعتمَد — استيراد جدول aSc"

REVIEW_NOTE = "روجِعت مقابلَ إسنادات المنصّة: المُسنَدُ يساوي الهدفَ التدريسيّ."


class Command(BaseCommand):
    help = "يُنشئ خطط الأنصبة من الإسناد ويُمرّرها: إدخالُ المنسّق، مراجعةُ النائب، اعتمادُ المدير."

    def add_arguments(self, parser):
        parser.add_argument("--year", required=True, help="العام الدراسيّ، مثل 2026-2027")
        parser.add_argument("--apply", action="store_true", help="اكتب — وبدونها تقريرٌ فقط")

    # ── الأشخاص ──────────────────────────────────────────────────

    def _one(self, school, role):
        """صاحبُ الدور الوحيدُ في المدرسة — والتعدّدُ يوقف العمل لا يُخمَّن فيه."""
        people = [
            m.user
            for m in Membership.objects.filter(
                school=school, role__name=role, is_active=True
            ).select_related("user")
            if m.user.is_active
        ]
        real = [u for u in people if "فحص" not in u.full_name]
        if not real:
            raise CommandError(f"لا أحدَ بدور «{role}» في هذه المدرسة — والدورةُ لا تُوقَّع بلا موقِّع.")
        if len(real) > 1:
            names = "، ".join(u.full_name for u in real)
            raise CommandError(f"أكثرُ من صاحبِ دورٍ «{role}»: {names} — عيّن واحداً قبل التشغيل.")
        return real[0]

    def _editors(self, school, deputy):
        """لكلّ قسمٍ مُدخِلُه: منسّقُه، وإلّا فالنائبُ الأكاديميُّ نيابةً عنه."""
        editors, borrowed = {}, []
        for dept in Department.objects.filter(school=school):
            head = dept.head if dept.head_id else None
            if head is None or not head.is_active:
                borrowed.append(dept.name)
                head = deputy
            editors[dept.id] = head
        return editors, borrowed

    # ── الحقائق ──────────────────────────────────────────────────

    def _assigned(self, school, year):
        totals = {}
        rows = SubjectClassAssignment.objects.filter(
            school=school, academic_year=year, is_active=True
        ).exclude(teacher=None)
        for row in rows:
            totals[row.teacher_id] = totals.get(row.teacher_id, 0) + row.weekly_periods
        return totals

    def _department_of(self, user):
        for m in Membership.objects.filter(user=user, is_active=True):
            if m.department_obj_id:
                return m.department_obj_id
        return None

    def _settled(self, plan, target):
        """خطّةٌ معتمَدةٌ تقول ما يقوله الإسنادُ اليومَ — فلا يُعاد فتحُها."""
        return (
            plan is not None
            and plan.status in (APPROVED, LOCKED)
            and plan.teaching_target == target
            and wf.has_diverged(plan) is False
        )

    # ── التنفيذ ──────────────────────────────────────────────────

    def handle(self, *args, **options):
        year = options["year"]
        school = School.objects.first()
        if school is None:
            raise CommandError("لا مدرسةَ في القاعدة.")

        principal = self._one(school, "principal")
        deputy = self._one(school, "vice_academic")
        editors, borrowed = self._editors(school, deputy)

        totals = self._assigned(school, year)
        if not totals:
            raise CommandError(f"لا إسنادَ في {year} — والخطّةُ لا تُبنى على فراغ.")

        users = {
            m.user_id: m.user
            for m in Membership.objects.filter(school=school, is_active=True).select_related("user")
        }

        self.stdout.write(f"المدرسة: {school.name} · العام: {year}")
        self.stdout.write(f"المعتمِد: {principal.full_name} · المراجع: {deputy.full_name}")
        if borrowed:
            self.stdout.write(f"أقسامٌ بلا منسّقٍ ينوب عنها النائب: {'، '.join(borrowed)}")
        self.stdout.write("")

        done, settled, blocked = [], [], []
        for teacher_id, target in sorted(totals.items(), key=lambda kv: -kv[1]):
            teacher = users.get(teacher_id)
            if teacher is None:
                continue
            latest = (
                TeacherWorkloadPlan.objects.filter(
                    school=school, teacher=teacher, academic_year=year
                )
                .order_by("-plan_version")
                .first()
            )
            if self._settled(latest, target):
                settled.append(teacher.full_name)
                continue

            editor = editors.get(self._department_of(teacher), deputy)
            if options["apply"]:
                try:
                    plan = self._cycle(school, teacher, year, target, editor, deputy, principal)
                except (ValidationError, PermissionDenied, wf.WorkflowError) as exc:
                    blocked.append((teacher.full_name, str(exc)))
                    continue
                done.append((teacher.full_name, plan.teaching_target, editor.full_name))
            else:
                probe = TeacherWorkloadPlan(
                    school=school,
                    teacher=teacher,
                    academic_year=year,
                    required_weekly_periods=target,
                    required_source_kind=FROM_MANUAL,
                    required_source_reference=REFERENCE,
                )
                failed = wf.blocking(wf.validate(probe))
                if failed:
                    blocked.append((teacher.full_name, "، ".join(failed)))
                else:
                    done.append((teacher.full_name, target, editor.full_name))

        verb = "اعتُمدت" if options["apply"] else "جاهزةٌ للاعتماد"
        self.stdout.write(
            f"{verb}: {len(done)} · معتمَدةٌ سلفاً: {len(settled)} · متعذّرة: {len(blocked)}"
        )
        for name, target, editor in done[:200]:
            self.stdout.write(f"   ✓ {name} — {target}ح · أدخلها {editor}")
        for name, why in blocked:
            self.stdout.write(self.style.WARNING(f"   ✗ {name} — {why}"))
        if not options["apply"]:
            self.stdout.write("")
            self.stdout.write("تقريرٌ فقط — أضِف --apply لإجراء الدورة.")

    @transaction.atomic
    def _cycle(self, school, teacher, year, target, editor, deputy, principal):
        """الدورةُ كاملةً لمعلّمٍ واحد — وسقوطُ خطوةٍ يُرجِع الخطّةَ كلَّها."""
        plan = wf.open_draft(
            school,
            teacher,
            year,
            by=editor,
            required_weekly_periods=target,
            required_source_kind=FROM_MANUAL,
            required_source_reference=REFERENCE,
        )
        wf.submit_for_review(plan, by=editor)
        wf.record_review(plan, by=deputy, comment=REVIEW_NOTE)
        wf.approve(plan, by=principal)
        return plan
