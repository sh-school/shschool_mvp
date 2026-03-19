.PHONY: up down build logs shell migrate seed full-seed test reset

# Docker (Development)
up:
	docker-compose up --build -d
	@echo "✅ http://localhost:8000"

down:
	docker-compose down

build:
	docker-compose build

logs:
	docker-compose logs -f web

shell:
	docker-compose exec web python manage.py shell

# Docker (Production)
prod-up:
	docker compose -f docker-compose.prod.yml up -d

prod-down:
	docker compose -f docker-compose.prod.yml down

prod-logs:
	docker compose -f docker-compose.prod.yml logs -f web

# Database
migrate:
	python manage.py migrate

seed:
	python manage.py full_seed

full-seed:
	python manage.py full_seed

reset:
	python manage.py full_seed --reset

# Local (without Docker)
local:
	pip install -r requirements.txt
	python manage.py migrate
	python manage.py full_seed
	python manage.py runserver

# Notifications
notify:
	python manage.py send_notifications --type all

# Tests
test:
	pytest tests/ -v

# Code Quality
lint:
	flake8 . --max-line-length=100 --exclude=migrations,venv,.venv

# Testing with coverage
test-cov:
	pytest tests/ -v --cov=. --cov-report=html --cov-report=term-missing \
	  --cov-omit="*/migrations/*,*/tests/*,manage.py,*/settings/*"

# Run specific test file
test-models:
	pytest tests/test_models.py -v

test-permissions:
	pytest tests/test_permissions.py -v

test-services:
	pytest tests/test_services.py -v

test-apis:
	pytest tests/test_apis.py -v
