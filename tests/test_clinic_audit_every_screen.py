"""
tests/test_clinic_audit_every_screen.py — كلُّ شاشةٍ صحّيّةٍ في العيادة تترك سطرَ تدقيق (W-20261020-026).

PDPPL م.11 وم.13: فتحُ قائمة الزيارات ولوحة العيادة والسجلّ الصحّي وصولٌ إلى بياناتٍ صحّيّةٍ
لقاصرين، فيُدقَّق بمعرّفاتٍ فقط. والاختبارُ شموليّ: يبني قائمةَ المسارات من محلّل الروابط، فكلُّ مسارٍ
جديدٍ لا يُصنَّف هنا (صحّيّ أو مستثنًى باسمه وسببه) يُسقطه.
"""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from clinic.models import ClinicVisit
from core.models import AuditLog

# شاشاتٌ تعرض بياناً صحّيّاً فرديّاً: اسمُ المسار ← (طريقة بناء الرابط).
HEALTH_VIEWS = {
    "dashboard",
    "health_record",
    "visits_list",
}

# مستثناةٌ مسمّاةٌ بسببها: لا تعرض بياناً صحّيّاً فرديّاً من الطالب.
NON_HEALTH_VIEWS = {
    "needs_care_import": "رفعُ ملفٍّ فقط؛ الصفحةُ لا تعرض سجلّاً، والتقريرُ أعدادٌ",
    "record_visit": "نموذجُ إدخالٍ فيه أسماءُ الطلاب دون بيانٍ صحّيّ؛ والإنشاءُ يُدقَّق بإشارة post_save",
    "record_visit_student": "كسابقه بمعرّف طالبٍ في الرابط",
    "statistics": "أعدادٌ مجمَّعةٌ لا سجلٌّ فرديّ",
    "api_clinic_charts": "أعدادٌ يوميّةٌ مجمَّعةٌ بصيغة JSON",
}


def _clinic_url_names():
    names = set()

    def walk(patterns, ns):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, p.namespace or ns)
            elif isinstance(p, URLPattern) and ns == "clinic" and p.name:
                names.add(p.name)

    walk(get_resolver().url_patterns, None)
    return names


def test_every_clinic_route_is_classified():
    """مسارٌ جديدٌ في العيادة بلا تصنيفٍ (صحّيّ/مستثنًى) يفشل — فيُقرَّر تدقيقُه عمداً."""
    names = _clinic_url_names()
    assert names, "لم تُحلَّ روابط العيادة"
    unclassified = names - HEALTH_VIEWS - set(NON_HEALTH_VIEWS)
    assert not unclassified, f"مسارات عيادةٍ بلا تصنيف تدقيق: {sorted(unclassified)}"
    stale = (HEALTH_VIEWS | set(NON_HEALTH_VIEWS)) - names
    assert not stale, f"تصنيفٌ لمسارات غير موجودة: {sorted(stale)}"


@pytest.mark.django_db
class TestHealthScreensAreAudited:
    def _url(self, name, student):
        if name == "health_record":
            return reverse("clinic:health_record", args=[student.id])
        return reverse(f"clinic:{name}")

    @pytest.mark.parametrize("name", sorted(HEALTH_VIEWS))
    def test_open_leaves_audit_line_without_pii(
        self,
        client_as,
        nurse_user,
        student_user,
        enrolled_student,
        health_record,
        clinic_visit,
        name,
    ):
        client = client_as(nurse_user)
        before = AuditLog.objects.filter(user=nurse_user, action="view").count()

        response = client.get(self._url(name, student_user))
        assert response.status_code == 200

        lines = AuditLog.objects.filter(user=nurse_user, action="view").order_by("-timestamp")
        assert lines.count() == before + 1, f"الشاشة {name} لم تترك سطر تدقيق"
        line = lines.first()
        blob = f"{line.object_repr} {line.object_id} {line.changes}"
        assert student_user.full_name not in blob
        for visit in ClinicVisit.objects.all():
            for text in (visit.reason, visit.treatment):
                if text:
                    assert text not in blob

    def test_htmx_partial_is_audited_too(
        self, client_as, nurse_user, student_user, enrolled_student, clinic_visit
    ):
        cache.clear()
        client = client_as(nurse_user)
        before = AuditLog.objects.filter(user=nurse_user, action="view").count()
        response = client.get(reverse("clinic:visits_list"), HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        assert AuditLog.objects.filter(user=nurse_user, action="view").count() == before + 1

    def test_live_search_is_throttled_to_one_line_per_minute(
        self, client_as, nurse_user, student_user, enrolled_student, clinic_visit
    ):
        cache.clear()
        client = client_as(nurse_user)
        before = AuditLog.objects.filter(user=nurse_user, action="view").count()
        for _ in range(5):
            client.get(reverse("clinic:visits_list"), HTTP_HX_REQUEST="true")
        assert AuditLog.objects.filter(user=nurse_user, action="view").count() == before + 1
        # فتحُ الصفحة الكاملة بعدها يُدقَّق ولا يخضع للتخفيف
        client.get(reverse("clinic:visits_list"))
        assert AuditLog.objects.filter(user=nurse_user, action="view").count() == before + 2

    def test_search_term_is_not_logged(
        self, client_as, nurse_user, student_user, enrolled_student, clinic_visit
    ):
        client = client_as(nurse_user)
        client.get(reverse("clinic:visits_list"), {"student": student_user.full_name})
        line = AuditLog.objects.filter(user=nurse_user, action="view").latest("timestamp")
        assert student_user.full_name not in f"{line.object_repr} {line.changes}"


from django.core.cache import cache

"""
tests/test_clinic_audit_every_screen.py — كلُّ شاشةٍ صحّيّةٍ في العيادة تترك سطرَ تدقيق (W-20261020-026).

PDPPL م.11 وم.13: فتحُ قائمة الزيارات ولوحة العيادة والسجلّ الصحّي وصولٌ إلى بياناتٍ صحّيّةٍ
لقاصرين، فيُدقَّق بمعرّفاتٍ فقط. والاختبارُ شموليّ: يبني قائمةَ المسارات من محلّل الروابط، فكلُّ مسارٍ
جديدٍ لا يُصنَّف هنا (صحّيّ أو مستثنًى باسمه وسببه) يُسقطه.
"""

import pytest
from django.urls import URLPattern, URLResolver, get_resolver, reverse

from clinic.models import ClinicVisit
from core.models import AuditLog

# شاشاتٌ تعرض بياناً صحّيّاً فرديّاً: اسمُ المسار ← (طريقة بناء الرابط).
HEALTH_VIEWS = {
    "dashboard",
    "health_record",
    "visits_list",
}

# مستثناةٌ مسمّاةٌ بسببها: لا تعرض بياناً صحّيّاً فرديّاً من الطالب.
NON_HEALTH_VIEWS = {
    "needs_care_import": "رفعُ ملفٍّ فقط؛ الصفحةُ لا تعرض سجلّاً، والتقريرُ أعدادٌ",
    "record_visit": "نموذجُ إدخالٍ فيه أسماءُ الطلاب دون بيانٍ صحّيّ؛ والإنشاءُ يُدقَّق بإشارة post_save",
    "record_visit_student": "كسابقه بمعرّف طالبٍ في الرابط",
    "statistics": "أعدادٌ مجمَّعةٌ لا سجلٌّ فرديّ",
    "api_clinic_charts": "أعدادٌ يوميّةٌ مجمَّعةٌ بصيغة JSON",
}


def _clinic_url_names():
    names = set()

    def walk(patterns, ns):
        for p in patterns:
            if isinstance(p, URLResolver):
                walk(p.url_patterns, p.namespace or ns)
            elif isinstance(p, URLPattern) and ns == "clinic" and p.name:
                names.add(p.name)

    walk(get_resolver().url_patterns, None)
    return names


def test_every_clinic_route_is_classified():
    """مسارٌ جديدٌ في العيادة بلا تصنيفٍ (صحّيّ/مستثنًى) يفشل — فيُقرَّر تدقيقُه عمداً."""
    names = _clinic_url_names()
    assert names, "لم تُحلَّ روابط العيادة"
    unclassified = names - HEALTH_VIEWS - set(NON_HEALTH_VIEWS)
    assert not unclassified, f"مسارات عيادةٍ بلا تصنيف تدقيق: {sorted(unclassified)}"
    stale = (HEALTH_VIEWS | set(NON_HEALTH_VIEWS)) - names
    assert not stale, f"تصنيفٌ لمسارات غير موجودة: {sorted(stale)}"


@pytest.mark.django_db
class TestHealthScreensAreAudited:
    def _url(self, name, student):
        if name == "health_record":
            return reverse("clinic:health_record", args=[student.id])
        return reverse(f"clinic:{name}")

    @pytest.mark.parametrize("name", sorted(HEALTH_VIEWS))
    def test_open_leaves_audit_line_without_pii(
        self,
        client_as,
        nurse_user,
        student_user,
        enrolled_student,
        health_record,
        clinic_visit,
        name,
    ):
        client = client_as(nurse_user)
        before = AuditLog.objects.filter(user=nurse_user, action="view").count()

        response = client.get(self._url(name, student_user))
        assert response.status_code == 200

        lines = AuditLog.objects.filter(user=nurse_user, action="view").order_by("-timestamp")
        assert lines.count() == before + 1, f"الشاشة {name} لم تترك سطر تدقيق"
        line = lines.first()
        blob = f"{line.object_repr} {line.object_id} {line.changes}"
        assert student_user.full_name not in blob
        for visit in ClinicVisit.objects.all():
            for text in (visit.reason, visit.treatment):
                if text:
                    assert text not in blob

    def test_htmx_partial_is_audited_too(
        self, client_as, nurse_user, student_user, enrolled_student, clinic_visit
    ):
        cache.clear()
        client = client_as(nurse_user)
        before = AuditLog.objects.filter(user=nurse_user, action="view").count()
        response = client.get(reverse("clinic:visits_list"), HTTP_HX_REQUEST="true")
        assert response.status_code == 200
        assert AuditLog.objects.filter(user=nurse_user, action="view").count() == before + 1

    def test_live_search_is_throttled_to_one_line_per_minute(
        self, client_as, nurse_user, student_user, enrolled_student, clinic_visit
    ):
        cache.clear()
        client = client_as(nurse_user)
        before = AuditLog.objects.filter(user=nurse_user, action="view").count()
        for _ in range(5):
            client.get(reverse("clinic:visits_list"), HTTP_HX_REQUEST="true")
        assert AuditLog.objects.filter(user=nurse_user, action="view").count() == before + 1
        # فتحُ الصفحة الكاملة بعدها يُدقَّق ولا يخضع للتخفيف
        client.get(reverse("clinic:visits_list"))
        assert AuditLog.objects.filter(user=nurse_user, action="view").count() == before + 2

    def test_search_term_is_not_logged(
        self, client_as, nurse_user, student_user, enrolled_student, clinic_visit
    ):
        client = client_as(nurse_user)
        client.get(reverse("clinic:visits_list"), {"student": student_user.full_name})
        line = AuditLog.objects.filter(user=nurse_user, action="view").latest("timestamp")
        assert student_user.full_name not in f"{line.object_repr} {line.changes}"
