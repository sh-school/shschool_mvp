"""[LAYERING] سقّاطةُ الطبقات — راجع `tests/layering_ratchet.py` للسبب والطريقة.

كانت الدوالُّ هنا تأخذ `update=False` وتُرجع `False` عند المخالفة: pytest لا يعدّ
القيمةَ المُرجعة سقوطاً، فكانت «4 passed» والحارسُ نفسُه يطبع `FAIL` لثلاثة عروض.
فالحكمُ الآن `assert`، والقياسُ والمقارنةُ في وحدةٍ لا يجمعها pytest.
"""

import json

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

    def test_update_refuses_to_record_an_increase(self):
        before = self._state(get_school={"a/views.py": 1})
        after = self._state(get_school={"a/views.py": 2})
        try:
            ratchet.ratchet_down(before, after)
        except ValueError as exc:
            assert "a/views.py" in str(exc)
        else:
            raise AssertionError("--update سجّل زيادة")

    def test_update_records_a_decrease(self):
        before = self._state(get_school={"a/views.py": 3})
        after = self._state(get_school={"a/views.py": 1})
        assert ratchet.ratchet_down(before, after) == after
