.PHONY: up down build logs shell migrate seed full-seed test reset \
        quality lint security ci test-cov pre-commit-install minify-js \
        axes-reset health-check ready-check test-v54 pip-audit-check

# ── Docker (Development) ──────────────────────────────
up:
	docker-compose up --build -d
	@echo "http://localhost:8000"

down:
	docker-compose down

build:
	docker-compose build

logs:
	docker-compose logs -f web

shell:
	docker-compose exec web python manage.py shell

# ── Docker (Production) ───────────────────────────────
prod-up:
	docker compose -f docker-compose.prod.yml up -d

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f web

# ── Database ──────────────────────────────────────────
migrate:
	python manage.py migrate

seed:
	python manage.py full_seed

full-seed:
	python manage.py full_seed

reset:
	python manage.py full_seed --reset

# ── Local (without Docker) ────────────────────────────
local:
	pip install -r requirements.txt
	python manage.py migrate
	python manage.py full_seed
	python manage.py runserver

# ── Notifications ─────────────────────────────────────
notify:
	python manage.py send_notifications --type all

# ══════════════════════════════════════════════════════
#  QUALITY GATES
# ══════════════════════════════════════════════════════

# الاختبارات فقط
test:
	pytest tests/ -v

# الاختبارات + Coverage Gate 80%
test-cov:
	pytest tests/ -v \
	  --cov=. \
	  --cov-report=html:htmlcov \
	  --cov-report=term-missing \
	  --cov-fail-under=80 \
	  --cov-omit="*/migrations/*,*/tests/*,manage.py,*/settings/*,*/.venv/*"
	@echo "التقرير: htmlcov/index.html"

# جودة الكود — ruff
lint:
	ruff check . --fix
	ruff format .

# فحص جودة بدون إصلاح (للتحقق فقط)
lint-check:
	ruff check . --output-format=github
	ruff format --check .

# فحص أمني — bandit
security:
	@echo "=== Bandit Security Scan ==="
	bandit -r . \
	  -x .venv,migrations,tests,manage.py \
	  --severity-level medium \
	  --confidence-level medium
	@echo ""
	@echo "=== pip-audit CVE Scan ==="
	pip-audit -r requirements.txt

# فحص شامل = lint + security + test-cov
quality: lint-check security test-cov
	@echo ""
	@echo "=== radon Complexity ==="
	radon cc . \
	  --exclude "migrations,.venv,manage.py" \
	  --min C \
	  --show-complexity \
	  --average
	@echo ""
	@echo "Quality Gate: اكتمل"

# نفس ما يشغله GitHub Actions CI
ci:
	@echo "=== 1. Ruff ==="
	ruff check . --output-format=github
	ruff format --check .
	@echo ""
	@echo "=== 2. Bandit ==="
	bandit -r . \
	  -x .venv,migrations,tests,manage.py \
	  --severity-level high \
	  --confidence-level high
	@echo ""
	@echo "=== 3. pytest + Coverage ==="
	pytest tests/ -v \
	  --cov=. \
	  --cov-report=term-missing \
	  --cov-fail-under=80 \
	  --cov-omit="*/migrations/*,*/tests/*,manage.py,*/settings/*,*/.venv/*" \
	  -q
	@echo ""
	@echo "CI محلي: اجتاز جميع الفحوصات"

# تثبيت pre-commit hooks
pre-commit-install:
	pip install pre-commit
	pre-commit install
	@echo "pre-commit hooks مثبّتة — ستعمل تلقائياً عند كل commit"

# تشغيل pre-commit على كل الملفات
pre-commit-run:
	pre-commit run --all-files

# ── JS Minification ──────────────────────────────────
minify-js:
	npx terser static/js/base.js -o static/js/base.min.js --compress --mangle
	npx terser static/js/app.js -o static/js/app.min.js --compress --mangle
	npx terser static/js/quality.js -o static/js/quality.min.js --compress --mangle
	@echo "JS minified successfully"

# ── E2E Tests (Playwright) ───────────────────────────
test-e2e:
	pytest tests/e2e/ -v --timeout=60

test-e2e-headed:
	pytest tests/e2e/ -v --headed --slowmo=500 --timeout=60

# ── Run specific test file ────────────────────────────
test-models:
	pytest tests/test_models.py -v

test-permissions:
	pytest tests/test_permissions.py -v

test-services:
	pytest tests/test_services.py -v

test-apis:
	pytest tests/test_api_v1.py -v

test-api-v1:
	pytest tests/test_api_v1.py -v

# ── Mutation Testing (mutmut) ──────────────────────────
test-mutmut:
	mutmut run --paths-to-mutate=core/ --runner="pytest tests/ -x -q --no-header --tb=no"
	mutmut results

test-mutmut-report:
	mutmut html
	@echo "تقرير Mutation: html/index.html"

# ── Load Testing (Locust) ─────────────────────────────
loadtest:
	locust -f tests/loadtest/locustfile.py --host=http://localhost:8000

loadtest-headless:
	locust -f tests/loadtest/locustfile.py --host=http://localhost:8000 \
	  --headless -u 50 -r 5 --run-time 2m \
	  --csv=tests/loadtest/results

# ── API Contract Tests ─────────────────────────────────
test-contracts:
	pytest tests/test_api_contract.py -v

# ══════════════════════════════════════════════════════
#  v5.4 — أوامر جديدة
# ══════════════════════════════════════════════════════

# إعادة تعيين محاولات تسجيل الدخول الفاشلة لمستخدم (django-axes)
# الاستخدام: make axes-reset USER=28765432101
axes-reset:
	python manage.py axes_reset_ip --username $(USER)
	@echo "تم إعادة تعيين قفل المستخدم: $(USER)"

# فحص الـ health endpoints محلياً
health-check:
	@echo "=== Liveness (/health/) ==="
	curl -s http://localhost:8000/health/ | python -m json.tool
	@echo ""
	@echo "=== Readiness (/ready/) ==="
	curl -s http://localhost:8000/ready/ | python -m json.tool

ready-check:
	curl -sf http://localhost:8000/ready/ && echo "✅ Ready" || echo "❌ Not Ready"

# تشغيل اختبارات v5.4 فقط
test-v54:
	pytest tests/test_v54_features.py -v --no-header

# فحص الثغرات الأمنية في المتطلبات
pip-audit-check:
	@echo "=== pip-audit Security Scan ==="
	pip-audit -r requirements.txt --progress-spinner off
	@echo "=== لا ثغرات معروفة ==="

# ── Help ──────────────────────────────────────────────
help:
	@echo ""
	@echo "الأوامر المتاحة:"
	@echo "  make test          الاختبارات فقط"
	@echo "  make test-cov      الاختبارات + Coverage >=80%"
	@echo "  make lint          إصلاح الكود (ruff)"
	@echo "  make lint-check    فحص الكود بدون إصلاح"
	@echo "  make security      bandit + pip-audit"
	@echo "  make quality       فحص شامل (lint+security+test-cov+radon)"
	@echo "  make ci            نفس GitHub Actions محلياً"
	@echo "  make pre-commit-install  تفعيل hooks"
	@echo "  make test-mutmut   Mutation Testing (mutmut)"
	@echo "  make loadtest      Load Testing (Locust UI)"
	@echo "  make loadtest-headless  Load Testing بدون واجهة"
	@echo "  make test-contracts  API Contract Tests"
	@echo ""
	@echo "v5.4 الجديدة:"
	@echo "  make axes-reset USER=<رقم_وطني>  إعادة تعيين قفل مستخدم"
	@echo "  make health-check   فحص /health/ و /ready/ محلياً"
	@echo "  make test-v54       اختبارات ميزات v5.4 فقط"
	@echo "  make pip-audit-check  فحص ثغرات المتطلبات"
	@echo ""
