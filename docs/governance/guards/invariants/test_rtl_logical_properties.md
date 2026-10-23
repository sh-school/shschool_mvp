# حارسُ الثوابت: الاتّجاه والتخطيط

> صفٌّ من جدول «ج. حرّاسُ الثوابت» — مقطعٌ من `docs/governance/regression_guards.md` (الفهرس)؛ النصُّ منقولٌ حرفيّاً (W-20261020-018).

| المجال | الحرّاس | ما يفرضونه |
|---|---|---|
| **الاتّجاه والتخطيط** | `test_rtl_logical_properties`، `test_reflow`، `test_z_scale` (ومعه K18 = 0 وشريطُ التثبيت `--z-banner` (300) تحت ما يفتحه المستخدم)، `test_safe_area_tokens`، `test_pwa_banner_position`، `test_mobile_layout`، `test_mobile_nav_menu`، `test_action_cards_fit_narrow_screens`، `test_inset_shorthand`، `test_exec_dash_column` | لا `left/right` مطلقاً؛ لا عرضَ ثابتاً > 320px (WCAG 1.4.10)؛ سلّمُ z-index؛ قواعدُ الجوال؛ نصُّ بطاقة الإجراء لا يفيض عند 375/360/320؛ **لا اختصارَ `inset-inline`/`inset-block` بقيمةٍ واحدةٍ `auto`** (يمحو الطرفين معاً)؛ **غلافُ `.exec-dash` بعمودٍ صريحٍ `minmax(0, 1fr)`** لا `auto` الضمنيّ؛ **صفُّ التصدير في رأس كشف الشعبة `.per-exports` يلتفّ** (510px بلا التفاف عند 375) |
