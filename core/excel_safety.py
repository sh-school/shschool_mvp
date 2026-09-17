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
