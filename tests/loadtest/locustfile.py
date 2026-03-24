"""
tests/loadtest/locustfile.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━
اختبار حمل SchoolOS باستخدام Locust.

التشغيل:
    pip install locust
    locust -f tests/loadtest/locustfile.py --host=http://localhost:8000

    # أو بدون واجهة:
    locust -f tests/loadtest/locustfile.py --host=http://localhost:8000 \
           --headless -u 50 -r 5 --run-time 2m

المتغيرات البيئية:
    LOCUST_NATIONAL_ID   — الرقم الوطني لتسجيل الدخول (افتراضي: 12345678901)
    LOCUST_PASSWORD      — كلمة المرور (افتراضي: TestPass123!)
"""

import os

from locust import HttpUser, between, task


class SchoolOSUser(HttpUser):
    """مستخدم عادي (معلم/مدير) يتصفح المنصة."""

    wait_time = between(1, 5)
    national_id = os.environ.get("LOCUST_NATIONAL_ID", "12345678901")
    password = os.environ.get("LOCUST_PASSWORD", "TestPass123!")

    def on_start(self):
        """تسجيل الدخول قبل بدء الاختبار."""
        # جلب CSRF token
        resp = self.client.get("/auth/login/")
        csrftoken = resp.cookies.get("csrftoken", "")

        # تسجيل الدخول
        self.client.post(
            "/auth/login/",
            data={
                "national_id": self.national_id,
                "password": self.password,
                "csrfmiddlewaretoken": csrftoken,
            },
            headers={"Referer": f"{self.host}/auth/login/"},
        )

    # ── صفحات HTML (أكثر استخداماً) ────────────────────────

    @task(10)
    def dashboard(self):
        """لوحة التحكم — أكثر صفحة زيارة."""
        self.client.get("/dashboard/", name="/dashboard/")

    @task(5)
    def teacher_schedule(self):
        """جدول المعلم الأسبوعي."""
        self.client.get("/teacher/schedule/", name="/teacher/schedule/")

    @task(3)
    def quality_dashboard(self):
        """لوحة الجودة."""
        self.client.get("/quality/", name="/quality/")

    @task(3)
    def analytics_dashboard(self):
        """لوحة التحليلات."""
        self.client.get("/analytics/", name="/analytics/")

    @task(2)
    def behavior_dashboard(self):
        """لوحة السلوك."""
        self.client.get("/behavior/dashboard/", name="/behavior/dashboard/")

    @task(2)
    def notifications_inbox(self):
        """صندوق الإشعارات."""
        self.client.get("/notifications/inbox/", name="/notifications/inbox/")

    @task(1)
    def reports_index(self):
        """صفحة التقارير."""
        self.client.get("/reports/", name="/reports/")

    # ── REST API endpoints ──────────────────────────────────

    @task(4)
    def api_me(self):
        """API: ملف المستخدم."""
        self.client.get("/api/v1/me/", name="/api/v1/me/")

    @task(3)
    def api_students(self):
        """API: قائمة الطلاب."""
        self.client.get("/api/v1/students/", name="/api/v1/students/")

    @task(3)
    def api_sessions(self):
        """API: الحصص."""
        self.client.get("/api/v1/sessions/", name="/api/v1/sessions/")

    @task(2)
    def api_notifications(self):
        """API: الإشعارات."""
        self.client.get("/api/v1/notifications/", name="/api/v1/notifications/")

    @task(2)
    def api_behavior(self):
        """API: المخالفات."""
        self.client.get("/api/v1/behavior/", name="/api/v1/behavior/")

    @task(1)
    def api_library_books(self):
        """API: الكتب."""
        self.client.get("/api/v1/library/books/", name="/api/v1/library/books/")

    # ── Health Check (خفيف) ─────────────────────────────────

    @task(1)
    def health_check(self):
        """فحص صحة النظام."""
        self.client.get("/health/", name="/health/")


class ParentUser(HttpUser):
    """ولي أمر — أنماط استخدام مختلفة."""

    wait_time = between(2, 8)
    weight = 3  # نسبة أقل من المعلمين

    national_id = os.environ.get("LOCUST_PARENT_ID", "98765432101")
    password = os.environ.get("LOCUST_PARENT_PASSWORD", "TestPass123!")

    def on_start(self):
        resp = self.client.get("/auth/login/")
        csrftoken = resp.cookies.get("csrftoken", "")
        self.client.post(
            "/auth/login/",
            data={
                "national_id": self.national_id,
                "password": self.password,
                "csrfmiddlewaretoken": csrftoken,
            },
            headers={"Referer": f"{self.host}/auth/login/"},
        )

    @task(5)
    def parent_dashboard(self):
        self.client.get("/parents/", name="/parents/")

    @task(3)
    def api_children(self):
        self.client.get("/api/v1/parent/children/", name="/api/v1/parent/children/")
