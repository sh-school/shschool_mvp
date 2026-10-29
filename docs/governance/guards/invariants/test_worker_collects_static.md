# حارسُ الثوابت: العاملُ يجمع الثابتَ (N-042)

> صفٌّ من جدول «ج. حرّاسُ الثوابت» — مقطعٌ من `docs/governance/regression_guards.md` (الفهرس)؛ النصُّ منقولٌ حرفيّاً (W-20261020-018).

| المجال | الحرّاس | ما يفرضونه |
|---|---|---|
| **العاملُ يجمع الثابتَ (N-042)** | `test_worker_collects_static` | `scripts/railway-worker.sh` فيه `python manage.py collectstatic --noinput` **قبل** `exec celery` (بعده لا يجري أبداً) وبعد `verify_runtime_db_role` وتصدير إعدادات production، وبالصيغة نفسِها في `railway-release.sh` — فحاويةُ العامل قرصُها محلّيٌّ تبدأ بلا `staticfiles.json`، وأيُّ قالبٍ فيه `{% static %}` يُصيَّر فيها (تصديرُ الجدول PDF) يسقط بـ`Missing staticfiles manifest entry` |
