"""[A11Y] الصفحاتُ المرسومةُ فعلاً: لكلّ حقلٍ اسمٌ محسوب، والإرسالُ كما كان.

حارسُ `tests/a11y_ratchet.py` يقرأ مصدرَ القالب، وهذا يقرأ ما يصل المتصفّحَ بعد
الرسم — بما فيه ما يولّده `{% field %}` و`{% filter_bar %}` والجزئيّاتُ المضمَّنة.
فيُحسب الاسمُ كما يحسبه قارئُ الشاشة: `aria-label`، أو `aria-labelledby` يشير إلى
معرّفٍ موجود، أو `<label for>` يطابق `id`، أو `<label>` يلتفّ حول الحقل، أو `title`.

ثمّ يُرسَل نموذجان ترحّلا: بحثُ سجلّ الطلاب (GET بـHTMX) وحفظُ السجلّ الصحّيّ
(POST) — فالأسماءُ البرمجيّةُ لم تتغيّر، والخادمُ يقرأها كما كان.
"""

import html
from html.parser import HTMLParser

import pytest
from django.urls import reverse

pytestmark = pytest.mark.django_db

VISIBLE = frozenset(
    {
        "text",
        "search",
        "number",
        "date",
        "email",
        "tel",
        "password",
        "file",
        "checkbox",
        "radio",
        "time",
        "url",
    }
)


class _Names(HTMLParser):
    """يجمع الحقولَ وما يسمّيها — بمكدّسٍ يعرف الحقلَ داخل `<label>`."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.fields: list[dict] = []
        self.label_for: set[str] = set()
        self.ids: set[str] = set()
        self.in_label = 0
        self.stack: list[str] = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if a.get("id"):
            self.ids.add(a["id"])
        if tag == "label":
            self.in_label += 1
            if a.get("for"):
                self.label_for.add(a["for"])
        if tag in ("input", "select", "textarea"):
            kind = (a.get("type") or "text").lower() if tag == "input" else tag
            if tag == "input" and kind not in VISIBLE:
                return
            self.fields.append({**a, "_tag": tag, "_wrapped": self.in_label > 0})
        if tag not in ("input", "img", "br", "hr", "meta", "link"):
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if tag == "label" and self.in_label:
            self.in_label -= 1


def unnamed_fields(html: str) -> list[str]:
    scan = _Names()
    scan.feed(html)
    missing = []
    for f in scan.fields:
        named = (
            f.get("aria-label")
            or (f.get("aria-labelledby") and set(f["aria-labelledby"].split()) <= scan.ids)
            or (f.get("id") and f["id"] in scan.label_for)
            or f["_wrapped"]
            or f.get("title")
        )
        if not named:
            missing.append(f"<{f['_tag']} name={f.get('name')!r} id={f.get('id')!r}>")
    return missing


PAGES = [
    ("student_affairs:student_list", "principal_user"),
    ("staff_affairs:staff_list", "principal_user"),
    ("quality:execution_list", "principal_user"),
    ("quality:review_list", "principal_user"),
    ("notification_inbox", "principal_user"),
    ("manage_parent_links", "principal_user"),
    ("transport:buses_list", "principal_user"),
    ("library:book_list", "principal_user"),
    ("ui_components", "principal_user"),
    ("permission_audit_log", "principal_user"),
]


def _url(name):
    try:
        return reverse(name)
    except Exception:
        return reverse(name.split(":", 1)[1])


@pytest.mark.parametrize("name,who", PAGES)
def test_every_field_on_the_page_has_a_computed_name(
    request, client_as, name, who, school_bus, library_book
):
    user = request.getfixturevalue(who)
    response = client_as(user).get(_url(name))
    assert response.status_code == 200, f"{name}: {response.status_code}"
    missing = unnamed_fields(response.content.decode())
    assert not missing, f"{name}: حقولٌ بلا اسمٍ محسوب:\n  " + "\n  ".join(missing)


def test_the_health_record_page_names_every_field(client_as, nurse_user, health_record):
    url = reverse("clinic:health_record", args=[health_record.student_id])
    response = client_as(nurse_user).get(url)
    assert response.status_code == 200
    body = response.content.decode()
    assert not unnamed_fields(body)
    assert "<h1" in body, "ترويسةُ الصفحة page_header تعطيها h1"
    assert 'for="f-blood_type"' in body and 'id="f-blood_type" name="blood_type"' in body


def test_the_student_search_still_answers_with_the_same_names(
    client_as, principal_user, enrolled_student
):
    """GET بالاسم `q` كما كان — والجزئيّةُ تعود بالجدول لا بخطأ."""
    url = reverse("student_affairs:student_list")
    # المتصفّحُ يفكّ `&#x27;` في السمة قبل أن يقرأها HTMX — فيُقارَن المفكوك.
    full = html.unescape(client_as(principal_user).get(url).content.decode())
    assert 'name="q"' in full and 'name="grade"' in full and 'name="parent_status"' in full
    assert 'role="search"' in full and "hx-include=\"[name='status'],[name='grade']" in full
    partial = client_as(principal_user).get(url + "?q=zzz-no-such-student", HTTP_HX_REQUEST="true")
    assert partial.status_code == 200


def test_saving_the_health_record_still_posts_the_same_names(client_as, nurse_user, health_record):
    url = reverse("clinic:health_record", args=[health_record.student_id])
    response = client_as(nurse_user).post(
        url,
        {
            "blood_type": "A-",
            "allergies": "حساسيّةٌ من اللاتكس",
            "chronic_diseases": "",
            "medications": "",
            "emergency_contact_name": "وليُّ الأمر",
            "emergency_contact_phone": "+97499900000",
        },
    )
    assert response.status_code in (200, 302)
    health_record.refresh_from_db()
    assert health_record.blood_type == "A-"
    assert health_record.allergies == "حساسيّةٌ من اللاتكس"
    assert health_record.emergency_contact_name == "وليُّ الأمر"
