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

    teacher = CustomUser.objects.create(national_id="28800000001", full_name="معلّم")
    observer = CustomUser.objects.create(national_id="28800000002", full_name="زائر")
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


def test_the_paper_and_margins_come_from_the_original(source):
    """12240×15840 twip = 8.5×11 بوصة، والهوامش 1620/720/1170/720."""
    assert "size: 8.5in 11in" in source
    assert "margin: 1.125in 0.5in 0.8125in 0.5in" in source


@pytest.mark.parametrize(
    ("colour", "where"),
    [("#943634", "شرائط العناوين"), ("#DDD9C3", "أرضيّة رؤوس الأعمدة")],
)
def test_the_colours_come_from_the_original(source, colour, where):
    assert colour in source, where


def test_the_original_fonts_are_asked_for_first(source):
    """الأصل بخطّي مايكروسوفت، وهما لا يُوزَّعان مع تطبيق. فيُطلبان أوّلاً
    — فيظهران حيث كانا مثبَّتَين — ويُسقَط إلى Amiri الحرّ."""
    assert "'Traditional Arabic', 'Sakkal Majalla', 'Amiri'" in source


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


def test_the_letterhead_is_read_from_the_school(source):
    assert "obs.school.letterhead" in source
    assert "obs.school.letterfoot" in source


def test_a_school_without_a_letterhead_gets_a_text_heading(db, observation):
    """لا ترويسةَ مدرسةٍ أخرى — عنوانٌ نصّيٌّ من اسمها هي."""
    from quality.observation_views import _pdf_context

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    assert observation.school.name in html
    assert "<img" not in html


# ── قسمة الصفحتين ────────────────────────────────────────────────────


def test_the_criteria_are_split_by_domain_not_by_length(db, observation, criteria):
    """الأصل يبدأ الصفحة الثانية بـ«التقويم». ولو تُركت للتدفّق لانقطع
    مجالٌ في منتصفه."""
    from quality.observation_views import _pdf_context

    blocks = _pdf_context(observation)["blocks"]

    assert len(blocks) == 2
    assert [d for d, _ in blocks[0]] == ["التخطيط", "تنفيذ الدرس"]
    assert [d for d, _ in blocks[1]] == ["التقويم", "الإدارة الصفية وبيئة التعلم"]


def test_the_title_repeats_on_the_second_page(db, observation, criteria):
    """الأصل يُعيد العنوان ورؤوس الأعمدة في الصفحة الثانية."""
    from quality.observation_views import _pdf_context

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    assert html.count('class="subject"') == 2, "العنوان مرّتان — لا ثلاثاً مع وسم <title>"


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
