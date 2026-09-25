"""[BUG] صفُّ جدول المعلّم في استمارة الزيارة الصفّية يُستبدَل ولا يُدسّ داخل نفسه.

`hx-target="#teacher-schedule-row"` هو الصفُّ نفسُه، وجذرُ الجزئيّ `teacher_schedule_row.html` هو
`<div id="teacher-schedule-row">` (والتعليقُ في رأسه يقول «يستبدله HTMX»). وبلا `hx-swap="outerHTML"`
يُطبَّق الافتراضيُّ `innerHTML` فيُدسّ الجزئيُّ الجديدُ داخل الصفّ القديم: معرّفٌ مكرَّرٌ
(`#teacher-schedule-row` مرّتين) بعد أوّل تغييرٍ للمعلّم أو التاريخ، وصنفُ `.qobs-schedule-row`
مرّتين. لم يرَه أحدٌ لأنّ العينَ لا تفرّق بينهما؛ كشفه `test_page_nav_htmx_process` (Playwright، وضعُ
strict: «resolved to 2 elements») حين وصل تشغيلُه المعزولُ الأوّل إلى آخره في `quality.yml` (REP-18) —
وهو ببطء المتصفّح، فهذا حارسٌ نصّيٌّ في بوّابة الطلبات لنفس العلّة.
"""

import pathlib
import re

FORM = pathlib.Path("templates/quality/observation_form.html")
TARGET = 'hx-target="#teacher-schedule-row"'


def _requests_targeting_the_row() -> list[str]:
    html = FORM.read_text(encoding="utf-8")
    return re.findall(rf"<input\b[^>]*{re.escape(TARGET)}[^>]*>", html, re.S)


def test_the_form_still_has_the_two_requests_that_refresh_the_row():
    # المعلّمُ (الحقلُ المخفيّ) والتاريخُ — فلا يمرّ الحارسُ فارغاً إن أُعيدت كتابةُ الاستمارة.
    assert len(_requests_targeting_the_row()) == 2


def test_every_request_that_targets_the_row_replaces_it_instead_of_nesting_the_partial():
    nesting = [tag for tag in _requests_targeting_the_row() if 'hx-swap="outerHTML"' not in tag]
    assert not nesting, (
        'طلبٌ يستهدف `#teacher-schedule-row` بلا `hx-swap="outerHTML"` — يُدسّ الجزئيُّ داخل الصفّ '
        "ويتكرّر المعرّف:\n  " + "\n  ".join(" ".join(t.split()) for t in nesting)
    )
