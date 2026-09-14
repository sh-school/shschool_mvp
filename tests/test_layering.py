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

    EMPTY: dict = {"views": {}, "get_school": {}, "core_imports": {}}

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
        assert set(over) == {"a/views.py::multi", "a/views.py::Page.get"}

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

    def test_every_app_but_core_is_downstream(self):
        apps = ratchet.downstream_apps()
        assert {"student_affairs", "analytics", "wings", "api"} <= apps
        assert not apps & {"core", "shschool", "tests"}

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
        before = self._state(core_imports={"core/x.py": {"behavior": 1}})
        after = self._state(core_imports={"core/x.py": {"behavior": 1, "quality": 1}})
        worse, _ = ratchet.compare(before, after)
        assert worse == ["core/x.py: 0 → 1 استيراداً من `quality` في النواة"]

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
