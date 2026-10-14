"""[QUALITY] استمارة الإشراف المطبوعة — طبق الأصل من نموذج المدرسة.

طلب المدير أن تخرج الزيارات الصفّية بصورة استمارته الورقيّة نفسها: الخطوط
والألوان والترويسة والتذييل. والقياسات كلّها مأخوذةٌ من `sectPr` في ملفّ
الـdocx لا مُقدَّرةً بالعين — هوامشُه بعينها، ولونا 943634 وDDD9C3. أمّا الورقُ فA4 لا Letter الأصل (طلبُ المالك 2026-09-26): انظر
`test_observation_pdf_a4.py`.

والشريطان صورتا المدرسة من **بياناتها** لا من هذا القالب: المنصّة متعدّدة
المدارس، وصورةٌ مكتوبةٌ في قالبٍ مشترك تطبع ترويسة مدرسةٍ على وثيقة أخرى.
ومن لم يرفعهما يُبنَ له عنوانٌ نصّيّ من اسمه.
"""

import pathlib
import re

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


def test_the_paper_is_a4_not_the_originals_letter(source):
    """الأصل 12240×15840 twip = Letter؛ والمالك طلب A4 (ورقُ الطباعة المعتمد) — فالهوامشُ من الأصل والورقُ A4. تفاصيلُه في `test_observation_pdf_a4`."""
    import re

    assert re.findall(r"(?<![\w-])size:\s*([^;]+);", source) == ["A4"]  # `font-size` لا يُحسب


def test_the_side_margins_come_from_the_original(source):
    """الجانبيّان 720 twip = نصف بوصة، كما في الأصل."""
    import re

    margin = re.search(r"margin: ([\d.]+(?:in|mm)) ([\d.]+)in ([\d.]+(?:in|mm)) ([\d.]+)in", source)

    assert margin, "هوامشُ الصفحة: علويٌّ وسفليٌّ (حدُّ الإطار) وجانبيّان بالبوصة"
    assert margin.group(2) == margin.group(4) == "0.5"


def _margin_boxes(html):
    """(مربّعُ الهامش ← (ارتفاعُ الهامش، ارتفاعُ محتواه)) من تخطيط WeasyPrint نفسِه لا من نصّ القالب."""
    weasyprint = pytest.importorskip("weasyprint")

    page = weasyprint.HTML(string=html).render().pages[0]._page_box
    found = {}

    def walk(box):
        if type(box).__name__ == "MarginBox":
            found[box.at_keyword] = (
                box.height,
                sum(child.margin_height() for child in box.children),
            )
        for child in getattr(box, "children", ()):
            walk(child)

    walk(page)
    return found


def test_the_vertical_margins_hold_the_standard_header_and_footer(db, observation):
    """الهامشان يسعان الترويسةَ والتذييلَ الموحَّدَين (وزارةٌ ومدرسةٌ وخطٌّ زخرفيّ؛ وسطران) — فلا يفيضان على المتن ولا يبقى بياضٌ كثير.

    يُقاس المرسومُ فعلاً: ارتفاعُ محتوى كلّ هامشٍ ≤ ارتفاعِه، وما زاد عليه فضلةٌ ≤ 0.35 بوصة (33.6px).
    """
    from quality.observation_views import _pdf_context

    boxes_ = _margin_boxes(
        render_to_string("quality/observation_pdf.html", _pdf_context(observation))
    )
    for keyword in ("@top-center", "@bottom-center"):
        height, content = boxes_[keyword]
        assert content <= height, (keyword, content, height)
        assert height - content <= 33.6, (keyword, "هامشٌ أكبر من حاجته", content, height)


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


def test_letterhead_and_letterfoot_images_are_gone(source, db, observation):
    """ترويسةُ الصور وتذييلُها أُلغيا (2026-09-26): لا يقرأ القالبُ ولا السياقُ صورةً مرفوعةً لهما — الهويّةُ نصٌّ موحَّدٌ كباقي ملفّات PDF."""
    from quality.observation_views import _pdf_context

    assert "letterhead" not in source and "letterfoot" not in source
    assert "letterhead" not in _pdf_context(observation) and "letterfoot" not in _pdf_context(
        observation
    )


def test_the_header_is_local_and_the_footer_is_the_shared_component(db, observation):
    """الترويسةُ نصّيّةٌ محلّيّة (شعارٌ فوزارةٌ فاسمُ المدرسة وخطٌّ زخرفيّ — **بلا رؤية**)، والتذييلُ من المكوّن المركزيّ
    `components/pdf_footer.html` (استعادةُ البنية، قرارُ المالك 2026-09-28): سطرٌ واحد — المدرسةُ والوزارةُ والرؤيةُ من مصدرها الواحد.

    والبيانُ من `obs.school` لا نصٌّ في القالب (منصّةٌ متعدّدةُ المدارس)؛ واسمُ المنصّة لا يظهر.
    """
    from quality.observation_views import _pdf_context

    school = observation.school
    school.vision = "رؤيةٌ اختباريّةٌ خاصّةٌ بالمدرسة"
    school.save(update_fields=["vision"])

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    for marker in (
        'class="doc-header"',
        'class="school-name"',
        'class="ornament-hr"',
        'class="pdf-footer-line"',
    ):
        assert marker in html, marker
    assert 'class="ministry-name"' not in html, "سطرُ الوزارة مجمَّد (D-400م)"
    header = html.split('<div id="sheet-header">', 1)[1].split('<div id="sheet-footer">', 1)[0]
    footer = html.split('<div id="sheet-footer">', 1)[1].split("<h1", 1)[0]
    assert "vision-text" not in header and school.vision not in header, "لا رؤيةَ في الترويسة"
    assert footer.count('class="pdf-footer-line"') == 1 and observation.school.name in footer
    assert 'class="vision-text"' in footer and school.vision in footer, "الرؤيةُ في السطر نفسِه"
    assert "ft-school" not in html and "ft-ministry" not in html
    assert (
        "SchoolOS" not in html and "SAMM" not in html
    ), "اسمُ المنصّة لا يظهر في تذييل أيّ تصدير (أمرُ المالك 2026-09-27)"
    # شعارُ المدرسة «ش» وحدَه (D-404م): صورةٌ واحدةٌ في الترويسة، لا في التذييل ولا شعارُ الوزارة (أُزيل — W-20261011-012)
    assert html.count("<img") == 1 and "<img" in header and "<img" not in footer


def test_two_planning_domains_sit_on_the_first_page_the_rest_on_the_second(
    db, observation, criteria
):
    """استعادةُ البنية الأصليّة (قرارُ المالك 2026-09-28): الصفحةُ الأولى «التخطيط» و«تنفيذ الدرس»، والثانيةُ الباقي — لا جدولٌ واحد."""
    from quality.observation_views import _pdf_context

    ctx = _pdf_context(observation)

    assert [d for d, _ in ctx["blocks"][0]] == ["التخطيط", "تنفيذ الدرس"]
    assert [d for d, _ in ctx["blocks"][1]] == ["التقويم", "الإدارة الصفية وبيئة التعلم"]


def test_the_second_domain_block_forces_a_page_break_and_repeats_the_grid(
    db, observation, criteria
):
    """عنوانان (أوّلٌ لكلّ صفحة) وجدولا معاييرَ (أوّلٌ لكلّ صفحة)، وفاصلُ صفحةٍ واحد بينهما — استعادةٌ من نموذج المدرسة الأصليّ."""
    from quality.observation_views import _pdf_context

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    assert html.count('class="subject"') == 2
    assert html.count("break-before: page") == 1
    assert html.count('class="grid"') == 2


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


def test_the_five_columns_and_the_recommendation_column_sum_to_the_full_width(source):
    """بلا عرضٍ مثبَّت تسحب الأعمدةُ الضيّقة عرضَ عمود المعايير فتنكسر كل كلمةٍ على سطر — وهو ما حدث في نسخةٍ سابقة.

    البنيةُ المستعادة (كالأصل): المجالُ 8% والمعاييرُ 26% وخمسةُ أعمدة تقديرٍ 8.4% لكلٍّ والتوصياتُ 24% — نسبٌ صريحةٌ تجمع 100%
    لا عمودَ معاييرَ يبتلع الباقي (خلافَ التصميم المؤقّت أحاديِّ الصفحة الذي لم يكن فيه عمودُ توصيات).
    """
    import re

    assert "table-layout: fixed" in source
    domain = float(re.search(r"\.c-domain \{ width: ([\d.]+)%", source).group(1))
    crit = float(re.search(r"\.c-crit\s*\{ width: ([\d.]+)%", source).group(1))
    rate = float(re.search(r"\.c-rate\s*\{ width: ([\d.]+)%", source).group(1))
    rec = float(re.search(r"\.c-rec\s*\{ width: ([\d.]+)%", source).group(1))

    assert domain + crit + 5 * rate + rec == pytest.approx(100.0)
    assert 184.6 * crit / 100 >= 40, "عمودُ المعايير يسع نصّاً مقروءاً ولو التفّ على أكثرَ من سطر"


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
    assert (
        'include "components/pdf_footer.html"' in source
    ), "الرؤيةُ تصل عبر المكوّن المركزيّ لا نصّاً هنا"
    assert "الريادة في توفير" not in source and "رِيَادِيٌّ" not in source, "يُضمَّن ولا يُنسخ"


# ── ختمُ التوقيع الإلكترونيّ في خانتَي التوقيع (F55E) ─────────────────────────
# التذكرةُ SOS-20260925-F55E: خانتا «توقيع المعلم» و«توقيع الزائر» كانتا فارغتين في نسخة PDF، والنموذجُ يحمل
# `submitted_at` (إرسال الزائر) و`teacher_acknowledged_at` (اطّلاع المعلّم). الاسمُ عند وجود البيانات، وإلّا تبقى
# الخانةُ فارغةً للتوقيع اليدويّ؛ لا اسمَ على مسودّةٍ أو مسحوبة؛ والأسماءُ وحدَها.
# W-20261005-007 (D-221م): الوثيقةُ طبقُ الأصل الرسميّ فسقطت منها عبارةُ «توقيعٌ إلكترونيّ داخل المنصّة» ووقتُ
# الختم؛ بقي الاسمُ وحدَه، ووقتُ الإرسال والاطّلاع شرطُ الظهور في القاعدة لا نصٌّ يُعرض.

PHRASE = "توقيعٌ إلكترونيّ داخل المنصّة"  # حُذفت من الوثيقة (D-221م): يُفحص غيابُها
BOX = '<div class="e-sign">'  # الخانةُ المملوءة بالاسم؛ وفي الأنماط `.e-sign {` لا يطابقها
VISITOR_NAME = "سالم الزائر الأوّل"
TEACHER_NAME = "ناصر المعلّم الأوّل"
SENT_AT = "2026-09-01T09:30:00+00:00"  # 12:30 بتوقيت الدوحة
ACK_AT = "2026-09-02T06:05:00+00:00"  # 09:05 بتوقيت الدوحة


def _stamp_of(name):
    """الخانةُ كما تخرج: صندوقٌ فيه الاسمُ وحدَه — لا عبارةَ ولا وقت."""
    return f"{BOX}<div>{name}</div></div>"


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

    assert html.count(BOX) == 1
    assert _stamp_of(VISITOR_NAME) in html
    # الاسمان في ترويسة الاستمارة دائماً؛ الخانةُ هي سطرُ «الاسم» داخل الصندوق
    assert _stamp_of(TEACHER_NAME) not in html, "المعلّمُ لم يطّلع بعدُ — خانتُه فارغةٌ للتوقيع اليدويّ"


def test_an_acknowledged_visit_stamps_both_cells(db, named):
    html = _html_of(_acknowledged(named))

    assert html.count(BOX) == 2
    assert _stamp_of(VISITOR_NAME) in html
    assert _stamp_of(TEACHER_NAME) in html


def test_a_draft_is_never_stamped_even_with_a_stale_time(db, named):
    """المسودّةُ ومنها المسحوبةُ (السحبُ يعيدها مسودّةً) بلا ختم — الحالةُ هي الحكمُ لا الوقتُ وحدَه."""
    named.status = "draft"
    named.submitted_at = _moment(SENT_AT)
    named.teacher_acknowledged_at = _moment(ACK_AT)
    named.save()

    html = _html_of(named)

    assert BOX not in html
    assert f"<div>{VISITOR_NAME}</div>" not in html and f"<div>{TEACHER_NAME}</div>" not in html


def test_a_reopened_visit_keeps_the_visitor_stamp_and_drops_the_teachers(db, named):
    """إعادةُ الفتح: مُقَرّة → مُرسَلة، ويُمحى اطّلاعُ المعلّم فتعود خانتُه فارغة."""
    _acknowledged(named)
    named.status = "submitted"
    named.teacher_acknowledged_at = None
    named.save()

    html = _html_of(named)

    assert html.count(BOX) == 1 and _stamp_of(TEACHER_NAME) not in html


def test_a_resubmitted_visit_keeps_the_name_and_shows_no_time(db, named):
    _sent(named, at="2026-09-01T09:30:00+00:00")
    named.submission_count = 2
    named.submitted_at = _moment("2026-09-03T07:15:00+00:00")  # 10:15 بتوقيت الدوحة
    named.save()

    html = _html_of(named)

    assert _stamp_of(VISITOR_NAME) in html
    assert "2026/09/03" not in html and "10:15" not in html and "2026/09/01" not in html
    named.refresh_from_db()
    assert named.submitted_at == _moment("2026-09-03T07:15:00+00:00"), "الإثباتُ في القاعدة لا يُمسّ"


def test_no_time_and_no_phrase_whatever_timezone_is_active(db, named):
    """لا وقتَ في الخانتين ولا عبارةَ ختمٍ، أيّاً كانت المنطقةُ الزمنيّةُ النشطة (D-221م)."""
    from django.utils import timezone

    _acknowledged(named)

    for tz in ("UTC", "Asia/Qatar"):
        with timezone.override(tz):
            html = _html_of(named)
        assert PHRASE not in html
        for shown in ("12:30", "09:30", "09:05", "06:05", "2026/09/02"):
            assert shown not in html, (tz, shown)


def test_the_proof_fields_in_the_database_are_untouched_by_the_pdf(db, named):
    """الوقتان في القاعدة دليلُ الإرسال والاطّلاع — عرضُ PDF لا يغيّرهما ولا يحذفهما."""
    _acknowledged(named)

    _html_of(named)
    named.refresh_from_db()

    assert named.submitted_at == _moment(SENT_AT)
    assert named.teacher_acknowledged_at == _moment(ACK_AT)


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

    assert _stamp_of(VISITOR_NAME) not in _html_of(named)


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
    """القبولُ: الجدولُ يبقى بعدد الصفحات نفسِه — الختمان لا يزيدان صفحةً.

    البنيةُ المستعادة (قرارُ المالك 2026-09-28) صفحتان دائماً على الأقلّ (فصلٌ قصديٌّ بالمجال)، فلا معنى للبحث عن صفحةٍ
    واحدة كما في التصميم المؤقّت السابق. نأخذ أكبرَ عددِ معاييرَ تسعه صفحتان **بلا ختم**، ونقيس الاستمارةَ المختومةَ
    بالختمَين عند العدد نفسِه.
    """
    pytest.importorskip("weasyprint")
    named.general_notes = ""
    named.status = "draft"
    named.save()

    for count in range(23, 8, -1):
        _real_criteria(school, count)
        if _page_count(named) == 2:
            break
    else:
        pytest.skip("لا عددَ معاييرَ تسعه صفحتان في هذه البيئة (خطوطُ PDF غيرُ مثبَّتة)")

    assert (
        _page_count(_acknowledged(named)) == 2
    ), f"الختمان أنزلا الاستمارةَ ({count} معياراً) عن صفحتَيها"


# ── لا شعارَ في الرأس (W-20261011-012، قرار المالك D-386م) ─────────────────────
# شعارُ الوزارة أُزيل من الاستمارة كلِّها: الهويّةُ نصٌّ (وزارةٌ ومدرسةٌ) وخطٌّ زخرفيّ، ولا صورةَ لا من المنصّة ولا من رفعِ المدرسة.

PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="


def _save_image(field, name):
    import base64

    from django.core.files.base import ContentFile

    field.save(name, ContentFile(base64.b64decode(PNG)), save=True)


def test_the_context_carries_no_logo_key(db, observation):
    from quality.observation_views import _pdf_context

    assert "logo" not in _pdf_context(observation)


def test_an_uploaded_school_logo_or_letterhead_never_reaches_the_form(db, observation):
    """صورةٌ مرفوعةٌ (شعارُ مدرسة أو تراثُ ترويسة) لا أثرَ لها: الهويّةُ نصٌّ وشعارُ «ش» الثابتُ من الأصل لا من المرفوع (D-404م)."""
    from quality.observation_views import _pdf_context

    _save_image(observation.school.logo, "own.png")
    _save_image(observation.school.letterhead, "head.png")
    _save_image(observation.school.letterfoot, "foot.png")

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    images = re.findall(r"<img[^>]*>", html)
    assert (
        len(images) == 1
        and 'class="school-logo' in images[0]
        and "data:image/png;base64," in images[0]
    )
    assert observation.school.name in html


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


def test_the_header_draws_only_the_school_logo(db, observation):
    """الترويسةُ نصٌّ وشعارُ المدرسة «ش» (28px) وحدَه. يُقاس من تخطيط WeasyPrint نفسِه: صندوقُ صورةٍ واحدٌ في الصفحة الأولى."""
    from quality.observation_views import _pdf_context

    html = render_to_string("quality/observation_pdf.html", _pdf_context(observation))

    assert _image_boxes(html) == [(28.0, 28.0)]


def test_the_pdf_carries_only_the_school_logo_image(db, school, named):
    """القبولُ: ملفُّ PDF الناتج بصورةٍ واحدةٍ في صفحته الأولى — شعارُ المدرسة «ش» (D-404م)."""
    import io

    from core.pdf_utils import render_pdf_bytes

    pypdf = pytest.importorskip("pypdf")
    _real_criteria(school, 12)

    reader = pypdf.PdfReader(io.BytesIO(render_pdf_bytes(_html_of(named))))

    assert len(reader.pages[0].images) == 1
