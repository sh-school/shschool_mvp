"""[NOTIFICATIONS] نصُّ الإشعار يُقرأ كاملاً في الصندوق — لا قصَّ بالحرف ولا بالأسطر.

بلاغ المالك (2026-09-25): إشعارٌ نصُّه مقطوعٌ بـ«…» ولا سبيلَ لقراءته كاملاً؛ والنقرُ على عنوانه يفتح صفحةً أخرى.
السببُ (فُحص على القالب والأنماط): القالبُ يطبع `body|truncatechars:160` — فيُحذف ما بعد الحرف 160 من الصفحة — وأنماطُه
تقصّ الفقرةَ بسطرين (`-webkit-line-clamp: 2`)؛ والنصُّ الكاملُ في `title` (تلميحٌ بالمرور لا يعمل على اللمس). وليس
للإشعار صفحةُ تفصيل: الرابطُ الوحيدُ هو عنوانُه إلى `related_url`.

فصار النصُّ كاملاً، ويُحفظ سطرُه الجديد (`white-space: pre-line`).
"""

import re
import uuid
from pathlib import Path

from django.template.loader import render_to_string
from django.utils import timezone

from notifications.models import InAppNotification
from tests.css_contrast import iter_rules
from tests.css_source import read_css

ROOT = Path(__file__).resolve().parent.parent
PARTIAL = (ROOT / "templates/notifications/partials/notif_item.html").read_text(encoding="utf-8")

LONG_BODY = (
    "مُنحت صلاحيّةُ «مشغّل الجدول» لمعلّمَين لإدخال الإسناد لكلّ الأقسام دون وقفِ المنسّقين، ولا تمنح اعتماداً "
    "ولا مراجعةَ أنصبة؛ ويُدقَّق المنحُ بسببٍ إلزاميّ. التوليدُ والاعتمادُ بعد إقلاع الأحد. راجع صفحةَ الإسناد "
    "للتفاصيل الكاملة والتواريخ، ثمّ أبلغ المشرفَ بما يلزم قبل بدء العمل بالجدول الجديد."
)


def _render(body: str) -> str:
    notif = InAppNotification(
        id=uuid.uuid4(),
        title="تفويض «مُشغِّل الجدول» لمعلّمَين",
        body=body,
        event_type=InAppNotification._meta.get_field("event_type").choices[0][0],
        priority="normal",
        is_read=False,
        related_url="/operations/schedule/assignments/",
        created_at=timezone.now(),
    )
    return render_to_string("notifications/partials/notif_item.html", {"notif": notif})


def _body_paragraph(html: str) -> str:
    match = re.search(r'<p class="notif-item__body"[^>]*>(.*?)</p>', html, re.S)
    assert match, "فقرةُ النصّ غائبة"
    return match.group(1)


def test_a_body_longer_than_160_chars_is_rendered_in_full():
    assert len(LONG_BODY) > 160
    shown = _body_paragraph(_render(LONG_BODY))
    assert shown.strip() == LONG_BODY
    assert "…" not in shown and "..." not in shown


def test_the_partial_no_longer_truncates_or_hides_the_text_in_a_tooltip():
    assert "truncatechars" not in PARTIAL
    paragraph = re.search(r'<p class="notif-item__body"[^>]*>', PARTIAL)
    assert paragraph and "title=" not in paragraph.group(0)


def _body_rule():
    merged: dict[str, str] = {}
    for selector, decls, _ctx in iter_rules(read_css()):
        if any(" ".join(part.split()) == ".notif-item__body" for part in selector.split(",")):
            merged.update({key: value.strip() for key, value in decls.items()})
    assert merged, ".notif-item__body غيرُ معرَّف"
    return merged


def test_the_css_does_not_clamp_the_body_to_a_fixed_number_of_lines():
    rule = _body_rule()
    assert not [key for key in rule if "line-clamp" in key]
    assert rule.get("overflow") != "hidden"
    assert rule.get("display") != "-webkit-box"


def test_line_breaks_in_the_body_are_kept():
    assert _body_rule()["white-space"] == "pre-line"
    assert _body_rule()["overflow-wrap"] == "anywhere"
