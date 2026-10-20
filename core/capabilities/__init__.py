"""سجلُّ القدرات — «من يفعل ماذا» بالفعل لا بالدور.

كان الحارسُ يسأل «أيُّ دورٍ أنت؟»، والجوابُ مكتوبٌ في مئتي موضعٍ بصيغٍ مختلفة: مجموعةٌ
مركزيّةٌ هنا، وقائمةٌ حرفيّةٌ هناك، وديكوريتورٌ مختصرٌ في ثالث. فالقائمةُ الجانبيّةُ تَعِد بما
يردّه الحارس، والبوّابةُ لا تعرف ما يعرفه، ومراجعةُ «من يرى درجاتِ الطلبة؟» تتطلّب قراءةَ
الشيفرة كلِّها — وهكذا مرّت ثغراتُ مراجعة 2026-09-13.

والقدرةُ تسمّي **الفعل**: ``assessments.enter_grades`` لا ``{"principal", "coordinator", ...}``.
فقدرتان تحملان اليومَ الأعضاءَ أنفسَهم تبقيان اثنتين، ويفترقان متى قُرّر ذلك دون أن تمسّ
إحداهما الأخرى.

**هذه الخطوةُ الأولى:** السجلُّ وحدَه. أعضاءُ كلّ قدرةٍ هم أعضاءُ الحرّاس القائمة حرفاً — مأخوذون
من المجموعات نفسِها حيث وُجدت — ولم يُحوَّل حارسٌ واحد. و``tests/test_capabilities_registry.py``
يُثبت أنّ كلَّ حارسٍ في المنصّة يطابق قدرةً في السجلّ، فلا يُعرض سجلٌّ ناقصٌ ولا مخترَع.

**والأساس** (``basis``) يقول من أين جاءت القدرة: نصٌّ وزاريٌّ بمرجعه، أو قرارٌ مؤرَّخ، أو
«افتراضُ المنصّة» — أي أنّها كذلك في الشيفرة ولم تُراجَع بعدُ مقابل نصّ. لا يُكتب مرجعٌ غيرُ موجود.

**الحزمةُ (W-20261019-007):** كان هذا ملفّاً واحداً على حدّ الألف سطر، فصار ملفّاً لكلّ مجالٍ تحت
``core/capabilities/``؛ والواجهةُ التي يستورد منها المستهلكون هنا ثابتةٌ كما كانت. وقدرةٌ جديدةٌ تُضاف
إلى ملفّ مجالها، وتجميعُها بالترتيب في ``registry.py``، و``tests/test_capabilities_snapshot.py`` يثبّت
المفاتيحَ والحقولَ والترتيب.
"""

from core.capabilities.access import capability, capability_required, has_capability
from core.capabilities.acting import (
    ACTING_NEVER_KEYS,
    ACTING_NEVER_TRANSFERS,
    acting_capabilities,
    acting_holds,
    acting_transferable,
    register_acting_roles_provider,
)
from core.capabilities.base import PLATFORM_ASSUMPTION, Capability
from core.capabilities.registry import registry
from core.capabilities.schedule_developer_only import (
    SCHEDULE_DEVELOPER_ONLY_CAPABILITIES,
    SCHEDULE_DEVELOPER_ONLY_MESSAGE,
    schedule_developer_only,
    schedule_developer_only_active,
    schedule_developer_only_blocks,
)

__all__ = [
    "ACTING_NEVER_KEYS",
    "ACTING_NEVER_TRANSFERS",
    "Capability",
    "PLATFORM_ASSUMPTION",
    "SCHEDULE_DEVELOPER_ONLY_CAPABILITIES",
    "SCHEDULE_DEVELOPER_ONLY_MESSAGE",
    "acting_capabilities",
    "acting_holds",
    "acting_transferable",
    "capability",
    "capability_required",
    "has_capability",
    "register_acting_roles_provider",
    "registry",
    "schedule_developer_only",
    "schedule_developer_only_active",
    "schedule_developer_only_blocks",
]
