"""core/excel_safety.py — تحييدُ حقن الصيغ في خلايا Excel المصدَّرة.

CWE-1236 (Formula Injection / CSV Injection): خليّةٌ تبدأ بـ``=`` أو ``+`` أو
``-`` أو ``@`` يُنفّذها Excel كصيغةٍ عند فتح الملفّ — لا كنصّ. واسمُ طالبٍ أو
سببُ إجازةٍ أو ملاحظةٌ حرّة يكتبها مستخدمٌ يمكن أن تبدأ بأحد هذه الرموز، فيصدَّر
ما كتبه حرفيّاً ويُنفَّذ على جهاز من يفتح التقرير.

المعالجة: إسباقُ القيمة بعلامةِ اقتباسٍ (``'``) — يقرؤها Excel نصّاً حرفيّاً
لا صيغة، بلا تغيير ظاهرٍ لما يراه المستخدم عند العرض العاديّ.
"""

from typing import Any

_FORMULA_PREFIXES = ("=", "+", "-", "@")


def neutralize_formula_value(value: Any) -> Any:
    """يُسبق القيمةَ بـ``'`` إن كانت نصّاً يبدأ برمز صيغة — وإلّا يُعيدها كما هي.

    القيمُ غيرُ النصّيّة (أرقام، تواريخ، ``None``) تمرّ بلا تغيير: openpyxl
    لا يكتبها صيغةً أصلاً، والتحويلُ إلى نصٍّ هنا يُفسد فرزها وتنسيقها في الملفّ.
    """
    if not isinstance(value, str):
        return value
    stripped = value.lstrip()
    if stripped.startswith(_FORMULA_PREFIXES):
        return "'" + value
    return value


def safe_value(value: Any) -> Any:
    """يحيِّد قيمةً مفردة قبل أن تدخل خليّةً أو عنوانَ دمجٍ أو ترويسة.

    اسمٌ آخر لـ``neutralize_formula_value`` بمعنى «القيمةُ جاهزةٌ للكتابة»؛
    يُستعمل حيث لا ورقةَ في المتناول (قيمةٌ تُركَّب ثمّ تُمرَّر لمُنسِّق).
    """
    return neutralize_formula_value(value)


def safe_cell(ws: Any, row: int, column: int, value: Any = None) -> Any:
    """الكاتبُ المركزيّ لخليّة: ``ws.cell(row, column, value)`` بعد تحييد القيمة.

    النصُّ المبدوء برمز صيغة يُسبق بـ``'``؛ الأرقامُ والتواريخُ و``None`` و``bool``
    تمرّ كما هي فلا يتغيّر نوعُ الخليّة ولا فرزُها. وعند ``value=None`` لا تُكتب
    قيمةٌ (سلوكُ openpyxl نفسُه) فتصلح لقراءة الخليّة وتنسيقها.
    """
    return ws.cell(row=row, column=column, value=neutralize_formula_value(value))


def safe_set(cell: Any, value: Any) -> Any:
    """يُسند ``cell.value`` بعد التحييد (بديلُ ``cell.value = ...`` المباشر)."""
    cell.value = neutralize_formula_value(value)
    return cell


def safe_append(ws: Any, values: Any) -> None:
    """بديلُ ``ws.append(...)``: يحيِّد كلَّ قيمةٍ في الصفّ (قائمة/مجموعة/مُوَلِّد/قاموس)."""
    if isinstance(values, dict):
        ws.append({key: neutralize_formula_value(val) for key, val in values.items()})
    else:
        ws.append([neutralize_formula_value(val) for val in values])
