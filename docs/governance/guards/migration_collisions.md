# حارسُ تصادم أرقام الهجرات

> قسمٌ فرعيٌّ من «3. ما يحجب الدمج فعلاً» — مقطعٌ من `docs/governance/regression_guards.md` (الفهرس)؛ النصُّ منقولٌ حرفيّاً (W-20261020-018).

### حارسُ تصادم أرقام الهجرات (W-20261019-002)

`scripts/check_migration_collisions.py` يقارن هجراتِ الفرع المضافة (عن merge-base) بهجرات الطلبات المفتوحة وبما دخل main بعد الأساس، ويفشل (1) عند تكرار الرقم في التطبيق نفسه ويسمّي الطلبَ المصادم؛ وغيابُ `gh` أو الشبكة «غير مقيس» (3) لا نجاحٌ صامت. يعمل في `make prepush` وفي `.github/workflows/migration-collisions.yml` (وظيفةٌ مستقلّةٌ لا تعدّل `quality-gate.yml`)؛ وجعلُها شرطاً في `needs:` قرارُ 0101/المالك. الاختبار: `tests/test_migration_collisions.py`.
