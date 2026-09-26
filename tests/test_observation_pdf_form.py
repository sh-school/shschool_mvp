"""[QUALITY] استمارة الإشراف المطبوعة — طبق الأصل من نموذج المدرسة.

طلب المدير أن تخرج الزيارات الصفّية بصورة استمارته الورقيّة نفسها: الخطوط
والألوان والترويسة والتذييل. والقياسات كلّها مأخوذةٌ من `sectPr` في ملفّ
الـdocx لا مُقدَّرةً بالعين — ورقُ Letter، وهوامشُه بعينها، ولونا 943634
وDDD9C3.

والشريطان صورتا المدرسة من **بياناتها** لا من هذا القالب: المنصّة متعدّدة
المدارس، وصورةٌ مكتوبةٌ في قالبٍ مشترك تطبع ترويسة مدرسةٍ على وثيقة أخرى.
ومن لم يرفعهما يُبنَ له عنوانٌ نصّيّ من اسمه.
"""

import pathlib

import pytest
from django.template.loader import render_to_string

TEMPLATE = pathlib.Path("templates/quality/observation_pdf.html")


@pytest.fixture
def source():
    return TEMPLATE.read_text(encoding="utf-8")


@pytest.fixture
def criteria(db, school):
    """معيارٌ واحدٌ لكل مجال — تكفي القسمة والعرض."""
    from quality.observation_models import OBSERVATION_DOMAINS, ObservationCriterion

    return [
        ObservationCriterion.objects.create(
            school=school, domain=domain, text=f"معيارٌ في {label}", order=i
        )
        for i, (domain, label) in enumerate(OBSERVATION_DOMAINS)
    ]


@pytest.fixture
def observation(db, school, criteria):
    from core.models import CustomUser
    from quality.observation_models import ClassroomObservation

    teacher = CustomUser.objects.create(
        must_change_password=False, national_id="28800000001", full_name="معلّم"
    )
    observer = CustomUser.objects.create(
        must_change_password=False, national_id="28800000002", full_name="زائر"
    )
    return ClassroomObservation.objects.create(
        school=school,
        teacher=teacher,
        observer=observer,
        topic="موضوع الحصة",
        follow_up_mode="field",
        follow_up_scope="full",
        general_notes="ملاحظةٌ عامّة.",
    )


# ── ما نُقل من الأصل حرفياً ───────────────────────────────────────────


def test_the_paper_comes_from_the_original(source):
    """12240×15840 twip = 8.5×11 بوصة."""
    assert "size: 8.5in 11in" in source


def test_the_side_margins_come_from_the_original(source):
    """الجانبيّان 720 twip = نصف بوصة، كما في الأصل."""
    import re

    margin = re.search(r"margin: ([\d.]+)in ([\d.]+)in ([\d.]+)in ([\d.]+)in", source)

    assert margin, "هوامشُ الصفحة مكتوبةٌ بالبوصة"
    assert margin.group(2) == margin.group(4) == "0.5"


def test_the_vertical_margins_hold_the_bands_and_no_more(source):
    """هامشا الأصل 1.125 و0.8125 بوصة، والشريطان أقصر: 0.878 و0.405 عند
    عرض 7.5 بوصة. فضُبطا على ارتفاعهما وفضلةٍ يسيرة، والفائض رُدّ إلى
    المتن — فالصفحة تمتلئ ولا يبقى بياضٌ فوق التذييل."""
    import re

    margin = re.search(r"margin: ([\d.]+)in ([\d.]+)in ([\d.]+)in ([\d.]+)in", source)
    top, bottom = float(margin.group(1)), float(margin.group(3))

    assert 0.878 < top < 1.125, "يسع الترويسة ولا يزيد كثيراً"
    assert 0.405 < bottom < 0.8125, "يسع التذييل ولا يزيد كثيراً"


@pytest.mark.parametrize(
    ("const", "colour", "where"),
    [
        ("FORM_BAND", "#943634", "شرائط العناوين"),
        ("FORM_KEY_BG", "#DDD9C3", "أرضيّة رؤوس الأعمدة"),
    ],
)
def test_the_colours_come_from_the_original(source, const, colour, where):
    """اللونان من الأصل — يُقرآن من `core.brand` (مرآةِ `:root`) لا يُكتبان في القالب."""
    from core import brand

    assert getattr(brand, const).lower() == colour.lower(), where
    assert f'{{% brand_color "{const}" %}}' in source, where


def test_the_original_font_is_asked_for_first_but_never_shipped(source):
    """«Traditional Arabic» ملكيّةُ Monotype، ومستودع المشروع عامّ — فإيداعُه
    فيه نشرٌ لبرمجيّةٍ مرخَّصة. فيُطلب أوّلاً فيظهر حيث هو مثبَّت، والمُودَع
    بديلٌ حرٌّ برخصة SIL OFL."""
    import pathlib

    assert "'Traditional Arabic', 'Noto Naskh Arabic', 'Amiri'" in source
    assert not pathlib.Path("static/fonts/trado.ttf").exists(), "لا يُودَع خطٌّ مملوك"
    assert pathlib.Path("static/fonts/NotoNaskhArabic-Regular.ttf").exists()
    assert pathlib.Path("static/fonts/NotoNaskhArabic-OFL.txt").exists(), "الرخصة معه"


def test_the_template_asks_for_no_font_by_relative_url(source):
    """`{% static %}` يُخرج رابطاً نسبياً — وفي الإنتاج يحمل بصمةً لا وجود
    لها إلّا في `staticfiles/`. وWeasyPrint يحلّ النسبيّ على القرص من
    `BASE_DIR` فلا يجده، ويسقط إلى DejaVu Sans بلا شكوى.

    وقد خرجت الاستمارة من الإنتاج بـDejaVu فعلاً — والخطوط تُحقن من
    `pdf_utils` بمسارات مطلقة.
    """
    assert "@font-face" not in source.split("{% endcomment %}", 1)[-1]


def test_the_pdf_toolchain_provides_the_free_naskh():
    from core.pdf_utils import _font_face_css_weasyprint

    css = _font_face_css_weasyprint()

    assert "Noto Naskh Arabic" in css
    assert "file:///" in css, "مسارٌ مطلق لا رابطٌ نسبيّ"


def test_the_header_repeats_on_every_page(source):
    """الأصل يضع الشريطين في `header1.xml` و`footer1.xml` — أي على كل صفحة.
    و`running()` هي مقابلها في CSS للطباعة."""
    assert "@top-center" in source and "running(sheet-header)" in source
    assert "@bottom-center" in source and "running(sheet-footer)" in source


def test_the_rating_cells_are_left_empty_to_be_ticked(source):
    """الأصل يترك خلايا التقدير فارغةً تُؤشَّر باليد، ولا يرسم فيها مربّعات.
    فإن كان التقدير مُدخَلاً وُضعت علامته في خانته وحدها."""
    assert "Webdings'," not in source
    assert ".box" not in source, "خلايا التقدير فارغةٌ تُؤشَّر باليد كما في الأصل"


# ── الترويسة بيانات مدرسةٍ لا ثابتُ قالب ──────────────────────────────


def test_no_school_name_is_written_into_the_template(source):
    """اسمٌ مكتوبٌ هنا يطبع ترويسة مدرسةٍ على وثيقة أخرى."""
    assert "الشحانية" not in source


def test_the_letterhead_is_embedded_not_linked(source):
    """الملفّات المرفوعة في القاعدة لا على قرص، و WeasyPrint يحلّ الروابط
    النسبية على القرص من `BASE_DIR` — فيبحث عن ملفٍّ لا وجود له ويطبع
    الصفحة بلا ترويسة، بلا خطأٍ ولا شكوى. فتُضمَّن الصورة."""
    assert "{{ letterhead }}" in source
    assert "letterhead.url" not in source
    assert "letterfoot.url" not in source


def test_the_embedded_letterhead_is_a_data_uri(db, observation):
    """الترويسة تُقرأ من القاعدة وتُضمَّن — لا رابطَ يُحلّ على قرصٍ لا يحملها."""
    import base64
    import io

    from django.core.files.base import ContentFile

    from quality.observation_views import _pdf_context

    png = base64.b64decode(
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
    )
    observation.school.letterhead.save("head.png", ContentFile(png), save=True)

    ctx = _pdf_context(observation)

    assert ctx["letterhead"].startswith("data:image/png;base64,")
    assert ctx["letterfoot"] == "", "ما لم يُرفع يبقى فارغاً"
    assert io  # noqa: B018 — الاستيراد يوثّق أنّ القراءة ثنائية


def test_a_school_without_a_letterhead_gets_a_text_heading_with_the_approved_logo(db, observation):
    """لا ترويسةَ مدرسةٍ أخرى — عنوانٌ نصّيٌّ من اسمها هي ومعه الشعارُ المعتمد (لا شعارَ مدرسةٍ أخرى)."""
    from quality.observation_views import _pdf_context

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    assert observation.school.name in html and "وزارة التربية والتعليم" in html
    assert html.count("<img") == 1 and 'class="logo"' in html


# ── قسمة الصفحتين ────────────────────────────────────────────────────


def test_all_four_domains_sit_in_one_table(db, observation, criteria):
    """الأصل صفحتان، وطلبت المدرسة صفحةً واحدة — فلا قسمة ولا فاصل."""
    from quality.observation_views import _pdf_context

    ctx = _pdf_context(observation)

    assert [d for d, _ in ctx["domains"]] == [
        "التخطيط",
        "تنفيذ الدرس",
        "التقويم",
        "الإدارة الصفية وبيئة التعلم",
    ]


def test_nothing_forces_a_second_page(db, observation, criteria):
    """عنوانٌ واحد، وجدولٌ واحد للمعايير، ولا `break-before`."""
    from quality.observation_views import _pdf_context

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    assert html.count('class="subject"') == 1
    assert "break-before" not in html
    assert html.count('class="grid"') == 1


def test_a_self_assessment_is_titled_as_one(db, observation, criteria):
    from quality.observation_views import _pdf_context

    observation.kind = "self"

    assert "التقييم الذاتي" in _pdf_context(observation)["form_subject"]


# ── القيم المُدخلة تظهر ───────────────────────────────────────────────


def test_the_chosen_rating_is_the_only_ticked_box(db, observation, criteria):
    from quality.observation_models import ObservationScore
    from quality.observation_views import _pdf_context

    ObservationScore.objects.create(
        observation=observation,
        criterion=criteria[0],
        rating="some",
        recommendation="توصيةٌ محدّدة.",
    )

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    # ثلاث علاماتٍ لا واحدة: تقديرُ المعيار، ومعهما «ميدانيّة» و«كلّيّة»
    # في جدول المعلومات — وكلاهما مُدخَلٌ في الزيارة نفسها.
    assert html.count("✓") == 3
    assert "توصيةٌ محدّدة." in html


# ── لا تُحقن ترويسةُ المنصّة فوق ترويسة المدرسة ───────────────────────


def test_the_template_declares_that_it_owns_its_page(source):
    """`pdf_utils` يحقن ترويسة المنصّة وخطّها وهوامش A4 في كل ملفّ إلّا ما
    أعلن أنّه يتولّى صفحته.

    وكان الاستثناء مربوطاً باسم صنفٍ في الترويسة القديمة (`doc-header`)،
    فلمّا أُعيدت كتابة الاستمارة سقط الاسم وعاد الحقن صامتاً: ترويسةُ
    المنصّة فوق ترويسة المدرسة، وخطُّ Tajawal فوق الخطّ المطلوب، وهوامشُ
    A4 فوق ورق Letter. ولم يشكُ شيء — خرج الملفّ وهو غيرُ الاستمارة.
    """
    from core.pdf_utils import OWN_PAGE_FURNITURE, _owns_its_page

    assert OWN_PAGE_FURNITURE in source
    assert _owns_its_page(source), "لا يُحقن فوق هذا القالب شيء"


def test_the_platform_furniture_is_not_injected(db, observation):
    from core.pdf_utils import _inject_wp_page_header_css
    from quality.observation_views import _pdf_context

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    assert _inject_wp_page_header_css(html, "مدرسة", "عنوان") == html


def test_an_ordinary_template_still_gets_the_furniture():
    """الاستثناء لهذا القالب وحده — لا تخفيفٌ عامّ."""
    from core.pdf_utils import _inject_wp_page_header_css

    plain = "<html><head><style></style></head><body><p>تقرير</p></body></html>"

    assert _inject_wp_page_header_css(plain, "مدرسة", "عنوان") != plain


def test_no_vertical_writing_mode(source):
    """الأصل يكتب رؤوس الأعمدة عمودياً، وجُرّب `writing-mode` فأخرج
    WeasyPrint حروفاً عربيةً مُشوَّهة ونفخ الجدول من صفحتين إلى خمس.

    والمحرّك هو الحَكَم لا المتصفّح: عاينتُ التدوير في Chromium فبدا
    سليماً، وأنتجه WeasyPrint خرابةً — وهو مَن يطبع.
    """
    # الشرحُ يذكرها ليقول لِمَ تُركت — والعبرة بما يُنفَّذ لا بما يُشرح.
    css = source.split("{% endcomment %}", 1)[-1]
    css = chr(10).join(l for l in css.splitlines() if not l.lstrip().startswith("`"))

    assert "writing-mode" not in css
    assert "rotate(" not in css


def test_the_criteria_column_keeps_its_width(source):
    """بلا عرضٍ مثبَّت تسحب الأعمدةُ الضيّقة عرضَ عمود المعايير فتنكسر كل
    كلمةٍ على سطر — وهو ما حدث."""
    assert "table-layout: fixed" in source
    assert ".c-crit" in source


# ── الخطّ المملوك يصل الخادم ولا يدخل المستودع ───────────────────────


def test_the_proprietary_font_is_never_committed():
    """مستودع المشروع عامّ، و«Traditional Arabic» ملكيّةُ Monotype.

    شقّان: ما في `.gitignore` يُقرأ من القرص، وما في الفهرس يحتاج غيتاً.
    وغيتٌ ليس في حاوية التطوير، فكان الفحصُ يسقط بـ`FileNotFoundError`
    في كلّ تشغيلٍ محلّيٍّ لأيّ فرع — حمرةٌ كاذبةٌ تُعمي عن الحمرة الصادقة.

    فصار الشقُّ الثاني يُتخطّى حين لا غيت، **إلّا في البوّابة**: هناك غيتٌ
    موجودٌ بالضرورة، فغيابُه عطبٌ في البيئة لا عذرٌ للتخطّي.
    """
    import os
    import pathlib
    import shutil
    import subprocess

    ignored = pathlib.Path(".gitignore").read_text(encoding="utf-8")
    assert "static/fonts/trado.ttf" in ignored

    git = shutil.which("git")
    if git is None:
        # في متغيّرٍ لا في `assert os.environ.get(...)` مباشرةً: pytest يطبع
        # ما يُقارَن عند الإخفاق، و`os.environ` تحمل أسراراً.
        in_ci = bool(os.environ.get("CI"))
        assert not in_ci, "لا غيتَ في البوّابة — الفحصُ لا يُتخطّى هنا"
        pytest.skip("لا غيتَ في هذه البيئة — فحصُ الفهرس يجري في البوّابة")

    tracked = subprocess.run(
        [git, "ls-files", "static/fonts"], capture_output=True, text=True, check=False
    ).stdout.lower()
    assert "trado" not in tracked and "tradbdo" not in tracked


def test_a_stored_font_reaches_the_stylesheet(db):
    """الخطّ المحفوظ في القاعدة يُخرَج إلى القرص ويُطلب بمسارٍ مطلق.

    وWeasyPrint لا يقرأ من قاعدة بيانات ولا يحلّ رابطاً نسبياً على الويب —
    يريد مساراً على القرص، وإلّا سقط إلى DejaVu Sans بلا شكوى.
    """
    from core.models.stored_file import StoredFile
    from core.pdf_utils import _MATERIALISED, _font_face_css_weasyprint, stored_font_key

    _MATERIALISED.clear()
    key = stored_font_key("Traditional Arabic", "400")
    StoredFile.objects.update_or_create(
        name=key,
        defaults={"content": bytes([0, 1, 116, 116, 102]), "size": 5, "content_type": "font/ttf"},
    )

    css = _font_face_css_weasyprint()

    assert "Traditional Arabic" in css
    assert "file:///" in css
    _MATERIALISED.clear()


def test_a_missing_stored_font_is_simply_absent(db):
    """من لم يُثبّت خطّه لا تنكسر وثيقته — تُطبع بالبديل الحرّ."""
    from core.models.stored_file import StoredFile
    from core.pdf_utils import _MATERIALISED, _font_face_css_weasyprint, stored_font_key

    _MATERIALISED.clear()
    StoredFile.objects.filter(
        name__startswith=stored_font_key("Traditional Arabic", "400")[:9]
    ).delete()

    css = _font_face_css_weasyprint()

    assert "Traditional Arabic" not in css
    assert "Noto Naskh Arabic" in css


def test_the_vision_is_included_never_written_here(source):
    """نصُّ الرؤية في هذه الاستمارة يأتي من صورة المدرسة التي ترفعها هي،
    ومن لم يرفعها يُذيَّل من المصدر الواحد.

    وكان القالب يحمل نصّاً كتبتُه في جلسةٍ سابقة لا سندَ لديّ عليه، ويخالف
    نصَّ رؤية المدرسة. سألت عنه المدرسةُ واعتمدت نصَّها، فحلّ في الجزئيّة
    وحدها. ووثيقةٌ رسميةٌ لا تنسب إلى وزارةٍ قولاً بلا مصدر، ولا تكتبه
    مرّتين فيختلفان.
    """
    assert 'include "components/ministry_vision.html"' in source
    assert "الريادة في توفير" not in source, "يُضمَّن ولا يُنسخ"


# ── ختمُ التوقيع الإلكترونيّ في خانتَي التوقيع (F55E) ─────────────────────────
# التذكرةُ SOS-20260925-F55E: خانتا «توقيع المعلم» و«توقيع الزائر» كانتا فارغتين في نسخة PDF، والنموذجُ يحمل
# `submitted_at` (إرسال الزائر) و`teacher_acknowledged_at` (اطّلاع المعلّم). الختمُ عند وجود البيانات، وإلّا تبقى
# الخانةُ فارغةً للتوقيع اليدويّ؛ لا ختمَ على مسودّةٍ أو مسحوبة؛ والوقتُ بتوقيت الدوحة؛ والأسماءُ وحدَها.

STAMP = "توقيعٌ إلكترونيّ داخل المنصّة"
VISITOR_NAME = "سالم الزائر الأوّل"
TEACHER_NAME = "ناصر المعلّم الأوّل"
SENT_AT = "2026-09-01T09:30:00+00:00"  # 12:30 بتوقيت الدوحة
ACK_AT = "2026-09-02T06:05:00+00:00"  # 09:05 بتوقيت الدوحة


def _stamp_of(name, at):
    """الختمُ كما يخرج: اسمٌ في سطرٍ ووقتٌ في سطرٍ (لا فاصلٌ يتدلّى في الخانة الضيّقة)."""
    return f"<div>{name}</div><div>{at}</div>"


def _moment(iso):
    from datetime import datetime

    return datetime.fromisoformat(iso)


def _html_of(obs):
    from quality.observation_views import _pdf_context

    return render_to_string("quality/observation_pdf.html", _pdf_context(obs))


@pytest.fixture
def named(observation):
    """الزائرُ والمعلّمُ باسمَين لا يُخلطان بكلمتَي «الزائر» و«المعلم» في عنوانَي الخانتين."""
    observation.observer.full_name = VISITOR_NAME
    observation.observer.save(update_fields=["full_name"])
    observation.teacher.full_name = TEACHER_NAME
    observation.teacher.save(update_fields=["full_name"])
    return observation


def _sent(obs, at=SENT_AT):
    obs.status = "submitted"
    obs.submitted_at = _moment(at)
    obs.submission_count = 1
    obs.teacher_acknowledged_at = None
    obs.save()
    return obs


def _acknowledged(obs):
    _sent(obs)
    obs.status = "acknowledged"
    obs.teacher_acknowledged_at = _moment(ACK_AT)
    obs.save()
    return obs


def test_a_sent_visit_stamps_the_visitor_and_leaves_the_teacher_cell_empty(db, named):
    html = _html_of(_sent(named))

    assert html.count(STAMP) == 1
    assert _stamp_of(VISITOR_NAME, "2026/09/01 12:30") in html
    # الاسمان في ترويسة الاستمارة دائماً؛ الختمُ هو سطرا «الاسم» و«الوقت»
    assert (
        f"<div>{TEACHER_NAME}</div>" not in html
    ), "المعلّمُ لم يطّلع بعدُ — خانتُه فارغةٌ للتوقيع اليدويّ"


def test_an_acknowledged_visit_stamps_both_cells(db, named):
    html = _html_of(_acknowledged(named))

    assert html.count(STAMP) == 2
    assert _stamp_of(VISITOR_NAME, "2026/09/01 12:30") in html
    assert _stamp_of(TEACHER_NAME, "2026/09/02 09:05") in html


def test_a_draft_is_never_stamped_even_with_a_stale_time(db, named):
    """المسودّةُ ومنها المسحوبةُ (السحبُ يعيدها مسودّةً) بلا ختم — الحالةُ هي الحكمُ لا الوقتُ وحدَه."""
    named.status = "draft"
    named.submitted_at = _moment(SENT_AT)
    named.teacher_acknowledged_at = _moment(ACK_AT)
    named.save()

    html = _html_of(named)

    assert STAMP not in html
    assert f"<div>{VISITOR_NAME}</div>" not in html and f"<div>{TEACHER_NAME}</div>" not in html


def test_a_reopened_visit_keeps_the_visitor_stamp_and_drops_the_teachers(db, named):
    """إعادةُ الفتح: مُقَرّة → مُرسَلة، ويُمحى اطّلاعُ المعلّم فتعود خانتُه فارغة."""
    _acknowledged(named)
    named.status = "submitted"
    named.teacher_acknowledged_at = None
    named.save()

    html = _html_of(named)

    assert html.count(STAMP) == 1 and f"<div>{TEACHER_NAME}</div>" not in html


def test_a_resubmitted_visit_shows_the_last_time(db, named):
    _sent(named, at="2026-09-01T09:30:00+00:00")
    named.submission_count = 2
    named.submitted_at = _moment("2026-09-03T07:15:00+00:00")  # 10:15 بتوقيت الدوحة
    named.save()

    html = _html_of(named)

    assert "2026/09/03 10:15" in html
    assert "2026/09/01" not in html


def test_the_time_is_doha_whatever_timezone_is_active(db, named):
    from django.utils import timezone

    _sent(named)

    with timezone.override("UTC"):
        html = _html_of(named)

    assert "12:30" in html and "09:30" not in html


def test_the_stamp_carries_names_only_no_id_and_no_number(db, named):
    _acknowledged(named)
    for user in (named.observer, named.teacher):
        assert user.national_id, "الفرضيّةُ: للمستخدمَين هويّةٌ في القاعدة، ولا تظهر في الختم"

    html = _html_of(named)

    for user in (named.observer, named.teacher):
        assert user.national_id not in html


def test_a_signer_without_a_name_gets_no_stamp(db, named):
    """ختمٌ بلا اسمٍ ليس توقيعاً — تبقى الخانةُ للتوقيع اليدويّ."""
    _sent(named)
    named.observer.full_name = "  "
    named.observer.save(update_fields=["full_name"])

    assert STAMP not in _html_of(named)


def test_the_signature_labels_stay_and_are_not_replaced_by_the_stamp(db, named):
    html = _html_of(_acknowledged(named))

    assert "توقيع المعلم" in html and "توقيع الزائر" in html


def _real_criteria(school, count):
    """معاييرُ الاستمارة الحقيقيّة (الأولى `count`) لا معيارُ الفحص الواحد — ويُزال ما في الفحوص من معايير."""
    from quality.management.commands.seed_observation_criteria import CRITERIA
    from quality.observation_models import ObservationCriterion

    ObservationCriterion.objects.filter(school=school).delete()
    for order, (domain, text) in enumerate(CRITERIA[:count], start=1):
        ObservationCriterion.objects.create(school=school, domain=domain, text=text, order=order)


def _page_count(obs):
    import io

    from core.pdf_utils import render_pdf_bytes

    pypdf = pytest.importorskip("pypdf")
    pdf = render_pdf_bytes(_html_of(obs))
    return len(pypdf.PdfReader(io.BytesIO(pdf)).pages)


def test_a_stamped_form_fits_wherever_the_unstamped_one_fits(db, school, named):
    """القبولُ: الجدولُ يبقى في صفحةٍ واحدة — الختمان لا يُنزلان الاستمارةَ عن الصفحة الواحدة.

    عددُ صفحات الأصل تحكمه الخطوطُ المثبَّتةُ في البيئة (بخطٍّ بديلٍ عريضٍ ينزل صفُّ التوقيع وحده إلى الصفحة الثانية
    ولو بلا ختم) — فلا رقمَ مطلقاً هنا: نأخذ أكبرَ عددِ معاييرَ تسعه صفحةٌ واحدةٌ **بلا ختم** (حتّى تمتلئ الصفحةُ إلى
    حافّتها)، ونقيس الاستمارةَ المختومةَ بالختمَين عند العدد نفسِه. صندوقُ الملاحظات يردّ ما يزيده الختمُ (`.notes.stamped`).
    """
    pytest.importorskip("weasyprint")
    named.general_notes = ""
    named.status = "draft"
    named.save()

    for count in range(23, 8, -1):
        _real_criteria(school, count)
        if _page_count(named) == 1:
            break
    else:
        pytest.skip("لا عددَ معاييرَ تسعه صفحةٌ في هذه البيئة (خطوطُ PDF غيرُ مثبَّتة)")

    assert (
        _page_count(_acknowledged(named)) == 1
    ), f"الختمان أنزلا الاستمارةَ ({count} معياراً) عن صفحتها"


# ── الشعارُ في الرأس (بلاغ المالك 2026-09-26) ─────────────────────────────────
# الترتيب: صورةُ الترويسة المرفوعة إن وُجدت (كما هي) ← `School.logo` إن وُجد ← الشعارُ المعتمد `static/brand/logoMaroon.png` مع الترويسة
# النصّيّة. فلا تحتاج مدرسةٌ إلى رفع شيءٍ لتظهر الاستمارةُ بشعار، وتبقى الصفحةُ واحدة.

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _save_image(field, name):
    import base64

    from django.core.files.base import ContentFile

    field.save(name, ContentFile(base64.b64decode(PNG)), save=True)


def test_without_any_upload_the_approved_logo_is_used(db, observation):
    import base64
    import pathlib

    from quality.observation_views import _pdf_context

    logo = _pdf_context(observation)["logo"]

    assert logo.startswith("data:image/png;base64,")
    expected = pathlib.Path("static/brand/logoMaroon.png").read_bytes()
    assert base64.b64decode(logo.split(",", 1)[1]) == expected, "الشعارُ المعتمدُ نفسُه لا نسخةٌ أخرى"


def test_the_schools_own_logo_comes_before_the_approved_one(db, observation):
    from quality.observation_views import _as_data_uri, _pdf_context
    from quality.pdf_assets import brand_logo_data_uri

    _save_image(observation.school.logo, "own.png")

    ctx = _pdf_context(observation)

    assert ctx["logo"] == _as_data_uri(observation.school.logo)
    assert ctx["logo"] != brand_logo_data_uri()


def test_an_uploaded_letterhead_replaces_the_text_heading_and_no_logo_is_added(db, observation):
    """الترويسةُ المرفوعة كما هي — لا شعارَ بجانبها ولا يُقرأ ملفُّه."""
    from quality.observation_views import _pdf_context

    _save_image(observation.school.letterhead, "head.png")
    _save_image(observation.school.logo, "own.png")

    ctx = _pdf_context(observation)
    html = render_to_string("quality/observation_pdf.html", ctx)

    assert ctx["logo"] == ""
    assert html.count("<img") == 1 and 'class="logo"' not in html


def test_a_missing_approved_logo_falls_back_to_the_text_heading(db, observation, tmp_path):
    from django.test import override_settings

    from quality.observation_views import _pdf_context

    with override_settings(BASE_DIR=tmp_path):
        ctx = _pdf_context(observation)
        html = render_to_string("quality/observation_pdf.html", ctx)

    assert ctx["logo"] == ""
    assert "<img" not in html and observation.school.name in html


def test_the_logo_fits_the_top_margin_without_touching_the_body(source):
    """ارتفاعُ الشعار + حشوا الشريط + حدُّ العنوان السفليّ ≤ الهامش العلويّ — وإلّا نزل من الهامش على المتن."""
    import re

    logo = float(re.search(r"\.plain-head \.logo \{[^}]*height: ([\d.]+)in", source).group(1))
    top = float(re.search(r"margin: ([\d.]+)in [\d.]+in [\d.]+in [\d.]+in", source).group(1))
    padding = 2 * float(re.search(r"#sheet-header \{[^}]*padding: ([\d.]+)in 0", source).group(1))
    border_and_gap = (2 + 4) / 72  # حدُّ العنوان 2pt وحشوُه السفليّ 4pt

    assert logo + padding + border_and_gap <= top, (logo, padding, top)


def _image_boxes(html):
    """(عرضٌ، ارتفاعٌ) بالبكسل CSS لكلّ صورةٍ في الصفحة الأولى — من تخطيط WeasyPrint نفسِه لا من نصّ القالب."""
    weasyprint = pytest.importorskip("weasyprint")
    from weasyprint.formatting_structure import boxes

    page = weasyprint.HTML(string=html).render().pages[0]._page_box
    found = []

    def walk(box):
        if isinstance(box, boxes.InlineReplacedBox | boxes.BlockReplacedBox):
            found.append((round(box.width, 1), round(box.height, 1)))
        for child in getattr(box, "children", ()):
            walk(child)

    walk(page)
    return found


def test_the_logo_is_drawn_small_not_stretched_across_the_header(db, observation):
    """القاعدةُ العامّة `#sheet-header img` تمدّ صورةَ الترويسة على عرض الشريط (6.8 بوصة) — وشعارٌ بقاعدةٍ أضعفَ خصوصيّةً يُمدّ معها فيغطّي الرأس.

    يُقاس حجمُه المرسوم فعلاً: مربّعٌ صغيرٌ بنحو 0.62 بوصة (59.5px) لا أوسعُ من بوصة.
    """
    from quality.observation_views import _pdf_context

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))
    images = _image_boxes(html)

    assert len(images) == 1, images
    width, height = images[0]
    assert width <= 96 and 50 <= height <= 62, images


def test_an_uploaded_letterhead_is_still_stretched_to_the_strip_width(db, observation):
    """`#sheet-header img` بقيت كما هي: الترويسةُ المرفوعة بعرض الشريط (6.8 بوصة = 652.8px)."""
    from quality.observation_views import _pdf_context

    _save_image(observation.school.letterhead, "head.png")
    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    assert [w for w, _h in _image_boxes(html)] == [652.8]


def _images_and_pages(obs):
    import io

    from core.pdf_utils import render_pdf_bytes

    pypdf = pytest.importorskip("pypdf")
    reader = pypdf.PdfReader(io.BytesIO(render_pdf_bytes(_html_of(obs))))
    return len(reader.pages), len(reader.pages[0].images)


def test_the_logo_reaches_the_pdf_as_an_image_and_its_absence_leaves_none(
    db, school, named, tmp_path
):
    """القبولُ: يظهر صورةً في PDF حين يُوجد الشعارُ ولا ترويسة، ولا يظهر حين لا يوجدان."""
    from django.test import override_settings

    pytest.importorskip("weasyprint")
    _real_criteria(school, 12)

    pages_with, images_with = _images_and_pages(named)
    with override_settings(BASE_DIR=tmp_path):  # لا شعارَ معتمداً ولا شعارَ مدرسة ولا ترويسة
        pages_without, images_without = _images_and_pages(named)

    assert images_with == 1 and images_without == 0
    assert pages_with == pages_without == 1


def test_the_logo_never_costs_a_page(db, school, named, tmp_path):
    """صفحةٌ واحدة: أكبرُ عددِ معاييرَ تسعه الصفحةُ بلا شعار (حتّى حافّتها) — والشعارُ عند العدد نفسِه لا يُنزلها إلى صفحتين.

    نسبيّ عمداً كما في ختم F55E: عددُ الصفحات المطلق تحكمه خطوطُ PDF المثبَّتةُ في البيئة.
    """
    from django.test import override_settings

    pytest.importorskip("weasyprint")
    named.general_notes = ""
    named.save()

    for count in range(23, 8, -1):
        _real_criteria(school, count)
        with override_settings(BASE_DIR=tmp_path):
            if _images_and_pages(named)[0] == 1:
                break
    else:
        pytest.skip("لا عددَ معاييرَ تسعه صفحةٌ في هذه البيئة (خطوطُ PDF غيرُ مثبَّتة)")

    assert _images_and_pages(named)[0] == 1, f"الشعارُ أنزل الاستمارةَ ({count} معياراً) عن صفحتها"
