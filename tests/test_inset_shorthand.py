"""`inset-inline: auto` وحدَه يمحو الطرفين — الاختصارُ بقيمةٍ واحدةٍ يسري على `start` و`end` معاً.

وقع في `.report-student-dropdown` (`30-modules-1.css`): قاعدةُ الجوّال تكتب `inset-inline: 8px` (الطرفين معاً)،
وقاعدةُ `@media (min-width: 641px)` كتبت `inset-inline: auto` تريد إلغاءَها، فصار الطرفان `auto` ولم يبقَ من
`inset-inline-end: 0` في القاعدة الأساس شيءٌ (كانت ميّتةً أصلاً منذ قاعدةِ الجوّال). فوقع الصندوقُ (366px) عند
موضعه الساكن يمتدّ إلى خارج الشاشة: حقلُ البحث مقصوصٌ وزرُّ «بحث» غيرُ ظاهر وتمريرٌ أفقيٌّ 202–217px على
`/reports/` (قياسُ ADR-0006).

والصحيحُ أن تُسمّى القيمتان: `inset-inline: auto 0` (start ثمّ end) أو تُكتب الخاصّيّةُ الطويلة وحدَها.
ولا يشمل الحارسُ `inset: auto` (تصفيرُ الجهات الأربع مشروعٌ)، ولا يقرأ غيرَ ملفّات `read_css()` الثمانية.
هذا حارسٌ ساكنٌ على الشكل، لا على التخطيط.
"""

import re

from tests.css_contrast import strip_noise
from tests.css_source import read_css

BARE_AUTO = re.compile(
    r"(?<![\w-])inset-(?:inline|block)\s*:\s*auto\s*(?:!important\s*)?(?:;|})", re.I
)


def test_no_inset_shorthand_is_a_bare_auto():
    css = strip_noise(read_css())
    found = [" ".join(m.group().split()) for m in BARE_AUTO.finditer(css)]
    assert not found, (
        "اختصارُ `inset-inline`/`inset-block` بقيمةٍ واحدةٍ `auto` يمحو الطرفين معاً (وقد يكون أحدُهما مقصوداً)؛ "
        f"سمِّ القيمتين (`auto 0`) أو اكتب الخاصّيّةَ الطويلة: {found}"
    )
