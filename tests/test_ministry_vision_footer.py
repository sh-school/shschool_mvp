"""[BRAND] رؤية الوزارة في ذيل الوثائق وفوتر المنصّة — من مصدرٍ واحد.

كانت مكتوبةً نصّاً في قالبَي طباعة وغائبةً عن الباقي. وتكرار النصّ يعني أن
تعديله لاحقاً يُصيب بعض الوثائق دون بعض — فوُحِّد في `components/ministry_vision.html`.

ومنذ SOS-20260910-3643 (2026-09-17) صار النصُّ حقلاً في `core.models.School`
(هجرة) لا ثابتاً في القالب — فتحديثُ صياغة الوزارة يُحرَّر من لوحة الإدارة
بلا نشر كود. والجزئيّةُ تبقى المصدرَ الوحيد الذي يُقرأ منه، ونصُّها الحرفيُّ
فيها احتياطٌ لمن استُدعي بلا `school` فقط — لا نسخةٌ ثانية تُصاغ.
"""

import pathlib

import pytest
from django.template.loader import render_to_string
from django.urls import reverse

#: نصُّ رؤية الوزارة كما تنشره في صفحة «مهام ومسؤوليات الوزارة»
#: (edu.gov.qa) ضمن استراتيجيتها 2024-2030 — لا الرسالة، فهما نصّان
#: مختلفان في الصفحة نفسها. ونصٌّ يُنسب إلى وزارةٍ يُؤخذ عنها لا يُصاغ.
VISION = "متعلم ريادي لتنمية مستدامة"

PARTIAL = pathlib.Path("templates/components/ministry_vision.html")

#: قوالب الطباعة المستقلّة — لا ترث ذيلاً من غيرها.
STANDALONE_DOCS = [
    "templates/quality/observation_pdf.html",
    "templates/schedule/print_schedule.html",
    "templates/behavior/pdf/base_form.html",
    "templates/reports/base_qatar_report.html",
]


def test_the_vision_has_one_source():
    """النصّ يُكتب مرّةً واحدة — في الجزئيّة وحدها."""
    holders = [
        f.as_posix()
        for f in pathlib.Path("templates").rglob("*.html")
        if VISION in f.read_text(encoding="utf-8", errors="ignore")
    ]

    assert holders == [PARTIAL.as_posix()], f"النصّ مكرّر في: {holders}"


@pytest.mark.parametrize("doc", STANDALONE_DOCS)
def test_every_standalone_document_footer_carries_the_vision(doc):
    assert 'include "components/ministry_vision.html"' in pathlib.Path(doc).read_text(
        encoding="utf-8"
    )


def test_the_partial_falls_back_without_a_school():
    """بلا `school` في السياق — نداءٌ لم يُحدَّث بعد، أو مكانٌ عارض لا مدرسةَ
    فيه — يبقى النصّ الافتراضيّ نفسُه ظاهراً، لا فراغاً في الفوتر."""
    rendered = render_to_string("components/ministry_vision.html").strip()

    assert rendered == VISION


@pytest.mark.django_db
def test_the_partial_reads_the_schools_vision_field(school):
    """SOS-20260910-3643: النصُّ حقلٌ في `School` — يُقرأ منه لا يُكتب هنا."""
    school.vision = "نصٌّ مخصَّصٌ اعتمدته هذه المدرسة"
    school.save(update_fields=["vision"])

    rendered = render_to_string("components/ministry_vision.html", {"school": school}).strip()

    assert rendered == "نصٌّ مخصَّصٌ اعتمدته هذه المدرسة"


@pytest.mark.django_db
def test_a_school_gets_the_current_vision_by_default(school):
    """مدرسةٌ لم تُحرِّر الحقل بعد — قيمتُه الافتراضية نصُّ الرؤية الحاليّ،
    لا فراغ. الهجرةُ تملأ به كلَّ مدرسةٍ قائمة أيضاً."""
    assert school.vision == VISION


@pytest.mark.django_db
def test_the_platform_footer_carries_the_vision(client, principal_user):
    """يُقاس على صفحةٍ مُصيَّرة عبر مكدّس العرض، لا على نصّ القالب.

    فوتر المنصّة في `base.html`، ولا يظهر إلا لمستخدمٍ داخل النظام.
    """
    client.force_login(principal_user)

    html = client.get(reverse("observation_list")).content.decode()

    assert VISION in html
    assert "site-footer-vision" in html


@pytest.mark.django_db
def test_the_field_is_actually_editable_from_the_admin_panel(client, school):
    """«تُحرَّر من لوحة الإدارة بلا نشر كود» ادّعاءٌ — وكاد يكذب: الحقلُ كان
    مضافاً إلى النموذج ولم يُضَف إلى `SchoolAdmin.fieldsets`، فـModelAdmin
    لا يعرض من الحقول إلّا ما ذُكر صراحةً فيها — فيختفي من الشاشة رغم وجوده
    في القاعدة، ولا طريقة لتحريره سوى القذيفة. هذا الاختبار يفتح شاشة
    التعديل نفسَها ويتحقّق من وجود الحقل، لا من مصدر القالب."""
    from core.models import CustomUser

    admin_user = CustomUser.objects.create(
        national_id="90000000099",
        full_name="مدير النظام",
        is_superuser=True,
        is_staff=True,
        must_change_password=False,
    )
    client.force_login(admin_user)

    html = client.get(f"/admin/core/school/{school.pk}/change/").content.decode()

    assert 'name="vision"' in html, "الحقل غائبٌ عن شاشة تعديل المدرسة في لوحة الإدارة"


@pytest.mark.django_db
def test_the_platform_footer_reflects_a_customised_vision(client, principal_user):
    """تحرير الحقل من لوحة الإدارة ينعكس على الفوتر بلا نشر كود."""
    school = principal_user.get_school()
    school.vision = "رؤيةٌ خاصّةٌ بهذه المدرسة"
    school.save(update_fields=["vision"])
    client.force_login(principal_user)

    html = client.get(reverse("observation_list")).content.decode()

    assert "رؤيةٌ خاصّةٌ بهذه المدرسة" in html
    assert VISION not in html
