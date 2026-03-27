"""api/pagination.py — إعدادات Pagination موحّدة للـ REST API."""

from rest_framework.pagination import PageNumberPagination


class StandardPagination(PageNumberPagination):
    """
    الـ Pagination الافتراضي لكل ListAPIView في SchoolOS.

    الاستخدام:
        class MyView(generics.ListAPIView):
            pagination_class = StandardPagination

    المعاملات:
        ?page=2          ← رقم الصفحة
        ?page_size=50    ← عدد العناصر في الصفحة (أقصى: 200)

    الاستجابة:
        {
          "count": 742,
          "next": "/api/v1/students/?page=2",
          "previous": null,
          "results": [...]
        }
    """

    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200
    page_query_param = "page"
