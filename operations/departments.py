"""operations/departments.py — تقسيم المعلّمين على الأقسام الأكاديمية.

**المصدرُ سجلُّ المدرسة** (`core.Department` + `Membership.department_obj`):
ثلاثةَ عشرَ قسماً، لكلٍّ رئيسٌ وأعضاء. وقرارُ الإدارة 2026-09-06: القسمُ ما
يقوله السجلُّ **بغضّ النظر عمّا يدرّسه المعلّم** — فالورقةُ رسميّةٌ تُوزَّع على
المنسّقين، ورجلٌ ينتقل من قسمٍ إلى قسمٍ لأنّ جدوله تغيّر ورقةٌ لا تُصدَّق.

وكان الاشتقاقُ من الموادّ هو المصدرَ الوحيدَ حين كُتب هذا الملفّ، إذ كان جدولُ
الأقسام فارغاً. فلمّا مُلئ صار احتياطاً لا أصلاً: `registered_departments`
أوّلاً، ثمّ `derived_department` لمن لا سجلَّ له فلا يسقط من الورق.

وما يلي وصفُ الاشتقاق الاحتياطيّ — والقرارُ في تجميعه للمدرسة لا للشيفرة:
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


def registered_departments(school) -> dict:
    """{معرّف العضو: قسمُه المسجَّل} — السجلُّ الإداريّ لا اشتقاقُ الموادّ.

    القرار (2026-09-06): القسمُ ما تقوله سجلّاتُ المدرسة **بغضّ النظر عمّا
    يدرّسه المعلّم**. فالاشتقاقُ من الموادّ يتبدّل كلّما تبدّل النصاب — ومعلّمٌ
    ينتقل من قسمٍ إلى قسمٍ لأنّ جدوله تغيّر ورقةٌ لا تُصدَّق. ويبقى الاشتقاقُ
    احتياطاً لمن لا قسمَ مسجّلاً له فلا يسقط من الورق.

    والترتيبُ من `Department.sort_order` كما رتّبته الإدارة.
    """
    from core.models import Membership

    rows = {}
    memberships = (
        Membership.objects.filter(school=school, is_active=True, department_obj__isnull=False)
        .select_related("department_obj", "department_obj__head")
        .order_by("department_obj__sort_order")
    )
    for membership in memberships:
        department = membership.department_obj
        rows[str(membership.user_id)] = {
            "code": department.code,
            "name": department.name,
            "order": department.sort_order,
            "head": department.head.full_name if department.head_id else "",
            "specialty": membership.specialty,
            "registered": True,
        }
    return rows


def derived_department(lessons) -> dict:
    """قسمٌ مشتقٌّ من الحصص — احتياطُ من لا سجلَّ له، ويأتي بعد المسجَّلين."""
    info = department_info(resolve_from_lessons(lessons))
    return {**info, "order": 1000 + info["order"], "head": "", "specialty": "", "registered": False}
