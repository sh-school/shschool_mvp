"""قائمةُ المخالفات على الدليل التنظيميّ لسياسة إدارة سلوك الطلبة 2026.

واحدٌ وأربعون مخالفةً (9 · 7 · 10 · 15) من جدول التصنيف (ص84)، مصدرُها
`behavior/conduct_2026.py` — مصدرٌ واحدٌ لا قائمةٌ منسوخةٌ هنا.

وكانت على الإنتاج قائمةُ 2025 (لائحة الشحانية، أربعون) بترميزٍ يتقاطع مع ترميز
2026 بمعانٍ مختلفة: «1-02» فيها «إثارة الفوضى» وفي الدليل «الخروج من الصفّ دون
استئذان». فالرمزُ الذي عليه مخالفاتٌ مسجَّلةٌ بمعنىً آخر لا يُكتب فوقه: يُنقل إلى
`25-<الرمز>` معطَّلاً، ويُنشأ رمزُ 2026 جديداً — فلا تتبدّل مخالفةٌ قديمةٌ صامتة.
وما لا يُستعمل يُحدَّث في مكانه. وما بقي من 2025 بلا مقابلٍ يُعطَّل ولا يُحذف.
"""

from django.db import migrations

from behavior.conduct_2026 import CATALOG

POINTS_BY_LEVEL = {1: 5, 2: 15, 3: 25, 4: 40}
OFFICIAL = r"^\d-\d{2}$"


def forwards(apps, schema_editor):
    ViolationCategory = apps.get_model("behavior", "ViolationCategory")
    BehaviorInfraction = apps.get_model("behavior", "BehaviorInfraction")
    codes = {item.code for item in CATALOG}

    for item in CATALOG:
        existing = ViolationCategory.objects.filter(code=item.code).first()
        if (
            existing is not None
            and existing.name_ar != item.name
            and BehaviorInfraction.objects.filter(violation_category=existing).exists()
        ):
            existing.code = f"25-{item.code}"
            existing.is_active = False
            existing.save(update_fields=["code", "is_active"])
        ViolationCategory.objects.update_or_create(
            code=item.code,
            defaults={
                "degree": item.degree,
                "name_ar": item.name,
                "points": POINTS_BY_LEVEL[item.degree],
                "is_active": True,
                "category": "",
                "requires_security_referral": item.degree == 4,
                "requires_parent_summon": item.degree >= 3,
            },
        )

    ViolationCategory.objects.filter(code__regex=OFFICIAL).exclude(code__in=codes).update(
        is_active=False
    )


def backwards(apps, schema_editor):
    """لا استرجاعَ لنصوص 2025: الرموزُ تبقى، والتعطيلُ يُرفع عمّا عُطّل."""
    ViolationCategory = apps.get_model("behavior", "ViolationCategory")
    ViolationCategory.objects.filter(code__regex=OFFICIAL).update(is_active=True)


class Migration(migrations.Migration):
    dependencies = [
        ("behavior", "0014_rls_parent_derived"),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
