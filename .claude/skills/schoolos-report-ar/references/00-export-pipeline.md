# مسارُ التصدير المركزيّ — من الزرّ إلى الملفّ

متى تقرأ هذا الملف: قبل أن تكتب أيَّ تصديرٍ جديد (PDF أو Excel)، أو حين تحوّل تصديراً متزامناً إلى خلفيّ، أو حين يسقط `tests/test_export_guards.py`.

المصادر: `docs/adr/0007-central-export-mechanism.md`، `core/exports/`، `core/pdf_utils.py`، `core/audit_export.py`، `tests/test_export_guards.py`، ذاكرة `project_export_core_vi30b_2026_09_26.md`.

## الأجزاء
| الجزء | الموضع | دورُه |
|---|---|---|
| السجلّ | `core/exports/registry.py` | `register(kind, *, build, capability, max_bytes=25MB, mode="job", p95_ms=None, measured_on="")` |
| البنّاء | `<app>/export_builders.py` (مثالا `reports/` و`student_affairs/`) | `build(school, user, params) -> ExportResult` — **بلا request** |
| النتيجة | `ExportResult(content, content_type, filename, rows=None, full_national_id=False, object_id="")` | `rows` و`full_national_id` يكتب بهما العاملُ سطرَ التدقيق `<kind>:built` |
| المدخل | `core/exports/services.py::respond_export(request, kind, params=None)` | قدرةٌ ← منعُ التكرار 60ث ← سقفُ 3 مهامّ نشطة ← صفٌّ ← مهمّة |
| العامل | مهمّةُ `core.export.run_job` (`core/exports/runner.py`) | soft 150ث / hard 170ث، رموزُ خطأٍ ثابتة (`timeout|too_large|failed|forbidden`) بلا نصّ استثناء |
| الواجهة | `static/js/export-center.js` وسمةُ `data-app-file` | «جارٍ التحضير» ثمّ التنزيل؛ 429/403/413 رسائلُ عربيّةٌ ثابتة (`core/exports/messages.py`) |
| الاحتفاظ | مهمّةٌ كلَّ ساعة | صفُّ `ExportJob` يُحذف بعد 24 ساعةً من إنشائه في كلّ حالاته |

## الخطوات لنوعٍ جديد
1. **البنّاء** في `<app>/export_builders.py`:
```python
def build_club_members_pdf(school, user, params) -> ExportResult:     # مثالٌ مختلَق
    from core.pdf_utils import render_pdf_bytes
    if not user.is_admin():            # الإذنُ هنا أيضاً: العاملُ يعيد فحصَ القدرة وحدَها
        raise PermissionDenied
    ctx = club_members_context(school, params)          # من selectors، لا من الـview
    html = render_to_string("clubs/pdf/members.html", {**ctx, "for_pdf": True})
    return ExportResult(render_pdf_bytes(html, paper_size="A4"), "application/pdf",
                        f"أعضاء_النادي_{ctx['year']}.pdf", rows=len(ctx["rows"]), full_national_id=False)
```
2. **التسجيل** في `ClubsConfig.ready()`: `export_registry.register("clubs.members_pdf", build=builders.build_club_members_pdf, capability="clubs.manage")` — مفتاحُ القدرة من `core/capabilities.py`.
3. **الـview**: `return respond_export(request, "clubs.members_pdf", params=params)`؛ ومعاملاتُ المسار (`class_id`…) تُضاف إلى نسخةٍ من `request.GET` كما في `reports/views.py::class_certificates_pdf`.
4. **الرابط**: `data-app-file` ليمرّ من مركز التصدير (`tests/test_app_mode_no_dead_ends.py`).
5. **الحرّاس**: شغّل `tests/test_export_guards.py` و`tests/test_export_core.py`. وإن حوّلتَ نوعاً قديماً فاحذف بندَه من `SYNC_ONLY_KINDS` و`HEAVY_IN_VIEWS` **في الطلب نفسِه** (السقّاطةُ تسقط على البند الذي لم يعد له أصل).

## العتبات (قرارُ المالك 2026-09-26)
- ≥ ~1000ms (p95) خلفيٌّ إلزاميّ؛ 300–1000 متزامنٌ بإشعارٍ بعد 600ms بشروط (p95 دافئ ≥ 20 نداءً، سقفٌ لكلّ مستخدم) — ولا نوعَ `direct` مسجَّلٌ بعد (ADR-0007 §3).
- أيُّ نوعٍ جديدٍ أو غيرِ مقيسٍ خلفيّ. والمتزامنُ القديم يُحوَّل «الأبطأ فالأبطأ» (قائمةٌ في `SYNC_ONLY_KINDS`).

## `core/pdf_utils.py` باختصار
- `render_pdf(html, filename, paper_size="A4", *, as_attachment=False) -> HttpResponse` — للـview (المعاينةُ والإطارُ المضمَّن تبقى متزامنةً بقرار المالك)؛ عند الفشل النهائيّ 503 نصّيّ لا 500.
- `render_pdf_bytes(html, paper_size="A4") -> bytes` — للبنّاء والعامل.
- المحرّكات بالترتيب: WeasyPrint ← Playwright ← xhtml2pdf، ويُتذكَّر الناجح. الإطارُ المركزيّ والعناصرُ الجارية لا تعمل إلّا في WeasyPrint.
- `paper_size` لا يؤثّر في قالبٍ يعلن `data-pdf-own-page` — المقاسُ حينها من `{% print_frame_css paper orient %}`.
- `_content_disposition` يكتب `filename` لاتينيّاً و`filename*` بـUTF-8 — الاسمُ العربيّ يصل صحيحاً؛ لا تكتب الترويسةَ يدويّاً.

## في العامل
- لا `request` ولا manifest للملفّات الثابتة: القالبُ بـ`for_pdf=True` بلا `{% static %}` (حادثةُ Sentry في `reports/export_builders.py`).
- لا تُرقِّع `render_pdf` في الاختبار (تستورده الوحدةُ بالاسم)؛ رقِّع `_generate_pdf_bytes` (ذاكرة VI-30ب).
- العاملُ لا يُعيد تحميلَ الشيفرة: بعد تعديل بنّاءٍ أعِد تشغيله (`restart worker`، `CLAUDE.md`).
- لا `apply_async(queue="<حرفيّ>")`: الطابورُ من الإعداد (`EXPORT_JOB_QUEUE`) وإلّا ضاعت المهمّةُ في شجرة العمل.

## أنماطٌ مضادّة
- `render_pdf` أو `openpyxl.Workbook()` داخل دالّة عرضٍ جديدة، أو داخل دالّةٍ مساعدةٍ لتفادي الحارس (السقّاطةُ لا تلتقطها، والمراجعةُ تلتقطها).
- `mode="direct"` بتقديرٍ لا بقياسٍ مؤرَّخ.
- `str(exc)` في رسالة المستخدم أو في `error_message`.
- بنّاءٌ يقرأ `request.user.get_school()` — المدرسةُ وسيطٌ صريح.
- زيادةُ بندٍ في `SYNC_ONLY_KINDS` لنوعٍ جديد.
