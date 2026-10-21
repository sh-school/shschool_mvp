# حارسُ الثوابت: إصداراتُ فاحص الأنواع مصدرٌ واحد (OWN-30)

> صفٌّ من جدول «ج. حرّاسُ الثوابت» — مقطعٌ من `docs/governance/regression_guards.md` (الفهرس)؛ النصُّ منقولٌ حرفيّاً (W-20261020-018).

| المجال | الحرّاس | ما يفرضونه |
|---|---|---|
| **إصداراتُ فاحص الأنواع مصدرٌ واحد (OWN-30)** | `test_mypy_pins_are_one_source`، `test_mypy_ratchet` | mypy وdjango-stubs وdjangorestframework-stubs مثبَّتةٌ في `requirements-mypy.txt` وحدَه؛ `requirements-dev.txt` يستدعيه بـ`-r` ووظيفةُ mypy في `quality-gate.yml` تثبّت منه، ولا إصدارَ حرفيّاً في أيّ سير عمل؛ وdependabot لا يقترح ترقيتَها (استثناءٌ كامل)؛ و`python -m tests.mypy_ratchet --update` يرفض التسجيلَ (رمز 2) إن خالف المثبَّتُ في البيئة الثابتَ. الترقيةُ قرارٌ ثلاثيّ: الملفّ + إعادةُ التسجيل بالإصدار الجديد + مراجعةُ فرق السجلّ |
