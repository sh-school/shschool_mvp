"""[SECURITY] كلُّ رابطٍ تعرضه القائمةُ لدورٍ يفتحه ذلك الدور.

القائمةُ الجانبيّةُ في `templates/base/base.html` ملاحةٌ منسَّقةٌ بيد: القيادةُ ترى
سبعَ قوائمَ منسدلة، وبقيّةُ الأدوار روابطَ عميقةً داخل الوحدات (الممرّضُ يرى
«سجلّ الزيارات» و«تسجيل زيارة» لا «العيادة» وحدَها). وسجلُّ الوحدات يعرف ثمانيَ
عشرةَ وحدةً مسطّحةً برابطٍ واحدٍ لكلٍّ — فلا يولّد هذه الملاحةَ ولا يُقاس بها.

**فالمحروسُ هنا ليس أن تُبنى القائمةُ من السجلّ، بل ألّا تَعِد بما لا يُفتح.**
ورابطٌ يُفضي إلى ٤٠٣ أسوأُ من رابطٍ غائب: الغائبُ لا يَعِد، والموجودُ يَعِد
ويُخلف — ويقرؤه المستخدمُ عطلاً في المنصّة لا قاعدةً في الصلاحيّات.

وهذا الحارسُ كان سيكشف عيبَ النائب الأكاديميّ في `/library/` و`/breach/` قبل أن
يُقاس، وعيبَ أخصائيَّي النطق والعلاج في `/quality/`.

**حدودُه بوضوح:** يفحص **الردَّ بـ٤٠٣ وحدَه**. فالرابطُ الذي يعطي ٤٠٤ أو ٥٠٠
لنقصِ بياناتٍ في بيئة الاختبار ليس كذباً في الصلاحيّة، وحراستُه شأنُ اختباراتِ
تلك الوحدة لا هذا الملفّ.
"""

import re

import pytest

from tests.conftest import MembershipFactory, RoleFactory, UserFactory

#: الأدوارُ التي لها فرعٌ في القائمة — مأخوذةٌ من `base.html` حرفاً، وممثَّلٌ
#: لكلّ فرعٍ بدورٍ واحد. و`platform_developer` فرعُ `else` الذي يرث قائمةَ المدير.
ROLES_WITH_A_BRANCH = [
    "principal",
    "vice_admin",
    "vice_academic",
    "coordinator",
    "teacher",
    "ese_teacher",
    "teacher_assistant",
    "e_projects_coordinator",
    "nurse",
    "librarian",
    "bus_supervisor",
    "transport_officer",
    "social_worker",
    "psychologist",
    "academic_advisor",
    "speech_therapist",
    "activities_coordinator",
    "admin",
    "secretary",
    "admin_supervisor",
    "it_technician",
    "receptionist",
    "platform_developer",
    "student",
]

#: «إجراءاتي» تُعرض لأدوارٍ لا يقبلها حارسُ الجودة — وليست رابطاً خاطئاً بل عملاً
#: حقيقيّاً: الشاشةُ تعرض لكلّ مستخدمٍ إجراءاتِه هو (`get_my_procedures(request.user)`)،
#: والخطّةُ التشغيليّةُ تُسند إجراءاتٍ للسكرتير نفسِه (المؤشّر 5.9). ففتحُ الرابط
#: وحدَه لا يكفي — منه تُفتح تفاصيلُ الإجراء وتحديثُ حالته ورفعُ الشاهد بالحارس
#: نفسِه — والحلُّ صلاحيّةٌ **بمنفِّذ الإجراء لا بالدور**، تصميمٌ مستقلّ.
#:
#: دَينٌ مُقَرٌّ به حتّى يُحسم (2026-09-12)، لا بابٌ لقبول أمثاله.
KNOWN_EXECUTOR_GAP = {
    ("admin", "/quality/my-procedures/"),
    ("secretary", "/quality/my-procedures/"),
    ("admin_supervisor", "/quality/my-procedures/"),
    ("receptionist", "/quality/my-procedures/"),
}

_ANCHOR = re.compile(r"<a\b[^>]*>", re.S)
_HREF = re.compile(r'href="([^"]+)"')


def _navigation_links(html: str) -> set[str]:
    """روابطُ الملاحة وحدَها: شريطُ القائمة (`class="nb"`) ولوحاتُها (`role="menuitem"`).

    ولا تُؤخذ روابطُ متن الصفحة — فهي وعدُ شاشةٍ لا وعدُ ملاحة، ولكلٍّ حارسُه.
    """
    links = set()
    for tag in _ANCHOR.findall(html):
        if 'class="nb"' not in tag and 'role="menuitem"' not in tag:
            continue
        found = _HREF.search(tag)
        if not found:
            continue
        href = found.group(1).split("?")[0].split("#")[0]
        if href.startswith("/") and not href.startswith("//"):
            links.add(href)
    return links


@pytest.fixture
def user_in_role(db, school):
    def _make(role_name):
        role = RoleFactory(school=school, name=role_name)
        user = UserFactory(full_name=f"صاحبُ دور {role_name}")
        MembershipFactory(user=user, school=school, role=role)
        return user

    return _make


@pytest.mark.parametrize("role_name", ROLES_WITH_A_BRANCH)
def test_no_link_in_the_menu_is_refused_to_whoever_sees_it(role_name, user_in_role, client_as):
    client = client_as(user_in_role(role_name))
    page = client.get("/dashboard/", follow=True)
    assert page.status_code != 403, f"«{role_name}» مردودٌ عن اللوحة نفسِها"
    assert page.status_code != 500, (
        f"«{role_name}» لوحتُه تسقط بخطأ خادم — ولا يُقاس ما لا يُعرض. "
        "وقد وقع مرّتين: استعلامُ الحافلات بحقلٍ لا وجودَ له، ونطاقُ مسارٍ غيرُ مسجَّل"
    )

    links = _navigation_links(page.content.decode())
    refused = sorted(
        href
        for href in links
        if (role_name, href) not in KNOWN_EXECUTOR_GAP
        and client.get(href, follow=True).status_code == 403
    )

    assert not refused, f"«{role_name}» تعرض له القائمةُ روابطَ يردُّه عنها الحارس: " + " · ".join(
        refused
    )


def test_the_menu_is_not_empty_for_staff(user_in_role, client_as):
    """حارسٌ للحارس: لو لم تُستخرَج روابطُ لمرّ الاختبارُ أعلاه بلا فحص."""
    page = client_as(user_in_role("teacher")).get("/dashboard/", follow=True)
    assert len(_navigation_links(page.content.decode())) >= 3


@pytest.mark.parametrize("role_name,href", sorted(KNOWN_EXECUTOR_GAP))
def test_the_known_executor_gap_is_still_open(role_name, href, user_in_role, client_as):
    """الدَّينُ ظاهرٌ في كلّ تشغيل — وحين يُسدّ يفشل هذا فيُحذف من المجموعة."""
    client = client_as(user_in_role(role_name))
    if client.get(href, follow=True).status_code != 403:
        pytest.fail(f"«{role_name}» بلغ {href} — سُدّ الدَّين، فاحذفه من `KNOWN_EXECUTOR_GAP`")
    pytest.xfail(f"«{role_name}» لا يبلغ {href} — صلاحيّةُ منفِّذ الإجراء لم تُبنَ")
