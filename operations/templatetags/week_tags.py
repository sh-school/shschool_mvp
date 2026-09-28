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


#: خطُّ ورقة A3 للجدول العامّ (بالنقطة) — **مصدرٌ واحدٌ** للقالب والاختبارات. ت1 = 7.9 (قرارُ المالك 2026-09-26)؛ ورُفع إلى 8.1
#: بما كسبه المتنُ من ارتفاعٍ بعد التصاق التذييل بأسفل الصفحة (قرارُ المالك 2026-09-27، مقيسٌ على PDF فعليّ: فراغٌ 8.6مم عند
#: 7.9pt هبط إلى 3.3مم عند 8.1pt). كلُّ مقاييس الورقة تتبعه (`a3_metrics`)، والقالبُ بلا رقمٍ مكتوب.
A3_SHEET_PT = 8.1
_BASE_PT = 7.9  # الخطُّ الذي قيست عليه الثوابتُ (ت1)

#: فراغُ المتن فوق التذييل (ملم) عند خطّ القياس 7.9pt بلا ملاحظات، وميلُ الفراغ مع الخطّ (مقيسان على PDF فعليّ: 7.9pt ← 8.64مم،
#: و8.1pt ← 3.26مم)، وارتفاعُ سطرِ ملاحظةٍ أسبوعيّةٍ (9pt + هامش). منها يُحسب أنّ الأسبوعَ ذا الملاحظات يُصغَّر خطُّه قليلاً فتبقى
#: الورقةُ واحدة (قياسُ المايسترو 2026-09-27) — أسبوعُ الخطّة وأغلبُ الأسابيع بلا ملاحظاتٍ فالخطُّ كاملاً.
_GAP_AT_BASE_MM = 8.64
_TABLE_FOLLOWING_FONT_MM = 212.0
_NOTE_LINE_MM = 3.6
_SAFETY_MM = 1.0


@register.simple_tag
def a3_metrics(note_lines: Any = 0) -> dict[str, Any]:
    """مقاييسُ ورقة A3 من `A3_SHEET_PT`: الخطُّ والحشوُ العلويُّ وارتفاعُ السطر (لتوسيط الرمز) وعرضا القسم والنصاب.

    مقيسةٌ عند 7.9pt (ت1) وتتناسب مع الخطّ: سطرٌ 1.05×الخطّ، وإزاحةُ التوسيط 0.42مم (حشوٌ علويٌّ ضعفُها ونقصٌ مثلُه من السطر فيبقى ارتفاعُ الصفّ
    1.05×الخطّ)، والقسمُ 16.4مم، والنصابُ 11مم. النصُّ لا رقمٌ في القوالب: فاصلةٌ عشريّةٌ لا تُترجم.

    **أسبوعٌ بملاحظات** (`nav.notes`: أيّامٌ مغلقةٌ/من الخطّة/حصصٌ بلا رقم — حتّى ثلاثةُ أسطر): كلُّ سطرٍ 3.6مم يأكل من فراغ المتن، فيُصغَّر الخطُّ بقدر ما يلزم
    (مع هامشِ أمانٍ 1مم) كي تبقى الورقةُ واحدةً أيّاً كان الأسبوع — لا خطّاً واحداً يكسر الصفحةَ في أسابيع الإغلاق.
    """
    try:
        lines = max(0, int(note_lines))
    except (TypeError, ValueError):
        lines = 0
    font = A3_SHEET_PT
    gap = _GAP_AT_BASE_MM - _TABLE_FOLLOWING_FONT_MM * (A3_SHEET_PT / _BASE_PT - 1)
    need = lines * _NOTE_LINE_MM - gap + _SAFETY_MM
    if need > 0:
        font = round(A3_SHEET_PT * (1 - need / _TABLE_FOLLOWING_FONT_MM), 2)
    k = font / _BASE_PT
    line = 1.05 * font * 0.3528
    pad = 0.84 * k
    return {
        "pt": font,
        "k": k,
        "font": f"{font:g}pt",
        "pad": f"{pad:.2f}mm",
        "lh": f"{line - pad:.2f}mm",
        "dept_w": f"{16.4 * k:.1f}mm",
        "total_w": f"{11 * k:.1f}mm",
    }


#: عرضُ حرفٍ عريضٍ من Tajawal بخطّ 7.9pt غليظاً ≈ 1.55مم (مقيسٌ: «عبدالباسط الجاسم» 16 حرفاً يسعها 24.8مم)، ومنه هامشُ أمانٍ.
_NAME_MM_PER_CHAR = 1.7
_NAME_MM_PAD = 1.6
_NAME_MM_MIN = 26.0
_NAME_MM_MAX = 36.0


@register.simple_tag
def matrix_stats_line(totals: dict | None, teacher_count: Any) -> str:
    """نصُّ إحصاء الجدول العامّ («المعلّمون: 72 · الشُّعب: 25 · الحصص: 869 من 869 مخطَّطة (منها 6 متوازية)») — بندُ `stats` في تذييل
    الإطار المركزيّ (`core/templatetags/print_frame.py::print_frame_footer`، طلبُ ترحيل ورقة A3 2026-09-27). نصٌّ حرٌّ جاهزٌ يمرّره
    القالبُ كما هو، لا يُركِّبه الإطارُ العامّ (تركيبتُه تخصّ هذه الوثيقةَ وحدَها).
    """
    parts = [f"المعلّمون: {teacher_count}"]
    if totals:
        parts.append(f"الشُّعب: {totals.get('sections')}")
        line = (
            f"الحصص: {totals.get('total')} من {totals.get('planned')} مخطَّطة"
            f" (منها {totals.get('parallel')} متوازية)"
        )
        if totals.get("missing"):
            line += f" — ناقص {totals.get('missing')}"
        parts.append(line)
    return " · ".join(parts)


@register.simple_tag
def schedule_subtitle(year: object, source: object, week_range: object) -> str:
    """سطرُ السنة تحت عنوان الجدول العامّ («العام الدراسي ⁦2026-2027⁩ — الأسبوع 27/9 – 1/10») — بمعامل `subtitle` في
    `print_frame_header`. عازلا الاتّجاه (LRI/PDI حقيقيّان لا كيانَي HTML) حول رقم العام: نصٌّ لاتينيُّ الأرقام وسط عربيٍّ."""
    text = f"العام الدراسي ⁦{year}⁩"
    if source == "actual" and week_range:
        text += f" — الأسبوع {week_range}"
    return text


@register.simple_tag
def name_column_mm(rows: Any, scale: Any = 1.0) -> str:
    """عرضُ عمود الاسم في ورقة A3 (ملم) من أطول اسمِ عرضٍ فيها — فلا يُقصّ اسمٌ (بلاغ المالك 2026-09-27: «عبدالباسط الجا»).

    كان ثابتاً 23.7 فقُصّ ما فوق 15 حرفاً؛ والاسمُ من مقطعين طولُه يتغيّر مع المعلّمين، فالعمودُ يتبع أطولَهم (له أرضيّةٌ وسقف)،
    والخلايا الخمسُ والثلاثون تتقاسم الباقي. نصٌّ لا رقمٌ: كي لا تُترجم الفاصلةُ العشريّةُ بلغة العرض.

    `scale` نسبةُ خطّ الورقة الفعليّ إلى خطّ القياس (`a3_metrics()["k"]`) — الحرفُ يعرض بقدرها فلا يضيق العمودُ عن الاسم
    حين يُصغَّر الخطُّ لأسبوعٍ بملاحظات.
    """
    longest = max(
        (
            len(str(getattr(row, "get", lambda *_: "")("display_name", "") or ""))
            for row in rows or []
        ),
        default=0,
    )
    k = float(scale or 1.0)
    width = min(
        _NAME_MM_MAX * k,
        max(_NAME_MM_MIN * k, _NAME_MM_PER_CHAR * k * longest + _NAME_MM_PAD),
    )
    return f"{width:.1f}"
