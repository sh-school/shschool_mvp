"""[SECURITY] عضويّة لجنة الجودة موقوتةٌ بعامها في كل موضعٍ تُفحص فيه.

أصلحتُ في [#85] قائمةَ التصفّح وحدها. ثم مسحتُ النماذج التي تحمل
`academic_year` و`is_active` معاً، فوجدت خمسة مواضع أخرى تفحص العضوية بلا
عام — **اثنان منها تحكّمٌ في الوصول لا عرضٌ**:

    quality/views.py            _is_review_member          ← بوّابة
    quality/views.py            _get_reviewer_domain
    quality/views.py            ترشيح الإجراءات بمجال العضو
    quality/views_committee.py  بوّابة تُعيد 403           ← بوّابة
    quality/views_reports.py    خريطة مسؤولي المجالات

وأصرحُ دليلٍ على القصد أن اثنتين منها كانتا تستقبلان `year` **ولا تستعملانها**:

    def _is_review_member(user, school, year):   ← مُمرَّرة
        return QualityCommitteeMember.objects.filter(
            school=school, user=user, ..., is_active=True,   ← ولا تُستعمل
        ).exists()

معاملٌ ميّت يشهد أن كاتبه قصد التقييد بالعام ثم نسيه. ولا شيء في المنصّة
يُطفئ `is_active` عند دوران العام — فالصفّ يُنشأ لعامه ويبقى نشطاً أبداً.
"""

import ast
import pathlib

import pytest

MODEL = "QualityCommitteeMember"
SKIP = ("/.venv/", "/node_modules/", "/.claude/", "/.mypy_cache/", "/migrations/", "/tests/")


def _membership_queries():
    """كل ترشيحٍ على عضوية اللجنة، مع مفاتيحه."""
    for f in sorted(pathlib.Path(".").rglob("*.py")):
        if any(x in "/" + f.as_posix() for x in SKIP):
            continue
        src = f.read_text(encoding="utf-8", errors="ignore")
        if MODEL not in src:
            continue
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, ast.Call):
                continue
            fn = n.func
            if not (isinstance(fn, ast.Attribute) and fn.attr in ("filter", "exclude")):
                continue
            if MODEL not in ast.unparse(n):
                continue
            yield f"{f.as_posix()}:{n.lineno}", {k.arg or "" for k in n.keywords}


def test_the_sweep_finds_the_queries():
    """حارسٌ يمسح لا شيء يمرّ دائماً."""
    found = list(_membership_queries())

    assert len(found) >= 5, found


def test_every_membership_check_is_scoped_to_a_year():
    """عضويّةٌ بلا عام تُبقي مَن انقضت ولايته مصرَّحاً له.

    والاستثناء الوحيد ما يُرشّح بالعام في مكانٍ آخر من السلسلة — ولا وجود
    له هنا: كل نداءٍ يفحص عضويةً يفحصها كاملةً.
    """
    unscoped = [
        where
        for where, keys in _membership_queries()
        if "is_active" in keys and not any(k.startswith("academic_year") for k in keys)
    ]

    assert not unscoped, f"عضويّةٌ تُفحص بلا عام في: {unscoped}"


def test_no_helper_takes_a_year_it_never_uses():
    """المعامل الميّت هو ما دلّني على العطب — فلا يعود.

    `_is_review_member(user, school, year)` كانت تستقبله وتتجاهله. ودالّةٌ
    تَعِد بالتقييد ولا تفي أخطرُ من دالّةٍ لا تَعِد.
    """
    dead = []
    for f in sorted(pathlib.Path("quality").rglob("*.py")):
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="ignore"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if not isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            args = {a.arg for a in n.args.args + n.args.kwonlyargs}
            if "year" not in args:
                continue
            body = ast.unparse(ast.Module(body=n.body, type_ignores=[]))
            if "year" not in body:
                dead.append(f"{f.as_posix()}:{n.lineno} {n.name}")

    assert not dead, f"معامل `year` مُستقبَلٌ ولا يُستعمل في: {dead}"


# ── الأثر الحيّ ───────────────────────────────────────────────────────


@pytest.fixture
def calendar(db, school):
    from django.core.management import call_command

    call_command("seed_academic_calendar", school=school.code, verbosity=0)
    return school


def _member(school, user, year):
    from quality.models import QualityCommitteeMember

    return QualityCommitteeMember.objects.create(
        school=school,
        user=user,
        job_title="منسّق الجودة",
        responsibility="عضو",
        committee_type=QualityCommitteeMember.REVIEW,
        academic_year=year,
        is_active=True,
    )


def test_a_reviewer_of_a_past_year_is_no_longer_a_reviewer(calendar, teacher_user):
    from core.academic_calendar import academic_year_for_school
    from quality.views import _is_review_member

    current = academic_year_for_school(calendar)
    member = _member(calendar, teacher_user, "2019-2020")

    assert member.is_active, "الصفّ باقٍ نشطاً — العام وحده تغيّر"
    assert _is_review_member(teacher_user, calendar, current) is False


def test_a_reviewer_of_the_current_year_still_is(calendar, teacher_user):
    from core.academic_calendar import academic_year_for_school
    from quality.views import _is_review_member

    current = academic_year_for_school(calendar)
    _member(calendar, teacher_user, current)

    assert _is_review_member(teacher_user, calendar, current) is True


def test_the_helper_derives_the_year_when_none_is_given(calendar, teacher_user):
    """‏`_get_reviewer_domain(user, school)` تُنادى بلا عامٍ في موضع."""
    from core.academic_calendar import academic_year_for_school
    from quality.views import _is_review_member

    _member(calendar, teacher_user, academic_year_for_school(calendar))

    assert _is_review_member(teacher_user, calendar) is True
