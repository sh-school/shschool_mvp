"""[SECURITY] بوّابةُ الوحدة تسع كلَّ من تسمّيه حرّاسُ واجهاتها — في الوحدات كلِّها.

`tests/test_quality_gate_matches_permissions.py` يحرس هذا في `/quality/` وحدَها،
وقد كُتب لأنّ الخللَ وقع فيها فعلاً. وهذا الملفُّ يعمّم الحراسةَ على الوحدات
المسجَّلة جميعاً، ويولّد الحالاتِ من السجلّ لا من قائمةٍ مكتوبةٍ باليد — فوحدةٌ
تُسجَّل غداً تُحرَس بلا تعديل سطرٍ هنا.

**العيبُ المحروس:** الميدلوير يسبق الديكوريتور. فدورٌ يسمح له حارسُ الواجهة
ويحجبه حارسُ المسار **يُردّ قبل أن تُقرأ صلاحيّتُه** — ٤٠٣ بلا سببٍ ظاهر. وقد
قِسناه في خمس وحداتٍ قبل هذا الملفّ: النائبُ الأكاديميُّ محجوبٌ عن المكتبة
وسجلّ الخرق، وأخصائيّا النطق والعلاج الوظائفيّ ومساعدا المعلّم عن الجودة،
ومنسّقُ الأنشطة عن التقييمات والكنترول.

**والوراثةُ جزءٌ من الحساب:** `role_required` توسّع المجموعةَ بـ`expand_roles`،
فمن يرث دوراً مأذوناً مأذونٌ في الواجهة — ويجب أن تسعه بوّابةُ الوحدة.
"""

import pytest
from django.urls import get_resolver

from core.module_registry import get_protected_paths

#: مساراتٌ مسجَّلةٌ لا تقابلها نقطةُ نهايةٍ واحدة — حارسٌ ميّتٌ لا يُفحص شيئاً.
#:
#: الثلاثةُ موثَّقةٌ في `docs/rbac_role_authority_study_2026-09.md` §٠٩: المساراتُ
#: الحقيقيّةُ `/teacher/` و`/import/`، و`schedule` و`attendance` وحدتان مسجَّلتان
#: ومسارُهما في الحقيقة واحد — فتصحيحُه قرارُ بنيةٍ (قسمُ المسارات أم حارسٌ
#: واحدٌ باتّحاد الأدوار) معلَّقٌ في البند ت٢ من الدراسة.
#:
#: ولا يُضاف إلى هذه المجموعة مسارٌ جديدٌ إلّا بقرارٍ مكتوبٍ مثلِه: هي إقرارٌ
#: بدَينٍ معروفٍ لا بابٌ لقبول أمثاله.
KNOWN_DEAD_PREFIXES = {
    "/operations/schedule/",
    "/operations/",
    "/staging/",
}


def _endpoints():
    """كلُّ نقاط النهاية بمسارها الكامل — بلا تعبيراتٍ نمطيّة."""

    def walk(patterns, prefix=""):
        for p in patterns:
            if hasattr(p, "url_patterns"):
                yield from walk(p.url_patterns, prefix + str(p.pattern))
            else:
                yield "/" + prefix + str(p.pattern), p.callback

    return list(walk(get_resolver().url_patterns))


def _guards_by_module():
    """لكلّ بادئةٍ مسجَّلة: أدوارُها في السجلّ، وأدوارُ حرّاس واجهاتها.

    والإسنادُ **بأطول بادئةٍ مطابقة** كما يفعل الميدلوير: نقطةٌ تحت
    `/quality/evaluations/` يحرسها حارسُها لا حارسُ `/quality/`.
    """
    modules = {prefix: set(roles) for prefix, roles in get_protected_paths().items()}
    by_longest = sorted(modules, key=len, reverse=True)
    guards = {prefix: set() for prefix in modules}
    counts = dict.fromkeys(modules, 0)

    for url, callback in _endpoints():
        for prefix in by_longest:
            if url.startswith(prefix):
                counts[prefix] += 1
                guards[prefix] |= set(getattr(callback, "_required_roles", ()) or ())
                break

    return modules, guards, counts


MODULES, GUARDS, COUNTS = _guards_by_module()


@pytest.mark.parametrize("prefix", sorted(MODULES))
def test_the_module_gate_admits_everyone_its_views_admit(prefix):
    """لا دورَ يسمح له حارسُ الواجهة ويردّه حارسُ المسار."""
    blocked = GUARDS[prefix] - MODULES[prefix]
    assert not blocked, (
        f"«{prefix}»: {', '.join(sorted(blocked))} — "
        "مأذونٌ في الواجهة ومحجوبٌ عن الوحدة، فيُردّ قبل أن تُقرأ صلاحيّتُه"
    )


@pytest.mark.parametrize("prefix", sorted(MODULES))
def test_every_registered_prefix_has_endpoints(prefix):
    """حارسٌ على مسارٍ لا وجودَ له لا يحرس شيئاً — ولا يُعرف أنّه لا يحرس."""
    if prefix in KNOWN_DEAD_PREFIXES:
        pytest.xfail("دَينٌ معروفٌ — قرارُ مسارات `/teacher/` معلَّق (الدراسة §٠٩ وت٢)")
    assert COUNTS[prefix], f"«{prefix}» مسجَّلٌ ولا تبدأ به نقطةُ نهايةٍ واحدة"


def test_no_module_opens_its_gate_to_beneficiaries_by_accident():
    """الطالبُ ووليُّ الأمر يدخلان ما يُقصد لهما، لا ما نسيه أحدٌ مفتوحاً."""
    #: والجدولُ منها: الطالبُ يرى جدولَه ووليُّ الأمر جدولَ ابنه — `SCHEDULE_VIEW`
    #: تسمّيهما صراحةً، وقائمةُ الوحدة الجانبيّةُ تعرضه لهما. ومثلُه الحضورُ:
    #: `ATTENDANCE_VIEW_CHILD` لوليّ الأمر، والطالبُ يرى غيابَه هو.
    intended = {
        "/parents/",  # بوّابةُ وليّ الأمر
        "/operations/schedule/",  # الطالبُ يرى جدولَه ووليُّ الأمر جدولَ ابنه
        "/operations/",  # `ATTENDANCE_VIEW_CHILD` — والطالبُ يرى غيابَه هو
        "/library/",  # `LIBRARY_VIEW` تسمّي الطالبَ: يتصفّح الكتب
    }
    for prefix, roles in MODULES.items():
        if prefix in intended:
            continue
        leaked = roles & {"student", "parent"}
        assert not leaked, f"«{prefix}» مفتوحٌ لـ{', '.join(sorted(leaked))} بلا قصد"


@pytest.mark.parametrize("prefix", sorted(MODULES))
def test_the_sidebar_never_promises_what_the_gate_denies(prefix):
    """رابطٌ في القائمة تردُّه البوّابةُ وعدٌ كاذب — والمستخدمُ يقرؤه ٤٠٣ بلا سبب.

    وقد وُجد في أربع وحدات: التقييماتُ والسلوكُ يعرضان لوليّ الأمر والطالب،
    والعيادةُ والنقلُ لوليّ الأمر — وبوّاباتُها الأربعُ تردُّهم. وبابُهم في
    الحقيقة `/parents/`، وواجهاتُ تلك الوحدات كلُّها للكادر.
    """
    from core.module_registry import get_all_modules

    module = next(m for m in get_all_modules().values() if m.url_prefix == prefix)
    promised = set(module.sidebar_roles) - set(module.allowed_roles)
    assert not promised, (
        f"«{prefix}»: {', '.join(sorted(promised))} — " "تَعِدهم القائمةُ وتردُّهم البوّابة"
    )


def test_the_registry_is_not_empty():
    """حارسٌ للحارس: لو فرغ السجلُّ لمرّت الاختباراتُ كلُّها بلا فحص."""
    assert len(MODULES) >= 15, f"السجلُّ فيه {len(MODULES)} وحدةً فقط — أفشل التحميل؟"
