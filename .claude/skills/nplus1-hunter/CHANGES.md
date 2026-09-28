# CHANGES — nplus1-hunter

الأصل: `snapshot/.claude/skills/nplus1-hunter/` (SKILL 134 سطراً بلا مراجع، سكربت 151). التحقّقُ على `origin/main@81bc4937` (2026-09-28)، وتشغيلُ الفاحصَين القديم والجديد على نسخةٍ من ملفّات main (`git archive`: 1494 ملفَّ بايثون و340 قالباً) وعلى حالاتٍ اصطناعيّةٍ تحت مسارٍ فيه `.claude/worktrees/`.

## سجلُّ الادّعاءات
| # | الادّعاء في الأصل | الحكم | الدليل |
|---|---|---|---|
| 1 | Django 5.2 + PostgreSQL | صحيح | `requirements.txt` |
| 2 | «1300+ قالب» | خاطئ | 340 ملفَّ HTML على main (`git ls-tree`) |
| 3 | «المسار الوحيد `D:\shschool_mvp`» | قديمٌ مخالف | `CLAUDE.md` القاعدة رقم 1 |
| 4 | «المعيار: كلُّ عمليّة >300ms تُعالَج» | صحيحٌ بمصدرٍ آخر | `~/.claude/CLAUDE.md` لا المستودع |
| 5 | `api/views.py` فيه `.select_related("student", "class_group")` | صحيح | `StudentListView.get_queryset` |
| 6 | `api/views.py` فيه `.prefetch_related("enrollments")` | خاطئ | لا `prefetch_related` في الملفّ |
| 7 | `.select_related("setup__subject")  # تجنب N+1…` | صحيح | `api/views.py` (سطران) |
| 8 | المثال `StudentEnrollment.objects.filter(school=school)` و`e.class_group.name` | خاطئ | لا حقلَ `school` على التسجيل ولا `name` على الشعبة (`core/models/academic.py`) |
| 9 | `ClassGroup…c.enrollments.count()` و`annotate(Count("enrollments"))` | صحيح | `related_name="enrollments"` |
| 10 | اختبارُ «النمط المعتمد»: `client.force_authenticate` مع `django_assert_num_queries(4)` | خاطئ | fixture `client` في pytest-django لا يملك `force_authenticate`؛ والوسيطُ يردّ `/api/` بـ401 بلا جلسة (مُثبَت في مختبر drf-endpoint-scaffold)؛ والنمطُ المعتمد فعلاً مقارنةُ صفٍّ بثلاثة (`tests/test_n_plus_one_queries.py::assert_flat`) |
| 11 | `CaptureQueriesContext` للقياس اليدويّ | صحيح | 11 ملفَّ اختبارٍ تستعمله |
| 12 | «`debug_toolbar` مفعّلٌ في `settings/development.py`» | قديمٌ عمليّاً | الإعدادُ مشروطٌ باستيراده، والحزمةُ ليست في `requirements*.txt` ولا في الصورة (`find_spec` = False) |
| 13 | مثالُ serializer `obj.session.teacher.full_name` | صحيح | `Session` له `teacher` (`api/views.py::SessionListView`) |
| 14 | مزالقُ الإفراط والعمق و`Prefetch` و`only/defer` و`values` | صحيح (معرفةُ Django) | أُبقيت ووُسّعت |
| 15 | «لا تُصلح القالب في القالب» | صحيح | أُبقيت قاعدةً مع سببها |
| 16 | الفاحص يعمل «من المشروع» | **خاطئ في كلّ شجرة عمل** | يستثني `.claude` و`worktrees` في المسار المطلق: 0·0 داخل `D:/shschool_mvp/.claude/worktrees/…` مقابل 135·567 على الشيفرة نفسِها خارجها |

## التغييرات
| البند | القديم | الجديد | السبب | الدليل |
|---|---|---|---|---|
| الوصف | عربيٌّ فقط، بلا «ليست لـ» | ثنائيٌّ pushy يذكر `get_role`/`school` والقوالب والتصدير، وما ليس لها | الكرّاسة §2 | — |
| البنية | SKILL 134 بلا مراجع | SKILL 50 + ثلاثةُ مراجع + `99-test-cases.md` | الكرّاسة §2 | — |
| نمطُ الاختبار | رقمٌ مطلق و`force_authenticate` | صفٌّ مقابل ثلاثة بعد إحماء، `force_login`، في `tests/` | نمطُ المشروع ولا يتقادم | `tests/test_n_plus_one_queries.py`، `tests/test_admin_changelist_queries.py` |
| الاستعلاماتُ الخفيّة | غائبة | `user.get_role/role/school/has_role`، `__str__` يقرأ علاقة، `.live()` | تفلت من الفاحص ومن العين | `core/models/user.py`، `transport/models.py` |
| الأمثلة | حقولٌ غيرُ موجودة | حقولٌ حقيقيّة (`class_group__school`، `short_label`) وسوابقُ main | مثالٌ خاطئٌ يُنسخ | `core/models/academic.py` |
| مزالقُ جديدة | — | فلترٌ بعد prefetch، `len` مقابل `count`، `iterator()` مع prefetch في Django 5، `annotate` بعدّين | أسبابٌ شائعةٌ لإصلاحٍ لا يعمل | وثائق Django |
| الفاحص | استثناءٌ بالمسار المطلق؛ متغيّرٌ مجهَّز = إنذار؛ `enumerate` مُهمَل؛ تكرار؛ ترميز | استثناءٌ نسبيٌّ للجذر؛ يتتبّع الإسنادَ في الدالّة؛ يفكّ `enumerate` و`for k, v`؛ بلا تكرار؛ `--path` و`--max`؛ خروجٌ 2 لمسارٍ مفقود؛ UTF-8 | البند 16 وضجيجُ المخرج | أدناه |

## اختبارُ السكربت
- حالاتٌ اصطناعيّة تحت `…/.claude/worktrees/demo/`: القديم 0 بايثون و0 قوالب؛ الجديد 3 و2 كما هو متوقَّع (المتغيّرُ المجهَّز لا يُعلَّم، `enumerate` يُعلَّم، `count()` مرّةً واحدة).
- على main كاملاً: بايثون 135 ← 60 (116 سطراً فريداً ← 58: أُسقط 71 أغلبُها حلقاتٌ على متغيّرٍ مجهَّزٍ بـ`select_related` — فُحصت عيّنة، مثلاً `academic_management/assignment_selectors.py:313`؛ وأُضيف 13 من حلقات `enumerate` مثل `student_affairs/views.py:519`). القوالب 567 ← 575.
- `--app nosuch` ← رسالةٌ ورمز 2. على طرفيّة ويندوز بلا `PYTHONIOENCODING` صار المخرجُ مقروءاً.
- لا `__pycache__` ولا ملفّاتٍ مؤقّتة في التسليم.

## يحتاج قرارَ المالك أو تأكيدَه
1. **`debug_toolbar`:** إعدادُه في `development.py` ميّتٌ عمليّاً (الحزمةُ غير مثبّتة). يُضاف إلى `requirements-dev.txt` والصورة، أم يُحذف الإعداد؟ المهارةُ الآن لا تعتمد عليه.
2. **`CustomUser.active_memberships` في القوائم:** استعلامٌ لكلّ مستخدم، ولا يُنقذه `prefetch_related` لأنّها تستدعي `filter()`. هل يُقبل تعديلُها لتقرأ من ذاكرة prefetch إن وُجدت (تغييرُ شيفرةٍ خارجَ المهارة، لمسار الخلفيّة)؟
3. **مرشّحاتُ القوالب (575)** لا يُحسم أغلبُها إلّا بقراءة الـview؛ هل يُرغب في حارسٍ يعدّ استعلاماتِ صفحاتٍ مختارة بدل توسيع الفاحص؟ (قرارٌ لمالك مسار الجودة.)
