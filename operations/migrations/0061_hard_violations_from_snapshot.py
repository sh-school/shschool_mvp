"""تصحيحُ `hard_violations` في التوليدات القائمة من لقطتها نفسِها (W-20260930-005).

كان المولّدُ يكتب `len(errors) + breaches.count` (نصوصٌ + مخالفات) بينما تقرأ بوّابةُ الاعتماد
`config_snapshot["breaches"]["count"]` وحده — فتخالف الرقمان في مسوّداتٍ قائمة (8 مقابل 1).
هجرةُ بياناتٍ فقط (بلا تغيير مخطّط): تُسوّي العمودَ على عدد اللقطة، وتحفظ القيمةَ القديمة في
`config_snapshot["legacy_hard_violations"]` ليكون التراجعُ دقيقاً. والصفوفُ بلا لقطة مخالفاتٍ تُترك كما هي.
"""

from django.db import migrations

LEGACY_KEY = "legacy_hard_violations"


def _recorded_count(snapshot):
    breaches = (snapshot or {}).get("breaches")
    if not isinstance(breaches, dict):
        return None
    count = breaches.get("count")
    return count if isinstance(count, int) and not isinstance(count, bool) else None


def align_from_snapshot(apps, schema_editor):
    generation = apps.get_model("operations", "ScheduleGeneration")
    for row in generation.objects.all().only("id", "hard_violations", "config_snapshot").iterator():
        count = _recorded_count(row.config_snapshot)
        if count is None or count == row.hard_violations:
            continue
        snapshot = dict(row.config_snapshot)
        snapshot[LEGACY_KEY] = row.hard_violations
        generation.objects.filter(pk=row.pk).update(hard_violations=count, config_snapshot=snapshot)


def restore_legacy(apps, schema_editor):
    generation = apps.get_model("operations", "ScheduleGeneration")
    for row in generation.objects.all().only("id", "config_snapshot").iterator():
        snapshot = row.config_snapshot
        if not isinstance(snapshot, dict) or LEGACY_KEY not in snapshot:
            continue
        snapshot = dict(snapshot)
        legacy = snapshot.pop(LEGACY_KEY)
        generation.objects.filter(pk=row.pk).update(hard_violations=legacy, config_snapshot=snapshot)


class Migration(migrations.Migration):
    dependencies = [
        ("operations", "0060_sch20_timestamps"),
    ]

    operations = [
        migrations.RunPython(align_from_snapshot, restore_legacy),
    ]
