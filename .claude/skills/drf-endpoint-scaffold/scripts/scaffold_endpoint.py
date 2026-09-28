#!/usr/bin/env python3
"""
scaffold_endpoint.py — يولّد هيكلَ نقطة REST في SchoolOS بطبقاتها واختبارها، وفق أعراف المشروع.

الاستخدام (من جذر الشجرة؛ لا يحتاج Django):
    python .claude/skills/drf-endpoint-scaffold/scripts/scaffold_endpoint.py \
        --app transport --model BusRoute --name bus-routes \
        --fields id,name,area --permission IsStaffMember --readonly
    # كتابةٌ (إنشاءٌ idempotent بمفتاحٍ فريد):
    ... --app operations --model Subject --name subjects --fields id,name_ar,code \
        --write-fields name_ar,code --unique-key code --permission IsTeacherOrAdmin

يُنشئ ملفّين، ولا يلمس الملفّات المشتركة (api/urls.py، api/views.py …) — الدمجُ بيدك:
    <app>/_scaffold_<name>.py      كتلٌ معلَّمةٌ بوجهاتها؛ يتجاهله git (القاعدة `_*.py` في .gitignore)
    tests/test_<name>_api.py       حيث تعيش fixtures المشروع (tests/conftest.py)

كلُّ ما يحتاج قراراً منك يُفشل التشغيلَ حتّى يُكتب (NotImplementedError) — لا قيمةَ مؤقّتةٌ تبدو صالحة.
رمزُ الخروج: 0 نجاح، 2 خطأ في المُدخلات (تطبيقٌ/نموذجٌ/صلاحيّةٌ غيرُ موجودة، أو ملفٌّ قائم بلا --force).
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

# جذرُ الشجرة: scripts ← drf-endpoint-scaffold ← skills ← .claude ← الجذر
ROOT = Path(__file__).resolve().parents[4]

# من يُسمح له ومن يُمنع في الاختبار المولَّد، حسب fixtures في tests/conftest.py
ROLE_FIXTURES = {
    "IsTeacherOrAdmin": ("teacher_user", "student_user"),
    "IsSchoolAdmin": ("principal_user", "teacher_user"),
    "IsLeadership": ("principal_user", "teacher_user"),
    "IsStaffMember": ("teacher_user", "student_user"),
    "IsParentOrAdmin": ("parent_user", "teacher_user"),
}
NOT_A_ROLE = {"IsAuthenticated", "AllowAny"}


def fail(msg: str) -> int:
    print(f"خطأ: {msg}")
    return 2


def model_source(app: str, model: str) -> str | None:
    files = [ROOT / app / "models.py", *sorted((ROOT / app / "models").glob("*.py"))]
    for f in files:
        if f.exists():
            src = f.read_text(encoding="utf-8", errors="ignore")
            m = re.search(rf"(?ms)^class {re.escape(model)}\(.*?(?=^class |\Z)", src)
            if m:
                return m.group(0)
    return None


def api_permissions() -> set[str]:
    src = (ROOT / "api" / "permissions.py").read_text(encoding="utf-8", errors="ignore")
    return set(re.findall(r"^class (\w+)\(BasePermission\)", src, re.M))


def line_budget(rel: str) -> str:
    """سطورُ الملفّ مقابل سقف tests/file_size_ratchet.py — يُقرأ السقفُ حيّاً لا يُنسخ."""
    ratchet = ROOT / "tests" / "file_size_ratchet.py"
    m = re.search(r"^HARD_LIMIT\s*=\s*(\d+)", ratchet.read_text(encoding="utf-8"), re.M) if ratchet.exists() else None
    limit = int(m.group(1)) if m else 1000
    path = ROOT / rel
    n = len(path.read_text(encoding="utf-8").splitlines()) if path.exists() else 0
    return f"{rel}: {n} سطراً من {limit}"


def staging(a) -> str:
    model, name, ident = a.model, a.name, a.name.replace("-", "_")
    fields = ", ".join(f'"{f}"' for f in a.fields)
    order = f'\n        .order_by({", ".join(repr(o) for o in a.order_by)})' if a.order_by else ""
    view_base = "ListAPIView" if a.readonly else "ListCreateAPIView"
    write = ""
    create = ""
    if not a.readonly:
        wf = ", ".join(f'"{f}"' for f in a.write_fields)
        kwargs = ", ".join(f"{f}" for f in a.write_fields)
        defaults = ", ".join(f'"{f}": {f}' for f in a.write_fields if f != a.unique_key)
        write = f'''

# ══════ (ب) خدمةُ الكتابة → {a.app}/services.py أو حزمةُ services القائمة ══════
from django.db import transaction  # noqa: E402


class {model}Service:
    @staticmethod
    @transaction.atomic
    def create(school, *, {kwargs}) -> {model}:
        """إنشاءٌ idempotent: إعادةُ الإرسال لا تُنشئ صفّاً ثانياً.
        شرطُه قيدٌ فريدٌ في القاعدة على (school, {a.unique_key}) — بدونه يسبق طلبان متزامنان get_or_create."""
        obj, _created = {model}.objects.get_or_create(
            school=school, {a.unique_key}={a.unique_key}, defaults={{{defaults}}}
        )
        return obj


# ══════ (ج) serializer الكتابة → بجانب serializer العرض ══════
class {model}WriteSerializer(serializers.ModelSerializer):
    class Meta:
        model = {model}
        fields = [{wf}]  # لا "school" هنا أبداً: المدرسةُ من المستخدم لا من الطلب
'''
        create = f'''
    def get_serializer_class(self):
        return {model}WriteSerializer if self.request.method == "POST" else {model}Serializer

    def create(self, request, *args, **kwargs):
        ser = {model}WriteSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        obj = {model}Service.create(_school(request), **ser.validated_data)
        return Response({model}Serializer(obj).data, status=status.HTTP_201_CREATED)
'''
    return f'''"""
ملفُّ تجهيزٍ مؤقّت لنقطة /api/v1/{name}/ — وزّع الكتل على وجهاتها ثمّ احذفه.
يتجاهله git (`_*.py`)، فلن يظهر في git status: احذفه بيدك.
ولّدته مهارةُ drf-endpoint-scaffold.
"""
from __future__ import annotations

from django.db.models import QuerySet
from drf_spectacular.utils import extend_schema
{"from rest_framework import generics, serializers" if a.readonly else "from rest_framework import generics, serializers, status"}
{"" if a.readonly else "from rest_framework.response import Response"}
from api.pagination import StandardPagination
from api.permissions import {a.permission}
from api.views import _school  # مدرسةُ المستخدم: request.user.get_school()
from {a.app}.models import {model}


# ══════ (أ) selector القراءة → {a.app}/selectors.py (أو selectors المجال القائم) ══════
def {ident}_for_school(school) -> QuerySet[{model}]:
    """القائمةُ مقيّدةٌ بالمدرسة. أضِف select_related/prefetch_related لكلّ علاقةٍ يقرؤها الـserializer."""
    return (
        {model}.objects.filter({a.school_path}=school)
        # .select_related(...)    ← FK/OneToOne يقرؤها الـserializer
        # .prefetch_related(...)  ← M2M/علاقةٌ عكسيّة{order}
    )


# ══════ serializer العرض → الوحدةُ نفسُها مع الـview (السابقة: api/views_erasure.py) ══════
class {model}Serializer(serializers.ModelSerializer):
    class Meta:
        model = {model}
        fields = [{fields}]  # صريحةٌ دائماً؛ PII بمبرّرٍ فقط (مهارةُ pdppl-pii-audit)
{write}

# ══════ (د) view → api/views_{ident}.py جديدة ({line_budget("api/views.py")}) ══════
class {model}ListView(generics.{view_base}):
    serializer_class = {model}Serializer
    permission_classes = [{a.permission}]  # تستبدل الافتراضيّ IsAuthenticated؛ وهي تفحص المصادقةَ نفسَها
    pagination_class = StandardPagination

    @extend_schema(summary="<عنوان عربيّ للنقطة>", tags=["{name}"])
    def get(self, *args, **kwargs):
        return super().get(*args, **kwargs)

    def get_queryset(self):
        return {ident}_for_school(_school(self.request))
{create}

# ══════ (هـ) المسار → api/urls.py (بادئةُ /api/v1/ من shschool/urls.py) ══════
# from . import views_{ident}
# path("{name}/", views_{ident}.{model}ListView.as_view(), name="{name}-list"),
'''


def test_file(a) -> str:
    allowed, denied = ROLE_FIXTURES.get(a.permission, ("<fixture الدور المسموح>", "student_user"))
    create_tests = ""
    if not a.readonly:
        create_tests = f'''

def payload() -> dict:
    """حقولُ الإنشاء الصالحة — يُفشل الاختبارَ حتّى تُكتب."""
    raise NotImplementedError("اكتب حمولةً صالحة لـ{a.model}: {", ".join(a.write_fields)}")


def test_create_is_idempotent(school, {allowed}):
    client = _client({allowed})
    first = client.post(URL, payload(), content_type="application/json")
    second = client.post(URL, payload(), content_type="application/json")
    assert first.status_code == 201, first.content
    assert second.status_code == 201, second.content
    assert first.json()["id"] == second.json()["id"]


def test_school_cannot_be_injected(school, {allowed}):
    other = SchoolFactory()
    body = {{**payload(), "school": str(other.pk)}}
    created = _client({allowed}).post(URL, body, content_type="application/json")
    assert created.status_code == 201, created.content
    assert not {a.model}.objects.filter(school=other).exists()
'''
    model_import = f"from {a.app}.models import {a.model}\n" if not a.readonly else ""
    return f'''"""/api/v1/{a.name}/ — الصلاحيّة، وعزلُ المدرسة، وثباتُ عدد الاستعلامات{"، وidempotency" if not a.readonly else ""}.

ولّدته مهارةُ drf-endpoint-scaffold. ما عليه NotImplementedError يُكتب قبل أن يخضرّ.
الدخولُ بـforce_login (جلسة) لا force_authenticate: وسيطُ المنصّة يردّ /api/ بـ401 قبل DRF لمن لا جلسةَ له.
"""

import pytest
from django.db import connection
from django.test import Client
from django.test.utils import CaptureQueriesContext

{model_import}from tests.conftest import SchoolFactory

pytestmark = pytest.mark.django_db
URL = "/api/v1/{a.name}/"


def make_row(school):
    """صفٌّ من {a.model} في المدرسة المعطاة — يُفشل الاختباراتِ حتّى يُكتب (مصنعٌ في tests/conftest.py أفضل)."""
    raise NotImplementedError("اكتب إنشاءَ {a.model} للمدرسة المعطاة")


def _client(user):
    client = Client()
    client.force_login(user)
    return client


def test_anonymous_gets_401():
    assert Client().get(URL).status_code == 401


def test_role_without_permission_gets_403({denied}):
    assert _client({denied}).get(URL).status_code == 403


def test_other_school_rows_are_invisible(school, {allowed}):
    mine, theirs = make_row(school), make_row(SchoolFactory())
    response = _client({allowed}).get(URL)
    assert response.status_code == 200
    ids = {{row["id"] for row in response.json()["results"]}}
    assert str(mine.pk) in ids
    assert str(theirs.pk) not in ids


def test_query_count_does_not_grow_with_rows(school, {allowed}):
    """نمطُ tests/test_n_plus_one_queries.py: إحماءٌ، ثمّ صفٌّ واحد مقابل ثلاثة — لا رقمَ ثابتاً يتقادم."""
    client = _client({allowed})
    make_row(school)
    client.get(URL)
    with CaptureQueriesContext(connection) as one:
        assert client.get(URL).status_code == 200
    make_row(school)
    make_row(school)
    with CaptureQueriesContext(connection) as three:
        assert client.get(URL).status_code == 200
    assert len(three) == len(one), [q["sql"] for q in three.captured_queries]
{create_tests}'''


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):  # طرفيّةُ ويندوز
        sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="مولّد نقاط SchoolOS الطرفيّة")
    ap.add_argument("--app", required=True, help="مجلّدُ التطبيق الذي فيه النموذج")
    ap.add_argument("--model", required=True, help="اسمُ صنف النموذج القائم")
    ap.add_argument("--name", required=True, help="مقطعُ المسار: جمعٌ بأحرفٍ صغيرة وشرطات (bus-routes)")
    ap.add_argument("--fields", required=True, help="حقولُ العرض مفصولةً بفواصل (لا __all__)")
    ap.add_argument("--permission", default="IsTeacherOrAdmin", help="صنفٌ من api/permissions.py")
    ap.add_argument("--school-path", default="school", help="مسارُ المدرسة في الاستعلام (مثل class_group__school)")
    ap.add_argument("--order-by", default="", help="ترتيبٌ صريح مفصولٌ بفواصل؛ الفراغُ = Meta.ordering")
    ap.add_argument("--readonly", action="store_true")
    ap.add_argument("--write-fields", default="", help="حقولُ الإنشاء (بلا school)")
    ap.add_argument("--unique-key", default="", help="حقلٌ فريدٌ مع school يجعل الإنشاءَ idempotent")
    ap.add_argument("--force", action="store_true", help="اكتب فوق ملفّاتٍ قائمة")
    a = ap.parse_args()
    a.fields = [f.strip() for f in a.fields.split(",") if f.strip()]
    a.write_fields = [f.strip() for f in a.write_fields.split(",") if f.strip()]
    a.order_by = [f.strip() for f in a.order_by.split(",") if f.strip()]

    if not (ROOT / a.app).is_dir():
        return fail(f"التطبيق غير موجود: {ROOT / a.app}")
    src = model_source(a.app, a.model)
    if src is None:
        return fail(f"لا صنفَ {a.model} في {a.app}/models.py ولا {a.app}/models/*.py")
    perms = api_permissions()
    if a.permission not in perms | NOT_A_ROLE:
        return fail(f"صلاحيّةٌ غير معروفة {a.permission}؛ المتاح: {', '.join(sorted(perms))}")
    if "__all__" in a.fields or "school" in a.write_fields:
        return fail("لا __all__ في الحقول، ولا school في حقول الإنشاء (عزلُ المدارس).")
    if not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", a.name):
        return fail("--name بأحرفٍ صغيرةٍ وأرقامٍ وشرطاتٍ فقط (مثل bus-routes).")
    if not a.readonly:
        if not a.write_fields or not a.unique_key:
            return fail("الإنشاءُ يحتاج --write-fields و--unique-key (أو --readonly).")
        if a.unique_key not in a.write_fields:
            return fail("--unique-key يجب أن يكون من --write-fields.")
        if "__" in a.school_path:
            return fail("الإنشاءُ على نموذجٍ مدرستُه عبر علاقة يحتاج خدمةً تُكتب يدويّاً — ولِّد --readonly.")

    stage = ROOT / a.app / f"_scaffold_{a.name.replace('-', '_')}.py"
    test = ROOT / "tests" / f"test_{a.name.replace('-', '_')}_api.py"
    for f in (stage, test):
        if f.exists() and not a.force:
            return fail(f"الملفُّ قائم: {f.relative_to(ROOT).as_posix()} (--force للكتابة فوقه)")
    stage.write_text(staging(a), encoding="utf-8")
    test.write_text(test_file(a), encoding="utf-8")

    print(f"الصواب: ولّدتُ نقطة /api/v1/{a.name}/")
    print(f"   التجهيز:  {stage.relative_to(ROOT).as_posix()}  (يتجاهله git — احذفه بعد التوزيع)")
    print(f"   الاختبار: {test.relative_to(ROOT).as_posix()}")
    if a.permission in NOT_A_ROLE:
        print(f"تنبيه:  {a.permission} ليست فحصَ دور: tests/test_every_route_is_guarded.py سيُسقط المسار ما لم يُسمَّ سببُه هناك.")
    if not a.readonly and not re.search(rf"unique=True|UniqueConstraint\([^)]*{re.escape(a.unique_key)}", src):
        print(f"تنبيه:  لا قيدَ فريد ظاهرٌ على {a.unique_key} في {a.model}: get_or_create وحده لا يمنع التكرار عند التزامن "
              "— أضِف UniqueConstraint(fields=['school', ...]) بهجرة (مهارة schoolos-migration-guard).")
    inherits_ordering = re.search(r"(TimeStamped|SchoolScoped|Audited|SoftDelete)Model", src.splitlines()[0])
    if not a.order_by and not inherits_ordering and not re.search(r"^\s+ordering\s*=", src, re.M):
        print(f"تنبيه:  {a.model} بلا Meta.ordering ولم تمرّر --order-by: الترقيمُ على قائمةٍ بلا ترتيب قد يكرّر صفوفاً "
              "ويُسقط أخرى بين الصفحات (UnorderedObjectListWarning) — أعِد التوليد بـ--order-by.")
    if a.school_path == "school" and not re.search(r"\bschool\s*=\s*models\.(ForeignKey|OneToOneField)", src) \
            and "SchoolScopedModel" not in src:
        print(f"تنبيه:  لا حقلَ school مباشرٌ ظاهرٌ في {a.model}: مرّر --school-path الصحيح (مثل class_group__school).")
    print("   الخطوات: وزّع الكتل ← اكتب ما عليه NotImplementedError ← شغّل الاختبار في حاوية الجلسة ← احذف ملفّ التجهيز.")
    print(f"   {line_budget('api/views.py')} · {line_budget('api/serializers.py')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
