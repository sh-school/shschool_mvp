# developer_feedback — أرسل إلى المطوّر

**الإصدار:** v1.0 (Production Ready — pending staging deployment)
**المرجع:** `PRD-SOS-DEV-FEEDBACK-v1.0` + `MTG-2026-014` + `MTG-2026-015`
**Sprint:** `SPRINT-DF-001`

## الهدف
قناة مباشرة يُرسل بها المستخدمون (غير الطلاب) رسائلهم ومقترحاتهم وشكاواهم إلى المطوّر، مع سجل تدقيق كامل وحماية قانونية وخصوصية.

## القرارات المعتمدة من المؤسس (E1)
- **المرفقات ملغاة كلياً في MVP** — نص فقط (subject 5-200، body 10-4000)
- **Onboarding قانوني إلزامي:** شاشة + اختبار (3/3) + تفويض إداري كتابي
- **SMTP:** TLS 1.3 + hash للـ user_id + محتوى مُقيّد (PDPPL)
- **النطاق:** كل الأدوار باستثناء `role=Student` (PDPPL مادة 16)
- **بريد المطوّر:** `s.mesyef0904@education.qa`
- **DPO:** أذكياء للبرمجيات
- **Retention:** 90 يوم للنصوص (cleanup تلقائي عبر management command)

## حالة الجولات (5 Rounds)
| # | الجولة | المحتوى | الحالة |
|---|---|---|---|
| 1 | Models + Admin + Migration | 5 نماذج + Choices + Admin + migration أولي | ✅ مكتملة |
| 2 | Forms + Services + Permissions | 3 forms + hashing + ticketing + notifications + 3 mixins | ✅ مكتملة |
| 3 | Views + URLs + Audit | 6 views + urls.py + audit service + notifications | ✅ مكتملة |
| 4 | Templates + CSS + JS + Navbar | 7 templates + feedback.css + feedback.js + navbar link | ✅ مكتملة |
| 5 | Tests + i18n + Cleanup + Cosmetic fixes | Unit/security tests + locale files + management command | ✅ مكتملة |

## Models (5)
| Model | الغرض |
|---|---|
| `DeveloperMessage` | الرسالة نفسها + ticket_number + context_json + جدولة الحذف التلقائي |
| `MessageStatusLog` | سجل تغيّر الحالات (who/when/why) |
| `DeveloperMessageNotification` | إشعارات SMTP / InApp + retry |
| `LegalOnboardingConsent` | موافقة قانونية إلزامية + درجة الاختبار + مرجع التفويض |
| `AuditLog` | سجل وصول للـ Inbox (view/update/delete) |

جميع verbose_names تستخدم `gettext_lazy` للترجمة عبر Django i18n.

## Forms (3)
- `DeveloperMessageForm` — إرسال رسالة + whitelist/scrub لـ context_json
- `OnboardingConsentForm` — 4 حقول موافقة قانونية
- `OnboardingQuizForm` — 3 أسئلة (3/3 إلزامي)

## Services (4)
- `services/hashing.py` — `hash_user_id` (SHA-256 + SECRET_KEY salt)
- `services/ticketing.py` — `generate_unique_ticket_number` بصيغة `SOS-YYYYMMDD-XXXX`
- `services/notifications.py` — `send_developer_notification` (SMTP + 3 retries + TLS)
- `services/audit.py` — `log_inbox_view` / `log_message_view` / `log_status_update`

## Permissions (3)
- `NotStudentMixin` — يحجب `role=Student` كلياً
- `OnboardingRequiredMixin` — يشترط إكمال Onboarding القانوني
- `DeveloperOnlyMixin` — superuser أو `developers` group فقط

## Views (6)
1. `OnboardingView` — شاشة الإعداد القانوني
2. `DeveloperMessageCreateView` — نموذج الإرسال
3. `MessageSuccessView` — صفحة النجاح + رقم التذكرة
4. `UserMessageHistoryView` — رسائلي
5. `DeveloperInboxListView` — صندوق المطوّر
6. `DeveloperInboxDetailView` — تفاصيل + تحديث حالة

## Templates (7)
- `onboarding.html`, `message_create.html`, `message_success.html`
- `my_messages.html`, `inbox_list.html`, `inbox_detail.html`
- `_status_badge.html` (partial)

## i18n — ملفات الترجمة
- `locale/ar/LC_MESSAGES/django.po` — الترجمات العربية (identity mapping — المصدر عربي)
- `locale/en/LC_MESSAGES/django.po` — الترجمات الإنجليزية (13+ مفتاح)

لتوليد/تحديث الترجمات:
```bash
python manage.py makemessages -l ar
python manage.py makemessages -l en
python manage.py compilemessages
```

## Management Command — cleanup_old_messages
يحذف الرسائل التي تجاوزت retention period (افتراضياً 90 يوم).

```bash
# Dry-run (يعرض العدد فقط، لا يحذف)
python manage.py cleanup_old_messages

# حذف فعلي
python manage.py cleanup_old_messages --apply

# تخصيص عدد الأيام
python manage.py cleanup_old_messages --days 60 --apply
```

للتشغيل الدوري: أضفه إلى cron/Task Scheduler (مثلاً يومياً الساعة 3 صباحاً).

## Tests
الاختبارات موجودة في `developer_feedback/tests/`:
- `test_services.py` — 8 اختبارات (hashing + ticketing)
- `test_forms.py` — 13 اختبار (3 forms)
- `test_models.py` — 5 اختبارات (DeveloperMessage + AuditLog)
- `test_security.py` — 8 اختبارات أمنية (XSS / IDOR / CSRF / PII / Role-based)

لتشغيل الاختبارات:
```bash
python manage.py test developer_feedback
```

## الحالة
**Production ready — pending staging deployment.**

جميع Tickets DF-01 إلى DF-30 مكتملة. لا توجد مراجعات معلّقة على الكود.
الخطوة التالية: النشر على بيئة staging للاختبار النهائي قبل GA.
