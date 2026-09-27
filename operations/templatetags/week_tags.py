from django import template
from django.utils.html import format_html_join
from django.utils.safestring import SafeString, mark_safe

from core.dept_colors import dept_key, wing_key
from operations.schedule_paper import cell_kind

register = template.Library()

#: `{{ cell|cell_kind }}` — علامةُ خانةٍ في الجدول العامّ (`swap` أو `cover` أو `comp` أو فارغ).
#: هنا في `operations/templatetags` لا `core/templatetags`: الدالّةُ من `operations.schedule_paper`،
#: واستيرادٌ نازلٌ من core إلى operations يخالف حارس الطبقات (انظر `exemption_tags`).
register.filter("cell_kind", cell_kind)

#: `{{ row.department.code|dept_key }}` — مفتاحُ لون القسم المركزيّ (`dept-{مفتاح}` في 20-components) لجدول الشاشة العامّ؛
#: الورقةُ تبقى بصنفها `dept-{كود}` لأنّ ألوانَها في قالبها (انظر `pdf/matrix_table.html`).
register.filter("dept_key", dept_key)

#: `{{ wing.order|wing_key }}` — مفتاحُ لون الجناح المركزيّ (`dept-{مفتاح}` نفسُه في 20-components، لوحةُ الأقسام) لصفحة جداول الشُّعب.
register.filter("wing_key", wing_key)


@register.filter
def stack_words(text: object) -> SafeString:
    """اسمُ القسم كلماتٍ متراصّةً بعضُها تحت بعض (قرارُ المالك 2026-09-26): «التربية / الإسلامية».

    حرفُ العطف «و» المفصولُ يلتصق بما بعده (ملتصقاً أصلاً في «وعلوم»)، والشرطةُ «—» في «العلوم — إعدادي» تُسقَط. والفاصلُ `<br>`
    لا صنفُ CSS — فلا يُضاف إلى أنماطٍ عليها سقفُ حجمٍ (ميزانيّةُ CSS)، ويصلح للورقة والشاشة بلا قاعدةٍ ثانية. كلُّ كلمةٍ تُهرَّب.
    """
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
    return format_html_join(mark_safe("<br>"), "{}", ((word,) for word in words))
