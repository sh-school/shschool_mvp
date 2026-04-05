# ══════════════════════════════════════════════════════════════
# SchoolOS v5.2 — Production Dockerfile
# - Pinned base image
# - Non-root user (appuser)
# - HEALTHCHECK instruction
# ══════════════════════════════════════════════════════════════

FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=shschool.settings.production

WORKDIR /app

# System dependencies (Cairo/Pango for PDF generation via pycairo/WeasyPrint)
# Include -dev packages + pkg-config for building pycairo from source
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    pkg-config \
    libpq-dev \
    libcairo2 \
    libcairo2-dev \
    libpango-1.0-0 \
    libpango1.0-dev \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libgdk-pixbuf-2.0-dev \
    libffi-dev \
    shared-mime-info \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code
COPY . .

# Create directories and non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && mkdir -p /app/media/letters /app/media/imports /app/staticfiles /app/logs \
    && chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD wget -qO- http://localhost:8000/health/ || exit 1

CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && gunicorn shschool.wsgi:application --config /app/gunicorn.conf.py"]
