"""[TEMPLATES] وسوم جانغو لا تتعدّى سطراً — والمتعدّي منها يُطبع للمستخدم.

مُحلِّل جانغو نفسه:

    tag_re = re.compile(r"({%.*?%}|{{.*?}}|{#.*?#})")

بلا `re.DOTALL`. فالنقطة لا تُطابق سطراً جديداً، ووسمٌ موزّع على أسطر لا
يُعرَّف وسماً أصلاً — بل يمرّ نصّاً خاماً إلى الصفحة. ورآه المستخدم في
الإنتاج على صفحة التقارير:

    {% include "components/empty_state.html" with icon="list-checks"
       title="لا توجد فصول" ... %}

مطبوعاً كما هو مكان حالة الفراغ. وكان في المنصّة تسعةُ مواضع كهذه — خمسةُ
`include` وأربعةُ تعليقات — كلّها تظهر للمستخدم حرفاً بحرف.

وخبثُها أنها لا تُخفق: لا استثناء، ولا سطر في السجلّ، ولا فحصٌ يلتقطها.
الصفحة تُعاد بـ200 وفيها شيفرةُ قالبٍ معروضة.

والتعليق متعدّد الأسطر له بديلٌ صحيح — `{% comment %}` — وهو وسمُ كتلةٍ
يمتدّ على ما شاء من الأسطر.
"""

import pathlib
import re

#: مُحلِّل جانغو حرفياً — django/template/base.py
TAG_RE = re.compile(r"({%.*?%}|{{.*?}}|{#.*?#})")

OPENERS = ("{%", "{{", "{#")

ROOTS = (pathlib.Path("templates"),)


def _templates():
    for root in ROOTS:
        yield from sorted(root.rglob("*.html"))


def test_the_sweep_reaches_the_templates():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    assert len(list(_templates())) > 100


def test_no_tag_spans_more_than_one_line():
    """يُطرح كلّ وسمٍ سليم، فلا يبقى إلّا فاتحةٌ بلا إغلاقٍ في سطرها."""
    stranded = []
    for f in _templates():
        masked = TAG_RE.sub(lambda m: " " * len(m.group()), f.read_text(encoding="utf-8"))
        for i, line in enumerate(masked.splitlines(), 1):
            if any(o in line for o in OPENERS):
                stranded.append(f"{f.as_posix()}:{i}  {line.strip()[:60]}")

    assert not stranded, "وسومٌ تتعدّى سطرها فتُطبع نصّاً:\n" + "\n".join(stranded)


def test_the_block_comment_is_used_where_prose_needs_lines():
    """`{% comment %}` وسمُ كتلة — يمتدّ حيث لا يمتدّ `{# #}`."""
    users = [f for f in _templates() if "{% comment %}" in f.read_text(encoding="utf-8")]

    assert users, "لم يعد أحدٌ يستعمل وسم الكتلة — تحقّق قبل حذف هذا الحارس"


def test_django_still_lexes_line_by_line():
    """لو صار مُحلِّل جانغو يقبل تعدّد الأسطر لسقط سببُ هذا الحارس كلّه."""
    from django.template.base import tag_re

    assert not tag_re.flags & re.DOTALL
    assert tag_re.pattern == TAG_RE.pattern
