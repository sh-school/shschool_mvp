# ══════════════════════════════════════════════════════════════
# SchoolOS v5.2 — Production Dockerfile
# - Pinned base image
# - Non-root user (appuser)
# - HEALTHCHECK instruction
# - بناءٌ متعدّد المراحل: المترجِمات وحزمُ -dev في مرحلة builder وحدَها (W-20261017-004)
# ══════════════════════════════════════════════════════════════

# 3.12 = ما تُفحص عليه البوّابات (ruff/mypy/pytest). كان 3.11 هنا وحدَه منذ
# 2026-04 فتُفحص الشيفرةُ على إصدارٍ وتعمل على غيره.
FROM python:3.12-slim-bookworm AS builder

# مرحلةُ البناء: gcc وg++ وpkg-config وحزمُ -dev لبناء pycairo وغيره من المصدر.
# لا شيءَ من هذه المرحلة يصل إلى الصورة النهائية سوى مجلّد /opt/venv.
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    g++ \
    pkg-config \
    libpq-dev \
    libcairo2-dev \
    libpango1.0-dev \
    libgdk-pixbuf-2.0-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /build
COPY requirements.txt requirements-dev.txt requirements-mypy.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# أدواتُ التطوير (pytest وruff وmypy) للصورة المحلّيّة وحدها: `docker-compose.yml`
# يمرّر INSTALL_DEV=true، وRailway يبني بلا وسيطٍ فتبقى صورةُ الإنتاج بلا أدواتٍ.
# وبلاها كانت كلُّ حاويةِ جلسةٍ تثبّت pytest بيدها، ويضيع مع إعادة إنشائها.
ARG INSTALL_DEV=false
RUN if [ "$INSTALL_DEV" = "true" ]; then pip install --no-cache-dir -r requirements-dev.txt; fi


# ── المرحلةُ النهائيّة: مكتباتُ التشغيل فقط ──────────────────────
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DJANGO_SETTINGS_MODULE=shschool.settings.production
ENV PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# مكتباتُ التشغيل وحدَها (Cairo/Pango لتوليد PDF عبر pycairo/WeasyPrint، وlibpq5 لـpsycopg)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi8 \
    shared-mime-info \
    wget \
    && rm -rf /var/lib/apt/lists/*

COPY --from=builder /opt/venv /opt/venv

# المستخدمُ غير الجذر؛ وتُملَّك له مجلّداتُ الكتابة فقط، ويُنسخ الكودُ بـ--chown
# بدل chown -R على /app كلِّه (كان يكرّر طبقةَ الشيفرة بحجمها).
RUN groupadd -r appuser && useradd -r -g appuser -d /app appuser \
    && mkdir -p /app/media/letters /app/media/imports /app/staticfiles /app/logs \
    && chown appuser:appuser /app \
    && chown -R appuser:appuser /app/media /app/staticfiles /app/logs

# Application code
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD wget -qO- http://localhost:8000/health/ || exit 1

# ASGI (daphne) — يدعم WebSocket/Channels مثل docker-compose.prod.yml (لا gunicorn WSGI)
CMD ["sh", "-c", "python manage.py migrate --noinput && python manage.py collectstatic --noinput && daphne -b 0.0.0.0 -p 8000 shschool.asgi:application"]
