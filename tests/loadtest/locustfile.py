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
    LOCUST_NATIONAL_ID   — الرقم الشخصي لتسجيل الدخول (افتراضي: 12345678901)
    LOCUST_PASSWORD      — كلمة المرور (افتراضي: TestPass123!)
    LOCUST_ALLOW_REMOTE  — "1" يسمح بمضيف غير محلي (لا يُستعمل إلا بإذن المالك)

السيناريوهات المضافة (الحضور والدرجات فقط):
    AttendanceLoadUser — قراءات الحضور: القوائم، الحصص، وحضور طالبٍ بعينه.
    GradesLoadUser     — قراءات الدرجات: لوحة التقييمات، الرسوم، ودرجات طالبٍ بعينه.

حدود القبول (تُفحص عند الإنهاء، ويخرج الاختبار برمز 1 عند تجاوزها):
    p95 لكلّ سيناريو ≤ LOCUST_P95_MS  (افتراضي 800 ميلي ثانية)
    نسبة الأخطاء ≤ LOCUST_MAX_FAIL_RATIO (افتراضي 0.01)
"""

import os
import random

from locust import HttpUser, between, events, task

LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]")
P95_LIMIT_MS = float(os.environ.get("LOCUST_P95_MS", "800"))
MAX_FAIL_RATIO = float(os.environ.get("LOCUST_MAX_FAIL_RATIO", "0.01"))


@events.test_start.add_listener
def refuse_remote_host(environment, **_kwargs):
    """يمنع الحمل على أيّ مضيف غير محلي: الإنتاج خطٌّ أحمر لا يُختبر بالحمل."""
    host = environment.host or ""
    if any(local in host for local in LOCAL_HOSTS):
        return
    if os.environ.get("LOCUST_ALLOW_REMOTE") == "1":
        return
    raise SystemExit(
        f"رُفض الحمل على المضيف {host!r}: مسموحٌ به محلياً فقط. "
        "الإنتاج لا يُختبر بالحمل (انظر .claude/skills/schoolos-load-test/SKILL.md)."
    )


ACCEPTANCE_SCOPES = ("attendance", "/grades", "/assessments")


@events.quitting.add_listener
def enforce_acceptance_limits(environment, **_kwargs):
    """يجعل رمز الخروج 1 إذا تجاوز مسارٌ من مسارات الحضور والدرجات حدَّ p95 أو حدَّ الأخطاء.

    الفحص لكلّ مسار على حدة (لا معدّلٌ عام)، فمسارٌ بطيءٌ لا تُخفيه المسارات السريعة.
    """
    failed = []
    for (name, method), entry in environment.stats.entries.items():
        if not any(scope in name for scope in ACCEPTANCE_SCOPES) or entry.num_requests == 0:
            continue
        p95 = entry.get_response_time_percentile(0.95) or 0
        fail_ratio = entry.num_failures / entry.num_requests
        if p95 > P95_LIMIT_MS or fail_ratio > MAX_FAIL_RATIO:
            failed.append(f"{method} {name}: p95={p95:.0f}ms fail={fail_ratio:.2%}")
    if failed:
        print("تجاوز حدود القبول:", "; ".join(failed))
        environment.process_exit_code = 1


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


class _LoadScenarioUser(HttpUser):
    """قاعدة مشتركة للسيناريوهات المركّزة: تسجيل دخول واحد، ثم طلب بيانات طالبٍ عشوائيّ."""

    abstract = True
    wait_time = between(1, 3)
    national_id = os.environ.get("LOCUST_NATIONAL_ID", "12345678901")
    password = os.environ.get("LOCUST_PASSWORD", "TestPass123!")

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
        self.student_ids = self._load_student_ids()

    def _load_student_ids(self):
        """يقرأ معرّفات الطلاب من القائمة؛ قائمةٌ فارغة تعني أن السيناريو يكتفي بالقوائم."""
        with self.client.get(
            "/api/v1/students/", name="/api/v1/students/ [setup]", catch_response=True
        ) as resp:
            if resp.status_code != 200:
                resp.failure(f"HTTP {resp.status_code}")
                return []
            payload = resp.json()
            rows = payload.get("results", payload) if isinstance(payload, dict) else payload
            return [row["id"] for row in rows[:50] if isinstance(row, dict) and "id" in row]


class AttendanceLoadUser(_LoadScenarioUser):
    """سيناريو الحضور: القوائم والحصص وحضور طالبٍ بعينه."""

    @task(5)
    def attendance_api_list(self):
        self.client.get("/api/v1/attendance/", name="/api/v1/attendance/")

    @task(3)
    def sessions_api_list(self):
        self.client.get("/api/v1/sessions/", name="/api/v1/sessions/ [attendance]")

    @task(2)
    def attendance_overview_page(self):
        self.client.get("/student-affairs/attendance/", name="/student-affairs/attendance/")

    @task(2)
    def attendance_board_page(self):
        self.client.get("/staff-affairs/attendance/", name="/staff-affairs/attendance/")

    @task(4)
    def student_attendance(self):
        if not self.student_ids:
            return
        student_id = random.choice(self.student_ids)
        self.client.get(
            f"/api/v1/students/{student_id}/attendance/",
            name="/api/v1/students/[id]/attendance/",
        )


class GradesLoadUser(_LoadScenarioUser):
    """سيناريو الدرجات: لوحة التقييمات والرسوم ودرجات طالبٍ بعينه."""

    @task(4)
    def assessments_dashboard(self):
        self.client.get("/assessments/", name="/assessments/")

    @task(3)
    def assessment_charts(self):
        self.client.get("/assessments/api/charts/", name="/assessments/api/charts/")

    @task(2)
    def failing_students(self):
        self.client.get("/assessments/failing/", name="/assessments/failing/")

    @task(5)
    def student_grades(self):
        if not self.student_ids:
            return
        student_id = random.choice(self.student_ids)
        self.client.get(
            f"/api/v1/students/{student_id}/grades/",
            name="/api/v1/students/[id]/grades/",
        )

    @task(1)
    def parent_grades_page(self):
        self.client.get("/parents/grades/", name="/parents/grades/")
