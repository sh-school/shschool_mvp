"""
conftest.py (root)
━━━━━━━━━━━━━━━━━━
يُخبر pytest بتجاهل مجلدات لا تحتوي على اختبارات pytest.
"""

# ✅ v5.4: Locust (loadtest) و Playwright (e2e) يحتاجان مكتبات خاصة
# غير مثبّتة في بيئة الاختبار العادية — نستثنيها من الجمع
collect_ignore_glob = [
    "tests/loadtest/**",
    "tests/e2e/**",
]
