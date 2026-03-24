"""
tests/test_components.py
اختبارات عرض مكونات القوالب (templates/components/)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
يختبر أن كل مكون يُعرض بدون أخطاء ويحتوي على العناصر الأساسية.
"""

import pytest
from django.template.loader import render_to_string
from django.test import RequestFactory

# ── جميع اختبارات هذا الملف تحتاج وصول DB (context_processor) ──
pytestmark = pytest.mark.django_db

# ──────────────────────────────────────────────
#  helper: تحميل component عبر include
# ──────────────────────────────────────────────

_factory = RequestFactory()


def render_component(template_name, context=None):
    """يُعيد HTML string للمكون — مع request وهمي لتجنب RecursionError."""
    from django.contrib.auth.models import AnonymousUser

    request = _factory.get("/")
    request.user = AnonymousUser()
    ctx = context or {}
    return render_to_string(template_name, ctx, request=request)


# ══════════════════════════════════════════════════════════
#  1. modal.html
# ══════════════════════════════════════════════════════════


class TestModalComponent:
    def test_renders_without_error(self):
        html = render_component(
            "components/modal.html",
            {
                "modal_id": "test-modal",
                "modal_title": "عنوان الـ Modal",
                "modal_body": "<p>محتوى</p>",
                "modal_size": "md",
            },
        )
        assert html is not None
        assert len(html) > 0

    def test_contains_modal_id(self):
        html = render_component(
            "components/modal.html",
            {
                "modal_id": "my-unique-modal",
                "modal_title": "عنوان",
                "modal_body": "محتوى",
            },
        )
        assert "my-unique-modal" in html

    def test_contains_title(self):
        html = render_component(
            "components/modal.html",
            {
                "modal_id": "modal-x",
                "title": "عنوان التجربة",
                "content": "محتوى",
            },
        )
        assert "عنوان التجربة" in html

    def test_role_dialog_present(self):
        """يجب أن يكون role=dialog لـ Accessibility."""
        html = render_component(
            "components/modal.html",
            {"modal_id": "m", "modal_title": "ع", "modal_body": "م"},
        )
        assert 'role="dialog"' in html or "role='dialog'" in html

    def test_size_variants(self):
        for size in ("sm", "md", "lg"):
            html = render_component(
                "components/modal.html",
                {"modal_id": "m", "modal_title": "ع", "modal_body": "م", "modal_size": size},
            )
            assert html  # لا أخطاء لأي حجم


# ══════════════════════════════════════════════════════════
#  2. toast.html
# ══════════════════════════════════════════════════════════


class TestToastComponent:
    def test_renders_container(self):
        html = render_component("components/toast.html")
        assert html is not None

    def test_contains_toast_container_id(self):
        html = render_component("components/toast.html", {"msg": "تم بنجاح", "type": "success"})
        assert "toast" in html.lower()


# ══════════════════════════════════════════════════════════
#  3. skeleton.html
# ══════════════════════════════════════════════════════════


class TestSkeletonComponent:
    def test_kpi_type(self):
        html = render_component("components/skeleton.html", {"type": "kpi", "count": 4})
        assert html is not None
        assert len(html) > 0

    def test_table_type(self):
        html = render_component("components/skeleton.html", {"type": "table", "rows": 5})
        assert html is not None

    def test_card_type(self):
        html = render_component("components/skeleton.html", {"type": "card", "count": 3})
        assert html is not None

    def test_contains_skeleton_class(self):
        html = render_component("components/skeleton.html", {"type": "table", "rows": 3})
        assert "skeleton" in html.lower() or "animate" in html.lower() or "shimmer" in html.lower()


# ══════════════════════════════════════════════════════════
#  4. confirm_dialog.html
# ══════════════════════════════════════════════════════════


class TestConfirmDialogComponent:
    def test_renders_without_error(self):
        html = render_component(
            "components/confirm_dialog.html",
            {
                "confirm_id": "delete-modal",
                "confirm_title": "تأكيد الحذف",
                "confirm_message": "هل أنت متأكد من حذف هذا العنصر؟",
                "confirm_action_url": "/delete/1/",
                "confirm_btn_label": "حذف",
            },
        )
        assert html is not None

    def test_contains_warning_message(self):
        html = render_component(
            "components/confirm_dialog.html",
            {
                "confirm_id": "m",
                "title": "تأكيد",
                "message": "هذا لا يمكن التراجع عنه",
                "action_url": "/delete/",
            },
        )
        assert "لا يمكن التراجع" in html

    def test_contains_action_url(self):
        html = render_component(
            "components/confirm_dialog.html",
            {
                "confirm_id": "m",
                "title": "حذف",
                "message": "رسالة",
                "action_url": "/custom/delete/99/",
            },
        )
        assert "/custom/delete/99/" in html


# ══════════════════════════════════════════════════════════
#  5. search_input.html
# ══════════════════════════════════════════════════════════


class TestSearchInputComponent:
    def test_renders_input(self):
        html = render_component(
            "components/search_input.html",
            {
                "search_url": "/library/books/",
                "target": "#books-container",
                "placeholder": "ابحث هنا...",
                "name": "q",
                "value": "",
            },
        )
        assert html is not None
        assert "<input" in html

    def test_contains_hx_get(self):
        html = render_component(
            "components/search_input.html",
            {
                "search_url": "/library/books/",
                "target": "#books-container",
                "placeholder": "بحث",
                "name": "q",
                "value": "",
            },
        )
        assert "hx-get" in html

    def test_contains_target(self):
        html = render_component(
            "components/search_input.html",
            {
                "search_url": "/books/",
                "target": "#my-target",
                "placeholder": "بحث",
                "name": "q",
                "value": "",
            },
        )
        assert "#my-target" in html

    def test_value_prefilled(self):
        html = render_component(
            "components/search_input.html",
            {
                "search_url": "/books/",
                "target": "#container",
                "placeholder": "بحث",
                "name": "q",
                "value": "رياضيات",
            },
        )
        assert "رياضيات" in html


# ══════════════════════════════════════════════════════════
#  6. empty_state.html
# ══════════════════════════════════════════════════════════


class TestEmptyStateComponent:
    def test_renders_title(self):
        html = render_component(
            "components/empty_state.html",
            {
                "empty_icon": "📭",
                "empty_title": "لا توجد بيانات",
                "empty_sub": "أضف عناصر جديدة للبدء",
            },
        )
        assert "لا توجد بيانات" in html

    def test_renders_icon(self):
        html = render_component(
            "components/empty_state.html",
            {
                "icon": "📚",
                "title": "عنوان",
                "subtitle": "",
            },
        )
        assert "📚" in html

    def test_optional_action_button(self):
        html = render_component(
            "components/empty_state.html",
            {
                "icon": "📋",
                "title": "لا شيء",
                "subtitle": "فارغ",
                "action_url": "/add/",
                "action_label": "إضافة جديد",
            },
        )
        assert "/add/" in html
        assert "إضافة جديد" in html


# ══════════════════════════════════════════════════════════
#  7. pagination.html
# ══════════════════════════════════════════════════════════


class TestPaginationComponent:
    def test_renders_without_error(self):
        # Mock page object
        class MockPaginator:
            num_pages = 5

        class MockPage:
            number = 2
            paginator = MockPaginator()

            def has_previous(self):
                return True

            def has_next(self):
                return True

            def previous_page_number(self):
                return 1

            def next_page_number(self):
                return 3

            def page_range(self):
                return range(1, 6)

        html = render_component(
            "components/pagination.html",
            {
                "page_obj": MockPage(),
                "target": "#items-container",
            },
        )
        assert html is not None

    def test_single_page_renders(self):
        class MockPaginator:
            num_pages = 1

        class MockPage:
            number = 1
            paginator = MockPaginator()

            def has_previous(self):
                return False

            def has_next(self):
                return False

            def page_range(self):
                return range(1, 2)

        html = render_component(
            "components/pagination.html",
            {"page_obj": MockPage(), "target": "#container"},
        )
        assert html is not None


# ══════════════════════════════════════════════════════════
#  8. file_upload.html
# ══════════════════════════════════════════════════════════


class TestFileUploadComponent:
    def test_renders_dropzone(self):
        html = render_component(
            "components/file_upload.html",
            {
                "upload_field_name": "document",
                "upload_accept": ".pdf,.docx",
                "upload_max_mb": 10,
            },
        )
        assert html is not None
        assert "<input" in html

    def test_contains_accept_attribute(self):
        html = render_component(
            "components/file_upload.html",
            {
                "upload_field_name": "file",
                "upload_accept": ".pdf,.jpg",
                "upload_max_mb": 5,
            },
        )
        assert ".pdf" in html or "accept" in html
