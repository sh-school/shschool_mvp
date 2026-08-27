"""[REPORTS] مراجعة وحدة التقارير — الوثيقة تُعرض في مكانها ببيانات مدرستها.

أربعة عيوب متداخلة:

  المعاينة تفتح تبويباً جديداً وتُعيد وثيقة الطباعة نفسها — قالبٌ يمتدّ من
  `base_qatar_report` بلا قائمة ولا فتات خبز ولا رجوع.

  زرّ PDF يُعيد الملفّ `inline`، فيحلّ عارض المتصفّح محلّ الصفحة.

  الذيل والترويسة يطلبان `school_name` **ولا أحد يمرّره** — الخدمة تُعيد
  `school`. فالبديل المُثبَّت نصّاً («الشحانية … · 44994205 · …») هو المسار
  الوحيد دائماً، لا احتياطاً. وفي منصّةٍ متعدّدة المدارس تُطبع بيانات مدرسةٍ
  على وثائق غيرها.

  فصلٌ بلا طلاب يُعيد وثيقة الطباعة برسالة — صفحةٌ عارية بلا رجوع.
"""

import pathlib
import re

import pytest
from django.urls import reverse

QATAR_BASE = pathlib.Path("templates/reports/base_qatar_report.html")
INDEX = pathlib.Path("templates/reports/index.html")


# ═══════════════════════════════════════════════════════════════════
#  الوثيقة تحمل بيانات مدرستها
# ═══════════════════════════════════════════════════════════════════


def test_the_report_footer_reads_the_school_object():
    """`school_name` لم يكن يُمرَّر قطّ، فكان النصّ المُثبَّت هو السلوك لا الاحتياط."""
    src = QATAR_BASE.read_text(encoding="utf-8")

    assert "{{ school.name }}" in src
    # المتغيّر لا أيّ ذكر: `{% block school_name %}` اسم كتلة، والتعليق يشرح
    # لماذا رُفع — والبحث النصّي الساذج يلتقط الاثنين ويسقط بلا سبب.
    assert not re.search(r"{{\s*school_name", src)


@pytest.mark.parametrize("literal", ["44994205", "ashahanyia-pb@edu.gov.qa"])
def test_no_school_contact_is_hardcoded_in_the_report_base(literal):
    assert literal not in QATAR_BASE.read_text(encoding="utf-8")


def test_the_copyright_year_is_not_frozen():
    """`© 2026` تكذب في يناير."""
    src = QATAR_BASE.read_text(encoding="utf-8")

    assert "© 2026" not in src
    assert '© {% now "Y" %}' in src


def test_the_dead_report_base_is_gone():
    """`base_report.html` لم يمتدّ منه شيء ولم يُصيَّر — ٤٤٩ سطراً تُوهم بأنها تُستعمل."""
    assert not pathlib.Path("templates/reports/base_report.html").exists()


# ═══════════════════════════════════════════════════════════════════
#  المعاينة داخل الصفحة لا في تبويبٍ عارٍ
# ═══════════════════════════════════════════════════════════════════


def test_previews_open_in_the_viewer_not_a_blank_tab():
    src = INDEX.read_text(encoding="utf-8")

    assert "preview=1" not in src
    assert 'target="_blank"' not in src
    assert "report_viewer" in src


def test_the_pdf_button_opens_the_viewer_not_a_download():
    """مدخلٌ واحد: الزرّ يفتح العارض، والتنزيل من داخله.

    كان في الصفحة زرّان — «معاينة» يفتح العارض و«PDF» يُنزّل مباشرةً — فبقي
    مسارٌ يغادر الصفحة. والنمط المعتمد هو نمط استمارة الزيارة: عرضٌ في المكان،
    وتحميلٌ من شريط أدواته.
    """
    src = INDEX.read_text(encoding="utf-8")

    assert "download=1" not in src
    assert src.count("report_viewer") >= 3


@pytest.mark.django_db
def test_the_viewer_page_has_a_way_back(client, principal_user, school):
    from core.models import ClassGroup

    cls = ClassGroup.objects.create(school=school, grade="7", section="1")
    client.force_login(principal_user)

    html = client.get(
        reverse("report_viewer"), {"r": "class_results_pdf", "id": str(cls.id)}
    ).content.decode()

    assert reverse("reports_index") in html
    assert 'class="breadcrumbs"' in html
    assert reverse("class_results_pdf", args=[cls.id]) in html


@pytest.mark.django_db
def test_an_unknown_report_name_is_refused(client, principal_user):
    """`r` يُطابَق على قائمةٍ بيضاء ثم يُعكَس — لا يُبنى مسارٌ من نصّ المستخدم."""
    client.force_login(principal_user)

    resp = client.get(reverse("report_viewer"), {"r": "admin:index", "id": "1"})

    assert resp.status_code == 302
    assert resp.url == reverse("reports_index")


@pytest.mark.django_db
def test_a_malformed_id_does_not_crash_the_viewer(client, principal_user):
    client.force_login(principal_user)

    resp = client.get(reverse("report_viewer"), {"r": "class_results_pdf", "id": "ليس-uuid"})

    assert resp.status_code == 302


# ═══════════════════════════════════════════════════════════════════
#  الوثائق تُعرض داخل إطار صفحتها
# ═══════════════════════════════════════════════════════════════════


def test_every_viewable_report_allows_same_origin_framing():
    """`X_FRAME_OPTIONS = "DENY"` عامٌّ، فبدون الاستثناء يظهر الإطار فارغاً
    و«refused to connect» مكان الوثيقة — بلا أثرٍ في أيّ سجلّ."""
    from reports import views

    src = pathlib.Path("reports/views.py").read_text(encoding="utf-8")

    for name in views.VIEWABLE_REPORTS:
        decorated = re.search(
            rf"@xframe_options_sameorigin\n(?:@[\w_]+(?:\([^)]*\))?\n)*def {name}\(", src
        )
        assert decorated, f"{name} بلا xframe_options_sameorigin"


# ═══════════════════════════════════════════════════════════════════
#  الفصل الفارغ
# ═══════════════════════════════════════════════════════════════════


@pytest.mark.django_db
def test_an_empty_class_returns_to_the_reports_page(client, principal_user, school):
    """بدل وثيقة طباعةٍ برسالة — صفحةٌ بلا قائمة ولا رجوع."""
    from core.models import ClassGroup

    cls = ClassGroup.objects.create(school=school, grade="8", section="2")
    client.force_login(principal_user)

    resp = client.get(reverse("class_results_pdf", args=[cls.id]))

    assert resp.status_code == 302
    assert resp.url == reverse("reports_index")


@pytest.mark.parametrize(
    "viewer",
    [
        "templates/reports/report_viewer.html",
        "templates/quality/observation_pdf_view.html",
    ],
)
def test_no_viewer_offers_an_escape_to_a_new_tab(viewer):
    """المطلوب الفتح **في نفس الصفحة**.

    وُضع زرّ «فتح في تبويب» في الصفحة العارضة كخيارٍ إضافي لم يُطلب، فصار
    أقرب زرٍّ إلى ما اعتاده المستخدم — وأعاد السلوك الذي بُنيت الصفحة لإزالته.
    """
    assert 'target="_blank"' not in pathlib.Path(viewer).read_text(encoding="utf-8")


def test_the_viewer_toolbar_offers_download_and_back():
    """التنزيل لم يُلغَ — انتقل إلى داخل العارض كما في استمارة الزيارة."""
    src = pathlib.Path("templates/reports/report_viewer.html").read_text(encoding="utf-8")

    assert "download=1" in src
    assert "reports_index" in src
