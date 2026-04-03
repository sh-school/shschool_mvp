#!/bin/bash
# ══════════════════════════════════════════════════════════════════════
# setup-server.sh — إعداد سيرفر OCI لمنصة SchoolOS
# ══════════════════════════════════════════════════════════════════════
# التشغيل: bash setup-server.sh
# المتطلبات: Ubuntu 22.04 LTS على OCI ARM A1 Instance
# ══════════════════════════════════════════════════════════════════════

set -euo pipefail

# ── الألوان ────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

log()  { echo -e "${BLUE}${BOLD}[$(date +%H:%M:%S)]${NC} $1"; }
ok()   { echo -e "${GREEN}✅ $1${NC}"; }
warn() { echo -e "${YELLOW}⚠️  $1${NC}"; }
err()  { echo -e "${RED}❌ $1${NC}"; exit 1; }

# ── المتغيرات ──────────────────────────────────────────────────────────
DEPLOY_DIR="/opt/schoolos"
REPO_URL="https://github.com/msuelem77/shschool_mvp.git"
DOMAIN="${DOMAIN:-schoolos.edu.qa}"
APP_USER="schoolos"

log "بدء إعداد سيرفر SchoolOS — OCI ARM A1 (Ubuntu 22.04)"
echo -e "${BOLD}========================================${NC}"
echo -e "  Domain: ${YELLOW}${DOMAIN}${NC}"
echo -e "  Dir:    ${YELLOW}${DEPLOY_DIR}${NC}"
echo -e "${BOLD}========================================${NC}"

# ══════════════════════════════════════════════════════════════
# 1. تحديث النظام
# ══════════════════════════════════════════════════════════════
log "1/8 تحديث النظام..."
apt-get update -qq && apt-get upgrade -y -qq
apt-get install -y -qq \
    curl wget git ufw fail2ban \
    ca-certificates gnupg lsb-release
ok "تم تحديث النظام"

# ══════════════════════════════════════════════════════════════
# 2. تثبيت Docker
# ══════════════════════════════════════════════════════════════
log "2/8 تثبيت Docker..."
if ! command -v docker &>/dev/null; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        | tee /etc/apt/sources.list.d/docker.list > /dev/null
    apt-get update -qq
    apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-compose-plugin
    systemctl enable docker
    systemctl start docker
    ok "تم تثبيت Docker"
else
    ok "Docker مثبت مسبقاً"
fi

# ══════════════════════════════════════════════════════════════
# 3. إعداد جدار الحماية (UFW)
# ══════════════════════════════════════════════════════════════
log "3/8 إعداد جدار الحماية UFW..."
ufw --force reset
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp comment 'SSH'
ufw allow 80/tcp comment 'HTTP'
ufw allow 443/tcp comment 'HTTPS'
ufw --force enable
ok "جدار الحماية مُفعَّل (22, 80, 443 فقط)"

# ══════════════════════════════════════════════════════════════
# 4. إعداد Fail2Ban
# ══════════════════════════════════════════════════════════════
log "4/8 إعداد Fail2Ban..."
cat > /etc/fail2ban/jail.local << 'EOF'
[DEFAULT]
bantime  = 1h
findtime = 10m
maxretry = 5

[sshd]
enabled = true
port    = ssh
logpath = /var/log/auth.log
EOF
systemctl enable fail2ban
systemctl restart fail2ban
ok "Fail2Ban مُفعَّل"

# ══════════════════════════════════════════════════════════════
# 5. إعداد مستخدم التطبيق
# ══════════════════════════════════════════════════════════════
log "5/8 إعداد مستخدم التطبيق..."
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -m -d "$DEPLOY_DIR" -s /bin/bash "$APP_USER"
    usermod -aG docker "$APP_USER"
    ok "تم إنشاء المستخدم: $APP_USER"
else
    ok "المستخدم موجود: $APP_USER"
fi

# ══════════════════════════════════════════════════════════════
# 6. استنساخ المشروع
# ══════════════════════════════════════════════════════════════
log "6/8 إعداد مجلد المشروع..."
mkdir -p "$DEPLOY_DIR"
if [ ! -d "$DEPLOY_DIR/.git" ]; then
    git clone "$REPO_URL" "$DEPLOY_DIR"
    ok "تم استنساخ المشروع"
else
    cd "$DEPLOY_DIR" && git pull origin main
    ok "تم تحديث المشروع"
fi

# إنشاء المجلدات المطلوبة
mkdir -p "$DEPLOY_DIR"/{logs,media/letters,media/imports,staticfiles,backups/wal,nginx/ssl}
chown -R "$APP_USER:$APP_USER" "$DEPLOY_DIR"

# ══════════════════════════════════════════════════════════════
# 7. إعداد ملف .env
# ══════════════════════════════════════════════════════════════
log "7/8 إعداد ملف .env..."
if [ ! -f "$DEPLOY_DIR/.env" ]; then
    cat > "$DEPLOY_DIR/.env" << EOF
# ════════════════════════════════════════
# SchoolOS — متغيرات البيئة للإنتاج
# عدّل القيم قبل التشغيل!
# ════════════════════════════════════════

# Django
SECRET_KEY=CHANGE_ME_$(openssl rand -hex 32)
DEBUG=False
ALLOWED_HOSTS=${DOMAIN},www.${DOMAIN},localhost

# قاعدة البيانات
DB_NAME=schoolos
DB_USER=schoolos
DB_PASSWORD=CHANGE_ME_$(openssl rand -hex 16)
DB_HOST=db
DB_PORT=5432

# Redis
REDIS_PASSWORD=CHANGE_ME_$(openssl rand -hex 16)

# البريد الإلكتروني
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_HOST_USER=
EMAIL_HOST_PASSWORD=

# Sentry
SENTRY_DSN=

# Twilio (SMS/WhatsApp)
TWILIO_ACCOUNT_SID=
TWILIO_AUTH_TOKEN=
TWILIO_FROM_NUMBER=

# VAPID (Push Notifications)
VAPID_PUBLIC_KEY=
VAPID_PRIVATE_KEY=

# التشفير (Fernet)
FERNET_KEY=CHANGE_ME_$(python3 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())" 2>/dev/null || echo "generate_with_python")
EOF
    warn ".env تم إنشاؤه — عدّل القيم قبل تشغيل المنصة!"
    warn "الملف: $DEPLOY_DIR/.env"
else
    ok ".env موجود مسبقاً"
fi

chmod 600 "$DEPLOY_DIR/.env"

# ══════════════════════════════════════════════════════════════
# 8. سكريبت النشر اليومي
# ══════════════════════════════════════════════════════════════
log "8/8 إنشاء سكريبت النشر..."
cat > /usr/local/bin/schoolos-deploy << 'DEPLOY_SCRIPT'
#!/bin/bash
# schoolos-deploy — نشر سريع من main branch
set -e
cd /opt/schoolos
git pull origin main
docker compose -f docker-compose.prod.yml build web
docker compose -f docker-compose.prod.yml run --rm web python manage.py migrate --noinput
docker compose -f docker-compose.prod.yml run --rm web python manage.py collectstatic --noinput
docker compose -f docker-compose.prod.yml up -d --no-deps web celery_worker celery_beat
sleep 15
curl -sf http://localhost/health/ && echo "✅ SchoolOS يعمل!" || echo "❌ تحقق من السجلات"
DEPLOY_SCRIPT
chmod +x /usr/local/bin/schoolos-deploy

# سكريبت المراقبة
cat > /usr/local/bin/schoolos-status << 'STATUS_SCRIPT'
#!/bin/bash
echo "═══════════════════════════════════"
echo "    SchoolOS — حالة الخدمات"
echo "═══════════════════════════════════"
cd /opt/schoolos
docker compose -f docker-compose.prod.yml ps
echo ""
echo "━━━ استخدام الموارد ━━━"
docker stats --no-stream --format "table {{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" \
    $(docker compose -f docker-compose.prod.yml ps -q 2>/dev/null) 2>/dev/null || true
echo ""
echo "━━━ فحص الصحة ━━━"
curl -s http://localhost/health/ | python3 -m json.tool 2>/dev/null || echo "الخدمة غير متاحة"
STATUS_SCRIPT
chmod +x /usr/local/bin/schoolos-status

ok "=== إعداد السيرفر مكتمل ==="
echo ""
echo -e "${BOLD}الخطوات التالية:${NC}"
echo -e "  1. ${YELLOW}عدّل ملف .env:${NC} nano $DEPLOY_DIR/.env"
echo -e "  2. ${YELLOW}احصل على SSL من Let's Encrypt بعد ضبط DNS${NC}"
echo -e "  3. ${YELLOW}شغّل المنصة:${NC} cd $DEPLOY_DIR && docker compose -f docker-compose.prod.yml up -d"
echo -e "  4. ${YELLOW}تحقق من الحالة:${NC} schoolos-status"
echo ""
echo -e "${GREEN}${BOLD}السيرفر جاهز لمنصة SchoolOS!${NC}"
