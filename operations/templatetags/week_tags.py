import html
from typing import Any

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
def open_if_single(start_open: object, n: object) -> bool:
    """`{{ start_open|open_if_single:n }}` — تفتح بطاقةً فرعيّةً (معلّمٌ تحت قسم، شعبةٌ تحت جناح) حين اختِيرت مجموعتُها
    بعينها من القائمة (`start_open`) **وكانت وحيدةً فيها** (`n<=1`، كمعلّمٍ اختِير بذاته فصار قسمُه مجموعةً من واحد).
    مجموعةٌ من عدّةٍ (قسمٌ بعشرة معلّمين، جناحٌ بخمس شُعب) تبقى فروعُها مطويّةً افتراضاً وإن فُتح غلافُها (قرارُ المالك 2026-09-27)
    — يتصفّح المستخدمُ القائمةَ مطويّةً ويفتح ما يريد بعينه، لا شاشةً طويلةً بعشرة جداولَ كاملة."""
    try:
        return bool(start_open) and int(str(n)) <= 1
    except (TypeError, ValueError):
        return False


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


@register.filter
def css_string(text: object) -> SafeString:
    """نصٌّ يُوضع داخل سلسلة CSS بين علامتَي اقتباس (`content: "…"` في هامش الصفحة) دون أن يكسرها ولا يخرج من وسم `<style>`.

    الرؤيةُ (`school.vision`) حقلٌ تحرّره الإدارةُ — فتُهرَّب الشرطةُ المائلةُ والاقتباسُ وسطرُ الفصل وعلاماتُ `<` و`>` و`&`
    بصيغة CSS (`\3C `…)، فلا يُغلق النصُّ سلسلتَه ولا وسمَ `<style>`. القالبُ يلفّ به كتلةً بـ`{% filter css_string %}`.
    """
    # المكوّنُ يُخرج الرؤيةَ مهرَّبةً بالـHTML (`&quot;`، `&amp;`)؛ تُفكّ هنا ثمّ تُهرَّب من جديدٍ بصيغة CSS فلا يبقى كيانٌ ظاهراً ولا حرفٌ خطير.
    out = html.unescape(str(text or ""))
    for raw, escaped in (
        ("\\", "\\\\"),
        ('"', '\\"'),
        ("\r", " "),
        ("\n", "\\A "),
        ("<", "\\3C "),
        (">", "\\3E "),
        ("&", "\\26 "),
    ):
        out = out.replace(raw, escaped)
    return mark_safe(out)


#: عرضُ حرفٍ عريضٍ من Tajawal بخطّ 7.9pt غليظاً ≈ 1.55مم (مقيسٌ: «عبدالباسط الجاسم» 16 حرفاً يسعها 24.8مم)، ومنه هامشُ أمانٍ.
_NAME_MM_PER_CHAR = 1.7
_NAME_MM_PAD = 1.6
_NAME_MM_MIN = 26.0
_NAME_MM_MAX = 36.0


@register.simple_tag
def name_column_mm(rows: Any) -> str:
    """عرضُ عمود الاسم في ورقة A3 (ملم) من أطول اسمِ عرضٍ فيها — فلا يُقصّ اسمٌ (بلاغ المالك 2026-09-27: «عبدالباسط الجا»).

    كان ثابتاً 23.7 فقُصّ ما فوق 15 حرفاً؛ والاسمُ من مقطعين طولُه يتغيّر مع المعلّمين، فالعمودُ يتبع أطولَهم (له أرضيّةٌ وسقف)،
    والخلايا الخمسُ والثلاثون تتقاسم الباقي. نصٌّ لا رقمٌ: كي لا تُترجم الفاصلةُ العشريّةُ بلغة العرض.
    """
    longest = max(
        (
            len(str(getattr(row, "get", lambda *_: "")("display_name", "") or ""))
            for row in rows or []
        ),
        default=0,
    )
    width = min(_NAME_MM_MAX, max(_NAME_MM_MIN, _NAME_MM_PER_CHAR * longest + _NAME_MM_PAD))
    return f"{width:.1f}"
