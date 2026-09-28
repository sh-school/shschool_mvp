# CHANGES — drf-endpoint-scaffold

الأصل: `snapshot/.claude/skills/drf-endpoint-scaffold/` (SKILL 120، `references/layers.md` 152، سكربت 204). التحقّقُ على `origin/main@81bc4937` (2026-09-28)، وفي مختبرٍ معزول: نسخةٌ كاملةٌ من main (`git archive`) في صورة `shschool_mvp-web` مع PostgreSQL 18 مؤقّت، وُلّدت فيها نقطتان ووُزّعتا واختُبرتا بـpytest وإعدادات `testing`.

## سجلُّ الادّعاءات
| # | الادّعاء في الأصل | الحكم | الدليل |
|---|---|---|---|
| 1 | الطبقات: `<app>/selectors.py`، `<app>/services.py`، `api/serializers.py`، `api/views.py` | جزئيّ | الـselectors بأسماء المجالات (`reports/selectors.py`، `operations/schedule_selectors.py`…)، و`operations/services/` حزمة؛ و`api/views.py` لا يستعمل selectors |
| 2 | `api/permissions.py`: `IsTeacherOrAdmin`/`IsLeadership`/`IsSchoolAdmin` | صحيح | ومعها `IsStaffMember`، `IsParentOrAdmin`، `IsSameDepartment` |
| 3 | «النماذجُ ترث `SchoolScopedModel`» | خاطئ | أربعةُ نماذج فقط (`CapabilityGrant`، `ExportJob`، `LeaveBalance`، `StudentActivity`) |
| 4 | `permission_classes = [IsAuthenticated, <Role>]` | صحيحٌ زائد | الأصنافُ تفحص المصادقة بنفسها، وأسلوبُ `api/views.py` الدورُ وحده |
| 5 | `StandardPagination` في `api/pagination.py` | صحيح | 50 افتراضاً، `page_size` حتّى 200 |
| 6 | drf-spectacular مفعّل و`@extend_schema` | صحيح | 0.30.0؛ `tests/test_api_contract.py` |
| 7 | `_school(request)` في `api/views.py` | صحيح | `request.user.get_school()` |
| 8 | مثالُ `Subject(name_ar, code)` و`school.subjects` | صحيح | `operations/models/schedule.py` |
| 9 | `get_or_create(school, code)` يجعل الإنشاءَ idempotent | ناقص | لا `UniqueConstraint` على (school, code) و`code` فيه `blank=True` |
| 10 | اختبارٌ بـ`APIClient.force_authenticate` | خاطئ | الوسيطُ يردّ 401 قبل DRF — مُثبَت: 401 حيث توقّع 403 و200 و201 |
| 11 | fixtures `subject_a`، `many_subjects`، `obj_same_school`… | خاطئ | غيرُ موجودة؛ و`teacher_user`/`student_user` موجودتان في `tests/conftest.py` لا تُريان خارج `tests/` |
| 12 | factory-boy وFaker في `requirements-dev.txt` | صحيح | 3.3.3، 40.39.0 |
| 13 | الإعداد `shschool.settings.testing` | صحيح | `pyproject.toml` |
| 14 | `ruff check . && mypy api <app> && pytest …` | جزئيّ | ruff بإصدار CI 0.4.4؛ سقّاطةُ mypy تفحص `core`/`shschool`/`governance` فقط؛ pytest في الحاوية |
| 15 | «المسار الوحيد `D:\shschool_mvp`» | قديمٌ مخالف | `CLAUDE.md` القاعدة رقم 1 |
| 16 | «كلُّ عمليّة >300ms ← Celery» | صحيحٌ بمصدرٍ آخر | `~/.claude/CLAUDE.md`؛ والتصديرُ بـADR-0007 |
| 17 | السكربت يكتب الاختبارَ في `<app>/tests/` | عطل | «fixture 'teacher_user' not found» ×5 (مختبر) |
| 18 | السكربت: `order_by("-created_at")`، `fields="__all__"`، `assert … in (201, 400)`، `payload = {}` | عطل | `Subject`/`BusRoute` بلا `created_at`؛ `__all__` يقبل `school` من الحمولة؛ القيمةُ المؤقّتة تمرّ فارغة (ذاكرة `feedback_placeholders_must_fail.md`) |
| 19 | السكربت على ويندوز | عطل | يكتب الملفّين ثمّ يسقط بـ`UnicodeEncodeError` |

## التغييرات
| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| الوصف | عربيٌّ فقط | ثنائيٌّ pushy، وما ليس لها (HTML، N+1 لنقطةٍ قائمة، PII، الهجرة، الدفع) | الكرّاسة §2 | — |
| البنية | SKILL 120 + `layers.md` | SKILL 57 + `00-api-conventions` + `01-layers` (نُقلت إليه معرفةُ `layers.md` الصحيحة: الطبقات، الخدمة الذرّيّة، SOLID) + `02-testing` + `99-test-cases` | الكرّاسة §2 | — |
| الصلاحيّة | `IsAuthenticated` + دور | دورٌ من `api/permissions.py` وحارسُ `test_every_route_is_guarded` | يسقط CI بدونه | `tests/test_every_route_is_guarded.py` |
| الموضع | إلى `api/views.py` | وحدةٌ جديدة `api/views_<name>.py` | 915 من 1000 سطر | `tests/file_size_ratchet.py`، السابقة `api/views_erasure.py` |
| idempotency | `get_or_create` وحده | مشروطٌ بقيدٍ فريدٍ في القاعدة، وإنذارٌ إن غاب | سباقُ التزامن | وثائق Django |
| الاختبار | `APIClient`، أرقامٌ ثابتة، fixtures وهميّة | `tests/`، `force_login`، 401/403/عزل/ثبات/تكرار/حقنُ school، و`NotImplementedError` لما يُكتب | البنود 10–11، 17–18 | المختبر |
| السكربت | يولّد بلا تحقّق | يتحقّق من التطبيق والنموذج والصلاحيّة؛ `--fields` إلزاميّة بلا `__all__`؛ `--school-path`، `--order-by`، `--write-fields`، `--unique-key`، `--force`؛ ينذر بغياب القيد والترتيب وحقل `school` و`IsAuthenticated`؛ يطبع السطورَ مقابل السقف؛ UTF-8؛ لا يُنشئ `<app>/tests/` | البنود 17–19 | أدناه |

## اختبارُ السكربت
- المدخلاتُ الخاطئة (نموذجٌ مفقود، `__all__`، صلاحيّةٌ مجهولة، إنشاءٌ بلا مفتاح، ملفٌّ قائمٌ بلا `--force`) ← رسالةٌ عربيّةٌ ورمز 2.
- `bus-routes` (قراءة، `bus__school`، `--order-by area_name,id`، `IsStaffMember`) و`lab-subjects` (إنشاءٌ على `Subject` بمفتاح `code`، مع إنذار «لا قيدَ فريد»): وُزّعا في `api/views_*.py` و`api/urls.py` وكُتبت `make_row`/`payload` ⇒ **10 اختباراتٍ خضراء**، وحارسُ المسارات أخضر.
- قبل كتابة `make_row` في نقطةٍ ثالثة غيرِ مسجَّلة: `NotImplementedError` في العزل والثبات، و404 في اختبار 403 — يسقط كما يجب.
- الاختبارُ المولَّد بالسكربت القديم: 5 أخطاء fixtures في `operations/tests/`، ثمّ 401 في كلّ طلبٍ مصادَقٍ بعد نقله إلى `tests/`.
- حُذف كلُّ ما في المختبر؛ ولا `__pycache__` في التسليم.

## يحتاج قرارَ المالك أو تأكيدَه
1. **`Subject` بلا قيدٍ فريدٍ على (school, code) و`code` يقبل الفراغ.** إنشاءٌ idempotent عبر API يحتاج القيد (هجرة، وADD_UNIQUE تُسقطه البوّابة ⇒ قرارُ مراجعة) أو مفتاحاً آخر. المثالُ في المهارة يصرّح بذلك ولا يفترضه.
2. **مكانُ serializers النقاط الجديدة:** المهارةُ تضعها مع الـview في `api/views_<name>.py` (السابقة `views_erasure`)؛ إن فضّل المالك `api/serializers/` حزمةً فذاك قرارٌ معماريٌّ (ADR).
3. **JWT مطفأ** (`API_JWT_ENABLED=False`) والوصفُ في `SPECTACULAR_SETTINGS` يذكر «JWT Bearer Token (التطبيق المحمول)» — يُؤكَّد أيّهما المقصود قبل بناء نقاطٍ لتطبيقٍ محمول.
4. **سقّاطةُ mypy لا تشمل `api/`** — هل يُضاف إلى `TARGETS` في `tests/mypy_ratchet.py`؟
