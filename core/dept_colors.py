"""لونُ القسم — كودُ القسم إلى مفتاح رمز `--dept-*`، كما يُلوّن الجدولَ العامّ المطبوع.

مصدرٌ واحدٌ لسؤال «أيُّ لونٍ لهذا القسم؟». الجدولُ المطبوعُ
(`templates/schedule/print_schedule.html`) يصبّ اللونَ على `tr.dept-{code}` بكودِ
القسم نفسِه، وهذا القاموسُ يقرأ منه الطرفَ الآخر: من أرادت شاشتُه لونَ القسم
كما في الجدول (الإسناد، وجدولُ الجدول العامّ على شاشة المنصّة عبر مرشّح `dept_key` في `week_tags`) نادى `dept_key(code)`
وأخذ صنفَ `dept-{key}` المركزيّ في `static/css/custom/20-components.css`، لا نسخةً ثانيةً من الجدول تنحرف عنه.

والرموزُ نفسُها (`--dept-*`) لها قيمةُ نهارٍ ولياليّةٌ في `custom/10-foundation.css` و`40-themes.css`،
فتتبع الوضعَ دون شيءٍ هنا.
"""

#: كودُ القسم (كما في `Department.code` والاشتقاق الاحتياطيّ) → مفتاحُ الرمز.
#: مطابقٌ لكتل `tr.dept-*` في ورقة الجدول: `science_prep` علومٌ، و`science_sec` أحياء.
DEPT_KEY_OF_CODE = {
    "sharia": "sharia",
    "islamic": "sharia",
    "arabic": "arabic",
    "math": "math",
    "english": "english",
    "science": "science",
    "science_prep": "science",
    "science_sec": "biology",
    "biology": "biology",
    "chemistry": "chemistry",
    "physics": "physics",
    "social": "social",
    "tech": "tech",
    "business": "business",
    "pe": "pe",
    "arts": "arts",
    "art": "arts",
    "life_skills": "life-skills",
    "life-skills": "life-skills",
}

#: قسمٌ لا يُعرف كودُه (أو بلا قسم) — رمادٌ محايد لا لونٌ يُخترع.
OTHER = "other"


def dept_key(code: object) -> str:
    """مفتاحُ لون هذا الكود — `other` لما لا يُعرف، فلا يسقط عرضٌ من كودٍ جديد."""
    return DEPT_KEY_OF_CODE.get(str(code or "").strip().lower(), OTHER)
