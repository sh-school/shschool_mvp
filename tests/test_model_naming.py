"""[UX] لا نموذجان يحملان الاسم نفسه في لوحة الإدارة.

«الفصل» في العربية المدرسية تحمل معنيين: المدّة الزمنية (الأول/الثاني)
والمجموعة الصفّية (١٠/١). فحين أُضيف `Semester` أخذ «الفصول الدراسية» — وكان
`ClassGroup` يحملها منذ سنة.

والنتيجة سطران متطابقان في اللوحة يقودان إلى شيئين لا صلة بينهما، ولا شيء
يكشف ذلك: كلاهما صحيحٌ في موضعه، والخطأ في اجتماعهما.

ومصطلح الوزارة يحسم القسمة:

    الفصل الدراسي   المدّة الزمنية        → Semester
    الصف            المرحلة (٧ … ١٢)
    الشعبة          التقسيم داخل الصف     → ClassGroup (grade + section)

وحقل `ClassGroup.section` كان يُسمّى «الشعبة» منذ البداية — فالتسمية الجديدة
تُصحّح تناقضاً قائماً لا تخترع اصطلاحاً.
"""

import collections

from django.apps import apps


def _labels():
    """كل اسمٍ معروض ومَن يحمله."""
    holders = collections.defaultdict(list)
    for model in apps.get_models():
        holders[str(model._meta.verbose_name_plural)].append(
            f"{model._meta.app_label}.{model.__name__}"
        )
    return holders


def test_no_two_models_share_a_display_name():
    """اسمٌ مكرّر يجعل اللوحة تعرض سطرين متطابقين لشيئين مختلفين."""
    clashes = {label: who for label, who in _labels().items() if len(who) > 1}

    assert not clashes, f"أسماءٌ متصادمة: {clashes}"


def test_the_semester_owns_the_ministry_term_for_a_term():
    """«الفصل الدراسي» يُطبع في الشهادات والاستمارات بمعناه الزمنيّ.

    فلو حمله نموذجٌ آخر لاختلف نصّ الواجهة عن نصّ الوثيقة الرسمية.
    """
    from core.models import Semester

    assert str(Semester._meta.verbose_name) == "فصل دراسي"


def test_the_class_group_is_named_after_its_own_field():
    """`ClassGroup` يحمل `grade` و`section` — والحقل يُسمّى «الشعبة» منذ البداية."""
    from core.models import ClassGroup

    assert str(ClassGroup._meta.verbose_name) == "شعبة دراسية"
    assert str(ClassGroup._meta.get_field("section").verbose_name) == "الشعبة"
