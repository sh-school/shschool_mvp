"""
بذر قوالب التقييم الوزارية السبعة — الاستمارات الرسمية من 06_attendance_performance_review.md
الإصدار: 2026-09-14
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from core.academic_calendar import default_academic_year
from core.models import School
from quality.models import EmployeeEvaluation, EvaluationAxis, RoleEvaluationTemplate

# === البيانات الوزارية المستخرجة حرفياً من المرجع ===


TEMPLATES = {
    # ────────────────────────────────────────────────────────────────
    # 1. استمارة تقييم المعلم (2.4 — 7 مجالات، 100 درجة)
    # المرجع: 06_attendance_performance_review.md §2.4
    # ────────────────────────────────────────────────────────────────
    "teacher": {
        "label": "استمارة تقييم المعلم",
        "source": "06_attendance_performance_review.md §2.4",
        "axes": [
            {
                "key": "planning_development",
                "label": "التخطيط لتطوير أداء وتحصيل الطلبة",
                "weight": 15,
                "order": 1,
            },
            {
                "key": "student_engagement",
                "label": "إشراك الطلبة في عملية التعلم وتطويرهم كمتعلمين",
                "weight": 25,
                "order": 2,
            },
            {
                "key": "learning_environment",
                "label": "توفير بيئة تعلم آمنة وداعمة ومثيرة للتحدي",
                "weight": 10,
                "order": 3,
            },
            {
                "key": "assessment",
                "label": "تقييم تعلم الطلبة واستخدام بيانات التقييم لتحسين تحصيلهم",
                "weight": 15,
                "order": 4,
            },
            {
                "key": "professional_practices",
                "label": "إظهار ممارسات مهنية عالية الجودة والمشاركة في التطوير المهني المستمر",
                "weight": 10,
                "order": 5,
            },
            {
                "key": "partnerships",
                "label": "الحفاظ على الشراكة الفاعلة مع أولياء الأمور والمجتمع",
                "weight": 10,
                "order": 6,
            },
            {
                "key": "personal_professional",
                "label": "الجوانب الشخصية والمهنية",
                "weight": 15,
                "order": 7,
            },
        ],
    },
    # ────────────────────────────────────────────────────────────────
    # 2. استمارة تقييم النائب الإداري (2.5 — 6 مجالات)
    # المرجع: 06_attendance_performance_review.md §2.5
    # ────────────────────────────────────────────────────────────────
    "admin_vice_principal": {
        "label": "استمارة تقييم النائب الإداري",
        "source": "06_attendance_performance_review.md §2.5",
        "axes": [
            {
                "key": "planning_organization",
                "label": "التخطيط والتنظيم",
                "weight": 10,
                "order": 1,
            },
            {
                "key": "hr_financial",
                "label": "إدارة الموارد البشرية والمالية",
                "weight": 20,
                "order": 2,
            },
            {
                "key": "responsibility",
                "label": "تحمل مسؤولياته الوظيفية",
                "weight": 20,
                "order": 3,
            },
            {
                "key": "staff_development",
                "label": "إدارة وتطوير الموظفين",
                "weight": 25,
                "order": 4,
            },
            {
                "key": "community_partnership",
                "label": "الشراكة المجتمعية",
                "weight": 10,
                "order": 5,
            },
            {
                "key": "personal_aspects",
                "label": "الجوانب الشخصية",
                "weight": 15,
                "order": 6,
            },
        ],
    },
    # ────────────────────────────────────────────────────────────────
    # 3. استمارة تقييم النائب الأكاديمي (2.6 — 5 مجالات)
    # المرجع: 06_attendance_performance_review.md §2.6
    # ────────────────────────────────────────────────────────────────
    "academic_vice_principal": {
        "label": "استمارة تقييم النائب الأكاديمي",
        "source": "06_attendance_performance_review.md §2.6",
        "axes": [
            {
                "key": "strategic_leadership",
                "label": "الإدارة والقيادة الاستراتيجية للمدرسة",
                "weight": 20,
                "order": 1,
            },
            {
                "key": "teaching_management",
                "label": "قيادة وإدارة التعليم والتعلم والتقييم",
                "weight": 35,
                "order": 2,
            },
            {
                "key": "people_management",
                "label": "قيادة وإدارة الأفراد والفرق وتطويرهم",
                "weight": 25,
                "order": 3,
            },
            {
                "key": "community_partnership",
                "label": "الشراكة المجتمعية",
                "weight": 10,
                "order": 4,
            },
            {
                "key": "professional_personal",
                "label": "الجوانب المهنية والسمات الشخصية",
                "weight": 10,
                "order": 5,
            },
        ],
    },
    # ────────────────────────────────────────────────────────────────
    # 4. الفئة العمالية (2.3 — 20 عنصر بلا مجالات موزونة)
    # المرجع: 06_attendance_performance_review.md §2.3
    # ملاحظة: هذه الاستمارة لا تُقسم إلى مجالات موزونة؛ بل 20 عنصر مسطح
    # كل عنصر له درجة ثابتة، المجموع = 100
    # ────────────────────────────────────────────────────────────────
    "worker": {
        "label": "استمارة تقييم الفئة العمالية",
        "source": "06_attendance_performance_review.md §2.3",
        "axes": [
            {"key": "appearance", "label": "المظهر", "weight": 8, "order": 1},
            {"key": "personal_conduct", "label": "التصرف الشخصي", "weight": 4, "order": 2},
            {
                "key": "work_quality",
                "label": "مدى تأديته للعمل بمستوى عالٍ من حيث السرعة والجودة والدقة",
                "weight": 5,
                "order": 3,
            },
            {
                "key": "discipline_attendance",
                "label": "الانضباط والمواظبة",
                "weight": 4,
                "order": 4,
            },
            {
                "key": "independent_work",
                "label": "القدرة على أداء الأعمال دون الرجوع إلى المسؤول",
                "weight": 4,
                "order": 5,
            },
            {
                "key": "integrity_responsibility",
                "label": "الأمانة الوظيفية والشعور بالمسؤولية",
                "weight": 4,
                "order": 6,
            },
            {
                "key": "follow_instructions",
                "label": "مراعاة توجيهات المسؤول وتعليمات الالتزام بالعمل",
                "weight": 8,
                "order": 7,
            },
            {
                "key": "diligence_adaptability",
                "label": "الاجتهاد والتجاوب مع ضغوط العمل",
                "weight": 4,
                "order": 8,
            },
            {
                "key": "confidentiality",
                "label": "الأمانة والمحافظة على سرية معلومات العمل",
                "weight": 5,
                "order": 9,
            },
            {
                "key": "self_control_respect",
                "label": "القدرة على ضبط النفس واكتساب احترام المسؤولين",
                "weight": 6,
                "order": 10,
            },
            {
                "key": "initiative_persistence",
                "label": "المبادرة والمثابرة (التحرك الذاتي لإنجاز الأعمال – إبداء الاقتراحات لتحسين العمل)",
                "weight": 4,
                "order": 11,
            },
            {
                "key": "avoid_exploitation",
                "label": "الامتناع عن استغلال الوظيفة لأغراض شخصية",
                "weight": 4,
                "order": 12,
            },
            {
                "key": "comply_systems",
                "label": "القيام بالواجبات الوظيفية حسب الأنظمة والتعليمات",
                "weight": 4,
                "order": 13,
            },
            {
                "key": "time_management",
                "label": "التقيد بمواعيد العمل والمحافظة على الوقت",
                "weight": 6,
                "order": 14,
            },
            {
                "key": "teamwork_cooperation",
                "label": "الإسهام في الواجبات التي تستلزم فرق عمل وتعاون مع الزملاء",
                "weight": 4,
                "order": 15,
            },
            {
                "key": "work_without_supervision",
                "label": "القدرة على العمل دون مراقبة",
                "weight": 4,
                "order": 16,
            },
            {
                "key": "accept_feedback",
                "label": "تقبل توجيهات وانتقادات الرؤساء",
                "weight": 5,
                "order": 17,
            },
            {
                "key": "relationships",
                "label": "العلاقة والسلوكيات مع الموظفين (العلاقة السلوكية مع الرؤساء – العلاقة السلوكية مع الزملاء – العلاقة السلوكية مع المراجعين)",
                "weight": 6,
                "order": 18,
            },
            {
                "key": "public_interest",
                "label": "تغليب المصلحة العامة على المصلحة الخاصة",
                "weight": 5,
                "order": 19,
            },
            {
                "key": "comply_policies",
                "label": "الالتزام بالأنظمة والسياسات المعمول بها",
                "weight": 6,
                "order": 20,
            },
        ],
    },
    # ────────────────────────────────────────────────────────────────
    # 5. الوظائف الإدارية 1 (2.7 — 6 مجالات)
    # المرجع: 06_attendance_performance_review.md §2.7
    # الفئات: مسؤول الإرشاد والتوجيه، منسق شؤون الطلاب، أخصائيون...
    # ────────────────────────────────────────────────────────────────
    "admin_role_1": {
        "label": "استمارة تقييم الوظائف الإدارية 1 (إرشاد، أخصائيون...)",
        "source": "06_attendance_performance_review.md §2.7",
        "axes": [
            {
                "key": "planning_organization",
                "label": "التخطيط والتنظيم",
                "weight": 12,
                "order": 1,
            },
            {
                "key": "supervision_follow_up",
                "label": "الإشراف والمتابعة والتوجيه",
                "weight": 23,
                "order": 2,
            },
            {
                "key": "responsibility",
                "label": "تحمل مسؤولياته الوظيفية",
                "weight": 20,
                "order": 3,
            },
            {
                "key": "professional_growth",
                "label": "النمو والتطوير المهني",
                "weight": 20,
                "order": 4,
            },
            {
                "key": "community_partnership",
                "label": "الشراكة المجتمعية",
                "weight": 10,
                "order": 5,
            },
            {
                "key": "personal_aspects",
                "label": "الجوانب الشخصية",
                "weight": 15,
                "order": 6,
            },
        ],
    },
    # ────────────────────────────────────────────────────────────────
    # 6. الوظائف الإدارية 2 (2.8 — 8 مجالات)
    # المرجع: 06_attendance_performance_review.md §2.8
    # الفئات: سكرتير مدرسة، محاسب، موظف استقبال، فني تقنية معلومات
    # ────────────────────────────────────────────────────────────────
    "admin_role_2": {
        "label": "استمارة تقييم الوظائف الإدارية 2 (إدارة، سكرتير، فني...)",
        "source": "06_attendance_performance_review.md §2.8",
        "axes": [
            {
                "key": "planning_organization",
                "label": "التخطيط والتنظيم",
                "weight": 10,
                "order": 1,
            },
            {
                "key": "responsibility",
                "label": "القدرة على تحمل المسؤولية",
                "weight": 20,
                "order": 2,
            },
            {
                "key": "initiative_innovation",
                "label": "القدرة على المبادرة والابتكار",
                "weight": 10,
                "order": 3,
            },
            {
                "key": "task_accomplishment",
                "label": "إنجاز المهام الوظيفية",
                "weight": 25,
                "order": 4,
            },
            {
                "key": "professional_development",
                "label": "التطوير المهني",
                "weight": 10,
                "order": 5,
            },
            {
                "key": "work_relationships",
                "label": "علاقات العمل",
                "weight": 10,
                "order": 6,
            },
            {
                "key": "commitment_discipline",
                "label": "الالتزام والانضباط",
                "weight": 10,
                "order": 7,
            },
            {
                "key": "general_appearance",
                "label": "المظهر العام",
                "weight": 5,
                "order": 8,
            },
        ],
    },
    # ────────────────────────────────────────────────────────────────
    # 7. الوظائف الإدارية 3 (2.9 — 6 مجالات)
    # المرجع: 06_attendance_performance_review.md §2.9
    # الفئات: منسق مشاريع، محضر مختبر، مرشد أكاديمي، مساعد معلم...
    # ────────────────────────────────────────────────────────────────
    "admin_role_3": {
        "label": "استمارة تقييم الوظائف الإدارية 3 (مشاريع، مختبر، مرشد...)",
        "source": "06_attendance_performance_review.md §2.9",
        "axes": [
            {
                "key": "planning_organization",
                "label": "التخطيط والتنظيم",
                "weight": 10,
                "order": 1,
            },
            {
                "key": "supervision_implementation",
                "label": "الإشراف والمتابعة والتنفيذ",
                "weight": 22,
                "order": 2,
            },
            {
                "key": "responsibility",
                "label": "تحمل مسؤولياته الوظيفية",
                "weight": 24,
                "order": 3,
            },
            {
                "key": "professional_growth",
                "label": "النمو والتطوير المهني",
                "weight": 14,
                "order": 4,
            },
            {
                "key": "community_partnership",
                "label": "الشراكة المجتمعية",
                "weight": 10,
                "order": 5,
            },
            {
                "key": "personal_aspects",
                "label": "الجوانب الشخصية",
                "weight": 20,
                "order": 6,
            },
        ],
    },
}

# خريطة ربط بين role_name في النظام والقالب الموجود في TEMPLATES
ROLE_TO_TEMPLATE = {
    "teacher": "teacher",
    "admin_vice_principal": "admin_vice_principal",
    "academic_vice_principal": "academic_vice_principal",
    "worker": "worker",
    "coordinator": "admin_role_1",  # منسق ← الوظائف الإدارية 1
    "counselor": "admin_role_1",  # مرشد ← الوظائف الإدارية 1
    "nurse": "admin_role_2",  # ممرضة ← الوظائف الإدارية 2
    "secretary": "admin_role_2",  # سكرتيرة ← الوظائف الإدارية 2  # pragma: allowlist secret
    "lab_technician": "admin_role_3",  # فني مختبر ← الوظائف الإدارية 3
}


def _locked_evaluations(template):
    """
    إصلاح ب.2 (مراجعة عدائيّة): التقييماتُ المرتبطة بهذا القالب والتي عليها
    درجاتٌ محفوظة (EvaluationScore) أو حالتها تجاوزت المسودّة — لا يجوز تعديلُ
    وزن/تسمية محاور قالبها من تحتها، فذلك يُفسد مجموعاً مُعتمَداً أو مُقدَّماً.
    """
    return (
        EmployeeEvaluation.objects.filter(template=template)
        .filter(Q(status__in=["submitted", "approved", "acknowledged"]) | Q(scores__isnull=False))
        .distinct()
    )


class Command(BaseCommand):
    help = """
    بذر قوالب التقييم الوزارية السبعة من المرجع 06_attendance_performance_review.md

    الاستخدام:
        python manage.py seed_quality_templates --dry-run
        python manage.py seed_quality_templates --apply
    """

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="عرض الفروقات بدون تطبيق",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="تطبيق التغييرات",
        )

    def handle(self, *args, **options):
        dry_run = options.get("dry_run")
        apply_changes = options.get("apply")

        if not dry_run and not apply_changes:
            self.stdout.write(self.style.ERROR("استخدم --dry-run أو --apply"))
            return

        try:
            school = School.objects.first()
            if not school:
                raise CommandError("لا توجد مدارس في قاعدة البيانات")

            academic_year = default_academic_year()
            self.stdout.write(f"المدرسة: {school.name}")
            self.stdout.write(f"العام الأكاديمي: {academic_year}")
            self.stdout.write("")

            if dry_run:
                self._dry_run(school, academic_year)
            elif apply_changes:
                self._apply(school, academic_year)

        except Exception as e:
            raise CommandError(str(e))

    def _dry_run(self, school, academic_year):
        """عرض الفروقات المتوقعة"""
        self.stdout.write(self.style.WARNING("وضع --dry-run: عرض فقط"))
        self.stdout.write("")

        for template_key, template_data in TEMPLATES.items():
            self.stdout.write(self.style.SUCCESS(f"قالب: {template_data['label']}"))
            self.stdout.write(f"  المصدر: {template_data['source']}")
            self.stdout.write(f"  المحاور: {len(template_data['axes'])}")

            # حساب مجموع الأوزان
            total_weight = sum(a["weight"] for a in template_data["axes"])
            if total_weight == 100:
                self.stdout.write(self.style.SUCCESS(f"  ✓ مجموع الأوزان: {total_weight}"))
            else:
                self.stdout.write(
                    self.style.ERROR(f"  ✗ مجموع الأوزان: {total_weight} (يجب أن يكون 100)")
                )

            for axis in template_data["axes"]:
                self.stdout.write(f"    - {axis['label']} ({axis['weight']}%)")

            # إصلاح ب.2: عدد التقييمات القائمة المتأثّرة لهذا الدور — لو
            # كان القالبُ موجوداً فعلاً وعليه تقييماتٌ مقفلة، فلن يُعدَّل.
            existing = RoleEvaluationTemplate.objects.filter(
                school=school, role_name=template_key, academic_year=academic_year
            ).first()
            if existing:
                locked_count = _locked_evaluations(existing).count()
                if locked_count:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠ {locked_count} تقييماً قائماً مقفلاً على هذا القالب — لن تُعدَّل محاوره"
                        )
                    )
            self.stdout.write("")

    def _apply(self, school, academic_year):
        """تطبيق البذر"""
        created_count = 0
        updated_count = 0
        skipped_locked = 0

        for template_key, template_data in TEMPLATES.items():
            with transaction.atomic():
                template, created = (
                    RoleEvaluationTemplate.objects.select_for_update().get_or_create(
                        school=school,
                        role_name=template_key,
                        academic_year=academic_year,
                        defaults={"is_active": True},
                    )
                )

                if created:
                    created_count += 1
                    self.stdout.write(self.style.SUCCESS(f"✓ أنشئ: {template_data['label']}"))
                else:
                    updated_count += 1
                    self.stdout.write(self.style.WARNING(f"⟳ موجود: {template_data['label']}"))

                # إصلاح ب.2: يُعاد فحصُ القفل هنا داخل معاملة الكتابة نفسها
                # (لا خارجها كما في --dry-run) لتفادي فتحةٍ بين الفحص والكتابة.
                locked_count = _locked_evaluations(template).count() if not created else 0

                # إضافة المحاور
                for axis_data in template_data["axes"]:
                    axis, axis_created = EvaluationAxis.objects.get_or_create(
                        template=template,
                        key=axis_data["key"],
                        defaults={
                            "label": axis_data["label"],
                            "weight": axis_data["weight"],
                            "order": axis_data["order"],
                        },
                    )
                    if not axis_created and (
                        axis.label != axis_data["label"] or axis.weight != axis_data["weight"]
                    ):
                        if locked_count:
                            skipped_locked += 1
                            self.stdout.write(
                                self.style.ERROR(
                                    f"  ⚠ تخطّي تعديل «{axis.label}» — {locked_count} تقييماً"
                                    " قائماً مقفلاً على هذا القالب"
                                )
                            )
                            continue
                        axis.label = axis_data["label"]
                        axis.weight = axis_data["weight"]
                        axis.order = axis_data["order"]
                        axis.save()

        self.stdout.write(self.style.SUCCESS(f"✓ تم إنشاء: {created_count} قالب"))
        self.stdout.write(self.style.WARNING(f"⟳ تم تحديث: {updated_count} قالب"))
        if skipped_locked:
            self.stdout.write(
                self.style.ERROR(f"⚠ تخطّي {skipped_locked} محوراً بسبب تقييماتٍ مقفلة عليها")
            )
