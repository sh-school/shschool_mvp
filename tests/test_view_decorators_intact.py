"""[SECURITY] الواجهتان اللتان كشفتُهما بيدي تبقيان محروستين.

أدخلتُ العطب أنا: أقحمتُ دالّةً مساعدة **بين المُزيِّنات ودالّتها**، فصارت
`@login_required` و`@role_required` تحرسان المساعدة وبقيت الواجهة مكشوفة:

    @login_required
    @role_required(STUDENT_AFFAIRS_MANAGE)
    def _behaviour_window(school, today):   ← المساعدة هي المحروسة
        ...

    def behavior_overview(request):          ← والواجهة عارية

ووقع مثله في `behavior_dashboard`. ولا شيء يُخفق: الواجهة تعمل، والصفحة
تُعرض، والحراسة وحدها تغيب.

ولم يلتقطه إلّا `pytest` في البوابة، ولسببٍ عارض تماماً — اختبارٌ استدعى
المساعدة مباشرةً فاصطدم بمُزيِّنٍ يطلب `request.user` من كائن `School`. ولولا
ذلك لَمرّ.

وحاولتُ أوّلاً حارساً عامّاً يفحص `__wrapped__` على كل واجهةٍ مسجَّلة، فأنتج
إيجابياتٍ كاذبة: `serve_db_file` يُفوّض داخل جسمه بـ`_authorize` fail-closed،
وواجهات أخرى مُزيَّنةٌ بآليةٍ لا تضع `__wrapped__`. وحارسٌ لا أستطيع جعله
صادقاً أسوأ من لا حارس. فالفحص هنا **على السلوك**: زائرٌ غير مسجَّل يُحوَّل.
"""

import pathlib

import pytest
from django.urls import reverse


@pytest.mark.parametrize(
    "url_name",
    ["student_affairs:behavior_overview", "behavior:dashboard"],
)
def test_an_anonymous_visitor_is_turned_away(client, db, url_name):
    """المُزيِّن يُحوّل إلى تسجيل الدخول — وغيابه يُعيد 200."""
    resp = client.get(reverse(url_name))

    assert resp.status_code in (302, 403), f"{url_name} مكشوفة"
    if resp.status_code == 302:
        assert "login" in resp.url


@pytest.mark.parametrize(
    "path,helper",
    [
        ("student_affairs/views.py", "_behaviour_window"),
        ("behavior/views.py", "_behaviour_year_window"),
    ],
)
def test_no_decorator_sits_above_a_helper(path, helper):
    """الشكل الذي أوقعني — مذكورٌ بموضعه كي لا يعود.

    والفحص بنيويّ لا سلوكيّ: يمسك الخطأ في اللحظة التي يُكتب فيها، لا بعد
    أن تُنشر واجهةٌ مكشوفة.
    """
    lines = pathlib.Path(path).read_text(encoding="utf-8").splitlines()
    i = next(n for n, line in enumerate(lines) if line.startswith(f"def {helper}"))

    assert not lines[i - 1].startswith("@"), f"{path}: مُزيِّنٌ يسبق دالّةً مساعدة"


def test_the_helpers_are_still_where_the_guard_looks():
    """حارسٌ يبحث عن دالّةٍ زالت يمرّ دائماً."""
    for path, helper in (
        ("student_affairs/views.py", "_behaviour_window"),
        ("behavior/views.py", "_behaviour_year_window"),
    ):
        src = pathlib.Path(path).read_text(encoding="utf-8")
        assert f"def {helper}" in src, f"{path}: {helper} لم تعد موجودة"
