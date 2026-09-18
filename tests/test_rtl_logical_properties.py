"""لا `left:`/`right:` فيزيائيّاً في تموضعٍ مطلق — الاتّجاه منطقيّ لا مقلوبٌ يدويّاً.

كانت 19 قاعدةَ `position` (مطلقٍ أو ثابت) تكتب `left`/`right` حرفيّاً —
تُترجَم صحيحةً على هذه المنصّة (RTL دائماً، لا صفحةَ LTR واحدة) لكنّها
تفترض الاتّجاهَ بدل أن تصفَه: من يقرأ `right: 12px` لا يعرف أهو تعمّدٌ
لليمين بصريّاً أم نسخٌ من مثالٍ إنجليزيّ. ورُحِّلت يومَ 2026-09-18
(خارطة طريق الهويّة البصريّة، P1-3) إلى `inset-inline-start/end` —
`start` يمين المستند دائماً هنا، و`end` يساره — فيصف الرمزُ نيّته لا
إحداثيّاتِ شاشةٍ بعينها.

**ما لا يُقاس هنا عمداً**: `padding-right`/`padding-left` في `.search-wrap
input[type="search"]` — زوجٌ مبنيٌّ على `html[dir="rtl"]` صريحاً، عُدَّ
استثناءً مقصوداً في تدقيق 2026-09-11 ولم يُرحَّل معه، فلا يُطابقه نمطُ
هذا الحارس أصلاً (`padding-` بادئةٌ تُستثنى). و`border-left`/`border-right`
فئةٌ منفصلة (حدودٌ لا تموضع) لم تدخل نطاقَ P1-3.
"""

import pathlib
import re

CSS_PATH = pathlib.Path("static/css/custom.css")

#: يطابق `left:`/`right:` بادئتيهما غير مسبوقتين بشرطةٍ (فلا يلتقط
#: `padding-right`/`border-left` وأخواتهما) ولا بحرفٍ آخر يجعلهما جزءاً
#: من اسمٍ أطول.
PHYSICAL_INSET = re.compile(r"(?<![-\w])(left|right)\s*:\s*[^;]+;")


def test_no_physical_left_or_right_in_positioning():
    css = CSS_PATH.read_text(encoding="utf-8")
    offenders = PHYSICAL_INSET.findall(css)
    matches = PHYSICAL_INSET.finditer(css)
    lines = []
    for m in matches:
        line_no = css.count("\n", 0, m.start()) + 1
        lines.append(f"  سطر {line_no}: {m.group(0)}")
    assert not offenders, (
        f"{len(offenders)} خاصيّةَ تموضعٍ فيزيائيّة (left/right) بدل "
        "inset-inline-start/end:\n" + "\n".join(lines[:25])
    )
