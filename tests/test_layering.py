"""[LAYERING] سقّاطةُ الطبقات — راجع `tests/layering_ratchet.py` للسبب والطريقة.

كانت الدوالُّ هنا تأخذ `update=False` وتُرجع `False` عند المخالفة: pytest لا يعدّ
القيمةَ المُرجعة سقوطاً، فكانت «4 passed» والحارسُ نفسُه يطبع `FAIL` لثلاثة عروض.
فالحكمُ الآن `assert`، والقياسُ والمقارنةُ في وحدةٍ لا يجمعها pytest.
"""

import json

import pytest

from tests import layering_ratchet as ratchet

UPDATE = "python -m tests.layering_ratchet --update"


def _baseline():
    return json.loads(ratchet.BASELINE.read_text(encoding="utf-8"))


def _worse_and_stale():
    return ratchet.compare(_baseline(), ratchet.snapshot())


def test_no_view_file_or_core_module_grows_past_its_record():
    worse, _stale = _worse_and_stale()
    assert not worse, (
        "زادت مخالفاتُ الطبقات — انقل القراءةَ إلى `selectors.py` والكتابةَ إلى `services.py`، "
        "واقرأ `request.school`، ولا تستورد نازلاً في core:\n  " + "\n  ".join(worse)
    )


def test_improvements_are_recorded_so_they_cannot_be_spent_again():
    _worse, stale = _worse_and_stale()
    assert not stale, (
        f"نقصت مخالفاتٌ ولم يُثبَّت نقصُها — أحسنت؛ ثبّته بـ `{UPDATE}` وأودع السجلّ:\n  "
        + "\n  ".join(stale)
    )


def test_baseline_records_only_what_is_over_the_caps():
    """سطرٌ تحت السقف في السجلّ رخصةٌ لعرضٍ أن يكبر إليه دون أن يُرى."""
    baseline = _baseline()
    for key, metrics in baseline["views"].items():
        assert metrics.get("lines", ratchet.MAX_LINES + 1) > ratchet.MAX_LINES, key
        assert metrics.get("orm", ratchet.MAX_ORM + 1) > ratchet.MAX_ORM, key
    assert all(v > 0 for v in baseline["get_school"].values())


def test_every_accepted_increase_says_why():
    """القبولُ بندٌ باسمه وسببه — لا سطرٌ بلا تعليل يُمرَّر في طلب دمج."""
    for item in _baseline().get("accepted", []):
        assert set(item) == {"where", "metric", "from", "to", "reason"}, item
        assert item["to"] > item["from"], item
        assert len(item["reason"].strip()) >= ratchet.MIN_REASON, item


class TestTheRatchetItself:
    """الحارسُ يحرس ما يقول إنّه يحرسه — لا يمرّ صامتاً على ما وُضع له."""

    EMPTY: dict = {"views": {}, "get_school": {}, "core_imports": {}, "core_import_sites": {}}

    def _state(self, **kw):
        return {**self.EMPTY, **kw}

    # ── القياس ──

    def test_a_long_view_is_measured_from_def_without_decorators(self):
        body = "\n".join(f"    x{i} = {i}" for i in range(ratchet.MAX_LINES))
        source = f"@login_required\n@require_GET\ndef long_view(request):\n{body}\n"
        over, _ = ratchet.measure_views(source, "app/views.py")
        assert over == {"app/views.py::long_view": {"lines": ratchet.MAX_LINES + 1}}

    def test_orm_calls_are_counted_in_code_not_in_comments_or_strings(self):
        source = (
            "def v(request):\n"
            "    # Student.objects.filter(a).filter(b)\n"
            '    """.filter( .annotate( Q("""\n'
            "    qs = Student.objects.filter(a=1).select_related('x').prefetch_related('y')\n"
            "    qs = qs.annotate(n=Count('id')).filter(Q(b=1) | models.Q(c=2))\n"
            "    return qs.aggregate(s=Sum('n'))\n"
        )
        over, _ = ratchet.measure_views(source, "a/views.py")
        # objects, filter, select_related, prefetch_related, annotate, filter, Q, Q, aggregate
        assert over == {"a/views.py::v": {"orm": 9}}

    def test_a_helper_without_request_is_measured_too(self):
        """نقلُ الاستعلام إلى مساعدٍ في ملفّ العروض نفسِه لا يُخفيه."""
        orm = "\n".join("    X.objects.filter" for _ in range(ratchet.MAX_ORM + 1))
        over, _ = ratchet.measure_views(
            f"def _get_director_ctx(school, today):\n{orm}\n", "c/views.py"
        )
        assert over == {"c/views.py::_get_director_ctx": {"orm": ratchet.MAX_ORM + 1}}

    def test_class_based_view_methods_and_multiline_signatures_are_views(self):
        calls = ratchet.MAX_ORM + 1
        in_function = "\n".join("    X.objects.all()" for _ in range(calls))
        in_method = "\n".join("        X.objects.all()" for _ in range(calls))
        source = (
            f"def multi(\n    request,\n    pk,\n):\n{in_function}\n\n"
            f"class Page(View):\n    def get(self, request, *a):\n{in_method}\n\n"
            f"def helper(user):\n{in_function}\n"
        )
        over, _ = ratchet.measure_views(source, "a/views.py")
        assert set(over) == {"a/views.py::multi", "a/views.py::Page.get", "a/views.py::helper"}

    def test_get_school_is_counted_across_the_whole_view_file(self):
        """نقلُه إلى دالّةٍ مساعدةٍ بلا `request` لا يُخفيه."""
        source = (
            "def _school(user):\n    return user.get_school()\n"
            "def v(request):\n    return request.user.get_school()\n"
        )
        _, calls = ratchet.measure_views(source, "a/views.py")
        assert calls == 2

    def test_lazy_imports_in_core_count_as_downstream(self):
        source = (
            "from core.models import School\n"
            "import analytics.services\n"
            "def f():\n    from behavior.models import X\n    from behavior import y\n"
        )
        found = ratchet.measure_core_imports(source, frozenset({"analytics", "behavior"}))
        assert found == {"analytics": 1, "behavior": 2}

    def test_only_app_packages_are_scanned(self, tmp_path):
        """نسخةٌ مؤقّتةٌ في مجلّدٍ مخفيّ (`.local/views_x.py`) ليست ملفَّ عروض."""
        for folder, package in (("app", True), (".local", False)):
            (tmp_path / folder).mkdir()
            (tmp_path / folder / "views.py").write_text("", encoding="utf-8")
            if package:
                (tmp_path / folder / "__init__.py").write_text("", encoding="utf-8")
        assert [p.parent.name for p in ratchet.view_files(tmp_path)] == ["app"]

    def test_every_app_but_core_is_downstream(self):
        apps = ratchet.downstream_apps()
        assert {"student_affairs", "analytics", "wings", "api"} <= apps
        assert not apps & {"core", "shschool", "tests"}

    def test_writes_shortcuts_and_related_managers_count_as_orm(self):
        """الكتابةُ في العرض لا تمرّ تحت السقف لأنّها لا تبدأ بـ`.filter(`."""
        source = (
            "def transfer_review(request, pk):\n"
            "    transfer = get_object_or_404(StudentTransfer, pk=pk)\n"
            "    rows = transfer.student.enrollments.exclude(x=1).order_by('y').values_list('id')\n"
            "    transfer.save()\n"
            "    Membership.objects.filter(a=1).update(is_active=False)\n"
            "    return rows\n"
        )
        over, _ = ratchet.measure_views(source, "a/views.py")
        # get_object_or_404, exclude, order_by, values_list, save, objects, filter, update
        assert over == {"a/views.py::transfer_review": {"orm": 8}}

    def test_aliases_of_a_manager_or_of_q_do_not_hide_calls(self):
        source = (
            "from django.db.models import Q as W\n"
            "def v(request):\n"
            "    m = Student.objects\n"
            "    a = m.get(pk=1)\n"
            "    b = m.create(name='x')\n"
            "    m.count()\n"
            "    return W(a=1) | W(b=2)\n"
        )
        over, _ = ratchet.measure_views(source, "a/views.py")
        # objects, get, create, count, W, W
        assert over == {"a/views.py::v": {"orm": 6}}

    def test_related_managers_and_instance_writes_count_as_orm(self):
        """التعريفُ الرابع: مديرٌ مرتبطٌ على مستقبِلٍ مجهول، وحفظُ نسخةٍ مُنشأة، وتفكيكُ الصفّ."""
        source = (
            "from core.models import Cover\n"
            "from .forms import NoteForm\n"
            "def v(request, s):\n"
            "    s.enrollments.create(a=1)\n"
            "    s.enrollments.get(pk=1)\n"
            "    s.enrollments.count()\n"
            "    s.enrollments.exists()\n"
            "    s.enrollments.first()\n"
            "    s.notes.values('a')\n"
            "    s.photo_set.update(c=3)\n"
            "    o = Cover(a=1)\n"
            "    o.save()\n"
            "    Cover(a=2).save()\n"
            "    x, created = Cover.objects.get_or_create(a=3)\n"
            "    x.save()\n"
            "    x.delete()\n"
            "    [r.save() for r in Cover.objects.all()]\n"
            "    if (w := Cover.objects.first()):\n"
            "        w.save()\n"
            "    request.user.save()\n"
            "    form = NoteForm(request.POST)\n"
            "    note = form.save(commit=False)\n"
            "    note.save()\n"
            "    return None\n"
        )
        over, _ = ratchet.measure_views(source, "a/views.py")
        # create get count exists first values update (7) · o.save · Cover().save (9)
        # objects get_or_create x.save x.delete (13) · save objects all (16)
        # objects first w.save (19) · request.user.save (20) · note.save (21) — لا commit=False
        assert over == {"a/views.py::v": {"orm": 21}}

    def test_form_file_and_dict_like_calls_are_not_orm(self):
        """ما يشبه المديرَ المرتبط ولا يقرأ القاعدة: قاموسُ المصنّف والطلب، والمسار، والمصنَّف."""
        lines = [
            "form.cleaned_data.get('x')",
            "request.GET.get('q')",
            "request.session.delete('k')",
            "request.resolver_match.kwargs.get('pk')",
            "os.path.exists(path)",
            "wb.save(path)",
            "err.message_dict.values()",
            "name.count('a')",
        ]
        # ستُّ نسخٍ من كلٍّ منها: لو عُدّ واحدٌ لتجاوز السقف.
        body = "".join(f"    {line}\n" for line in lines * (ratchet.MAX_ORM + 1))
        source = f"def v(request, wb, path, err, name):\n    form = NoteForm(request.POST)\n{body}"
        over, _ = ratchet.measure_views(source, "a/views.py")
        assert over == {}

    def test_splitting_queries_over_same_file_helpers_does_not_hide_them(self):
        """التعريفُ الرابع: العرضُ يُحمَّل استعلاماتِ مساعديه في الملفّ نفسِه، ولو تسلسلت."""
        two = "    X.objects.filter()\n"  # اثنان: objects وfilter
        source = (
            f"def _a():\n{two}{two}"
            f"def _b():\n{two}    _c()\n"
            f"def _c():\n{two}"
            f"def view(request):\n    _a()\n    _b()\n    _a()\n{two}"
            "class Page(View):\n"
            f"    def _part(self):\n    {two}    {two}"
            "    def get(self, request):\n        self._part()\n        return _a()\n"
        )
        over, _ = ratchet.measure_views(source, "a/views.py")
        # view: نفسُه 2 + _a 4 + _b 2 + _c 2 = 10 — و_a مرّةً: شيفرةٌ لا تنفيذ
        # Page.get: _part 4 + _a 4 = 8؛ و_b: 2 + 2 = 4 تحت السقف
        assert over == {"a/views.py::view": {"orm": 10}, "a/views.py::Page.get": {"orm": 8}}

    def test_helpers_in_selectors_are_not_charged_to_the_view(self, tmp_path):
        """النقلُ إلى `selectors.py` هو الترحيل — لا يُحمَّل؛ والنقلُ إلى ملفّ عروضٍ آخر يُحمَّل."""
        app = tmp_path / "app"
        app.mkdir()
        body = "".join("    X.objects.filter()\n" for _ in range(3))
        for name, text in (
            ("__init__.py", ""),
            ("selectors.py", f"def rows():\n{body}"),
            ("views_common.py", f"def _rows():\n{body}"),
            (
                "views.py",
                "from .selectors import rows\nfrom .views_common import _rows\n"
                "def a(request):\n    return rows()\n"
                "def b(request):\n    return _rows()\n",
            ),
        ):
            (app / name).write_text(text, encoding="utf-8")
        assert ratchet.snapshot(tmp_path)["views"] == {
            "app/views.py::b": {"orm": 6},
            "app/views_common.py::_rows": {"orm": 6},
        }

    def test_get_school_wrappers_count_at_every_call_site(self):
        """غلافٌ في الملفّ يُعدّ حيث يُستدعى، ومثلُه الاسمُ المستعارُ وgetattr."""
        source = (
            "def _get_school(request):\n"
            "    if hasattr(request.user, 'get_school'):\n"
            "        return request.user.get_school()\n"
            "    return None\n"
            "def _school(request):\n    return _get_school(request)\n"
            "def v1(request):\n    school = _get_school(request)\n"
            "def v2(request):\n    return _school(request)\n"
            "def v3(request):\n    return getattr(request.user, 'get_school')()\n"
            "def v4(request):\n    g = request.user.get_school\n    return g()\n"
            "def not_a_wrapper(user):\n    school = user.get_school()\n    return 2026\n"
            "def v5(request):\n    return not_a_wrapper(request.user)\n"
            "class Page(View):\n"
            "    def _school(self):\n        return self.request.user.get_school()\n"
            "    def get(self, request):\n        return self._school()\n"
        )
        _, calls = ratchet.measure_views(source, "a/views.py")
        # الغلافُ 1، واستدعاؤه في _school وv1 (3)، و_school في v2 (4)، وgetattr (5)،
        # والمستعار (6)، وnot_a_wrapper نفسُه لا مَن يستدعيه (7)، وتابعُ الصنف ومستدعيه (9)
        assert calls == 9

    def test_get_school_wrappers_imported_from_the_app_count_too(self, tmp_path):
        app = tmp_path / "app"
        app.mkdir()
        (app / "__init__.py").write_text("", encoding="utf-8")
        (app / "utils.py").write_text(
            "def school_of(request):\n    return request.user.get_school()\n"
            "def year_of(request):\n    return 2026\n",
            encoding="utf-8",
        )
        (app / "views.py").write_text(
            "from .utils import school_of, year_of\n"
            "import app.utils as u\n"
            "def a(request):\n    return school_of(request)\n"
            "def b(request):\n    return u.school_of(request), year_of(request)\n",
            encoding="utf-8",
        )
        assert ratchet.snapshot(tmp_path)["get_school"] == {"app/views.py": 2}

    def test_dynamic_imports_in_core_count_as_downstream(self):
        source = (
            "import importlib\n"
            "from django.apps import apps\n"
            "def f():\n"
            "    __import__('operations.models', fromlist=['X'])\n"
            "    importlib.import_module('behavior.models')\n"
            "    apps.get_model('clinic', 'Visit')\n"
            "    apps.get_model('clinic.Visit')\n"
            "    import_string('behavior.services.x')\n"
            "    apps.get_model('core', 'School')\n"
        )
        found = ratchet.measure_core_imports(
            source, frozenset({"operations", "behavior", "clinic"})
        )
        assert found == {"behavior": 2, "clinic": 2, "operations": 1}

    def test_dict_list_and_request_methods_are_not_orm(self):
        """`.get(` و`.update(` و`.values(` تُعدّ على ما جاء من ORM وحده."""
        source = (
            "def v(request):\n"
            "    ctx = {}\n"
            "    ctx.update(a=1)\n"
            "    q = request.GET.get('q')\n"
            "    request.session.get('x')\n"
            "    items = [1, 2]\n"
            "    items.count(1)\n"
            "    data = Student.objects.aggregate(n=Count('id'))\n"
            "    data.get('n')\n"
            "    data.values()\n"
            "    data.update(m=1)\n"
            "    return ctx.values()\n"
        )
        over, _ = ratchet.measure_views(source, "a/views.py")
        assert over == {}  # objects و aggregate — اثنان

    def test_files_named_something_views_are_view_files(self, tmp_path):
        """`api_views.py` و`assignment_views.py` ملفّاتُ عروض كـ`views_swap.py`."""
        app = tmp_path / "app"
        (app / "views").mkdir(parents=True)
        for name in ("__init__.py", "views.py", "views_swap.py", "api_views.py", "reviews.py"):
            (app / name).write_text("", encoding="utf-8")
        (app / "views" / "pages.py").write_text("", encoding="utf-8")
        found = sorted(p.relative_to(tmp_path).as_posix() for p in ratchet.view_files(tmp_path))
        assert found == [
            "app/api_views.py",
            "app/views.py",
            "app/views/pages.py",
            "app/views_swap.py",
        ]

    def test_the_projects_suffixed_view_files_are_scanned(self):
        found = {p.relative_to(ratchet.ROOT).as_posix() for p in ratchet.view_files()}
        assert {
            "academic_management/assignment_views.py",
            "operations/api_views.py",
            "quality/evaluation_views.py",
            "quality/observation_views.py",
        } <= found

    def test_querysets_returned_by_a_helper_are_counted_where_they_are_evaluated(self, tmp_path):
        """التعريفُ الخامس: `qs = rows()` من قارئٍ يُرجع QuerySet — عدُّه وقراءتُه وكتابتُه في العرض تُعدّ.

        نُقل بناءُ الاستعلام إلى `selectors.py` وبقي في `_get_therapist_ctx` العدُّ عليه
        (`sessions_today.count()`)، فنقص العدّادُ ولم ينقص عددُ الاستعلامات.
        """
        app = tmp_path / "app"
        app.mkdir()
        (app / "__init__.py").write_text("", encoding="utf-8")
        (app / "selectors.py").write_text(
            "def rows(school):\n    return X.objects.filter(school=school)\n"
            "def summary(school):\n    return {'n': 1}\n"
            "def total(school):\n    return X.objects.filter(school=school).count()\n"
            "def maybe(school):\n    return rows(school) if school else None\n",
            encoding="utf-8",
        )
        dict_calls = "".join(
            "    d.get('n')\n    d.update(m=1)\n    d.values()\n" for _ in range(6)
        )
        (app / "views.py").write_text(
            "from .selectors import rows, summary, total, maybe\n"
            "def v(request):\n"
            "    qs = rows(request.school)\n"
            "    qs.count()\n    qs.first()\n    qs.get(pk=1)\n    qs.exists()\n"
            "    qs.update(a=1)\n    qs.delete()\n    qs.last()\n"
            "    return qs\n"
            "def w(request):\n"
            "    d = summary(request.school)\n"
            "    n = total(request.school)\n"
            f"{dict_calls}"
            "    return n\n"
            "def u(request):\n"
            "    maybe(request.school).values('a')\n"
            "    for row in rows(request.school):\n        row.save()\n"
            "    q = _base()\n    q.count()\n    q.values('b')\n"
            "    return q.exists()\n"
            "def _base():\n    return X.objects.all()\n",
            encoding="utf-8",
        )
        assert ratchet.snapshot(tmp_path)["views"] == {
            # سبعةُ تقييماتٍ لـ qs — والقارئُ نفسُه في selectors لا يُحمَّل
            "app/views.py::v": {"orm": 7},
            # values · save · _base (objects all) · count · values · exists
            "app/views.py::u": {"orm": 7},
        }

    def test_helpers_passed_by_reference_are_charged_to_the_view(self):
        """التعريفُ الخامس: المساعدُ يُبلغ بمرجعه — حلقةٌ، `map`، `key=`، `partial`، قاموسُ توزيع."""
        two = "    X.objects.filter()\n"
        source = (
            f"def _a():\n{two}{two}"
            f"def _b():\n{two}{two}"
            f"def _c():\n{two}{two}"
            "HANDLERS = {'a': _a, 'b': _b}\n"
            "def v1(request):\n    for f in (_a, _b):\n        f()\n"
            "def v2(request):\n    return list(map(_a, [])) + sorted([], key=_b)\n"
            "def v3(request, k):\n    return HANDLERS[k]()\n"
            "def v4(request):\n    return functools.partial(_c)(), _a\n"
            "@_c\ndef v5(request):\n    return None\n"
        )
        over, _ = ratchet.measure_views(source, "a/views.py")
        # كلُّ مساعدٍ أربعة، وكلُّ عرضٍ يبلغ اثنين منها = 8؛ والمزيِّنُ ليس من جسم العرض
        assert over == {f"a/views.py::v{i}": {"orm": 8} for i in (1, 2, 3, 4)}

    def test_only_selectors_and_services_relieve_the_view(self, tmp_path):
        """التعريفُ الخامس: كلُّ وحدةٍ غيرِ طبقةِ القراءة والكتابة تُحمَّل — لا ملفّاتُ العروض وحدَها."""
        app = tmp_path / "app"
        (app / "selectors").mkdir(parents=True)
        body = "".join("    X.objects.filter()\n" for _ in range(3))
        for name, text in (
            ("__init__.py", ""),
            ("helpers.py", f"def rows():\n{body}"),
            ("tables.py", f"def rows():\n{body}"),
            ("services.py", f"def rows():\n{body}"),
            ("dashboard_selectors.py", f"def rows():\n{body}"),
            ("selectors/__init__.py", ""),
            ("selectors/students.py", f"def rows():\n{body}"),
            (
                "views.py",
                "from . import helpers\n"
                "from .tables import rows as table_rows\n"
                "from . import services\n"
                "from .dashboard_selectors import rows as dash_rows\n"
                "from .selectors.students import rows as student_rows\n"
                "def a(request):\n    return helpers.rows()\n"
                "def b(request):\n    return table_rows()\n"
                "def c(request):\n    return services.rows(), dash_rows(), student_rows()\n",
            ),
        ):
            (app / name).write_text(text, encoding="utf-8")
        assert ratchet.snapshot(tmp_path)["views"] == {
            "app/views.py::a": {"orm": 6},
            "app/views.py::b": {"orm": 6},
        }

    # ── المقارنة ──

    def test_a_new_view_over_the_cap_is_worse(self):
        after = self._state(views={"a/views.py::v": {"lines": 61}})
        worse, stale = ratchet.compare(self.EMPTY, after)
        assert len(worse) == 1 and not stale

    def test_a_recorded_view_that_grows_is_worse(self):
        before = self._state(views={"a/views.py::v": {"lines": 84, "orm": 9}})
        after = self._state(views={"a/views.py::v": {"lines": 91, "orm": 9}})
        worse, stale = ratchet.compare(before, after)
        assert len(worse) == 1 and not stale

    def test_a_migrated_view_is_stale_until_recorded(self):
        before = self._state(views={"a/views.py::v": {"lines": 200, "orm": 25}})
        worse, stale = ratchet.compare(before, self.EMPTY)
        assert not worse and len(stale) == 2

    def test_a_new_get_school_is_worse(self):
        before = self._state(get_school={"a/views.py": 3})
        after = self._state(get_school={"a/views.py": 4, "b/views.py": 1})
        worse, _ = ratchet.compare(before, after)
        assert len(worse) == 2

    def test_a_new_downstream_import_in_core_is_worse(self):
        before = self._state(core_imports={"behavior": 1})
        after = self._state(
            core_imports={"behavior": 1, "quality": 1}, core_import_sites={"quality": ["core/x.py"]}
        )
        worse, _ = ratchet.compare(before, after)
        assert worse == ["core → quality: 0 → 1 جملةَ استيرادٍ في النواة (core/x.py)"]

    def test_moving_an_import_between_core_modules_is_neutral(self):
        before = self._state(
            core_imports={"behavior": 2},
            core_import_sites={"behavior": ["core/views_dashboard.py"]},
        )
        after = self._state(
            core_imports={"behavior": 2},
            core_import_sites={"behavior": ["core/dashboard_selectors.py"]},
        )
        assert ratchet.compare(before, after) == ([], [])

    def test_update_records_decreases_and_keeps_increases_at_their_record(self):
        """فرعٌ فيه نقصٌ وزيادةٌ معاً: يُثبَّت النقص، وتبقى الزيادةُ على قيمتها فتُسقط."""
        before = self._state(
            views={"a/views.py::v": {"lines": 110, "orm": 17}, "a/views.py::w": {"lines": 73}},
            get_school={"a/views.py": 3, "b/views.py": 1},
        )
        after = self._state(
            views={"a/views.py::v": {"lines": 118, "orm": 12}, "a/views.py::n": {"lines": 65}},
            get_school={"a/views.py": 1, "b/views.py": 2},
        )
        recorded, worse = ratchet.ratchet_down(before, after)
        assert recorded["views"] == {"a/views.py::v": {"lines": 110, "orm": 12}}
        assert recorded["get_school"] == {"a/views.py": 1, "b/views.py": 1}
        assert len(worse) == 3  # v أسطراً، والعرضُ الجديد n، وget_school في b
        worse_again, stale = ratchet.compare(recorded, after)
        assert worse_again == worse and not stale

    def test_accept_raises_one_named_item_and_writes_why(self):
        before = self._state(views={"a/views.py::v": {"lines": 110}}, get_school={"a/views.py": 4})
        after = self._state(
            views={"a/views.py::v": {"lines": 118}, "a/views.py::n": {"lines": 65}},
            get_school={"a/views.py": 6},
        )
        reason = "فرعٌ أساسُه قبل الحارس زاد ثمانيةَ أسطر"
        recorded = ratchet.accept(before, after, "a/views.py::v", reason)
        assert recorded["views"] == {"a/views.py::v": {"lines": 118}}
        assert recorded["get_school"] == {"a/views.py": 4}  # لم يُقبل — لم يُسمَّ
        assert recorded["accepted"] == [
            {"where": "a/views.py::v", "metric": "lines", "from": 110, "to": 118, "reason": reason}
        ]
        worse, _ = ratchet.compare(recorded, after)
        assert len(worse) == 2  # n وget_school ما زالا يُسقطان

    def test_accept_refuses_a_short_reason_and_what_did_not_grow(self):
        before = self._state(views={"a/views.py::v": {"lines": 110}})
        after = self._state(views={"a/views.py::v": {"lines": 118}})
        for where, reason in (
            ("a/views.py::v", "ok"),
            ("a/views.py::other", "سببٌ طويلٌ بما يكفي لأن يُقرأ"),
        ):
            try:
                ratchet.accept(before, after, where, reason)
            except ValueError:
                continue
            raise AssertionError(f"قُبل {where} بسبب «{reason}»")

    def test_accept_of_a_core_import_records_its_sites(self):
        before = self._state(core_imports={"wings": 1}, core_import_sites={"wings": ["core/a.py"]})
        after = self._state(
            core_imports={"wings": 5}, core_import_sites={"wings": ["core/a.py", "core/b.py"]}
        )
        recorded = ratchet.accept(
            before, after, "core → wings", "نطاقُ الجناح في النواة من main #285"
        )
        assert recorded["core_imports"] == {"wings": 5}
        assert recorded["core_import_sites"] == {"wings": ["core/a.py", "core/b.py"]}

    # ── إعادةُ القياس ──

    def _tree(self, tmp_path, name, *, definition, exit_code=0, view_orm=6, accepted=None):
        """نسخةٌ مصدَّرةٌ من إيداع: حارسُه القديم (بديلٌ يخرج برمزه) وسجلُّه وعرضٌ واحد."""
        tree = tmp_path / name
        (tree / "tests").mkdir(parents=True)
        (tree / "app").mkdir()
        (tree / "tests" / "__init__.py").write_text("", encoding="utf-8")
        (tree / "tests" / "layering_ratchet.py").write_text(
            f"import sys\nprint('زاد: app/views.py::v')\nsys.exit({exit_code})\n", encoding="utf-8"
        )
        baseline = {**self.EMPTY, "definition": definition}
        if accepted:
            baseline["accepted"] = accepted
        (tree / "tests" / "layering_baseline.json").write_text(
            json.dumps(baseline, ensure_ascii=False), encoding="utf-8"
        )
        (tree / "app" / "__init__.py").write_text("", encoding="utf-8")
        body = "".join("    X.objects\n" for _ in range(view_orm))
        (tree / "app" / "views.py").write_text(f"def v(request):\n{body}", encoding="utf-8")
        return tree

    def test_the_baseline_was_measured_by_this_definition(self):
        """السجلُّ يحمل رقمَ التعريف الذي قاسه — فلا يُعاد القياسُ إلّا حين يتغيّر."""
        assert (
            _baseline().get("definition") == ratchet.DEFINITION
        ), "تغيّر تعريفُ العدّ ولم يُعَد القياس: python -m tests.layering_ratchet --rebaseline"

    def test_rebaseline_refuses_when_the_definition_did_not_change(self, tmp_path):
        tree = self._tree(tmp_path, "head", definition=ratchet.DEFINITION)
        with pytest.raises(ValueError, match="--update"):
            ratchet.rebaseline_tree(tree)

    def test_rebaseline_refuses_a_commit_that_fails_its_own_guard(self, tmp_path):
        """زيادةٌ أُودعت قبل إعادة القياس تُسقط الإيداعَ بحارسه القديم — فلا تذوب في التعريف."""
        tree = self._tree(tmp_path, "head", definition=ratchet.DEFINITION - 1, exit_code=1)
        with pytest.raises(ValueError, match="app/views.py::v"):
            ratchet.rebaseline_tree(tree)

    def test_rebaseline_measures_the_commit_so_uncommitted_growth_still_fails(self, tmp_path):
        """القياسُ الجديدُ للإيداع لا للشجرة: ما زاد في العمل الجاري يبقى زيادةً تُسمّى."""
        accepted = [{"where": "x", "metric": "orm", "from": 1, "to": 2, "reason": "r" * 20}]
        head = self._tree(tmp_path, "head", definition=ratchet.DEFINITION - 1, accepted=accepted)
        recorded, report = ratchet.rebaseline_tree(head)
        assert recorded == {
            **ratchet.snapshot(head),
            "definition": ratchet.DEFINITION,
            "accepted": accepted,
        }
        assert report == ["رفعه التعريف: app/views.py::v: 0 → 6 استدعاءَ ORM (السقف 5)"]
        work = self._tree(tmp_path, "work", definition=ratchet.DEFINITION - 1, view_orm=9)
        worse, _ = ratchet.compare(recorded, ratchet.snapshot(work))
        assert worse == ["app/views.py::v: 6 → 9 استدعاءَ ORM (السقف 5)"]

    def _git_repo_with_two_commits(self, tmp_path):
        """مستودعٌ صغيرٌ فيه إيداعان — القديم قبل تعديلٍ، والرأسُ بعده."""
        import subprocess

        repo = tmp_path / "repo"
        repo.mkdir()
        run = lambda *args: subprocess.run(  # noqa: E731
            ["git", *args], cwd=repo, capture_output=True, encoding="utf-8", check=True
        )
        run("init", "-q")
        run("config", "user.email", "t@example.com")
        run("config", "user.name", "t")
        (repo / "a.txt").write_text("old", encoding="utf-8")
        run("add", "a.txt")
        run("commit", "-q", "-m", "old")
        old_sha = run("rev-parse", "HEAD").stdout.strip()
        (repo / "a.txt").write_text("new", encoding="utf-8")
        run("add", "a.txt")
        run("commit", "-q", "-m", "new")
        head_sha = run("rev-parse", "HEAD").stdout.strip()
        return repo, old_sha, head_sha

    def test_rebaseline_refuses_a_ref_other_than_head(self, tmp_path, monkeypatch, capsys):
        """`--ref` غيرُ الرأس يُرفض قبل أيّ تصديرٍ أو قياس — لا يذوب فرقٌ بينهما في السجلّ."""
        repo, old_sha, head_sha = self._git_repo_with_two_commits(tmp_path)
        monkeypatch.setattr(ratchet, "ROOT", repo)
        rc = ratchet.main(["--rebaseline", "--ref", old_sha])
        assert rc == 1
        out = capsys.readouterr().out
        assert "--ref يجب أن يكون HEAD" in out
        assert head_sha[:8] in out
        assert old_sha[:8] in out

    def test_rebaseline_accepts_head_itself(self, tmp_path, monkeypatch):
        """`--ref HEAD` (الافتراضيّ) والرأسُ بمعرّفه الكامل كلاهما يجتازان فحصَ التطابق مع الرأس.

        نُصادر `export_ref` بدالّةٍ تُثير علامةً فور استدعائها، فنُثبت بلوغَه — أي اجتيازَ
        الفحص — دون الحاجة إلى تصديرٍ حقيقيّ أو ملفّ سجلٍّ في المستودع الوهميّ.
        """
        repo, _old_sha, head_sha = self._git_repo_with_two_commits(tmp_path)
        monkeypatch.setattr(ratchet, "ROOT", repo)
        monkeypatch.setattr(
            ratchet,
            "export_ref",
            lambda ref, dest: (_ for _ in ()).throw(RuntimeError("passed-the-ref-check")),
        )
        for ref in ("HEAD", head_sha):
            with pytest.raises(RuntimeError, match="passed-the-ref-check"):
                ratchet.main(["--rebaseline", "--ref", ref])

    def test_update_and_accept_keep_the_definition(self):
        before = {**self._state(views={"a/views.py::v": {"lines": 90}}), "definition": 7}
        after = self._state(views={"a/views.py::v": {"lines": 95}})
        assert ratchet.ratchet_down(before, after)[0]["definition"] == 7
        reason = "فرعٌ أساسُه قبل الحارس زاد خمسةَ أسطر"
        assert ratchet.accept(before, after, "a/views.py::v", reason)["definition"] == 7
