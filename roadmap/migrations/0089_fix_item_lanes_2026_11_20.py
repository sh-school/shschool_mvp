"""الخارطة (2026-11-20): نقلُ 45 بنداً من مساراتٍ لا تعرفها الصفحة إلى مساراتها المعتمدة.

**العلّة:** هجراتُ مزامنةٍ سابقة (0048 إلى 0088) كتبت مساراتٍ ليست في قائمة المسارات (`meta.lanes`):
`security` و`operations` و`behavior` و`design` و`tools`. والصفحةُ تبني المصفوفةَ والخطَّ الزمنيَّ وقائمةَ المسارات
من تلك القائمة وحدَها، فسقطت هذه البنودُ من العرض كلّه وإن بقيت في العدّ.
**الإصلاح:** جدولٌ صريحٌ لكلّ رمز: المسارُ القديمُ والمعتمد. الأمنُ إلى `sec`، والأدواتُ إلى `quality`، والتصميمُ إلى
`frontend`، والسلوكُ إلى `backend`؛ و`operations` إلى `ops` لما هو تشغيلٌ وبنية، وإلى `backend` لوظائف المنصّة
(متابعةُ الغياب، ومصادرُ قانون الموارد البشريّة، وأسرةُ العيادة).
**حارسة:** لا يُلمس بندٌ تغيّر مسارُه عن القديم (عدّله المطوّرُ من الصفحة)، ولا يُنقل بندٌ إلى مسارٍ غائبٍ عن القائمة،
ولا تُلمس الحالةُ ولا التقدّمُ ولا الملاحظة. تُعاد بلا أثر.
**المقيس (2026-11-20):** بياناتُ صفحة الخارطة على الإنتاج: 547 بنداً، منها 45 بمسارٍ خارج القائمة (11 security،
و24 operations، و4 behavior، و3 design، و3 tools).
"""

from django.db import migrations

META_KEY = "roadmap"

SEC = ("security", "sec")
TOOLS = ("tools", "quality")
DESIGN = ("design", "frontend")
BEHAVIOR = ("behavior", "backend")
OPS = ("operations", "ops")
OPS_FEATURE = ("operations", "backend")

#: الرمز ← (المسارُ القديم، المسارُ المعتمد).
LANE_FIXES = {
    # الأمن والامتثال
    "N-066": SEC,
    "N-075": SEC,
    "N-076": SEC,
    "N-158": SEC,
    "N-159": SEC,
    "N-169": SEC,
    "CLN-01": SEC,
    "CLN-02": SEC,
    "CLN-03": SEC,
    "CLN-05": SEC,
    "CLN-10": SEC,
    # أدواتُ التطوير والاختبار والوثائق
    "N-147": TOOLS,
    "N-148": TOOLS,
    "N-149": TOOLS,
    # الهويّةُ والتخطيطُ والطباعة
    "N-154": DESIGN,
    "N-161": DESIGN,
    "N-162": DESIGN,
    # السلوكُ وطلباتُ أولياء الأمور
    "N-152": BEHAVIOR,
    "N-153": BEHAVIOR,
    "N-165": BEHAVIOR,
    "N-166": BEHAVIOR,
    # تشغيلٌ وبنية: CI والنشر والنسخُ الاحتياطيّ وبيئةُ المطوّر واختبارُ الحمل
    "N-155": OPS,
    "N-156": OPS,
    "N-157": OPS,
    "N-163": OPS,
    "N-164": OPS,
    "N-167": OPS,
    "N-168": OPS,
    # وظائفُ المنصّة: متابعةُ الغياب ومصادرُ قانون الموارد البشريّة والعيادة
    "N-150": OPS_FEATURE,
    "N-151": OPS_FEATURE,
    "N-160": OPS_FEATURE,
    "CLN-00": OPS_FEATURE,
    "CLN-04": OPS_FEATURE,
    "CLN-06": OPS_FEATURE,
    "CLN-08": OPS_FEATURE,
    "CLN-09": OPS_FEATURE,
    "CLN-11": OPS_FEATURE,
    "CLN-12": OPS_FEATURE,
    "CLN-13": OPS_FEATURE,
    "CLN-14": OPS_FEATURE,
    "CLN-15": OPS_FEATURE,
    "CLN-16": OPS_FEATURE,
    "CLN-17": OPS_FEATURE,
    "CLN-18": OPS_FEATURE,
    "CLN-19": OPS_FEATURE,
}


def known_lanes(meta_model):
    """مفاتيحُ المسارات في وثيقة الخارطة؛ مجموعةٌ فارغةٌ إن غابت الوثيقة."""
    doc = meta_model.objects.filter(key=META_KEY).first()
    lanes = (doc.data or {}).get("lanes", []) if doc else []
    return {str(lane.get("key")) for lane in lanes if isinstance(lane, dict)}


def fix_lanes(item_model, lanes):
    """تنقل كلَّ بندٍ ما زال على مساره القديم إلى المعتمد إن كان في القائمة؛ تُرجع الرموزَ المنقولة."""
    moved = []
    for code, (old, new) in LANE_FIXES.items():
        if new not in lanes:
            continue
        if item_model.objects.filter(code=code, lane=old).update(lane=new):
            moved.append(code)
    return moved


def forwards(apps, schema_editor):
    item_model = apps.get_model("roadmap", "RoadmapItem")
    meta_model = apps.get_model("roadmap", "RoadmapMeta")
    # قاعدةٌ بلا استيراد (اختبار، شجرةٌ جديدة): لا شيء يُزامَن.
    if not item_model.objects.exists():
        return
    fix_lanes(item_model, known_lanes(meta_model))


class Migration(migrations.Migration):
    dependencies = [
        ("roadmap", "0088_sync_items_2026_11_20"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
