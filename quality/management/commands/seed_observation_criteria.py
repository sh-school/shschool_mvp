"""
seed_observation_criteria — يزرع معايير الملاحظة الصفّية الـ23 (4 مجالات)
لكل مدرسة، مطابقةً لاستمارة الإشراف على أداء المعلّم الرسمية. idempotent.
"""

from django.core.management.base import BaseCommand

from core.models import School
from quality.observation_models import ObservationCriterion

# (domain, text) بالترتيب — الترقيم order يُحسب تلقائياً
CRITERIA = [
    # ── التخطيط ──
    ("planning", "خطة الدرس متوفرة وبنودها مستكملة ومناسبة ومعلنة على نظام قطر للتعليم."),
    ("planning", "أهداف التعلم مناسبة ودقيقة الصياغة وقابلة للقياس."),
    ("planning", "أنشطة الدرس الرئيسة واضحة ومتدرجة ومرتبطة بالأهداف."),
    # ── تنفيذ الدرس ──
    ("execution", "أهداف التعلم معروضة ويتم مناقشتها."),
    ("execution", "أنشطة التمهيد مفعّلة بشكل مناسب."),
    ("execution", "محتوى الدرس واضح، والعرض منظم، ومترابط."),
    ("execution", "طرائق التدريس وإستراتيجياته متنوعة وتتمحور حول الطالب."),
    ("execution", "مصادر التعلم الرئيسة والمساندة موظّفة بصورة واضحة وسليمة."),
    ("execution", "الوسائل التعليميّة والتكنولوجيا موظّفة بصورة مناسبة."),
    ("execution", "الأسئلة الصفية ذات صياغة سليمة ومتدرجة ومثيرة للتفكير."),
    ("execution", "المادة العلمية دقيقة ومناسبة."),
    ("execution", "الكفايات الأساسية متضمنة في السياق المعرفي للدرس."),
    ("execution", "القيم الأساسيّة متضمنة في السياق المعرفي للدرس."),
    ("execution", "التكامل بين محاور المادة ومع المواد الأخرى يتم بشكل مناسب."),
    ("execution", "الفروق الفردية بين الطلبة يتم مراعاتها."),
    ("execution", "غلق الدرس يتم بشكل مناسب."),
    # ── التقويم ──
    ("assessment", "أساليب التقويم (القبلي والبنائي والختامي) مناسبة ومتنوعة."),
    ("assessment", "التغذية الراجعة متنوعة ومستمرة."),
    ("assessment", "أعمال الطلبة متابعة ومصححة بدقة ورقيًا وإلكترونيًا."),
    # ── الإدارة الصفية وبيئة التعلم ──
    ("management", "البيئة الصفيّة إيجابيّة وآمنة وداعمة للتعلُّم."),
    ("management", "إدارة أنشطة التعلُّم والمشاركات الصفيّة تتم بصورة منظمة."),
    ("management", "قوانين إدارة الصف وإدارة السلوك مفعلة."),
    ("management", "الاستثمار الأمثل لزمن الحصة."),
]


class Command(BaseCommand):
    help = "زرع معايير الملاحظة الصفّية (23 معياراً × 4 مجالات) لكل مدرسة."

    def add_arguments(self, parser):
        parser.add_argument("--school", help="رمز مدرسة محددة (افتراضياً كل المدارس)")

    def handle(self, *args, **options):
        schools = School.objects.all()
        if options.get("school"):
            schools = schools.filter(code=options["school"])

        total_created = 0
        for school in schools:
            created = 0
            for order, (domain, text) in enumerate(CRITERIA, start=1):
                _, was_created = ObservationCriterion.objects.get_or_create(
                    school=school,
                    domain=domain,
                    text=text,
                    defaults={"order": order, "is_active": True},
                )
                created += int(was_created)
            total_created += created
            self.stdout.write(f"✓ {school.name}: {created} معيار جديد ({len(CRITERIA)} إجمالاً)")
        self.stdout.write(self.style.SUCCESS(f"اكتمل — {total_created} معيار مزروع."))
