"""يطبّق على هذه القاعدة (الإنتاج عادةً) ما دُمق من قاعدةٍ أخرى (8500) — بالمفتاح الطبيعيّ، لا بمعرّفٍ عابر.

    ملفّ JSON (من dump_preview_workload_changes) → مطابقةٌ بالمفتاح الطبيعيّ → حقنُ الفرق فقط

تقريرٌ كاملٌ قبل أيّ كتابة (الافتراضُ)؛ ولا يكتب إلّا بـ`--apply`. الإسنادُ عبر
`assignment_services.apply_assignment` (لا `save()` مباشرةً)، وخطّةُ النصاب عبر `workload_workflow`
(بوّابةٌ وتوقيعٌ لا حقلَ حالةٍ يُكتب) — فتبقى الحراسةُ والتدقيقُ كما لكلّ تعديلٍ آخر في المنصّة.

صفٌّ غيرُ نشطٍ في الدمق (`is_active: false`) لا يُنشأ له سجلٌّ هنا، وإن كان نشطاً على هذه القاعدة يُطفَأ —
ولا يُفعَّل أبداً حتى لو اختلفت حصصُه (`apply_assignment` يُفعِّل دائماً فلا يصلح لهذا المسار). والإطفاءُ يُطبَّق
على كلّ صفوف الدمق قبل أن يُطبَّق أيُّ تفعيل، بصرف النظر عن ترتيبها في الملفّ — فنقلُ مادّةٍ من معلّمٍ إلى آخر في
الدمق نفسِه لا يمرّ بلحظةٍ سجلّان نشطان فيها (F-10).

خطّةٌ معتمَدةٌ أو مقفلةٌ على هذه القاعدة تختلف عمّا دُمق **لا تُعدَّل آليّاً أبداً** — تُذكر لمراجعةٍ يدويّة.
والإسنادُ يُطبَّق قبل خطط الأنصبة دائماً: الاعتمادُ يتحقّق من أنّ المُسنَدَ الفعليّ يساوي الهدفَ التدريسيّ،
فلا يصحّ إلّا بعد أن يستقرّ الإسنادُ.

والاعتمادُ توقيعٌ مستقلٌّ عن المراجعة (`workload_workflow.approve`): من راجع لا يعتمد — قاعدةٌ في المنصّة لا
استثناءَ لها هنا. فمن يتقدّم بخطّةٍ إلى «معتمدة» أو «مقفلة» يحتاج شخصَين مختلفَين: `--actor-employee-number`
يحرّر ويراجع، و`--approver-employee-number` يعتمد. غيابُ الثاني يوقف الخطّةَ عند «روجعت» ويقول ذلك صراحةً —
لا يُخمَّن اعتمادٌ من نفس الشخص.

    python manage.py apply_preview_workload_changes --in changes.json
    python manage.py apply_preview_workload_changes --in changes.json --apply \
        --actor-employee-number 12345 --approver-employee-number 54321
"""

from __future__ import annotations

import json

from django.core.exceptions import PermissionDenied, ValidationError
from django.core.management.base import BaseCommand, CommandError

from academic_management import assignment_services as svc
from academic_management import preview_reconciliation as recon
from academic_management import workload_workflow as wf
from academic_management.models import (
    APPROVED,
    DRAFT,
    EDITABLE_STATUSES,
    FROZEN_STATUSES,
    LOCKED,
    REVIEWED,
    SUBMITTED,
    TeacherWorkloadPlan,
)
from academic_management.preview_reconciliation import ReconciliationError
from core.models import CustomUser
from operations.models import SubjectClassAssignment

REPLAY_REFERENCE = "استُوردت من 8500 — عملُ المالك المنقول، طلبُ 2026-09-27"

#: تسلسلُ الانتقالات نحو حالةٍ مستهدفة — بالترتيب الذي يقبله `workload_workflow._move`.
#: "actor" يحرّر ويراجع، و"approver" يعتمد ويقفل — شخصان مختلفان إلزاماً (راجع الخبرَ أعلاه).
_STEPS_TO = {
    SUBMITTED: (("actor", wf.submit_for_review),),
    REVIEWED: (("actor", wf.submit_for_review), ("actor", wf.record_review)),
    APPROVED: (
        ("actor", wf.submit_for_review),
        ("actor", wf.record_review),
        ("approver", wf.approve),
    ),
    LOCKED: (
        ("actor", wf.submit_for_review),
        ("actor", wf.record_review),
        ("approver", wf.approve),
        ("approver", wf.lock),
    ),
}


class Command(BaseCommand):
    help = "يطبّق تسويةَ إسنادٍ وخططَ أنصبةٍ من ملفّ 8500 على هذه القاعدة — تقريرٌ فقط بلا --apply."

    def add_arguments(self, parser):
        parser.add_argument("--in", dest="in_path", required=True, help="ملفُّ JSON من الدمق")
        parser.add_argument("--apply", action="store_true", help="اكتب فعلاً — وبدونها تقريرٌ فقط")
        parser.add_argument(
            "--actor-employee-number",
            default="",
            help="الرقمُ الوظيفيّ لمن يحرّر ويراجع — وفراغُه أوّلَ مطوِّرِ منصّةٍ (superuser)",
        )
        parser.add_argument(
            "--approver-employee-number",
            default="",
            help="الرقمُ الوظيفيّ لمن يعتمد — يلزم شخصاً غيرَ مَن راجع؛ وفراغُه يوقف كلَّ خطّةٍ هدفُها "
            "«معتمدة» أو «مقفلة» عند «روجعت»",
        )

    def handle(self, *args, **options):
        try:
            # `utf-8-sig` يقرأ الملفَّ بعلامة BOM أو بدونها كليهما — أدواتُ ويندوز (PowerShell) تكتب
            # UTF-8 بعلامة BOM افتراضيّاً، و`json.load` على `utf-8` العاديّ يرفضها بخطأ فكِّ ترميز.
            with open(options["in_path"], encoding="utf-8-sig") as handle:
                payload = json.load(handle)
        except OSError as exc:
            raise CommandError(f"تعذّر فتحُ الملفّ: {options['in_path']}") from exc

        # قائمةُ السماح واستثناءُ حسابات المعاينة (D-167م): يُرفض الملفُّ كلُّه قبل أيّ كتابةٍ ولو بلا --apply.
        violations = recon.injection_violations(payload)
        if violations:
            raise CommandError("رُفض ملفُّ الحقن: " + "؛ ".join(violations))

        actor = self._actor(options["actor_employee_number"])
        approver = self._approver(options["approver_employee_number"], actor)
        self.stdout.write(
            f"المحرّرُ/المراجعُ: {actor.full_name} · {'كتابةٌ فعليّة' if options['apply'] else 'تقريرٌ فقط'}"
        )
        self.stdout.write(f"المعتمِدُ: {approver.full_name if approver else '— غيرُ مُمرَّر'}")
        self.stdout.write("")

        self.stdout.write(self.style.MIGRATE_HEADING("الإسنادُ"))
        assignments = payload.get("assignments", [])
        # الإطفاءُ قبل التفعيل: فصفٌّ فُقد صاحبُه في 8500 يُطفَأ أوّلاً، ولا يُترك سجلٌّ نشطٌ
        # عابرٌ لحظةً حين يحلّ محلَّه صفٌّ آخر في الدمق نفسِه (F-10).
        for data in assignments:
            if not data["is_active"]:
                self._one_assignment(data, actor, options["apply"])
        for data in assignments:
            if data["is_active"]:
                self._one_assignment(data, actor, options["apply"])

        self.stdout.write("")
        self.stdout.write(self.style.MIGRATE_HEADING("خططُ الأنصبة"))
        for data in payload.get("workload_plans", []):
            self._one_plan(data, actor, approver, options["apply"])

        if not options["apply"]:
            self.stdout.write("")
            self.stdout.write("تقريرٌ فقط — أضِف --apply للكتابة.")

    def _actor(self, employee_number):
        if employee_number:
            actor = CustomUser.objects.filter(employee_number=employee_number).first()
            if actor is None:
                raise CommandError(f"لا مستخدِمَ بالرقم الوظيفيّ «{employee_number}».")
            return actor
        actor = CustomUser.objects.filter(is_superuser=True).first()
        if actor is None:
            raise CommandError(
                "لا مطوّرَ منصّةٍ (superuser) في هذه القاعدة ليوقِّع — مرّر --actor-employee-number."
            )
        return actor

    def _approver(self, employee_number, actor):
        if not employee_number:
            return None
        approver = CustomUser.objects.filter(employee_number=employee_number).first()
        if approver is None:
            raise CommandError(f"لا مستخدِمَ بالرقم الوظيفيّ «{employee_number}».")
        if approver.id == actor.id:
            raise CommandError("المعتمِدُ لا يكون الشخصَ نفسَه الذي يراجع — مرّر رقماً وظيفيّاً مختلفاً.")
        return approver

    # ── الإسنادُ ──────────────────────────────────────────────────────

    def _one_assignment(self, data, actor, apply):
        try:
            resolved = recon.resolve_assignment(data)
        except ReconciliationError as exc:
            self.stdout.write(self.style.ERROR(f"   ✗ {data.get('subject_code')} — {exc}"))
            return

        label = f"{resolved.class_group} · {resolved.subject.name_ar}"
        current = SubjectClassAssignment.objects.filter(
            school=resolved.school,
            academic_year=data["academic_year"],
            class_group=resolved.class_group,
            subject=resolved.subject,
            teacher=resolved.teacher,
        ).first()

        if not data["is_active"]:
            self._one_inactive_assignment(current, actor, apply, label)
            return

        if (
            current is not None
            and current.weekly_periods == data["weekly_periods"]
            and current.requires_lab == data["requires_lab"]
            and (current.parallel_group or "") == (data.get("parallel_group") or "")
            and current.is_active
        ):
            self.stdout.write(f"   = {label} — مطابقٌ سلفاً، لا تغيير")
            return

        verb = "تعديلٌ" if current else "جديد"
        self.stdout.write(
            f"   {'~' if current else '+'} {label} → {resolved.teacher.full_name if resolved.teacher else '—'} "
            f"{data['weekly_periods']}ح ({verb})"
        )
        if not apply:
            return
        try:
            svc.apply_assignment(
                school=resolved.school,
                academic_year=data["academic_year"],
                class_group=resolved.class_group,
                subject=resolved.subject,
                teacher=resolved.teacher,
                weekly_periods=data["weekly_periods"],
                by=actor,
                override_reason=data.get("periods_override_reason", ""),
                parallel_group=data.get("parallel_group", ""),
                requires_lab=data.get("requires_lab", False),
                confirm_transfer=True,
            )
            self.stdout.write(self.style.SUCCESS("      ✓ كُتب"))
        except svc.AssignmentError as exc:
            self.stdout.write(self.style.ERROR(f"      ✗ رُفض: {exc}"))

    def _one_inactive_assignment(self, current, actor, apply, label):
        """صفٌّ غيرُ نشطٍ في 8500: لا يُنشأ له سجلٌّ هنا، وإن كان نشطاً هنا يُطفَأ — لا يُفعَّل أبداً

        (`apply_assignment` يُفعِّل دائماً، فلا يصلح لهذا؛ الإطفاءُ عبر `remove_assignment` وحدَه).
        """
        if current is None or not current.is_active:
            self.stdout.write(f"   = {label} — غيرُ نشطٍ سلفاً، لا تغيير")
            return

        self.stdout.write(f"   - {label} — إطفاءٌ (غيرُ نشطٍ في 8500)")
        if not apply:
            return
        svc.remove_assignment(assignment=current, by=actor, reason=REPLAY_REFERENCE)
        self.stdout.write(self.style.SUCCESS("      ✓ أُطفئ"))

    # ── خطّةُ النصاب ──────────────────────────────────────────────────

    def _one_plan(self, data, actor, approver, apply):
        try:
            resolved = recon.resolve_plan(data)
        except ReconciliationError as exc:
            self.stdout.write(self.style.ERROR(f"   ✗ {exc}"))
            return

        school, teacher = resolved.school, resolved.teacher
        label = teacher.full_name
        latest = (
            TeacherWorkloadPlan.objects.filter(
                school=school, teacher=teacher, academic_year=data["academic_year"]
            )
            .order_by("-plan_version")
            .first()
        )

        if latest is not None and self._matches(latest, data):
            self.stdout.write(f"   = {label} — مطابقةٌ سلفاً، لا تغيير")
            return

        if latest is not None and latest.status in FROZEN_STATUSES:
            self.stdout.write(
                self.style.WARNING(
                    f"   ⚠ {label} — خطّةٌ {latest.get_status_display()} على هذه القاعدة تختلف عن 8500؛ "
                    "لا تُعدَّل آليّاً — راجعها من الشاشة."
                )
            )
            return

        if latest is not None and latest.status not in EDITABLE_STATUSES:
            self.stdout.write(
                self.style.WARNING(
                    f"   ⚠ {label} — خطّةٌ {latest.get_status_display()} (قيدَ المراجعة) تختلف عن 8500؛ "
                    "لا تُعدَّل آليّاً — رُدَّها إلى المسودّة يدويّاً أوّلاً إن أردتَ استيراد القيم الجديدة."
                )
            )
            return

        verb = "تعديلُ مسودّةٍ" if latest else "مسودّةٌ جديدة"
        self.stdout.write(
            f"   {'~' if latest else '+'} {label} — {data['required_weekly_periods']}ح ({verb})"
        )
        if not apply:
            return

        try:
            plan = self._write_draft(school, teacher, data, actor, latest)
            for role, step in _STEPS_TO.get(data["status"], ()):
                if role == "approver" and approver is None:
                    self.stdout.write(
                        self.style.WARNING(
                            f"      ⚠ توقّفت عند «{plan.get_status_display()}» — الاعتمادُ يحتاج "
                            "--approver-employee-number (شخصٌ غيرُ من راجع)."
                        )
                    )
                    return
                signer = approver if role == "approver" else actor
                if step is wf.record_review:
                    step(plan, by=signer, comment=REPLAY_REFERENCE)
                else:
                    step(plan, by=signer)
            self.stdout.write(
                self.style.SUCCESS(f"      ✓ كُتبت — الحالةُ: {plan.get_status_display()}")
            )
        except (ValidationError, PermissionDenied, wf.WorkflowError) as exc:
            self.stdout.write(self.style.ERROR(f"      ✗ توقّفت عند حالةٍ متعذّرة: {exc}"))

    def _matches(self, plan, data):
        return (
            plan.status == data["status"]
            and plan.required_weekly_periods == data["required_weekly_periods"]
            and plan.reduction_periods == data["reduction_periods"]
            and plan.required_source_kind == data["required_source_kind"]
        )

    def _write_draft(self, school, teacher, data, actor, latest):
        """المسودّةُ وحدَها تُحرَّر مباشرةً؛ وغيابُها أو كونُها معتمَدةً يعني إصداراً جديداً."""
        fields = {
            "required_weekly_periods": data["required_weekly_periods"],
            "required_source_kind": data["required_source_kind"],
            "required_source_reference": data["required_source_reference"] or REPLAY_REFERENCE,
            "required_policy_key": data.get("required_policy_key", ""),
            "reduction_periods": data.get("reduction_periods", 0),
            "reduction_reason": data.get("reduction_reason", ""),
            "reduction_source": data.get("reduction_source", ""),
            "reduction_source_reference": data.get("reduction_source_reference", ""),
        }
        if latest is not None and latest.status == DRAFT:
            for name, value in fields.items():
                setattr(latest, name, value)
            latest.updated_by = actor
            latest.full_clean(exclude=["created_by", "updated_by"])
            latest.save()
            return latest
        return wf.open_draft(school, teacher, data["academic_year"], by=actor, **fields)
