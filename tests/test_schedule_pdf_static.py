"""تصديرُ PDF للجدول من عامل Celery لا يحلّ ملفّاً ساكناً بالـmanifest (2026-09-25).

في الإنتاج فشل تصديرُ A3 من العامل بـ`ValueError: Missing staticfiles manifest entry for 'js/actions.js'`
(Sentry: SCHOOLOS-PRODUCTION-2X). القالبُ يُعرض في العامل لا في طلب الويب، ومخزنُ الملفّات الساكنة
`ManifestStaticFilesStorage` صارمٌ: أيُّ `{% static %}` لا مدخلَ له في `staticfiles.json` يرمي — والعاملُ لا
يملك بالضرورة manifest الويب. ومسارُ PDF أصلاً لا يحتاج سكربتاً: كلُّ ما فيه محروسٌ بـ`for_pdf` (الشعارُ والخطُّ
وشريطُ الرجوع) إلّا سكربتَين ظلّا يُدرجان: `actions.js` و`schedule-matrix.js`. وبقي الخللُ خفيّاً لأنّ الاختبارات
تعمل بمخزنٍ غيرِ صارم.

فهذا الاختبارُ يعرض مسارَ PDF بمخزنٍ صارمٍ بلا manifest، فيسقط عند أوّل `{% static %}` لم يُحرس.
"""

import pytest
from django.http import QueryDict
from django.template.loader import render_to_string

from operations.schedule_selectors import schedule_print_payload

pytestmark = pytest.mark.django_db

STRICT_MANIFEST = "django.contrib.staticfiles.storage.ManifestStaticFilesStorage"


@pytest.fixture
def strict_static(settings):
    """المخزنُ كما في الإنتاج بلا manifest في هذه العملية: أيُّ `{% static %}` يرمي."""
    settings.STORAGES = {**settings.STORAGES, "staticfiles": {"BACKEND": STRICT_MANIFEST}}


def _render(school, user, query, *, for_pdf):
    ctx = schedule_print_payload(school, user, QueryDict(query))
    ctx["embed"] = True  # كما تبنيه مهمّةُ التصدير (`render_schedule_export_task`)
    ctx["for_pdf"] = for_pdf
    return render_to_string("schedule/print_schedule.html", ctx)


class TestThePdfPathNeedsNoManifest:
    def test_the_harness_is_really_strict(self, school, principal_user, strict_static):
        """الشاهدُ: الصفحةُ العاديّةُ (بسكربتاتها) ترمي بهذا المخزن — فالاختبارُ التالي يقيس شيئاً."""
        with pytest.raises(ValueError, match="Missing staticfiles manifest entry"):
            _render(school, principal_user, "view=teacher", for_pdf=False)

    @pytest.mark.parametrize("view", ["all_teachers", "teacher"])
    def test_the_pdf_render_resolves_no_static_file(
        self, school, principal_user, strict_static, view
    ):
        query = "view=all_teachers" if view == "all_teachers" else "view=teacher"

        html = _render(school, principal_user, query, for_pdf=True)

        assert "<script src" not in html, "مسارُ PDF لا يحتاج سكربتاً خارجيّاً"
        assert "js/actions.js" not in html and "js/schedule-matrix.js" not in html
