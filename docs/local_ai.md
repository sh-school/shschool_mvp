# الذكاءُ المحلّيّ (local_ai) — النموذجُ اللغويّ على جهاز المدرسة

> تطبيقُ Django يربط SchoolOS بخادم **LM Studio** المحلّيّ (`http://127.0.0.1:1234/v1`). لا يغادر بيانٌ الجهازَ، ولا مزوِّدَ خارجيّاً ولا مفتاحَ API — وهذا أساسُ موقفه من PDPPL.

## ما يقدّمه

| القدرة | أين | لمن |
|---|---|---|
| **مساعدُ المحادثة** يجيب من وثائق المدرسة بمراجع مرقّمة، ومعرفةً عامّةً مع التصريح بذلك | `/ai/` | كلُّ موظّف (`staff_required`) |
| **وثائقُ المعرفة (RAG)**: رفعُ تعميمٍ/سياسةٍ/خطّة → تقطيعٌ → تضمينٌ (bge-m3) → بحثٌ دلاليٌّ بالعربيّة | `/ai/documents/` | القيادة (`leadership_required`) |
| **استخراجٌ منظَّم** (JSON Schema): بطاقةُ وثيقة، تصنيف، حقولٌ مخصّصة | `local_ai.services.structured` | الشيفرة |
| **الأتمتة** (Celery): فهرسةٌ فور الرفع، بطاقةُ وثيقةٍ تلقائيّة، مسحٌ كلَّ ساعة لما بقي، إعادةُ محاولة ليليّة | `local_ai.tasks` | Beat |
| **API للمطوّرين**: `LMStudioClient.chat / chat_stream / embed / chat_json` | `local_ai.client` | الشيفرة |

## الخصوصيّة بالبنية

- المساعدُ **لا يملك أدواتٍ تقرأ سجلّات الطلبة**؛ سياقُه الوحيد مقاطعُ وثائق المعرفة التي رفعتها القيادة. سؤالٌ عن طالبٍ بعينه يُحال إلى صفحته في المنصّة.
- المحادثةُ في **جلسة المستخدم** (آخر 10 أدوار) لا في قاعدة البيانات.
- الجدولان (`local_ai_knowledgedocument`، `local_ai_documentchunk`) يحملان `school_id` وعليهما سياسةُ `school_isolation` (الهجرة 0002) كبقيّة الجداول.
- صفحةُ الرفع تحذّر صراحةً: وثائقُ عامّةٌ فقط، لا كشوفَ طلبة.

## التثبيت (مرّةً واحدة)

```powershell
# 1) الملفّات: انسخ مجلّدَي local_ai/ و tests/local_ai/ وهذا الملفّ إلى جذر المشروع، ثمّ:
.\.venv\Scripts\python.exe scripts\apply_local_ai_patches.py   # INSTALLED_APPS + urls + celery + .env.example

# 2) في .env على جهاز المدرسة (حيث يعمل LM Studio):
#    LOCAL_AI_ENABLED=true

# 3) الهجرات ثمّ الفحص
.\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run   # يجب: No changes detected
.\.venv\Scripts\python.exe manage.py migrate local_ai
.\.venv\Scripts\python.exe manage.py local_ai_ping --full              # الخادم + التضمين + المحادثة

# 4) الاختبارات (كما في CI)
make test-docker  # أو: DJANGO_SETTINGS_MODULE=shschool.settings.testing ... -m pytest tests/local_ai -q
```

## المتطلّبات على جهاز المدرسة

- LM Studio 0.4.28+ مع تبويب **Server** شغّالاً على 1234، وفيه: `qwen/qwen3-8b` (المحادثة) و`text-embedding-bge-m3` (التضمين). يحمّل LM Studio النموذجَ عند أوّل طلبٍ (JIT).
- الذاكرة: Qwen3-8B بسياق 14K ≈ 5.4 GB VRAM؛ لا تحمّل نموذجاً بصريّاً كبيراً معه على كرت 8 GB.
- لا حزمَ بايثون جديدة: `requests` و`numpy` و`pdfplumber` و`python-docx` كلُّها في المتطلّبات.

## الاستعمال من الشيفرة

```python
from local_ai.client import get_client
from local_ai.services import rag, structured

client = get_client()
client.chat([{"role": "user", "content": "لخّص سياسة الحضور في جملتين."}]).content
rag.answer(school, "متى تسليم الخطط الفصلية؟").text          # إجابةٌ مسنَدةٌ بمراجع
structured.classify("لم يصل الباص اليوم", ["شكوى", "استفسار", "شكر"])
structured.extract(text, schema={...}, instructions="استخرج …")  # أيُّ مخطّطٍ تريده
```

## الأتمتة (Celery Beat)

| المهمّة | متى | ماذا |
|---|---|---|
| `local_ai.index_document` | فور الرفع أو إعادة الفهرسة | تقطيعٌ + تضمينٌ + حالةُ الوثيقة، ثمّ تطلق الإثراء |
| `local_ai.enrich_document` | بعد الفهرسة | بطاقةُ الوثيقة (ملخّصٌ، جهةٌ، مواعيدُ، إجراءات) في `summary`/`metadata` |
| `local_ai.index_pending_documents` | كلَّ ساعة (:20) | ما رُفع والخادمُ مطفأ |
| `local_ai.index_pending_documents(include_failed=True)` | 02:40 ليلاً | إعادةُ محاولة ما فشل خارج الدوام |

كلُّ مهمّةٍ تعود بهدوء حين `LOCAL_AI_ENABLED=false`، ولا تُسقط مدرسةٌ معطوبةٌ غيرَها.

## التوسّع لاحقاً

- **pgvector** حين تتجاوز المقاطعُ عشراتِ الآلاف: `services.rag.search` هي الواجهةُ الوحيدة التي تتغيّر.
- **البثّ** في الواجهة: `client.chat_stream` جاهزٌ؛ يحتاج `StreamingHttpResponse` وقالبَ HTMX `hx-ext="sse"`.
- **أدواتٌ للمساعد** (قراءةُ الجدول الأسبوعيّ، البحثُ في الوثائق كأداة): `client.chat(tools=[…])` يدعم استدعاءَ الأدوات، وتُضاف أداةٌ بأداةٍ مع مراجعة الخصوصيّة لكلّ واحدة.
