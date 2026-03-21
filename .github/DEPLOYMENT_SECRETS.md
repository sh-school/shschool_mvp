# GitHub Actions — Secrets المطلوبة

أضف هذه الـ Secrets في:
**GitHub → Repository → Settings → Secrets and variables → Actions**

## Secrets مطلوبة للنشر (deploy.yml)

| الـ Secret | الوصف | مثال |
|-----------|-------|------|
| `SERVER_HOST` | IP أو hostname الخادم | `178.128.x.x` |
| `SERVER_USER` | اسم المستخدم على الخادم | `ubuntu` أو `root` |
| `SERVER_SSH_KEY` | المفتاح الخاص SSH (كامل) | محتوى ملف `~/.ssh/id_rsa` |
| `SERVER_PORT` | منفذ SSH (اختياري — افتراضي 22) | `22` |

## كيف تُنشئ SSH Key للـ CI/CD

```bash
# على جهازك المحلي
ssh-keygen -t ed25519 -C "github-actions-deploy" -f ~/.ssh/schoolos_deploy

# انسخ المفتاح العام للخادم
ssh-copy-id -i ~/.ssh/schoolos_deploy.pub user@your-server

# انسخ المفتاح الخاص إلى GitHub Secrets
cat ~/.ssh/schoolos_deploy  # هذا ما تضعه في SERVER_SSH_KEY
```

## بنية المجلد على الخادم

```
/opt/schoolos/          ← مجلد المشروع
├── docker-compose.prod.yml
├── .env                ← ملف البيئة (لا يُرفع لـ Git)
├── nginx/
├── media/
├── staticfiles/
├── logs/
└── backups/
```

## أول نشر يدوي (مرة واحدة فقط)

```bash
# على الخادم
git clone https://github.com/sh-school/shschool_mvp.git /opt/schoolos
cd /opt/schoolos
cp .env.example .env   # عدّل القيم
docker compose -f docker-compose.prod.yml up -d
```

بعدها كل push لـ main يُنشر تلقائياً.
