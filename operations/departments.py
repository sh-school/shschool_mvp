"""operations/departments.py — تقسيم المعلّمين على الأقسام الأكاديمية.

القسمُ هنا **مشتقٌّ من نصاب المعلّم الفعليّ**، لا مكتوبٌ في حقلٍ يُملأ يدوياً:
جدولُ `core.Department` قائمٌ في النظام وفارغٌ في هذه المدرسة، و`Membership.
department_obj` غير مضبوطٍ لأحد — فاشتقاقُ القسم من الحصص هو الوحيد الذي
يُعطي إجابةً اليوم، وهو أصدقُ من حقلٍ يُملأ مرّةً ثم يشيخ: من دُرِّس نصابُه
كيمياءَ فهو في قسم الكيمياء وإن كُتب في ملفّه غير ذلك.

ومتى ملأت المدرسة جدول الأقسام وربطت المعلّمين به، صار هو المصدر ووجب أن
يتقدّم على هذا الاشتقاق.

القرارُ في التجميع للمدرسة لا للشيفرة (قرارٌ معتمدٌ من الإدارة):
  • الدراسات الاجتماعية والتاريخ والجغرافيا — قسمٌ واحد.
  • التكنولوجيا وتكنولوجيا المعلومات وعلوم الحاسب — قسمٌ واحد.
  • وإدارةُ الأعمال قسمٌ مستقلٌّ برجلٍ واحد (قرارُ الإدارة، 2026-09-01): مادّةُ
    تجارةٍ لا مادّةُ حاسب، ومعلّمُها لا يُدرّس شيئاً من موادّ ذلك القسم.
  • العلومُ تنقسم بالمرحلة: إعداديٌّ قسم، وثانويٌّ قسمٌ يضمّ العلوم العامة
    والأحياء. والكيمياءُ والفيزياء قسمان مستقلّان.
"""

from collections import Counter

#: الأقسام مرتّبةً كما تُقرأ في ورقة الجدول العام: العلومُ بعد اللغات،
#: والمواد التطبيقية في الذيل. والترتيبُ هنا هو ترتيبُ السطور في الورقة.
#: (الرمز، الاسم)
DEPARTMENTS: list[tuple[str, str]] = [
    ("sharia", "الشرعية"),
    ("arabic", "اللغة العربية"),
    ("math", "الرياضيات"),
    ("english", "اللغة الإنجليزية"),
    ("science_prep", "العلوم — إعدادي"),
    ("science_sec", "العلوم — ثانوي"),
    ("chemistry", "الكيمياء"),
    ("physics", "الفيزياء"),
    ("social", "الاجتماعيات"),
    ("tech", "التكنولوجيا وعلوم الحاسب"),
    ("business", "إدارة الأعمال"),
    ("pe", "التربية الرياضية"),
    ("arts", "الفنون البصرية"),
    ("life_skills", "المهارات الحياتية والمهنية"),
    ("other", "غير محدَّد"),
]

DEPARTMENT_NAMES: dict[str, str] = dict(DEPARTMENTS)
DEPARTMENT_ORDER: dict[str, int] = {code: i for i, (code, _) in enumerate(DEPARTMENTS)}

#: القسمُ الذي يُنسب إليه من لم تُعرف مادّته — ولا يسقط من الورقة.
FALLBACK = "other"

#: المادّة → القسم. والاسمُ هو المفتاح لأنّ `Subject.code` فارغٌ في أكثر
#: الموادّ الأساسية في هذه المدرسة، فالاسمُ وحده ما يُعوَّل عليه.
SUBJECT_DEPARTMENT: dict[str, str] = {
    "التربية الإسلامية": "sharia",
    "اللغة العربية": "arabic",
    "الرياضيات": "math",
    "اللغة الإنجليزية": "english",
    "العلوم العامة": "science_sec",
    "الأحياء": "science_sec",
    "الكيمياء": "chemistry",
    "الفيزياء": "physics",
    "الدراسات الاجتماعية": "social",
    "التاريخ": "social",
    "الجغرافيا": "social",
    "التكنولوجيا": "tech",
    "تكنولوجيا المعلومات": "tech",
    "علوم الحاسب": "tech",
    "إدارة الأعمال": "business",
    "التربية البدنية": "pe",
    "الفنون البصرية": "arts",
    "المهارات الحياتية والمهنية": "life_skills",
}

#: «العلوم» مادّةٌ واحدةٌ باسمها، وقسمان بالمرحلة: معلّمُ علوم السابع ليس
#: من قسم معلّم علوم الحادي عشر، وإن حملت حصصُهما اسم المادّة نفسه.
SUBJECT_DEPARTMENT_BY_LEVEL: dict[str, dict[str, str]] = {
    "العلوم": {"prep": "science_prep", "sec": "science_sec"},
}

#: موادُّ تُسنَد تكميلاً للنصاب لا تخصّصاً: ثمانيةُ معلّمين يُدرّسون «المهارات
#: الحياتية والمهنية» حصّتين حصّتين، وكلُّهم أهلُ تربيةٍ رياضيةٍ أو تاريخٍ أو
#: إدارة أعمال. فلو حُسبت كغيرها لسحبت بعضهم إلى قسمٍ لا ينتمون إليه.
#:
#: وهي مرجوحةٌ لا مُلغاة: من كان نصابُه كلُّه منها فهو من أهلها — ومعلّمان
#: في المدرسة كذلك. فتُحسب حين لا يُوجد سواها، ولا تُحسب حين يوجد.
FILL_SUBJECTS: frozenset[str] = frozenset({"المهارات الحياتية والمهنية"})

#: عند تساوي النصابين يفوز التخصّصُ على العموم: من له ستُّ حصص كيمياءَ وستٌّ
#: علومَ هو معلّمُ كيمياء يسدّ نقصاً في العلوم، لا العكس.
_TIE_PRIORITY: dict[str, int] = {"science_prep": 0, "science_sec": 0}

#: صفوفُ المرحلة الإعدادية. والعاشرُ ثانويٌّ وإن كان بلا مسار.
_PREP_GRADES = frozenset({"G7", "G8", "G9"})


def level_of(grade: str) -> str:
    """«prep» للسابع والثامن والتاسع، و«sec» لما فوقها."""
    return "prep" if grade in _PREP_GRADES else "sec"


def is_fill_subject(subject_name: str) -> bool:
    """أهي مادّةٌ تكميليّةٌ لا تُرجَّح إلّا حين لا سواها؟"""
    return (subject_name or "").strip() in FILL_SUBJECTS


def department_of_subject(subject_name: str, grade: str) -> str | None:
    """قسمُ المادّة الواحدة — و`None` لمادّةٍ لا تُعرف."""
    name = (subject_name or "").strip()
    if not name:
        return None
    by_level = SUBJECT_DEPARTMENT_BY_LEVEL.get(name)
    if by_level:
        return by_level[level_of(grade)]
    return SUBJECT_DEPARTMENT.get(name)


def resolve_department(weights: Counter) -> str:
    """القسمُ الغالب على النصاب — {رمز: عدد حصص} → رمز.

    الترجيح: الأكثرُ حصصاً، فإن تساويا فالتخصّصُ على العموم، فإن بقي التساوي
    فترتيبُ الورقة — كي لا يتبدّل موضعُ المعلّم بين طباعتين.
    """
    if not weights:
        return FALLBACK
    return max(
        weights,
        key=lambda code: (
            weights[code],
            _TIE_PRIORITY.get(code, 1),
            -DEPARTMENT_ORDER.get(code, len(DEPARTMENTS)),
        ),
    )


def resolve_from_lessons(lessons) -> str:
    """قسمُ معلّمٍ من حصصه — `(اسم المادّة، الصفّ، الوزن)` لكلّ حصّةٍ أو إسناد.

    وهنا تُطبَّق قاعدةُ المادّة التكميليّة: تُجمع في دلوٍ على حدة، ولا تُرجَّح
    إلّا حين لا سواها. فمعلّمُ تربيةٍ رياضيّةٍ له حصّتا «مهاراتٍ حياتيّة» يبقى
    في قسمه، ومن كان نصابُه كلُّه منها فهو من أهلها.
    """
    weights, fill = Counter(), Counter()
    for name, grade, weight in lessons:
        code = department_of_subject(name, grade)
        if not code:
            continue
        bucket = fill if is_fill_subject(name) else weights
        bucket[code] += weight
    return resolve_department(weights or fill)


def department_info(code: str) -> dict:
    """رمزُ القسم واسمُه وترتيبه — كما يقرؤها القالب."""
    return {
        "code": code,
        "name": DEPARTMENT_NAMES.get(code, DEPARTMENT_NAMES[FALLBACK]),
        "order": DEPARTMENT_ORDER.get(code, len(DEPARTMENTS)),
    }
