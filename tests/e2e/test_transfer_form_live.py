"""نموذجُ طلب الانتقال في المتصفّح (W-20261106-020).

الانتقالُ الداخليّ يُرسَل ولا يُطلَب فيه اسمُ المدرسة الأخرى، وحقلُ `other_school_name` يبقى إلزاميّاً في الوارد والصادر.
كان الملفُّ يخفي حاويةَ الحقل في الداخليّ دون أن يرفع عنه `required`، فيمنع المتصفّحُ الإرسالَ على حقلٍ مخفيٍّ لا يستطيع
أن يُظهر عليه رسالة، فلا يقع شيءٌ عند الضغط. والاختبارُ يُسقط ذلك كما يراه المدير: ضغطةُ الزرّ تُرسل أو يُوقفها المتصفّحُ على حقلٍ ظاهر.
"""

import pytest
from django.utils import timezone

pytest.importorskip("pytest_playwright")

from student_affairs.models import StudentTransfer  # noqa: E402
from tests.attendance_fixtures import *  # noqa: E402,F401,F403
from tests.conftest import ClassGroupFactory  # noqa: E402

pytestmark = [pytest.mark.django_db, pytest.mark.pin_clock]

PATH = "/student-affairs/transfers/create/"


@pytest.fixture
def klass2(school, year, wing):
    """شعبةٌ أخرى في الصفّ نفسه: هدفُ الانتقال الداخليّ."""
    return ClassGroupFactory(
        school=school, grade="G7", section="2", level_type="prep", academic_year=year, wing=wing
    )


def _open_form(page, live_server, user):
    """دخولُ المدير ثمّ فتحُ نموذج الانتقال."""
    page.goto(f"{live_server.url}/auth/login/")
    page.fill('input[name="identifier"]', user.national_id)
    page.fill('input[name="password"]', "testpass123")  # pragma: allowlist secret
    page.click('button[type="submit"]')
    page.wait_for_url(lambda url: "/auth/login" not in url, timeout=30_000)
    page.goto(f"{live_server.url}{PATH}", wait_until="load")


def _watch_posts(page):
    """قائمةٌ تمتلئ بعناوين طلبات POST المُرسَلة إلى النموذج."""
    posts = []
    page.on(
        "request", lambda r: posts.append(r.url) if r.method == "POST" and PATH in r.url else None
    )
    return posts


def _fill(page, student, direction):
    page.select_option("#f-student_id", str(student.pk))
    page.select_option("[name=direction]", direction)
    # «اليوم» يُقرأ عند الاستدعاء لا عند الاستيراد، فيوافق الساعةَ المثبَّتة للاختبار
    page.fill("[name=transfer_date]", timezone.localdate().isoformat())


def _submit(page):
    page.click(".form-footer button[type=submit]")
    # المتصفّحُ يوقف الإرسال عند حقلٍ غير صالح، فيبقى المسارُ كما هو؛ وينتهي الانتظارُ الانتقالَ الناجح إن وقع.
    page.wait_for_timeout(500)


def test_internal_transfer_is_sent_without_other_school(
    page, live_server, principal_user, kid, klass2
):
    _open_form(page, live_server, principal_user)
    posts = _watch_posts(page)
    _fill(page, kid, "internal")
    page.select_option("#f-to_class_group_id", str(klass2.pk))

    page.click(".form-footer button[type=submit]")
    page.wait_for_url(lambda url: PATH not in url, timeout=10_000)

    assert len(posts) == 1, "الانتقالُ الداخليّ لم يُرسَل بطلب POST"
    assert StudentTransfer.objects.filter(
        student=kid, direction="internal", to_class_group=klass2
    ).exists()


def test_internal_transfer_asks_for_the_class_before_sending(
    page, live_server, principal_user, kid
):
    _open_form(page, live_server, principal_user)
    posts = _watch_posts(page)
    _fill(page, kid, "internal")

    _submit(page)

    assert posts == [], "أُرسل النموذج بلا شعبة منقول إليها"
    assert page.eval_on_selector(
        "#f-to_class_group_id", "el => el.required && el.validity.valueMissing"
    )
    assert PATH in page.url


@pytest.mark.parametrize("direction", ["in", "out"])
def test_other_school_stays_required_for_external_transfers(
    page, live_server, principal_user, kid, direction
):
    _open_form(page, live_server, principal_user)
    posts = _watch_posts(page)
    _fill(page, kid, direction)

    _submit(page)

    assert posts == [], "أُرسل النموذج الخارجيّ وحقلُ المدرسة الأخرى فارغ"
    assert page.eval_on_selector(
        "[name=other_school_name]", "el => el.required && el.validity.valueMissing"
    )
    assert PATH in page.url
