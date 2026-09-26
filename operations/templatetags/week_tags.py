from typing import Any

from django import template
from django.utils.html import format_html_join
from django.utils.safestring import SafeString, mark_safe

from core.dept_colors import dept_key
from operations.schedule_paper import cell_kind

register = template.Library()

#: `{{ cell|cell_kind }}` — علامةُ خانةٍ في الجدول العامّ (`swap` أو `cover` أو `comp` أو فارغ).
#: هنا في `operations/templatetags` لا `core/templatetags`: الدالّةُ من `operations.schedule_paper`،
#: واستيرادٌ نازلٌ من core إلى operations يخالف حارس الطبقات (انظر `exemption_tags`).
register.filter("cell_kind", cell_kind)

#: `{{ row.department.code|dept_key }}` — مفتاحُ لون القسم المركزيّ (`dept-{مفتاح}` في 20-components) لجدول الشاشة العامّ؛
#: الورقةُ تبقى بصنفها `dept-{كود}` لأنّ ألوانَها في قالبها (انظر `pdf/matrix_table.html`).
register.filter("dept_key", dept_key)


def dept_words(text: object) -> list[str]:
    """كلماتُ اسم القسم للتكديس: الشرطةُ «—» تُسقَط، وحرفُ العطف «و» المفصولُ يلتصق بما بعده (ملتصقاً أصلاً في «وعلوم»)."""
    words: list[str] = []
    pending = ""
    for word in str(text or "").replace("—", " ").split():
        if word == "و":
            pending = word
            continue
        words.append(pending + word)
        pending = ""
    if pending:
        words.append(pending)
    return words


@register.filter
def stack_words(text: object) -> SafeString:
    """اسمُ القسم كلماتٍ متراصّةً بعضُها تحت بعض (قرارُ المالك 2026-09-26): «التربية / الإسلامية».

    والفاصلُ `<br>` لا صنفُ CSS — فلا يُضاف إلى أنماطٍ عليها سقفُ حجمٍ (ميزانيّةُ CSS)، ويصلح للورقة والشاشة بلا قاعدةٍ ثانية.
    كلُّ كلمةٍ تُهرَّب.
    """
    return format_html_join(mark_safe("<br>"), "{}", ((word,) for word in dept_words(text)))


#: سطرُ الجدول العامّ المطبوع بمباعدة 1.05 (ت1، قرارُ المالك 2026-09-26)، والنقطةُ 0.3528 ملم.
_LINE_FACTOR = 1.05
_PT_MM = 0.3528


@register.simple_tag
def dept_row_height(name: object, rows: Any, font_pt: Any) -> str:
    """ارتفاعُ كلّ صفٍّ من قسمٍ ضيّق حين لا تسع صفوفُه كلماتِ اسمه مكدَّسةً؛ وفارغٌ إن اتّسعت (فلا حشو).

    كلُّ كلمةٍ سطرٌ بارتفاع `1.05 × الخطّ`؛ فقسمٌ بصفّين وثلاثِ كلماتٍ («المهارات الحياتية والمهنية») يرفع صفَّيه ليسع الأسطرَ الثلاثة
    (`(كلماتٌ × سطر + 0.3) ÷ صفوفٌ` ملم) بدل أن يتمدّد الجدولُ فوضى. يقرؤه وسمُ `--row-h` على السطر في ورقة الطباعة وحدَها.
    """
    try:
        count = int(rows)
        size = float(font_pt)
    except (TypeError, ValueError):
        return ""
    if count < 1 or size <= 0:
        return ""
    line = _LINE_FACTOR * size * _PT_MM
    need = len(dept_words(name)) * line + 0.3
    if count * (line + 0.15) >= need:
        return ""
    return f"{need / count:.2f}mm"
